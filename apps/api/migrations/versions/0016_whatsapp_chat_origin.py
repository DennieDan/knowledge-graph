"""whatsapp chat origin: live WAHA import vs uploaded chat export

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_chats", sa.Column("origin", sa.String(length=16), server_default="waha", nullable=False))
    op.create_check_constraint("valid_chat_origin", "whatsapp_chats", "origin IN ('waha','export')")


def downgrade() -> None:
    op.drop_constraint("valid_chat_origin", "whatsapp_chats", type_="check")
    op.drop_column("whatsapp_chats", "origin")
