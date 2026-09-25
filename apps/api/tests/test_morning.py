"""Morning message (#95): empty queue, open findings, permission filter, no SMTP."""
from __future__ import annotations

import logging
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.findings import create_finding
from app.main import app
from app.models import MorningDelivery, Organization, OrganizationMembership, User
from app.morning import build_morning_message, deliver_morning_dry_run


class MorningMessageTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4().hex[:8]}@example.com", display_name="Alice")
        self.bob = User(email=f"bob-{uuid4().hex[:8]}@example.com", display_name="Bob")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Morning test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add_all(
            [
                OrganizationMembership(
                    organization_id=self.organization.id, user_id=self.alice.id, role="admin"
                ),
                OrganizationMembership(
                    organization_id=self.organization.id, user_id=self.bob.id, role="member"
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

    def test_empty_queue_returns_zero_waiting(self):
        message = build_morning_message(self.session, self.organization.id, self.alice)
        self.assertEqual(0, message["waiting_count"])
        self.assertEqual([], message["items"])
        self.assertIn("generated_at", message)

        response = self.client.get(f"/accounts/{self.organization.id}/morning")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(0, body["waiting_count"])
        self.assertEqual([], body["items"])

    def test_open_findings_appear_in_morning(self):
        create_finding(
            self.session,
            organization_id=self.organization.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="PO qty changed from 40 to 60",
            fingerprint="morning-open-1",
        )
        create_finding(
            self.session,
            organization_id=self.organization.id,
            check_key="record_not_updated_since_threshold",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="Order stale for 30 days",
            fingerprint="morning-open-2",
        )
        self.session.flush()

        message = build_morning_message(self.session, self.organization.id, self.alice)
        self.assertEqual(2, message["waiting_count"])
        summaries = {item["summary_sentence"] for item in message["items"]}
        self.assertIn("PO qty changed from 40 to 60", summaries)
        self.assertIn("Order stale for 30 days", summaries)

        response = self.client.get(f"/accounts/{self.organization.id}/morning")
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, response.json()["waiting_count"])

    def test_owner_only_finding_hidden_from_other_member(self):
        create_finding(
            self.session,
            organization_id=self.organization.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="Alice private change",
            owner_user_id=self.alice.id,
            fingerprint="morning-private",
        )
        create_finding(
            self.session,
            organization_id=self.organization.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="Shared change",
            owner_user_id=None,
            fingerprint="morning-shared",
        )
        self.session.flush()

        alice_msg = build_morning_message(self.session, self.organization.id, self.alice)
        bob_msg = build_morning_message(self.session, self.organization.id, self.bob)
        self.assertEqual(2, alice_msg["waiting_count"])
        self.assertEqual(1, bob_msg["waiting_count"])
        self.assertEqual("Shared change", bob_msg["items"][0]["summary_sentence"])

    def test_deliver_dry_run_logs_and_stores_without_smtp(self):
        create_finding(
            self.session,
            organization_id=self.organization.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="Waiting for confirm",
            fingerprint="morning-deliver",
        )
        self.session.flush()

        with (
            patch("smtplib.SMTP") as smtp_cls,
            patch("smtplib.SMTP_SSL") as smtp_ssl_cls,
            self.assertLogs("app.morning", level=logging.INFO) as logs,
        ):
            result = deliver_morning_dry_run(self.session, self.organization.id, self.alice)
            self.session.commit()

        self.assertTrue(result["dry_run"])
        self.assertEqual("email", result["channel"])
        self.assertEqual(1, result["waiting_count"])
        self.assertIsNotNone(result["delivery_id"])
        smtp_cls.assert_not_called()
        smtp_ssl_cls.assert_not_called()
        self.assertTrue(any("morning_email_dry_run" in line for line in logs.output))

        row = self.session.scalar(
            select(MorningDelivery).where(MorningDelivery.id == UUID(result["delivery_id"]))
        )
        self.assertIsNotNone(row)
        self.assertEqual("email", row.channel)
        self.assertTrue(row.payload.get("dry_run"))
        self.assertEqual(self.alice.email, row.payload.get("to"))

        with patch("smtplib.SMTP") as smtp_cls, patch("smtplib.SMTP_SSL") as smtp_ssl_cls:
            response = self.client.post(f"/accounts/{self.organization.id}/morning/deliver")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["dry_run"])
        smtp_cls.assert_not_called()
        smtp_ssl_cls.assert_not_called()

    def test_non_member_gets_404(self):
        outsider = User(email=f"out-{uuid4().hex[:8]}@example.com")
        self.session.add(outsider)
        self.session.flush()
        self.current_user = outsider
        response = self.client.get(f"/accounts/{self.organization.id}/morning")
        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
