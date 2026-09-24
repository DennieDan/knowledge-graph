"""stacks: substacks, generated contents, citations

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

STACK_TYPES = (
    "sales-orders", "clients", "items", "invoices", "suppliers",
    "supplier-orders", "production-jobs", "specifications",
    "conversations", "pics", "meetings", "files",
)


def upgrade() -> None:
    op.create_table(
        "substacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("stack_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.String(length=10), server_default="system", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('proposed','confirmed')", name="valid_substack_status"),
        sa.CheckConstraint("created_by IN ('system','user')", name="valid_substack_created_by"),
        sa.CheckConstraint(
            "stack_type IN (" + ",".join(f"'{t}'" for t in STACK_TYPES) + ")",
            name="valid_stack_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_substacks_organization_id", "substacks", ["organization_id"])
    op.create_index("ix_substacks_owner_user_id", "substacks", ["owner_user_id"])

    op.create_table(
        "substack_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="evidence", nullable=False),
        sa.CheckConstraint("role IN ('evidence','attachment')", name="valid_substack_source_role"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("substack_id", "document_id"),
    )
    op.create_index("ix_substack_sources_substack_id", "substack_sources", ["substack_id"])
    op.create_index("ix_substack_sources_document_id", "substack_sources", ["document_id"])

    op.create_table(
        "substack_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=False),
        sa.Column("related_substack_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["related_substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("substack_id", "related_substack_id"),
    )
    op.create_index("ix_substack_links_substack_id", "substack_links", ["substack_id"])
    op.create_index("ix_substack_links_related_substack_id", "substack_links", ["related_substack_id"])

    op.create_table(
        "substack_contents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("prompt_key", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("inputs_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("revision > 0", name="positive_content_revision"),
        sa.CheckConstraint("status IN ('proposed','confirmed','stale')", name="valid_content_status"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("substack_id", "revision"),
    )
    op.create_index("ix_substack_contents_substack_id", "substack_contents", ["substack_id"])

    op.create_table(
        "content_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["substack_contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_citations_content_id", "content_citations", ["content_id"])
    op.create_index("ix_content_citations_document_id", "content_citations", ["document_id"])

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_key", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("input_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="ok", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('ok','error')", name="valid_generation_run_status"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_runs_substack_id", "generation_runs", ["substack_id"])


def downgrade() -> None:
    op.drop_table("generation_runs")
    op.drop_table("content_citations")
    op.drop_table("substack_contents")
    op.drop_table("substack_links")
    op.drop_table("substack_sources")
    op.drop_table("substacks")
