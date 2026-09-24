"""Gap findings + handover pack (#103). Invented corpus only."""
from hashlib import sha256
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.findings import create_finding, dismiss_finding
from app.gaps import (
    gap_knowledge_concentration,
    gap_missing_field,
    run_gap_checks,
)
from app.handover import build_handover_pack, pack_to_markdown
from app.main import app
from app.models import (
    Finding,
    Organization,
    OrganizationMembership,
    Substack,
    SubstackContent,
    SubstackLink,
    User,
)


def _hash(text: str) -> str:
    return sha256(text.encode()).hexdigest()


def _ev(value: str | None) -> dict:
    return {"value": value, "citations": ["c1"] if value else [], "confidence": "high"}


class GapAndHandoverTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name="Gap demo corp", account_type="personal")
        self.session.add(self.org)
        self.session.flush()
        self.alice = User(
            email=f"alice-{uuid4().hex[:8]}@demo.example",
            display_name="Alice Tan",
        )
        self.bob = User(
            email=f"bob-{uuid4().hex[:8]}@demo.example",
            display_name="Bob Lim",
        )
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.session.add_all(
            [
                OrganizationMembership(
                    organization_id=self.org.id, user_id=self.alice.id, role="admin"
                ),
                OrganizationMembership(
                    organization_id=self.org.id, user_id=self.bob.id, role="member"
                ),
            ]
        )
        self.session.flush()
        self.current_user = self.alice

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.current_user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _substack(self, stack_type: str, name: str, **kwargs) -> Substack:
        row = Substack(
            organization_id=self.org.id,
            stack_type=stack_type,
            name=name,
            status=kwargs.get("status", "confirmed"),
            review_state=kwargs.get("review_state", "clean"),
            owner_user_id=kwargs.get("owner_user_id"),
            created_by_user_id=kwargs.get("created_by_user_id"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _content(
        self,
        substack: Substack,
        *,
        revision: int,
        extraction: dict,
        status: str = "confirmed",
        confirmed_by: User | None = None,
    ) -> SubstackContent:
        content = SubstackContent(
            substack_id=substack.id,
            revision=revision,
            prompt_key="test",
            prompt_version="v1",
            model="test",
            content={"extraction": extraction},
            status=status,
            inputs_fingerprint=_hash(f"{substack.id}-{revision}"),
            confirmed_by_user_id=confirmed_by.id if confirmed_by else None,
            confirmed_at=datetime.now(timezone.utc) if confirmed_by else None,
        )
        self.session.add(content)
        self.session.flush()
        return content

    def test_gap_missing_field_on_incomplete_order(self):
        order = self._substack("sales-orders", "PO-DEMO-1")
        self._content(
            order,
            revision=1,
            extraction={
                "order_number": _ev(None),
                "customer_name": _ev("Northwind Components Pte Ltd"),
                "line_items": [{"quantity": _ev("10")}],
            },
        )
        drafts = gap_missing_field(self.session, self.org.id)
        self.assertEqual(1, len(drafts))
        self.assertEqual("gap_missing_field", drafts[0].check_key)
        self.assertIn("order_number", drafts[0].observed_value or "")

    def test_gap_missing_field_skips_complete_client(self):
        client = self._substack("clients", "Northwind Components Pte Ltd")
        self._content(
            client,
            revision=1,
            extraction={
                "name": _ev("Northwind Components Pte Ltd"),
                "registration_number": _ev("UEN-DEMO-001"),
            },
        )
        drafts = gap_missing_field(self.session, self.org.id)
        self.assertEqual([], drafts)

    def test_gap_missing_field_ignores_non_scope_stacks(self):
        meeting = self._substack("meetings", "Weekly ops")
        self._content(meeting, revision=1, extraction={"title": _ev(None)})
        drafts = gap_missing_field(self.session, self.org.id)
        self.assertEqual([], drafts)

    def test_gap_knowledge_concentration_single_confirmer(self):
        client = self._substack("clients", "Contoso Fabrication")
        self._content(
            client,
            revision=1,
            status="superseded",
            confirmed_by=self.alice,
            extraction={
                "name": _ev("Contoso Fabrication"),
                "customer_id": _ev("C-100"),
            },
        )
        self._content(
            client,
            revision=2,
            status="confirmed",
            confirmed_by=self.alice,
            extraction={
                "name": _ev("Contoso Fabrication"),
                "customer_id": _ev("C-100"),
                "payment_terms": _ev("Net 30"),
            },
        )
        order = self._substack("sales-orders", "PO-CONTOSO-9")
        self.session.add(SubstackLink(substack_id=order.id, related_substack_id=client.id))
        self.session.flush()
        self._content(
            order,
            revision=1,
            confirmed_by=self.alice,
            extraction={
                "order_number": _ev("PO-CONTOSO-9"),
                "customer_name": _ev("Contoso Fabrication"),
                "line_items": [{"quantity": _ev("5")}],
            },
        )
        drafts = gap_knowledge_concentration(self.session, self.org.id)
        self.assertTrue(any(d.check_key == "gap_knowledge_concentration" for d in drafts))
        hit = next(d for d in drafts if d.check_key == "gap_knowledge_concentration")
        self.assertIn("Contoso", hit.summary_sentence)
        self.assertIn("Alice", hit.summary_sentence)
        self.assertEqual(str(self.alice.id), hit.evidence["top_confirmer_user_id"])

    def test_gap_knowledge_concentration_shared_confirmers_no_finding(self):
        client = self._substack("clients", "Shared Client Co")
        self._content(
            client,
            revision=1,
            status="superseded",
            confirmed_by=self.alice,
            extraction={"name": _ev("Shared Client Co"), "customer_id": _ev("S-1")},
        )
        self._content(
            client,
            revision=2,
            confirmed_by=self.bob,
            extraction={"name": _ev("Shared Client Co"), "customer_id": _ev("S-1")},
        )
        drafts = gap_knowledge_concentration(self.session, self.org.id)
        self.assertEqual([], drafts)

    def test_run_gap_checks_writes_findings(self):
        order = self._substack("sales-orders", "PO-GAP-RUN")
        self._content(
            order,
            revision=1,
            extraction={
                "order_number": _ev("PO-GAP-RUN"),
                "customer_name": _ev(None),
                "line_items": [{"quantity": _ev("1")}],
            },
        )
        created = run_gap_checks(self.session, self.org.id)
        keys = {f.check_key for f in created}
        self.assertIn("gap_missing_field", keys)

    def test_handover_pack_json_and_markdown(self):
        client = self._substack("clients", "Fabrikam Supplies")
        self._content(
            client,
            revision=1,
            status="superseded",
            confirmed_by=self.alice,
            extraction={
                "name": _ev("Fabrikam Supplies"),
                "customer_id": _ev("F-1"),
                "payment_terms": _ev("Net 14"),
            },
        )
        self._content(
            client,
            revision=2,
            confirmed_by=self.alice,
            extraction={
                "name": _ev("Fabrikam Supplies"),
                "customer_id": _ev("F-1"),
                "payment_terms": _ev("Net 45"),
            },
        )
        finding = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="gap_missing_field",
            subject_kind="substack",
            subject_id=client.id,
            summary_sentence="demo dismiss",
            fingerprint="handover-dismiss",
        )
        dismiss_finding(self.session, finding, user_id=self.alice.id, reason="already_handled")
        acted = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="gap_missing_field",
            subject_kind="substack",
            subject_id=client.id,
            summary_sentence="demo acted",
            fingerprint="handover-acted",
        )
        acted.decision = "acted"
        acted.decided_by_user_id = self.alice.id
        acted.decided_at = datetime.now(timezone.utc)
        self.session.flush()

        pack = build_handover_pack(self.session, self.org.id, focus="client", user_id=self.alice.id)
        self.assertEqual("client", pack["focus"])
        self.assertTrue(any(o["field"] == "payment_terms" for o in pack["overrides"]))
        self.assertTrue(any(c["substack_name"] == "Fabrikam Supplies" for c in pack["key_claims"]))
        self.assertTrue(any(d["dismissal_reason"] == "already_handled" for d in pack["dismissed_findings"]))
        self.assertTrue(any(f["decision"] == "acted" for f in pack["confirmed_fixes"]))
        md = pack_to_markdown(pack)
        self.assertIn("# Handover pack — Clients", md)
        self.assertIn("payment_terms", md)

        response = self.client.get(
            f"/accounts/{self.org.id}/handover-pack",
            params={"focus": "client", "user_id": str(self.alice.id)},
        )
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("client", body["focus"])
        self.assertTrue(body["overrides"])

        md_response = self.client.get(
            f"/accounts/{self.org.id}/handover-pack",
            params={"focus": "orders", "format": "markdown"},
        )
        self.assertEqual(200, md_response.status_code)
        self.assertIn("text/markdown", md_response.headers["content-type"])
        self.assertIn("attachment", md_response.headers.get("content-disposition", ""))
        self.assertIn("# Handover pack — Sales orders", md_response.text)

    def test_handover_pack_rejects_bad_focus(self):
        response = self.client.get(
            f"/accounts/{self.org.id}/handover-pack",
            params={"focus": "events"},
        )
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
