"""Review queue + timeline (#93 Steps 2–4). Invented data only.

Covers:
- create_claim WhatsApp user/org seam
- confirm / fix / dismiss in one transaction (finding + claim + change_event + order_event)
- timeline append + GET ordered by at
- existing /findings dismiss path still works beside /queue
"""
from __future__ import annotations

from decimal import Decimal
from unittest import mock
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.claims import create_claim, is_whatsapp_origin
from app.database import get_engine, get_session
from app.main import app
from app.models import (
    ChangeEvent,
    Claim,
    Finding,
    OrderEvent,
    Organization,
    OrganizationMembership,
    Record,
    User,
)
from app.timeline import append_order_event


class QueueTimelineTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.user = User(email=f"queue-{uuid4().hex[:8]}@example.com", display_name="Ada")
        self.other = User(email=f"other-{uuid4().hex[:8]}@example.com", display_name="Bea")
        self.session.add_all([self.user, self.other])
        self.session.flush()
        self.org = Organization(name="Queue corp", account_type="personal")
        self.session.add(self.org)
        self.session.flush()
        self.session.add_all(
            [
                OrganizationMembership(
                    organization_id=self.org.id, user_id=self.user.id, role="admin"
                ),
                OrganizationMembership(
                    organization_id=self.org.id, user_id=self.other.id, role="member"
                ),
            ]
        )
        self.session.flush()
        self.current_user = self.user

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

    def _record(self, **overrides) -> Record:
        values = {
            "organization_id": self.org.id,
            "stack_key": "sales-orders",
            "match_key": "PO-20931",
            "attributes": {},
        }
        values.update(overrides)
        record = Record(**values)
        self.session.add(record)
        self.session.flush()
        return record

    def _open_finding(
        self,
        record: Record,
        *,
        check_key: str = "source_changed",
        owner_user_id=None,
        summary: str = "PO content differs: Qty 40 → 60",
    ) -> Finding:
        finding = Finding(
            organization_id=self.org.id,
            owner_user_id=owner_user_id,
            check_key=check_key,
            subject_kind="record",
            subject_id=record.id,
            summary_sentence=summary,
            evidence={},
            dedupe_key=f"{check_key}:{record.id}:{uuid4().hex}",
        )
        self.session.add(finding)
        self.session.flush()
        return finding

    def test_create_claim_whatsapp_requires_visible_via(self):
        self.assertTrue(is_whatsapp_origin("whatsapp"))
        record = self._record()
        with self.assertRaises(ValueError) as ctx:
            create_claim(
                self.session,
                organization_id=self.org.id,
                record_id=record.id,
                field_key="headcount",
                value_type="numeric",
                value_numeric=Decimal("12"),
                origin="whatsapp",
            )
        self.assertIn("visible_via", str(ctx.exception))

        claim = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="headcount",
            value_type="numeric",
            value_numeric=Decimal("12"),
            origin="whatsapp",
            visible_via_user_id=self.user.id,
        )
        self.assertEqual(claim.organization_id, self.org.id)
        self.assertEqual(claim.visible_via_user_id, self.user.id)

        # Non-WhatsApp origins may omit visible_via (org-wide once confirmed).
        other = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="po_number",
            value_type="text",
            value_text="PO-20931",
            origin="extraction",
        )
        self.assertIsNone(other.visible_via_user_id)

    def test_queue_lists_open_blocking_first_membership_filtered(self):
        record = self._record()
        soft = self._open_finding(
            record, check_key="record_not_updated_since_threshold", summary="stale"
        )
        blocking = self._open_finding(record, check_key="source_changed", summary="changed")
        private = self._open_finding(
            record, check_key="sources_disagree", owner_user_id=self.other.id, summary="private"
        )
        self.session.flush()

        resp = self.client.get(f"/accounts/{self.org.id}/queue")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        ids = [row["id"] for row in body["items"]]
        self.assertIn(str(blocking.id), ids)
        self.assertIn(str(soft.id), ids)
        self.assertNotIn(str(private.id), ids)
        # Blocking check_key sorts ahead of non-blocking.
        self.assertLess(ids.index(str(blocking.id)), ids.index(str(soft.id)))
        self.assertTrue(body["items"][ids.index(str(blocking.id))]["blocking"])

        # Legacy findings path still works for To check UI.
        legacy = self.client.get(f"/accounts/{self.org.id}/findings")
        self.assertEqual(legacy.status_code, 200)
        legacy_ids = {row["id"] for row in legacy.json()["findings"]}
        self.assertIn(str(blocking.id), legacy_ids)
        self.assertNotIn(str(private.id), legacy_ids)

    def test_confirm_writes_claim_change_and_order_event_atomically(self):
        record = self._record()
        finding = self._open_finding(record)
        claim = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("60"),
            origin="extraction",
            finding_id=finding.id,
        )
        self.session.flush()

        resp = self.client.post(f"/accounts/{self.org.id}/queue/{finding.id}/confirm")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["decision"], "confirmed")
        self.assertIn(str(claim.id), data["confirmed_claim_ids"])

        loaded = self.session.get(Finding, finding.id)
        self.assertEqual(loaded.decision, "confirmed")
        self.assertEqual(loaded.decided_by_user_id, self.user.id)

        claim_loaded = self.session.get(Claim, claim.id)
        self.assertEqual(claim_loaded.status, "confirmed")
        self.assertEqual(claim_loaded.confirmed_by_user_id, self.user.id)
        self.assertIsNotNone(claim_loaded.confirmed_at)

        change = self.session.get(ChangeEvent, data["change_event_id"])
        self.assertIsNotNone(change)
        self.assertEqual(change.change_kind, "confirm")
        self.assertEqual(change.caused_by_finding_id, finding.id)

        order_event = self.session.get(OrderEvent, data["order_event_id"])
        self.assertIsNotNone(order_event)
        self.assertEqual(order_event.kind, "confirmed")
        self.assertEqual(order_event.order_id, record.id)
        self.assertEqual(order_event.actor_user_id, self.user.id)

    def test_confirm_rolls_back_when_order_event_fails(self):
        record = self._record()
        finding = self._open_finding(record)
        create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("60"),
            origin="extraction",
            finding_id=finding.id,
        )
        self.session.flush()

        with mock.patch(
            "app.queue.append_order_event",
            side_effect=ValueError("forced_order_event_failure"),
        ):
            with self.assertRaises(ValueError):
                self.client.post(f"/accounts/{self.org.id}/queue/{finding.id}/confirm")

        self.session.expire_all()
        still = self.session.get(Finding, finding.id)
        self.assertIsNone(still.decision)
        claims = self.session.scalars(select(Claim).where(Claim.finding_id == finding.id)).all()
        self.assertTrue(all(c.status == "proposed" for c in claims))
        self.assertEqual(
            self.session.scalar(
                select(ChangeEvent).where(ChangeEvent.caused_by_finding_id == finding.id)
            ),
            None,
        )

    def test_fix_supersedes_old_claim_and_confirms_new(self):
        record = self._record()
        finding = self._open_finding(record)
        old = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("40"),
            origin="extraction",
            finding_id=finding.id,
        )
        self.session.flush()

        resp = self.client.post(
            f"/accounts/{self.org.id}/queue/{finding.id}/fix",
            json={"field": "quantity", "new_value": "60", "value_type": "numeric"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["superseded_claim_id"], str(old.id))

        self.session.expire_all()
        self.assertEqual(self.session.get(Claim, old.id).status, "superseded")
        new_claim = self.session.get(Claim, data["claim_id"])
        self.assertEqual(new_claim.status, "confirmed")
        self.assertEqual(new_claim.value_numeric, Decimal("60"))
        self.assertEqual(new_claim.confirmed_by_user_id, self.user.id)
        self.assertEqual(self.session.get(Finding, finding.id).decision, "confirmed")

        change = self.session.get(ChangeEvent, data["change_event_id"])
        self.assertEqual(change.change_kind, "fix")
        order_event = self.session.get(OrderEvent, data["order_event_id"])
        self.assertEqual(order_event.kind, "edited")

    def test_dismiss_retracts_proposed_claims_fixed_reason(self):
        record = self._record()
        finding = self._open_finding(record)
        claim = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("60"),
            origin="extraction",
            finding_id=finding.id,
        )
        self.session.flush()

        bad = self.client.post(
            f"/accounts/{self.org.id}/queue/{finding.id}/dismiss",
            json={"reason": "not_a_real_reason"},
        )
        self.assertEqual(bad.status_code, 400)

        resp = self.client.post(
            f"/accounts/{self.org.id}/queue/{finding.id}/dismiss",
            json={"reason": "not_a_change"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.session.expire_all()
        self.assertEqual(self.session.get(Finding, finding.id).decision, "dismissed")
        self.assertEqual(self.session.get(Finding, finding.id).dismissal_reason, "not_a_change")
        self.assertEqual(self.session.get(Claim, claim.id).status, "retracted")
        self.assertIsNotNone(self.session.get(Claim, claim.id).retracted_at)
        change = self.session.get(ChangeEvent, resp.json()["change_event_id"])
        self.assertEqual(change.change_kind, "dismiss")

        # Legacy dismiss still available.
        finding2 = self._open_finding(record, summary="second")
        legacy = self.client.post(
            f"/accounts/{self.org.id}/findings/{finding2.id}/dismiss",
            json={"reason": "duplicate"},
        )
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.json()["decision"], "dismissed")

    def test_timeline_append_and_get_ordered_by_at(self):
        record = self._record()
        e1 = append_order_event(
            self.session,
            organization_id=self.org.id,
            order_id=record.id,
            kind="read",
            actor_user_id=self.user.id,
            payload={"source": "upload"},
        )
        e2 = append_order_event(
            self.session,
            organization_id=self.org.id,
            order_id=record.id,
            kind="proposed",
            actor_user_id=self.user.id,
            payload={"fields": ["quantity"]},
        )
        e3 = append_order_event(
            self.session,
            organization_id=self.org.id,
            order_id=record.id,
            kind="confirmed",
            actor_user_id=self.user.id,
            payload={"claim_field": "quantity"},
        )
        self.session.flush()

        resp = self.client.get(f"/accounts/{self.org.id}/records/{record.id}/timeline")
        self.assertEqual(resp.status_code, 200)
        events = resp.json()["events"]
        self.assertEqual([e["kind"] for e in events], ["read", "proposed", "confirmed"])
        self.assertEqual([e["id"] for e in events], [str(e1.id), str(e2.id), str(e3.id)])
        self.assertTrue(all(e["actor_user_id"] == str(self.user.id) for e in events))

        missing = self.client.get(f"/accounts/{self.org.id}/records/{uuid4()}/timeline")
        self.assertEqual(missing.status_code, 404)

    def test_fix_rolls_back_when_change_event_fails(self):
        record = self._record()
        finding = self._open_finding(record)
        old = create_claim(
            self.session,
            organization_id=self.org.id,
            record_id=record.id,
            field_key="quantity",
            value_type="numeric",
            value_numeric=Decimal("40"),
            origin="extraction",
            finding_id=finding.id,
        )
        self.session.flush()

        with mock.patch(
            "app.queue.append_change_event",
            side_effect=RuntimeError("forced_change_event_failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    f"/accounts/{self.org.id}/queue/{finding.id}/fix",
                    json={"field": "quantity", "new_value": "60", "value_type": "numeric"},
                )

        self.session.expire_all()
        self.assertIsNone(self.session.get(Finding, finding.id).decision)
        self.assertEqual(self.session.get(Claim, old.id).status, "proposed")
        # No new confirmed claim for this finding.
        statuses = [
            c.status
            for c in self.session.scalars(select(Claim).where(Claim.finding_id == finding.id)).all()
        ]
        self.assertEqual(statuses, ["proposed"])


if __name__ == "__main__":
    unittest.main()
