"""subscriptions table for Drive/Gmail/Graph push watches (#92 Step 1)

Revision ID: 0016
Revises: 0015

Stub only: no verified webhook domain yet. Drive polling in drive_sync.py stays
the live path; this table + renewal worker prepare for changes.watch later.
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_channel_id", sa.String(length=255), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["drive_connections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])
    op.create_index("ix_subscriptions_connection_id", "subscriptions", ["connection_id"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_subscriptions_expires_at", table_name="subscriptions")
    op.drop_index("ix_subscriptions_connection_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_organization_id", table_name="subscriptions")
    op.drop_table("subscriptions")
