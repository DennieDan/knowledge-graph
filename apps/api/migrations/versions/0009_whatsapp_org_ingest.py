"""whatsapp org ingest

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_chats", sa.Column("organization_id", sa.Uuid(), nullable=True))
    op.add_column("whatsapp_chats", sa.Column("pending_ingest", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_foreign_key("fk_whatsapp_chats_organization", "whatsapp_chats", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_whatsapp_chats_organization_id", "whatsapp_chats", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_chats_organization_id", table_name="whatsapp_chats")
    op.drop_constraint("fk_whatsapp_chats_organization", "whatsapp_chats", type_="foreignkey")
    op.drop_column("whatsapp_chats", "pending_ingest")
    op.drop_column("whatsapp_chats", "organization_id")
