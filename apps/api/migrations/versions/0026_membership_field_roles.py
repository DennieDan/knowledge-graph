"""Extend membership roles for field-level access (#101).

Revision ID: 0026
Revises: 0025

Additive only: keeps admin|member (issue #9 / main) and adds
owner|sales|planner|supervisor from the Rows to Records PRD.
Does not remove the older vocabulary; callers migrate later.
No RLS in this revision — app-layer filter ships first.

Note: PR #108 (#92) also proposes revision 0016 from 0015. Whichever
merges second must rebase its migration number.
"""
from alembic import op


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

ROLES_BEFORE = ("admin", "member")
ROLES_AFTER = ("admin", "member", "owner", "sales", "planner", "supervisor")


def _role_constraint(roles: tuple[str, ...]) -> str:
    return "role IN (" + ",".join(f"'{r}'" for r in roles) + ")"


def upgrade() -> None:
    op.drop_constraint("valid_membership_role", "organization_memberships", type_="check")
    op.create_check_constraint(
        "valid_membership_role",
        "organization_memberships",
        _role_constraint(ROLES_AFTER),
    )


def downgrade() -> None:
    op.drop_constraint("valid_membership_role", "organization_memberships", type_="check")
    op.create_check_constraint(
        "valid_membership_role",
        "organization_memberships",
        _role_constraint(ROLES_BEFORE),
    )
