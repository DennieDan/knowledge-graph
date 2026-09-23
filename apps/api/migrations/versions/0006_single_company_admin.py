"""single company admin

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_company_admin",
        "organization_memberships",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("role = 'admin'"),
    )


def downgrade() -> None:
    op.drop_index("uq_company_admin", table_name="organization_memberships")
