"""optional reason on chat message feedback (#94)

Revision ID: 0016
Revises: 0015

Additive column for thumbs-up/down reasons. If another branch already claimed
0016 before this lands, rebase and renumber (e.g. 0020) rather than rewriting.
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("feedback_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "feedback_reason")
