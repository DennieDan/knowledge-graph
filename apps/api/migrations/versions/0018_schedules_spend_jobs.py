"""schedules, spend, source failure columns, job observability (#31)

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


JOB_KINDS_BEFORE = ("embed_version", "discover_document", "generate_substack", "reconcile_scope", "run_checks")
JOB_KINDS_AFTER = JOB_KINDS_BEFORE + ("sync_workspace", "whatsapp_ingest")
JOB_STATUSES_BEFORE = ("queued", "running", "succeeded", "failed", "cancelled")
JOB_STATUSES_AFTER = JOB_STATUSES_BEFORE + ("budget_exhausted",)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


def _set_job_constraints(kinds: tuple[str, ...], statuses: tuple[str, ...]) -> None:
    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.drop_constraint("valid_knowledge_job_status", "knowledge_jobs", type_="check")
    op.create_check_constraint("valid_knowledge_job_kind", "knowledge_jobs", _in("kind", kinds))
    op.create_check_constraint("valid_knowledge_job_status", "knowledge_jobs", _in("status", statuses))


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("daily_token_budget", sa.Integer(), server_default="500000", nullable=False),
    )

    for table in ("drive_workspaces", "whatsapp_chats"):
        op.add_column(table, sa.Column("last_error", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))

    _set_job_constraints(JOB_KINDS_AFTER, JOB_STATUSES_AFTER)

    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("cron", sa.String(length=80), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "organization_id", name="uq_schedule_key_org"),
    )
    op.create_index("ix_schedules_next_run", "schedules", ["enabled", "next_run_at"])

    op.create_table(
        "spend",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "day", name="uq_spend_org_day"),
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW job_failures AS
        SELECT id, organization_id, owner_user_id, kind, status, attempts, max_attempts,
               last_error, created_at, updated_at, payload
        FROM knowledge_jobs
        WHERE status = 'failed'
           OR status = 'budget_exhausted'
           OR (last_error IS NOT NULL AND status IN ('queued', 'running'))
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS job_failures")
    op.drop_table("spend")
    op.drop_index("ix_schedules_next_run", table_name="schedules")
    op.drop_table("schedules")
    _set_job_constraints(JOB_KINDS_BEFORE, JOB_STATUSES_BEFORE)
    for table in ("whatsapp_chats", "drive_workspaces"):
        op.drop_column(table, "last_success_at")
        op.drop_column(table, "last_error_at")
        op.drop_column(table, "last_error")
    op.drop_column("organizations", "daily_token_budget")
