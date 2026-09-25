"""Health (#21): confirm events per kind, alarms as findings, the fifty-word read.

#102 extends the payload with per_template metrics and a golden panel.
"""
import unittest
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import (
    ConfirmEvent,
    Finding,
    Organization,
    OrganizationMembership,
    Substack,
    SubstackContent,
    User,
)


class HealthApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.session.add(self.alice)
        self.session.flush()
        self.organization = Organization(name=f"Health-{uuid4().hex[:6]}", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add(OrganizationMembership(organization_id=self.organization.id, user_id=self.alice.id, role="admin"))
        self.session.flush()

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.alice
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _proposed_substack(self, name: str, stack_type: str = "sales-orders") -> tuple[Substack, SubstackContent]:
        substack = Substack(organization_id=self.organization.id, stack_type=stack_type, name=name, status="proposed")
        self.session.add(substack)
        self.session.flush()
        content = SubstackContent(
            substack_id=substack.id,
            revision=1,
            prompt_key=stack_type.replace("-", "_"),
            prompt_version="v1",
            model="test",
            content={"lines": []},
            status="proposed",
            inputs_fingerprint=sha256(name.encode()).hexdigest(),
        )
        self.session.add(content)
        self.session.flush()
        return substack, content

    def _events(self) -> list[ConfirmEvent]:
        return self.session.scalars(
            select(ConfirmEvent).where(ConfirmEvent.organization_id == self.organization.id)
        ).all()

    def test_rest_line_when_nothing_to_act_on_and_no_test_run(self):
        resp = self.client.get(f"/accounts/{self.organization.id}/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["alarms"], [])
        self.assertEqual(body["at_rest"], "Nothing to act on. Nightly test has not run with labels yet.")
        self.assertLessEqual(len(body["at_rest"].split()), 50)
        self.assertEqual(body["windows"]["7d"]["confirms"], {"person": 0, "bulk": 0, "auto": 0})
        # #102 shape present even with no activity.
        self.assertEqual(body["golden"]["status"], "fixture")
        self.assertEqual(len(body["per_template"]), 12)

    def test_single_confirm_writes_a_person_event(self):
        substack, content = self._proposed_substack("PO-1")
        resp = self.client.post(f"/substacks/{substack.id}/contents/{content.id}/confirm")
        self.assertEqual(resp.status_code, 200)
        events = self._events()
        self.assertEqual([(e.kind, e.by_user_id) for e in events], [("person", self.alice.id)])

    def test_bulk_confirm_trips_the_alarm_and_lands_in_to_check(self):
        for index in range(12):
            self._proposed_substack(f"PO-{index}")
        resp = self.client.post(f"/accounts/{self.organization.id}/substacks/confirm-all")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["confirmed"], 12)
        kinds = {e.kind for e in self._events()}
        self.assertEqual(kinds, {"bulk"})

        body = self.client.get(f"/accounts/{self.organization.id}/health").json()
        self.assertEqual(body["windows"]["7d"]["confirms"], {"person": 0, "bulk": 12, "auto": 0})
        self.assertIn("bulk_confirm_share", [alarm["key"] for alarm in body["alarms"]])
        self.assertEqual(body["at_rest"], "Bulk confirms dominate this week.")

        # Alarms are findings, so they appear in To check like everything else.
        finding = self.session.scalar(
            select(Finding).where(
                Finding.organization_id == self.organization.id,
                Finding.check_key == "health_bulk_confirm_share",
                Finding.decision.is_(None),
            )
        )
        self.assertIsNotNone(finding)
        queue = self.client.get(f"/accounts/{self.organization.id}/findings").json()["findings"]
        self.assertIn(str(finding.id), [row["id"] for row in queue])

        # A second read the same day does not raise the alarm twice.
        self.client.get(f"/accounts/{self.organization.id}/health")
        count = self.session.scalars(
            select(Finding).where(Finding.organization_id == self.organization.id, Finding.check_key == "health_bulk_confirm_share")
        ).all()
        self.assertEqual(len(count), 1)

    def test_health_includes_per_template_and_golden_fixture_shape(self):
        """#102: every template row + golden panel (fixture until #106 live cut)."""
        from datetime import datetime, timezone

        from app.models import STACK_TYPES

        # Person confirm on sales-orders (rev 2 = one edit), auto on clients.
        orders, order_content = self._proposed_substack("PO-metric")
        order_content.revision = 2
        order_content.status = "confirmed"
        order_content.confirmed_at = datetime.now(timezone.utc)
        order_content.confirmed_by_user_id = self.alice.id
        clients, client_content = self._proposed_substack("Client-A", stack_type="clients")
        client_content.status = "confirmed"
        client_content.confirmed_at = datetime.now(timezone.utc)
        self.session.add(
            ConfirmEvent(
                organization_id=self.organization.id,
                substack_id=orders.id,
                content_id=order_content.id,
                kind="person",
                by_user_id=self.alice.id,
            )
        )
        self.session.add(
            ConfirmEvent(
                organization_id=self.organization.id,
                substack_id=clients.id,
                content_id=client_content.id,
                kind="auto",
                by_user_id=None,
            )
        )
        self.session.flush()

        body = self.client.get(f"/accounts/{self.organization.id}/health").json()

        self.assertIn("per_template", body)
        self.assertIn("golden", body)
        self.assertEqual(body["golden"]["status"], "fixture")
        self.assertEqual(body["golden"]["metrics"]["question_count"], 50)
        self.assertIn("per_template", body["golden"]["metrics"])

        rows = body["per_template"]
        self.assertEqual(len(rows), len(STACK_TYPES))
        by_key = {row["template_or_stack_key"]: row for row in rows}
        for key in STACK_TYPES:
            self.assertIn(key, by_key)
            row = by_key[key]
            self.assertIn("review_rate", row)
            self.assertIn("edit_count", row)
            self.assertIn("acceptance", row)

        sales = by_key["sales-orders"]
        self.assertEqual(sales["review_rate"], 1.0)
        self.assertEqual(sales["edit_count"], 1)
        self.assertEqual(sales["acceptance"], 0.0)

        clients_row = by_key["clients"]
        self.assertEqual(clients_row["review_rate"], 0.0)
        self.assertEqual(clients_row["edit_count"], 0)

        # Existing Health shape is preserved.
        self.assertIn("at_rest", body)
        self.assertIn("alarms", body)
        self.assertIn("windows", body)
        self.assertIn("nightly_test", body)
        self.assertIn("jobs", body)

    def test_golden_panel_flips_to_live_when_acceptance_metrics_present(self):
        from datetime import datetime, timezone

        from app.models import TestRun

        self.session.add(
            TestRun(
                organization_id=self.organization.id,
                kind="retrieval",
                status="passed",
                started_at=datetime.now(timezone.utc),
                metrics={
                    "source": "golden",
                    "acceptance_mean": 0.91,
                    "question_count": 50,
                    "per_template": {"sales-orders": {"acceptance": 0.95}},
                },
            )
        )
        self.session.flush()

        body = self.client.get(f"/accounts/{self.organization.id}/health").json()
        self.assertEqual(body["golden"]["status"], "live")
        self.assertEqual(body["golden"]["metrics"]["acceptance_mean"], 0.91)
        sales = next(
            row for row in body["per_template"] if row["template_or_stack_key"] == "sales-orders"
        )
        self.assertEqual(sales["acceptance"], 0.95)


if __name__ == "__main__":
    unittest.main()
