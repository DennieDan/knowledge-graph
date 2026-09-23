"""record who confirmed content, and whether an answer is checked

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("substack_contents", sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("substack_contents", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_substack_contents_confirmed_by_user_id_users",
        "substack_contents",
        "users",
        ["confirmed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Content confirmed before this migration keeps a NULL person: it is not
    # known to have been checked by anyone, which is what NULL already means.
    op.execute(
        "UPDATE substack_contents SET confirmed_at = created_at WHERE status = 'confirmed'"
    )
    op.add_column("chat_messages", sa.Column("checked", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "checked")
    op.drop_constraint("fk_substack_contents_confirmed_by_user_id_users", "substack_contents", type_="foreignkey")
    op.drop_column("substack_contents", "confirmed_at")
    op.drop_column("substack_contents", "confirmed_by_user_id")
