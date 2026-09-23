"""test_runs + test_results, score_questions job kind (#19)

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


JOB_KINDS_BEFORE = (
    "embed_version", "discover_document", "generate_substack", "reconcile_scope",
    "run_checks", "sync_workspace", "whatsapp_ingest",
)
JOB_KINDS_AFTER = JOB_KINDS_BEFORE + ("score_questions",)


def _kind_constraint(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ",".join(f"'{k}'" for k in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("git_sha", sa.String(length=64), nullable=True),
        sa.Column("prompt_versions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("kind IN ('retrieval','answer')", name="valid_test_run_kind"),
        sa.CheckConstraint("status IN ('running','passed','failed','skipped')", name="valid_test_run_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_runs_organization_id", "test_runs", ["organization_id", "started_at"])

    op.create_table(
        "test_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("rank_of_first_expected", sa.Integer(), nullable=True),
        sa.Column("recall_at_5", sa.Float(), nullable=True),
        sa.Column("recall_at_20", sa.Float(), nullable=True),
        sa.Column("cited_expected", sa.Boolean(), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["test_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "question_id", name="uq_test_result_run_question"),
    )

    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint("valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_AFTER))


def downgrade() -> None:
    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint("valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_BEFORE))
    op.drop_table("test_results")
    op.drop_index("ix_test_runs_organization_id", table_name="test_runs")
    op.drop_table("test_runs")
