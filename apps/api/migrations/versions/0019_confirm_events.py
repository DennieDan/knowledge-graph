"""confirm_events: person / bulk / auto confirms as their own event type (#21)

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "confirm_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("by_user_id", sa.Uuid(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('person','bulk','auto')", name="valid_confirm_event_kind"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["substack_contents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_confirm_events_organization_id", "confirm_events", ["organization_id"])
    op.create_index("ix_confirm_events_at", "confirm_events", ["organization_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_confirm_events_at", table_name="confirm_events")
    op.drop_index("ix_confirm_events_organization_id", table_name="confirm_events")
    op.drop_table("confirm_events")
