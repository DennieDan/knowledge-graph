"""Add propose_version knowledge job kind (#92 Steps 3–4)

Revision ID: 0025
Revises: 0024

After a new document version is ingested, the worker runs propose_from so every
proposed field carries a verbatim quote. Extends the job-kind check only.
"""
from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


JOB_KINDS_BEFORE = (
    "embed_version",
    "discover_document",
    "generate_substack",
    "reconcile_scope",
    "run_checks",
    "sync_workspace",
    "whatsapp_ingest",
    "score_questions",
    "run_recheck",
)
JOB_KINDS_AFTER = JOB_KINDS_BEFORE + ("propose_version",)


def _kind_constraint(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ",".join(f"'{k}'" for k in kinds) + ")"


def upgrade() -> None:
    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint(
        "valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("valid_knowledge_job_kind", "knowledge_jobs", type_="check")
    op.create_check_constraint(
        "valid_knowledge_job_kind", "knowledge_jobs", _kind_constraint(JOB_KINDS_BEFORE)
    )
