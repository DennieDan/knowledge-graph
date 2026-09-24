"""findings table + run_checks job kind (#15)

Revision ID: 0015
Revises: 0014

Stacked after #74 (0014_confirmation_attribution). PRs #70/#72/#74 own 0012-0014.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


JOB_KINDS_BEFORE = ("embed_version", "discover_document", "generate_substack", "reconcile_scope")
JOB_KINDS_AFTER = JOB_KINDS_BEFORE + ("run_checks",)


def _kind_constraint(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ",".join(f"'{k}'" for k in kinds) + ")"


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("check_key", sa.String(length=80), nullable=False),
        sa.Column("subject_kind", sa.String(length=50), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("observed_value", sa.Text(), nullable=True),
        sa.Column("threshold_value", sa.Text(), nullable=True),
        sa.Column("summary_sentence", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("detector_version", sa.String(length=50), server_default="checks-v1", nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.String(length=40), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('dismissed','acted','confirmed')",
            name="valid_finding_decision",
        ),
        sa.CheckConstraint(
            "dismissal_reason IS NULL OR dismissal_reason IN ("
            "'not_a_change','already_handled','source_is_wrong','duplicate','other_recorded_below')",
            name="valid_finding_dismissal_reason",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("ix_findings_organization_id", "findings", ["organization_id"])
    op.create_index("ix_findings_owner_user_id", "findings", ["owner_user_id"])
    op.create_index("ix_findings_check_key", "findings", ["organization_id", "check_key"])
    op.create_index(
        "ix_findings_open",
        "findings",
        ["organization_id", "detected_at"],
        postgresql_where=sa.text("decision IS NULL"),
    )

    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint("valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_AFTER))


def downgrade() -> None:
    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint("valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_BEFORE))
    op.drop_index("ix_findings_open", table_name="findings")
    op.drop_table("findings")
