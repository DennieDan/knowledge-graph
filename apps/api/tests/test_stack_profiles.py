"""Industry stack catalogue API (#97 Step 1)."""
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import Organization, OrganizationMembership, STACK_TYPES, Stack, StackField, User
from app.stack_profiles import INDUSTRY_PROFILES, SALES_ORDER_FIELDS


class StackProfilesApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.outsider = User(email=f"out-{uuid4()}@other.example")
        self.session.add_all([self.alice, self.outsider])
        self.session.flush()
        self.organization = Organization(name="Catalogue test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add(
            OrganizationMembership(organization_id=self.organization.id, user_id=self.alice.id, role="admin")
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

    def onboard(self, key="supplier"):
        return self.client.post(
            f"/accounts/{self.organization.id}/onboarding/industry",
            json={"key": key},
        )

    def catalog(self):
        return self.client.get(f"/accounts/{self.organization.id}/stack-catalog")

    def test_supplier_profile_seeds_twelve_stacks_with_sales_order_fields(self):
        response = self.onboard("supplier")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("supplier", body["profile_key"])
        self.assertEqual(len(STACK_TYPES), len(body["stacks"]))
        by_key = {row["key"]: row for row in body["stacks"]}
        self.assertEqual(set(STACK_TYPES), set(by_key))
        self.assertEqual("Sales Orders", by_key["sales-orders"]["name"])
        field_keys = [field["key"] for field in by_key["sales-orders"]["fields"]]
        self.assertEqual(
            {"order_number", "revision", "quantity", "unit_price", "due_date"},
            set(field_keys),
        )
        order_number = next(f for f in by_key["sales-orders"]["fields"] if f["key"] == "order_number")
        self.assertEqual("text", order_number["value_type"])
        self.assertTrue(order_number["required"])
        self.assertTrue(order_number["searchable"])
        self.assertEqual(len(SALES_ORDER_FIELDS), len(by_key["sales-orders"]["fields"]))
        self.assertGreaterEqual(len(by_key["clients"]["fields"]), 1)
        self.assertLessEqual(len(by_key["clients"]["fields"]), 2)

        stored = self.session.scalars(select(Stack).where(Stack.organization_id == self.organization.id)).all()
        self.assertEqual(len(STACK_TYPES), len(stored))
        fields = self.session.scalars(select(StackField)).all()
        self.assertGreater(len(fields), 0)

    def test_onboarding_is_idempotent_for_same_profile(self):
        first = self.onboard("supplier")
        self.assertEqual(200, first.status_code)
        second = self.onboard("supplier")
        self.assertEqual(200, second.status_code)
        self.assertEqual(first.json()["stacks"][0]["id"], second.json()["stacks"][0]["id"])
        count = len(self.session.scalars(select(Stack).where(Stack.organization_id == self.organization.id)).all())
        self.assertEqual(len(STACK_TYPES), count)

    def test_stack_catalog_lists_seeded_stacks(self):
        self.assertEqual([], self.catalog().json()["stacks"])
        self.onboard("supplier")
        listed = self.catalog().json()
        self.assertEqual("supplier", listed["profile_key"])
        self.assertEqual(len(STACK_TYPES), len(listed["stacks"]))
        self.assertTrue(listed["stacks"][0]["fields"])

    def test_event_organiser_profile_uses_catalogue_only_keys(self):
        response = self.onboard("event_organiser")
        self.assertEqual(200, response.status_code)
        keys = {row["key"] for row in response.json()["stacks"]}
        expected = {stack.key for stack in INDUSTRY_PROFILES["event_organiser"]}
        self.assertEqual(expected, keys)
        self.assertIn("events", keys)
        self.assertNotIn("events", STACK_TYPES)
        self.assertIn("venues", keys)
        self.assertNotIn("venues", STACK_TYPES)

    def test_cannot_reseed_different_profile(self):
        self.assertEqual(200, self.onboard("supplier").status_code)
        conflict = self.onboard("event_organiser")
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("industry_profile_already_seeded", conflict.json()["detail"])

    def test_unknown_profile_rejected(self):
        response = self.onboard("aerospace")
        self.assertEqual(422, response.status_code)

    def test_non_member_cannot_onboard_or_list(self):
        self.current_user = self.outsider
        self.assertEqual(404, self.onboard("supplier").status_code)
        self.assertEqual(404, self.catalog().status_code)


if __name__ == "__main__":
    unittest.main()
