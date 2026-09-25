"""connector_keys: one named, revocable, read-only key per AI assistant (#94)

Revision ID: 0030
Revises: 0029

Additive only. The assistant connector (MCP, app/connector.py) authenticates
with these keys. Only the SHA-256 of each key is stored.
"""
from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_connector_keys_organization_id", "connector_keys", ["organization_id"])
    op.create_index("ix_connector_keys_user_id", "connector_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_connector_keys_user_id", table_name="connector_keys")
    op.drop_index("ix_connector_keys_organization_id", table_name="connector_keys")
    op.drop_table("connector_keys")
