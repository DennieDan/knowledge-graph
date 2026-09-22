import socket
from uuid import UUID

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .database import get_engine
from .embedding_jobs import embed_document_version
from .jobs import claim_job, fail_job, finish_job
from .knowledge_analysis import discover_document, generate_substack
from .models import Substack


def _transient(error: Exception) -> bool:
    try:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
        provider_errors = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
    except ImportError:
        provider_errors = ()
    return isinstance(error, (OperationalError, *provider_errors))


def run_one(worker_id: str | None = None) -> bool:
    identity = worker_id or socket.gethostname()
    with Session(get_engine()) as session:
        job = claim_job(session, identity)
    if job is None:
        return False
    try:
        with Session(get_engine()) as session:
            if job.kind == "embed_version":
                embed_document_version(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
            elif job.kind == "discover_document":
                discover_document(session, UUID(job.payload["document_version_id"]), job.analysis_run_id)
            elif job.kind == "generate_substack":
                generate_substack(session, UUID(job.payload["substack_id"]), job.analysis_run_id)
            else:
                raise ValueError(f"unsupported_job_kind:{job.kind}")
        with Session(get_engine()) as session:
            finish_job(session, job.id)
    except Exception as error:
        transient = _transient(error)
        with Session(get_engine()) as session:
            if job.kind == "generate_substack" and job.payload.get("substack_id") and (not transient or job.attempts >= job.max_attempts):
                substack = session.get(Substack, UUID(job.payload["substack_id"]))
                if substack is not None:
                    substack.review_state = "generation_error"
                    session.commit()
            fail_job(session, job.id, error, transient=transient)
    return True
