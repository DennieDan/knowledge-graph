"""unique company domain

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_company_google_domain",
        "organizations",
        ["google_domain"],
        unique=True,
        postgresql_where=sa.text("account_type = 'company'"),
    )


def downgrade() -> None:
    op.drop_index("uq_company_google_domain", table_name="organizations")
