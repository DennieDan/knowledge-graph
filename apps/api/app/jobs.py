"""Durable Postgres-backed jobs for embedding and knowledge analysis."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AnalysisRun, KnowledgeJob


LEASE_SECONDS = 300
RETRY_DELAYS_SECONDS = (10, 30, 120, 600)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_job(
    session: Session,
    *,
    organization_id: UUID,
    owner_user_id: UUID | None,
    kind: str,
    payload: dict,
    dedupe_key: str,
    analysis_run_id: UUID | None = None,
    max_attempts: int = 4,
) -> KnowledgeJob:
    existing = session.scalar(select(KnowledgeJob).where(KnowledgeJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    job = KnowledgeJob(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        kind=kind,
        payload=payload,
        dedupe_key=dedupe_key,
        analysis_run_id=analysis_run_id,
        max_attempts=max_attempts,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(KnowledgeJob).where(KnowledgeJob.dedupe_key == dedupe_key))
        if existing is None:
            raise
        return existing
    return job


def create_run(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    trigger: str,
    *,
    documents_total: int = 0,
) -> AnalysisRun:
    run = AnalysisRun(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        trigger=trigger,
        documents_total=documents_total,
    )
    session.add(run)
    session.flush()
    return run


def claim_job(session: Session, worker_id: str) -> KnowledgeJob | None:
    now = utcnow()
    expired = now - timedelta(seconds=LEASE_SECONDS)
    job = session.scalar(
        select(KnowledgeJob)
        .where(
            or_(
                (KnowledgeJob.status == "queued") & (KnowledgeJob.available_at <= now),
                (KnowledgeJob.status == "running") & (KnowledgeJob.locked_at < expired),
            )
        )
        .order_by(KnowledgeJob.available_at, KnowledgeJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    session.commit()
    session.refresh(job)
    session.expunge(job)
    return job


def finish_job(session: Session, job_id: UUID) -> None:
    job = session.get(KnowledgeJob, job_id)
    if job is None:
        return
    job.status = "succeeded"
    job.locked_at = None
    job.locked_by = None
    job.last_error = None
    session.commit()


def fail_job(session: Session, job_id: UUID, error: Exception, *, transient: bool) -> None:
    job = session.get(KnowledgeJob, job_id)
    if job is None:
        return
    job.last_error = f"{type(error).__name__}: {error}"[:500]
    job.locked_at = None
    job.locked_by = None
    if transient and job.attempts < job.max_attempts:
        delay_index = min(job.attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)
        job.status = "queued"
        job.available_at = utcnow() + timedelta(seconds=RETRY_DELAYS_SECONDS[delay_index])
    else:
        job.status = "failed"
        if job.analysis_run_id:
            run = session.get(AnalysisRun, job.analysis_run_id)
            if run is not None:
                run.failures += 1
                run.status = "partial" if run.documents_processed else "failed"
                run.error_summary = job.last_error
                run.completed_at = utcnow()
    session.commit()


def retry_failed_run(session: Session, run: AnalysisRun) -> int:
    jobs = session.scalars(
        select(KnowledgeJob).where(
            KnowledgeJob.analysis_run_id == run.id,
            KnowledgeJob.status == "failed",
        )
    ).all()
    for job in jobs:
        job.status = "queued"
        job.attempts = 0
        job.available_at = utcnow()
        job.last_error = None
    if jobs:
        run.status = "queued"
        run.failures = 0
        run.error_summary = None
        run.completed_at = None
    session.flush()
    return len(jobs)
