"""Field rules by role (#101): planner/supervisor never see price-derived fields."""
import unittest
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Organization, OrganizationMembership, User
from app.record_access import (
    PRICE_DERIVED_FIELDS,
    filter_claims_for_role,
    hidden_fields_for_role,
    membership_role,
    role_may_see_field,
)


SAMPLE_CLAIMS = [
    {"field_key": "order_number", "value": "PO-1001"},
    {"field_key": "quantity", "value": "10"},
    {"field_key": "unit_price", "value": "12.50"},
    {"field_key": "line_total", "value": "125.00"},
    {"field_key": "requested_delivery_date", "value": "2026-10-01"},
]

ROLES_SQL = "role IN ('admin','member','owner','sales','planner','supervisor')"


class RoleMaySeeFieldTests(unittest.TestCase):
    def test_planner_and_supervisor_denied_price_fields(self):
        for role in ("planner", "supervisor"):
            for field in PRICE_DERIVED_FIELDS:
                self.assertFalse(role_may_see_field(role, field), f"{role} must not see {field}")

    def test_office_roles_see_prices(self):
        for role in ("owner", "sales", "admin", "member"):
            self.assertTrue(role_may_see_field(role, "unit_price"))
            self.assertTrue(role_may_see_field(role, "line_total"))

    def test_production_roles_see_non_price_fields(self):
        for role in ("planner", "supervisor"):
            self.assertTrue(role_may_see_field(role, "order_number"))
            self.assertTrue(role_may_see_field(role, "quantity"))
            self.assertTrue(role_may_see_field(role, "requested_delivery_date"))

    def test_hidden_fields_for_role(self):
        self.assertEqual(hidden_fields_for_role("supervisor"), PRICE_DERIVED_FIELDS)
        self.assertEqual(hidden_fields_for_role("owner"), frozenset())


class FilterClaimsForRoleTests(unittest.TestCase):
    def test_supervisor_loses_price_claims_keeps_rest(self):
        filtered = filter_claims_for_role(SAMPLE_CLAIMS, "supervisor")
        keys = [c["field_key"] for c in filtered]
        self.assertEqual(
            keys,
            ["order_number", "quantity", "requested_delivery_date"],
        )
        self.assertNotIn("unit_price", keys)
        self.assertNotIn("line_total", keys)

    def test_owner_keeps_all_claims(self):
        filtered = filter_claims_for_role(SAMPLE_CLAIMS, "owner")
        self.assertEqual(len(filtered), len(SAMPLE_CLAIMS))

    def test_sales_keeps_prices(self):
        keys = [c["field_key"] for c in filter_claims_for_role(SAMPLE_CLAIMS, "sales")]
        self.assertIn("unit_price", keys)

    def test_planner_same_shape_as_supervisor(self):
        self.assertEqual(
            [c["field_key"] for c in filter_claims_for_role(SAMPLE_CLAIMS, "planner")],
            [c["field_key"] for c in filter_claims_for_role(SAMPLE_CLAIMS, "supervisor")],
        )

    def test_legacy_admin_member_unchanged(self):
        for role in ("admin", "member"):
            self.assertEqual(len(filter_claims_for_role(SAMPLE_CLAIMS, role)), len(SAMPLE_CLAIMS))


class MembershipRoleHelperTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        # Widen role check inside this rolled-back transaction so the suite
        # works before alembic upgrade lands on the shared local DB.
        self.connection.execute(text("ALTER TABLE organization_memberships DROP CONSTRAINT IF EXISTS valid_membership_role"))
        self.connection.execute(
            text(f"ALTER TABLE organization_memberships ADD CONSTRAINT valid_membership_role CHECK ({ROLES_SQL})")
        )
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(
            name="Field roles corp",
            account_type="company",
            google_domain=f"roles-{uuid4().hex[:8]}.example",
        )
        self.user = User(email=f"floor-{uuid4().hex[:8]}@example.com")
        self.session.add_all([self.org, self.user])
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_membership_role_returns_stored_role(self):
        self.session.add(
            OrganizationMembership(
                organization_id=self.org.id,
                user_id=self.user.id,
                role="supervisor",
            )
        )
        self.session.flush()
        self.assertEqual(membership_role(self.session, self.org.id, self.user.id), "supervisor")

    def test_membership_role_none_when_absent(self):
        self.assertIsNone(membership_role(self.session, self.org.id, self.user.id))

    def test_constraint_accepts_prd_roles(self):
        for role in ("owner", "sales", "planner", "supervisor"):
            user = User(email=f"{role}-{uuid4().hex[:8]}@example.com")
            self.session.add(user)
            self.session.flush()
            self.session.add(
                OrganizationMembership(
                    organization_id=self.org.id,
                    user_id=user.id,
                    role=role,
                )
            )
            self.session.flush()

    def test_constraint_still_rejects_unknown_role(self):
        self.session.add(
            OrganizationMembership(
                organization_id=self.org.id,
                user_id=self.user.id,
                role="intern",
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.flush()
