"""run_recheck job kind for nightly confirmed-content re-check (#98)

Revision ID: 0020
Revises: 0019
"""
from alembic import op


revision = "0020"
down_revision = "0019"
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
)
JOB_KINDS_AFTER = JOB_KINDS_BEFORE + ("run_recheck",)


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
