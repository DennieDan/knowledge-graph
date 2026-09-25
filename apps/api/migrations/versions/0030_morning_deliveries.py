"""morning_deliveries table for email dry-run logging (#95)

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "morning_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("channel IN ('email','in_app')", name="valid_morning_delivery_channel"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_morning_deliveries_organization_id", "morning_deliveries", ["organization_id"])
    op.create_index("ix_morning_deliveries_user_id", "morning_deliveries", ["user_id"])
    op.create_index(
        "ix_morning_deliveries_org_user",
        "morning_deliveries",
        ["organization_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_morning_deliveries_org_user", table_name="morning_deliveries")
    op.drop_index("ix_morning_deliveries_user_id", table_name="morning_deliveries")
    op.drop_index("ix_morning_deliveries_organization_id", table_name="morning_deliveries")
    op.drop_table("morning_deliveries")
