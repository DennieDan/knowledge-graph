"""Tests for generic claim validation and current_claims (#97 Steps 2–3)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
import unittest

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Claim, Organization, Record
from app.typed_values import (
    MAX_SEARCHABLE_PROMOTED,
    PROMOTED_SEARCHABLE_KEYS,
    searchable_keys_to_promote,
)
from app.validate import FindingSpec, castable, claim_value, current_claims, validate


@dataclass
class FakeField:
    key: str
    value_type: str
    required: bool = False
    searchable: bool = False


@dataclass
class FakeClaim:
    value_type: str
    value_text: str | None = None
    value_numeric: Decimal | None = None
    value_date: date | None = None
    value_bool: bool | None = None


class ValidateUnitTests(unittest.TestCase):
    def test_required_missing_when_claim_is_none(self):
        finding = validate(None, FakeField("order_number", "text", required=True))
        self.assertIsInstance(finding, FindingSpec)
        self.assertEqual("required_value_missing", finding.check_key)
        self.assertEqual("order_number", finding.field_key)

    def test_optional_missing_is_ok(self):
        self.assertIsNone(validate(None, FakeField("revision", "text", required=False)))

    def test_required_missing_when_typed_column_empty(self):
        claim = FakeClaim(value_type="text", value_text=None)
        finding = validate(claim, FakeField("order_number", "text", required=True))
        self.assertEqual("required_value_missing", finding.check_key)

    def test_type_mismatch(self):
        claim = FakeClaim(value_type="text", value_text="40")
        finding = validate(claim, FakeField("quantity", "numeric", required=True))
        self.assertIsNotNone(finding)
        self.assertEqual("not_a_numeric", finding.check_key)
        self.assertEqual("text", finding.observed_value)

    def test_matching_typed_value_passes(self):
        claim = FakeClaim(value_type="numeric", value_numeric=Decimal("40"))
        self.assertIsNone(validate(claim, FakeField("quantity", "numeric", required=True)))
        self.assertEqual(Decimal("40"), claim_value(claim))
        self.assertTrue(castable(claim, "numeric"))

    def test_bool_and_date_values(self):
        self.assertEqual(
            True,
            claim_value(FakeClaim(value_type="bool", value_bool=True)),
        )
        self.assertEqual(
            date(2026, 9, 24),
            claim_value(FakeClaim(value_type="date", value_date=date(2026, 9, 24))),
        )

    def test_searchable_promote_respects_cap_and_allowlist(self):
        fields = [
            FakeField("order_number", "text", searchable=True),
            FakeField("company_name", "text", searchable=True),
            FakeField("sku", "text", searchable=True),
            FakeField("invoice_number", "text", searchable=True),
            FakeField("po_number", "text", searchable=True),
            FakeField("job_number", "text", searchable=True),
            FakeField("drawing_number", "text", searchable=True),
            FakeField("file_name", "text", searchable=True),
            FakeField("extra_search", "text", searchable=True),
            FakeField("not_searchable", "text", searchable=False),
        ]
        keys = searchable_keys_to_promote(fields)
        self.assertEqual(MAX_SEARCHABLE_PROMOTED, len(keys))
        self.assertEqual(list(PROMOTED_SEARCHABLE_KEYS), keys)
        self.assertNotIn("extra_search", keys)
        self.assertNotIn("not_searchable", keys)


class CurrentClaimsTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name="Validate corp")
        self.session.add(self.org)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _record(self) -> Record:
        record = Record(
            organization_id=self.org.id,
            stack_key="sales-orders",
            match_key="PO-4411",
            attributes={"order_number": "PO-4411"},
        )
        self.session.add(record)
        self.session.flush()
        return record

    def test_current_claims_distinct_on_latest_non_retracted(self):
        record = self._record()
        older = datetime.now(timezone.utc) - timedelta(hours=2)
        newer = datetime.now(timezone.utc) - timedelta(hours=1)
        self.session.add_all(
            [
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="quantity",
                    value_type="numeric",
                    value_numeric=Decimal("10"),
                    origin="extraction",
                    status="superseded",
                    asserted_at=older,
                ),
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="quantity",
                    value_type="numeric",
                    value_numeric=Decimal("40"),
                    origin="extraction",
                    status="confirmed",
                    asserted_at=newer,
                ),
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="order_number",
                    value_type="text",
                    value_text="PO-4411",
                    origin="extraction",
                    status="confirmed",
                    asserted_at=newer,
                ),
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="revision",
                    value_type="text",
                    value_text="A",
                    origin="extraction",
                    status="retracted",
                    asserted_at=newer,
                    retracted_at=newer,
                ),
            ]
        )
        self.session.flush()

        current = current_claims(self.session, record.id)
        by_key = {c.field_key: c for c in current}
        self.assertEqual({"quantity", "order_number"}, set(by_key))
        self.assertEqual(Decimal("40"), by_key["quantity"].value_numeric)
        self.assertNotIn("revision", by_key)

    def test_current_values_distinct_on_sql(self):
        """Same DISTINCT ON shape as migration 0018's current_values view."""
        record = self._record()
        older = datetime.now(timezone.utc) - timedelta(hours=2)
        newer = datetime.now(timezone.utc)
        self.session.add_all(
            [
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="order_number",
                    value_type="text",
                    value_text="OLD",
                    origin="extraction",
                    status="superseded",
                    asserted_at=older,
                ),
                Claim(
                    organization_id=self.org.id,
                    record_id=record.id,
                    field_key="order_number",
                    value_type="text",
                    value_text="PO-4411",
                    origin="extraction",
                    status="confirmed",
                    asserted_at=newer,
                ),
            ]
        )
        self.session.flush()
        rows = self.session.execute(
            text(
                """
                SELECT DISTINCT ON (record_id, field_key) field_key, value_text
                FROM claims
                WHERE retracted_at IS NULL AND record_id = :rid
                ORDER BY record_id, field_key, asserted_at DESC
                """
            ),
            {"rid": record.id},
        ).all()
        self.assertEqual([("order_number", "PO-4411")], [(r[0], r[1]) for r in rows])
        helper = current_claims(self.session, record.id)
        self.assertEqual(1, len(helper))
        self.assertEqual("PO-4411", helper[0].value_text)

if __name__ == "__main__":
    unittest.main()
