"""Subscription renewal selects rows with under 25% of watch TTL remaining (#92)."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Organization, Subscription
from app.subscriptions import (
    DRIVE_WATCH_TTL,
    RENEW_WHEN_REMAINING_FRACTION,
    is_renewal_due,
    renew_due_subscriptions,
    select_due_subscriptions,
)


class SubscriptionRenewalTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.organization = Organization(name="Sub test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def add_subscription(self, *, expires_at: datetime, provider: str = "drive") -> Subscription:
        row = Subscription(
            provider=provider,
            external_channel_id=f"ch-{uuid4()}",
            resource_id=f"res-{uuid4()}",
            cursor="page-token-1",
            expires_at=expires_at,
            organization_id=self.organization.id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def test_is_renewal_due_when_remaining_under_quarter_ttl(self):
        threshold = DRIVE_WATCH_TTL * RENEW_WHEN_REMAINING_FRACTION
        due = self.add_subscription(expires_at=self.now + threshold - timedelta(seconds=1))
        fresh = self.add_subscription(expires_at=self.now + threshold + timedelta(hours=1))
        self.assertTrue(is_renewal_due(due, now=self.now))
        self.assertFalse(is_renewal_due(fresh, now=self.now))

    def test_select_due_subscriptions_includes_expired_and_near_expiry(self):
        threshold = DRIVE_WATCH_TTL * RENEW_WHEN_REMAINING_FRACTION
        expired = self.add_subscription(expires_at=self.now - timedelta(hours=1))
        near = self.add_subscription(expires_at=self.now + timedelta(days=1))
        fresh = self.add_subscription(expires_at=self.now + threshold + timedelta(days=1))
        due_ids = {row.id for row in select_due_subscriptions(self.session, now=self.now)}
        self.assertEqual(due_ids, {expired.id, near.id})
        self.assertNotIn(fresh.id, due_ids)

    def test_renew_due_subscriptions_calls_start_watch_only_for_due(self):
        threshold = DRIVE_WATCH_TTL * RENEW_WHEN_REMAINING_FRACTION
        due = self.add_subscription(expires_at=self.now + timedelta(hours=12))
        fresh = self.add_subscription(expires_at=self.now + threshold + timedelta(days=2))
        with patch("app.subscriptions.start_watch") as start_watch:
            start_watch.side_effect = lambda *args, **kwargs: kwargs.get("subscription")
            selected = renew_due_subscriptions(self.session, now=self.now)
        self.assertEqual([row.id for row in selected], [due.id])
        self.assertEqual(start_watch.call_count, 1)
        self.assertEqual(start_watch.call_args.kwargs["subscription"].id, due.id)
        self.assertEqual(start_watch.call_args.kwargs["organization_id"], self.organization.id)
        self.assertNotIn(fresh.id, [row.id for row in selected])


if __name__ == "__main__":
    unittest.main()
