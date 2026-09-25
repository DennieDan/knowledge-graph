"""Reply drafts from confirmed claims only; send is dry-run (#105)."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import (
    Claim,
    Document,
    OrderEvent,
    Organization,
    OrganizationMembership,
    Record,
    Substack,
    SubstackSource,
    User,
)
from app.replies import draft_reply


class ReplyDraftTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.user = User(email=f"reply-{uuid4().hex[:8]}@example.com", display_name="Alex Tan")
        self.session.add(self.user)
        self.session.flush()
        self.org = Organization(name="Reply corp", account_type="personal")
        self.session.add(self.org)
        self.session.flush()
        self.session.add(
            OrganizationMembership(organization_id=self.org.id, user_id=self.user.id, role="admin")
        )
        self.session.flush()

        self.substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="PO HH-2231",
            status="confirmed",
            review_state="clean",
            created_by="user",
        )
        self.session.add(self.substack)
        self.session.flush()
        self.record = Record(
            organization_id=self.org.id,
            stack_key="sales-orders",
            match_key="HH-2231",
            substack_id=self.substack.id,
            attributes={"customer": "Harbour Hotel"},
        )
        self.session.add(self.record)
        self.session.flush()

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _confirm_claim(self, field_key: str, **values) -> Claim:
        claim = Claim(
            organization_id=self.org.id,
            record_id=self.record.id,
            field_key=field_key,
            origin="extraction",
            status="confirmed",
            confirmed_by_user_id=self.user.id,
            confirmed_at=datetime.now(timezone.utc),
            **values,
        )
        self.session.add(claim)
        self.session.flush()
        return claim

    def test_draft_uses_confirmed_claims_not_raw_pdf(self):
        raw_pdf = "CONFIDENTIAL PDF BODY qty 999 secret-price $12.50 Harbour Hotel PO HH-2231"
        document = Document(
            organization_id=self.org.id,
            source="google_drive",
            external_id=f"doc-{uuid4().hex[:8]}",
            title="HH-2231.pdf",
            owner_user_id=self.user.id,
        )
        self.session.add(document)
        self.session.flush()
        # Raw PDF text lives on the version — drafts must never copy it.
        from app.models import DocumentVersion
        import hashlib

        self.session.add(
            DocumentVersion(
                document_id=document.id,
                revision=1,
                content_hash=hashlib.sha256(raw_pdf.encode()).hexdigest(),
                content=raw_pdf,
            )
        )
        self.session.add(SubstackSource(substack_id=self.substack.id, document_id=document.id, role="evidence"))
        # Proposed / unconfirmed claim must never appear.
        self.session.add(
            Claim(
                organization_id=self.org.id,
                record_id=self.record.id,
                field_key="quantity",
                value_type="numeric",
                value_numeric=Decimal("999"),
                quote="qty 999",
                origin="extraction",
                status="proposed",
            )
        )
        self._confirm_claim(
            "po_number",
            value_type="text",
            value_text="HH-2231",
            quote="PO HH-2231 from scanned PDF garbage",
        )
        self._confirm_claim(
            "quantity",
            value_type="numeric",
            value_numeric=Decimal("40"),
            quote="qty 999 is wrong; confirmed is 40",
        )
        self._confirm_claim(
            "item",
            value_type="text",
            value_text="Item A",
        )
        self.session.commit()

        response = self.client.post(
            f"/accounts/{self.org.id}/substacks/{self.substack.id}/reply/draft",
            json={"channel": "email"},
        )
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        body = payload["body"]
        self.assertEqual("email", payload["channel"])
        self.assertIn("HH-2231", body)
        self.assertIn("40", body)
        self.assertIn("Item A", body)
        # Raw / unconfirmed values must not leak.
        self.assertNotIn("999", body)
        self.assertNotIn("12.50", body)
        self.assertNotIn("CONFIDENTIAL", body)
        self.assertNotIn("secret-price", body)
        self.assertNotIn("scanned PDF garbage", body)
        self.assertTrue(any(s["field_key"] == "po_number" for s in payload["sources_used"]))

    def test_draft_reply_function_skips_unconfirmed(self):
        self._confirm_claim("po_number", value_type="text", value_text="PO-1")
        self.session.add(
            Claim(
                organization_id=self.org.id,
                record_id=self.record.id,
                field_key="quantity",
                value_type="numeric",
                value_numeric=Decimal("7"),
                origin="extraction",
                status="proposed",
            )
        )
        self.session.flush()
        draft = draft_reply(self.session, self.substack, "whatsapp", user=self.user)
        self.assertEqual("whatsapp", draft["channel"])
        self.assertIn("PO-1", draft["body"])
        self.assertNotIn("7", draft["body"])

    def test_send_is_dry_run_and_appends_order_event(self):
        self._confirm_claim("po_number", value_type="text", value_text="HH-2231")
        self._confirm_claim("quantity", value_type="numeric", value_numeric=Decimal("40"))
        self.session.commit()

        draft = self.client.post(
            f"/accounts/{self.org.id}/substacks/{self.substack.id}/reply/draft",
            json={"channel": "whatsapp"},
        ).json()

        with self.assertLogs("app.replies", level="INFO") as logged:
            response = self.client.post(
                f"/accounts/{self.org.id}/substacks/{self.substack.id}/reply/send",
                json={"body": draft["body"], "channel": "whatsapp"},
            )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({"status": "logged"}, response.json())
        self.assertTrue(any("reply_send_dry_run" in line for line in logged.output))

        events = list(
            self.session.scalars(
                select(OrderEvent).where(OrderEvent.order_id == self.record.id)
            ).all()
        )
        self.assertEqual(1, len(events))
        self.assertEqual("replied", events[0].kind)
        self.assertEqual(self.user.id, events[0].actor_user_id)
        self.assertTrue(events[0].payload.get("dry_run"))
        self.assertEqual("whatsapp", events[0].payload.get("channel"))
        self.assertEqual(draft["body"], events[0].payload.get("body"))

    def test_send_rejects_body_with_foreign_numbers(self):
        self._confirm_claim("po_number", value_type="text", value_text="HH-2231")
        self.session.commit()
        response = self.client.post(
            f"/accounts/{self.org.id}/substacks/{self.substack.id}/reply/send",
            json={"body": "Received HH-2231 for 999 units.", "channel": "email"},
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("draft_contains_unconfirmed_value", response.json()["detail"])

    def test_draft_requires_confirmed_claims(self):
        self.session.add(
            Claim(
                organization_id=self.org.id,
                record_id=self.record.id,
                field_key="po_number",
                value_type="text",
                value_text="HH-2231",
                origin="extraction",
                status="proposed",
            )
        )
        self.session.commit()
        response = self.client.post(
            f"/accounts/{self.org.id}/substacks/{self.substack.id}/reply/draft",
            json={},
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("no_confirmed_claims", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
