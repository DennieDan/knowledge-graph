import socket
from uuid import UUID

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .checks import run_all_checks
from .database import get_engine
from .embedding_jobs import embed_document_version
from .jobs import claim_job, fail_job, finish_job
from .knowledge_analysis import discover_document, generate_substack
from .models import KnowledgeJob, Substack

# Scheduled kinds never retry into the next run; a miss is recorded as a failed job.
SCHEDULED_KINDS = ("run_checks",)


def _transient(error: Exception) -> bool:
    provider_errors: tuple[type[Exception], ...] = ()
    try:
        provider_errors = (__import__("openai").APIConnectionError, __import__("openai").RateLimitError)
    except (ImportError, AttributeError):
        pass
    return isinstance(error, (OperationalError, *provider_errors))


def _dispatch(session: Session, job: KnowledgeJob) -> None:
    if job.kind == "embed_version":
        embed_document_version(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
    elif job.kind == "discover_document":
        discover_document(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
    elif job.kind == "generate_substack":
        generate_substack(session, UUID(job.payload["substack_id"]), job.analysis_run_id)
    elif job.kind == "run_checks":
        run_all_checks(session, job.organization_id)
    else:
        raise ValueError(f"unsupported_job_kind:{job.kind}")


def run_one(worker_id: str | None = None) -> bool:
    identity = worker_id or socket.gethostname()
    with Session(get_engine()) as session:
        job = claim_job(session, identity)
    if job is None:
        return False
    try:
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
