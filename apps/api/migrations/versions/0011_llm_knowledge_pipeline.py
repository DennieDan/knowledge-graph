"""durable LLM knowledge pipeline

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("trigger", sa.String(length=20), server_default="ingest", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("documents_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documents_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_embedded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidates_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("substacks_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("substacks_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("config_version", sa.String(length=50), server_default="core-v1", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("trigger IN ('ingest','manual','retry','backfill')", name="valid_analysis_trigger"),
        sa.CheckConstraint("status IN ('queued','embedding','discovering','generating','completed','partial','failed')", name="valid_analysis_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_organization_id", "analysis_runs", ["organization_id"])
    op.create_index("ix_analysis_runs_owner_user_id", "analysis_runs", ["owner_user_id"])

    op.create_table(
        "knowledge_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="4", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('embed_version','discover_document','generate_substack','reconcile_scope')", name="valid_knowledge_job_kind"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="valid_knowledge_job_status"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_knowledge_jobs_analysis_run_id", "knowledge_jobs", ["analysis_run_id"])
    op.create_index("ix_knowledge_jobs_organization_id", "knowledge_jobs", ["organization_id"])
    op.create_index("ix_knowledge_jobs_owner_user_id", "knowledge_jobs", ["owner_user_id"])
    op.create_index("ix_knowledge_jobs_available", "knowledge_jobs", ["status", "available_at"])

    op.add_column("substacks", sa.Column("review_state", sa.String(length=30), server_default="clean", nullable=False))
    op.add_column("substacks", sa.Column("identity_key", sa.Text(), nullable=True))
    op.add_column("substacks", sa.Column("identity_kind", sa.String(length=50), nullable=True))
    op.add_column("substacks", sa.Column("last_analysis_run_id", sa.Uuid(), nullable=True))
    op.create_check_constraint("valid_substack_review_state", "substacks", "review_state IN ('clean','pending','pending_update','unsupported','generation_error')")
    op.create_foreign_key("fk_substacks_last_analysis_run", "substacks", "analysis_runs", ["last_analysis_run_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_substacks_last_analysis_run_id", "substacks", ["last_analysis_run_id"])
    op.create_index("uq_shared_substack_identity", "substacks", ["organization_id", "stack_type", "identity_key"], unique=True, postgresql_where=sa.text("owner_user_id IS NULL AND identity_key IS NOT NULL"))
    op.create_index("uq_private_substack_identity", "substacks", ["organization_id", "owner_user_id", "stack_type", "identity_key"], unique=True, postgresql_where=sa.text("owner_user_id IS NOT NULL AND identity_key IS NOT NULL"))

    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("identity_key", sa.Text(), nullable=True),
        sa.Column("identity_kind", sa.String(length=50), nullable=True),
        sa.Column("candidate_key", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cited_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("substack_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_key", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="current", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("entity_type IN ('sales-orders','clients','items')", name="valid_entity_mention_type"),
        sa.CheckConstraint("status IN ('current','superseded')", name="valid_entity_mention_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["substack_id"], ["substacks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_version_id", "candidate_key"),
    )
    for column in ("organization_id", "owner_user_id", "document_id", "document_version_id", "substack_id"):
        op.create_index(f"ix_entity_mentions_{column}", "entity_mentions", [column])

    op.drop_constraint("valid_content_status", "substack_contents", type_="check")
    op.create_check_constraint("valid_content_status", "substack_contents", "status IN ('proposed','confirmed','superseded','stale','unsupported')")
    op.add_column("generation_runs", sa.Column("input_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("generation_runs", sa.Column("retrieval_version", sa.String(length=50), nullable=True))
    op.add_column("generation_runs", sa.Column("provider_request_id", sa.String(length=255), nullable=True))
    op.add_column("generation_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("generation_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("output_tokens", "input_tokens", "provider_request_id", "retrieval_version", "input_fingerprint"):
        op.drop_column("generation_runs", column)
    op.drop_constraint("valid_content_status", "substack_contents", type_="check")
    op.create_check_constraint("valid_content_status", "substack_contents", "status IN ('proposed','confirmed','stale')")
    op.drop_table("entity_mentions")
    op.drop_index("uq_private_substack_identity", table_name="substacks")
    op.drop_index("uq_shared_substack_identity", table_name="substacks")
    op.drop_index("ix_substacks_last_analysis_run_id", table_name="substacks")
    op.drop_constraint("fk_substacks_last_analysis_run", "substacks", type_="foreignkey")
    op.drop_constraint("valid_substack_review_state", "substacks", type_="check")
    op.drop_column("substacks", "last_analysis_run_id")
    op.drop_column("substacks", "identity_kind")
    op.drop_column("substacks", "identity_key")
    op.drop_column("substacks", "review_state")
    op.drop_table("knowledge_jobs")
    op.drop_table("analysis_runs")
