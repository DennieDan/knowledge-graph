"""chat threads and messages

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_threads_organization_id", "chat_threads", ["organization_id"])
    op.create_index("ix_chat_threads_user_id", "chat_threads", ["user_id"])
    op.create_index("ix_chat_threads_org_user", "chat_threads", ["organization_id", "user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("resolved_question", sa.Text(), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("retrieval_version", sa.String(length=50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="valid_chat_message_role"),
        sa.CheckConstraint("feedback IN ('up','down')", name="valid_chat_feedback"),
        sa.CheckConstraint("role = 'assistant' OR feedback IS NULL", name="feedback_on_assistant_only"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])
    op.create_index("ix_chat_messages_thread_created", "chat_messages", ["thread_id", "created_at"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_threads")
