"""Insert/read coverage for records, claims, links, change_events, order_events (#93).

Invented data only. Findings are left untouched — a claim may optionally point at one.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
import unittest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import (
    ChangeEvent,
    Claim,
    Finding,
    OrderEvent,
    Organization,
    Record,
    RecordLink,
    User,
)


class RecordsClaimsTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name="Records corp")
        self.session.add(self.org)
        self.session.flush()
        self.user = User(email=f"records-{uuid4().hex[:8]}@example.com", display_name="Ada Coordinator")
        self.session.add(self.user)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _record(self, **overrides) -> Record:
        values = {
            "organization_id": self.org.id,
            "stack_key": "sales-orders",
            "match_key": "PO-20931",
            "attributes": {"customer": "Kestrel Fabrication"},
        }
        values.update(overrides)
        record = Record(**values)
        self.session.add(record)
        self.session.flush()
        return record

    def test_record_and_claim_round_trip(self):
        parent = self._record()
        line = self._record(
            match_key="PO-20931:1",
            parent_record_id=parent.id,
            attributes={"line": 1},
        )
        claim = Claim(
            organization_id=self.org.id,
            record_id=line.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("40"),
            quote="Qty 40",
            location={"page": 1, "bbox": [10, 20, 30, 40]},
            origin="extraction",
            status="proposed",
            visible_via_user_id=self.user.id,
        )
        self.session.add(claim)
        self.session.flush()

        loaded = self.session.get(Claim, claim.id)
        self.assertEqual(loaded.value_numeric, Decimal("40"))
        self.assertEqual(loaded.value_type, "numeric")
        self.assertEqual(loaded.status, "proposed")
        self.assertEqual(loaded.visible_via_user_id, self.user.id)
        self.assertEqual(loaded.record_id, line.id)
        self.assertEqual(self.session.get(Record, line.id).parent_record_id, parent.id)

        text_claim = Claim(
            organization_id=self.org.id,
            record_id=parent.id,
            field_key="po_number",
            value_type="text",
            value_text="PO-20931",
            origin="extraction",
            status="confirmed",
            confirmed_by_user_id=self.user.id,
            confirmed_at=datetime.now(timezone.utc),
        )
        date_claim = Claim(
            organization_id=self.org.id,
            record_id=parent.id,
            field_key="due_date",
            value_type="date",
            value_date=date(2026, 9, 30),
            origin="user",
            status="proposed",
        )
        bool_claim = Claim(
            organization_id=self.org.id,
            record_id=parent.id,
            field_key="rush",
            value_type="bool",
            value_bool=False,
            origin="extraction",
            status="proposed",
        )
        self.session.add_all([text_claim, date_claim, bool_claim])
        self.session.flush()

        by_field = {
            c.field_key: c
            for c in self.session.scalars(select(Claim).where(Claim.record_id == parent.id)).all()
        }
        self.assertEqual(by_field["po_number"].value_text, "PO-20931")
        self.assertEqual(by_field["due_date"].value_date, date(2026, 9, 30))
        self.assertIs(by_field["rush"].value_bool, False)
        self.assertEqual(by_field["po_number"].confirmed_by_user_id, self.user.id)

    def test_claim_may_reference_existing_finding(self):
        record = self._record()
        finding = Finding(
            organization_id=self.org.id,
            owner_user_id=self.user.id,
            check_key="source_changed",
            subject_kind="record",
            subject_id=record.id,
            summary_sentence="PO content differs from the one confirmed on 3 Sep: Qty 40 → 60",
            evidence={"before": 40, "after": 60},
            dedupe_key=f"source_changed:{record.id}:{uuid4().hex}",
        )
        self.session.add(finding)
        self.session.flush()

        claim = Claim(
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("60"),
            origin="extraction",
            status="proposed",
            finding_id=finding.id,
        )
        self.session.add(claim)
        self.session.flush()

        loaded = self.session.get(Claim, claim.id)
        self.assertEqual(loaded.finding_id, finding.id)
        # Finding row itself is unchanged (enhance, never delete).
        still = self.session.get(Finding, finding.id)
        self.assertEqual(still.summary_sentence, finding.summary_sentence)
        self.assertIsNone(still.decision)

    def test_record_link_and_change_event_round_trip(self):
        order = self._record()
        client = self._record(stack_key="clients", match_key="CUST-KESTREL", attributes={})
        link = RecordLink(
            organization_id=self.org.id,
            from_kind="record",
            from_id=order.id,
            to_kind="record",
            to_id=client.id,
            relation_name="ordered_by",
        )
        self.session.add(link)
        self.session.flush()

        found = self.session.scalars(
            select(RecordLink).where(
                RecordLink.organization_id == self.org.id,
                RecordLink.from_id == order.id,
            )
        ).one()
        self.assertEqual(found.relation_name, "ordered_by")
        self.assertEqual(found.to_id, client.id)

        event = ChangeEvent(
            organization_id=self.org.id,
            sequence_no=1,
            caused_by_user_id=self.user.id,
            change_kind="confirm",
            before_json={"quantity": 40},
            after_json={"quantity": 60},
        )
        self.session.add(event)
        self.session.flush()
        loaded = self.session.get(ChangeEvent, event.id)
        self.assertEqual(loaded.sequence_no, 1)
        self.assertEqual(loaded.after_json["quantity"], 60)

        self.session.add(
            ChangeEvent(
                organization_id=self.org.id,
                sequence_no=1,
                change_kind="confirm",
                after_json={},
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.flush()
        self.session.rollback()

    def test_order_events_timeline_requires_actor(self):
        order = self._record()
        t0 = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 9, 3, 8, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 3, 8, 2, tzinfo=timezone.utc)
        first = OrderEvent(
            organization_id=self.org.id,
            order_id=order.id,
            kind="read",
            actor_user_id=self.user.id,
            at=t0,
            payload={"source": "upload"},
        )
        second = OrderEvent(
            organization_id=self.org.id,
            order_id=order.id,
            kind="proposed",
            actor_user_id=self.user.id,
            at=t1,
            payload={"fields": ["quantity"]},
        )
        third = OrderEvent(
            organization_id=self.org.id,
            order_id=order.id,
            kind="confirmed",
            actor_user_id=self.user.id,
            at=t2,
            payload={"claim_field": "quantity"},
        )
        self.session.add_all([first, second, third])
        self.session.flush()

        timeline = self.session.scalars(
            select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.at)
        ).all()
        self.assertEqual([e.kind for e in timeline], ["read", "proposed", "confirmed"])
        self.assertTrue(all(e.actor_user_id == self.user.id for e in timeline))

        self.session.add(
            OrderEvent(
                organization_id=self.org.id,
                order_id=order.id,
                kind="edited",
                actor_user_id=None,  # type: ignore[arg-type]
                payload={},
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.flush()


if __name__ == "__main__":
    unittest.main()
