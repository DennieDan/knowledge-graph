import socket
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .checks import run_all_checks
from .database import get_engine
from .embedding_jobs import embed_document_version
from .findings import create_finding
from .jobs import claim_job, fail_job, finish_job, park_budget_exhausted
from .knowledge_analysis import discover_document, generate_substack
from .models import DriveConnection, DriveWorkspace, DriveWorkspaceConnection, KnowledgeJob, Substack, User
from .scoring import run_score_job
from .spend import budget_exhausted

# Tolerances (#31 step 3).
# Prompt and idempotent, retried 4x with backoff: embed_version, sync_workspace, whatsapp_ingest.
# Batchable, retried 4x then marked generation_error: discover_document, generate_substack.
# Scheduled and skippable, never retried into the next night: run_checks, score_questions.
SCHEDULED_KINDS = ("run_checks", "score_questions")
# Kinds that call a model check the daily token budget before running.
BUDGETED_KINDS = ("generate_substack", "score_questions")


def _transient(error: Exception) -> bool:
    provider_errors: tuple[type[Exception], ...] = ()
    try:
        provider_errors = (__import__("openai").APIConnectionError, __import__("openai").RateLimitError)
    except (ImportError, AttributeError):
        pass
    return isinstance(error, (OperationalError, *provider_errors))


def _record_sync_failure(workspace_id: UUID, organization_id: UUID, owner_user_id: UUID | None, error: Exception) -> None:
    """Use a fresh session so a failed sync transaction cannot mask the error."""
    with Session(get_engine()) as session:
        workspace = session.get(DriveWorkspace, workspace_id)
        if workspace is not None:
            workspace.last_error = f"{type(error).__name__}: {error}"[:500]
            workspace.last_error_at = datetime.now(timezone.utc)
        create_finding(
            session,
            organization_id=organization_id,
            check_key="source_failed",
            subject_kind="drive_workspace",
            subject_id=workspace_id,
            summary_sentence="A Drive sync failed.",
            observed_value=type(error).__name__,
            evidence={"error_class": type(error).__name__, "detail": str(error)[:200]},
            owner_user_id=owner_user_id,
        )
        session.commit()


def _handle_sync_workspace(session: Session, job: KnowledgeJob) -> None:
    from .drive_sync import sync_workspace

    workspace_id = UUID(job.payload["workspace_id"])
    workspace = session.get(DriveWorkspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace_not_found")
    link = session.scalar(
        select(DriveWorkspaceConnection).where(DriveWorkspaceConnection.workspace_id == workspace.id)
    )
    if link is None:
        raise ValueError("workspace_connection_missing")
    connection = session.get(DriveConnection, link.connection_id)
    if connection is None:
        raise ValueError("drive_connection_missing")
    user = session.get(User, connection.user_id)
    if user is None:
        raise ValueError("drive_user_missing")
    try:
        sync_workspace(session, workspace, connection, user)
        workspace.last_success_at = datetime.now(timezone.utc)
        workspace.last_error = None
        workspace.last_error_at = None
        session.commit()
    except Exception as error:
        session.rollback()
        _record_sync_failure(workspace_id, job.organization_id, workspace.owner_user_id, error)
        raise


def _handle_whatsapp_ingest(session: Session, job: KnowledgeJob) -> None:
    from .models import WhatsappChat, WhatsappConnection
    from .whatsapp import ingest_chat_transcript

    chat_id = UUID(job.payload["chat_id"])
    chat = session.get(WhatsappChat, chat_id)
    if chat is None:
        raise ValueError("chat_not_found")
    if not chat.pending_ingest and job.payload.get("force") is not True:
        return
    conn = session.get(WhatsappConnection, chat.connection_id)
    chat.pending_ingest = False
    if conn is None:
        raise ValueError("whatsapp_connection_missing")
    try:
        if chat.import_status == "imported":
            ingest_chat_transcript(session, conn, chat)
        chat.last_success_at = datetime.now(timezone.utc)
        chat.last_error = None
        chat.last_error_at = None
        session.commit()
    except Exception as error:
        session.rollback()
        chat = session.get(WhatsappChat, chat_id)
        if chat is not None:
            chat.last_error = f"{type(error).__name__}: {error}"[:500]
            chat.last_error_at = datetime.now(timezone.utc)
            session.commit()
        raise


def _dispatch(session: Session, job: KnowledgeJob) -> None:
    if job.kind == "embed_version":
        embed_document_version(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
    elif job.kind == "discover_document":
        discover_document(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
    elif job.kind == "generate_substack":
        generate_substack(session, UUID(job.payload["substack_id"]), job.analysis_run_id)
    elif job.kind == "sync_workspace":
        _handle_sync_workspace(session, job)
    elif job.kind == "whatsapp_ingest":
        _handle_whatsapp_ingest(session, job)
    elif job.kind == "run_checks":
        run_all_checks(session, job.organization_id)
    elif job.kind == "score_questions":
        run_score_job(session, job.organization_id)
    else:
        raise ValueError(f"unsupported_job_kind:{job.kind}")


def run_one(worker_id: str | None = None) -> bool:
    identity = worker_id or socket.gethostname()
    with Session(get_engine()) as session:
        job = claim_job(session, identity)
    if job is None:
        return False
    try:
        if job.kind in BUDGETED_KINDS:
            with Session(get_engine()) as session:
                if budget_exhausted(session, job.organization_id):
                    park_budget_exhausted(session, job.id)
                    return True
        with Session(get_engine()) as session:
            _dispatch(session, job)
        with Session(get_engine()) as session:
            finish_job(session, job.id)
    except Exception as error:
        transient = _transient(error) and job.kind not in SCHEDULED_KINDS
        with Session(get_engine()) as session:
            if job.kind == "generate_substack" and job.payload.get("substack_id") and (not transient or job.attempts >= job.max_attempts):
                substack = session.get(Substack, UUID(job.payload["substack_id"]))
                if substack is not None:
                    substack.review_state = "generation_error"
                    session.commit()
            fail_job(session, job.id, error, transient=transient)
    return True
