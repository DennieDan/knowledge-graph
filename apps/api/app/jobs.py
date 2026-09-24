"""Durable Postgres-backed jobs for embedding and knowledge analysis."""
import heapq
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AnalysisRun, KnowledgeJob


LEASE_SECONDS = 300
RETRY_DELAYS_SECONDS = (10, 30, 120, 600)
RUN_JOB_KINDS = ("embed_version", "discover_document", "generate_substack", "reconcile_scope")
DURATION_SAMPLES = 20
DURATION_HISTORY_DAYS = 7
WORKER_WINDOW_SECONDS = 600
QUEUE_SCAN_LIMIT = 2000


class JobNotReady(Exception):
    """Raised by a job that must wait for other jobs in its run; the worker re-queues it."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def complete_run_if_last(session: Session, run_id: UUID | None) -> None:
    """Close the run when the calling (still running) job is the last one left."""
    run = session.get(AnalysisRun, run_id) if run_id else None
    if run is None:
        return
    remaining = session.scalar(select(func.count()).select_from(KnowledgeJob).where(
        KnowledgeJob.analysis_run_id == run.id,
        KnowledgeJob.kind.in_(RUN_JOB_KINDS),
        KnowledgeJob.status.in_(("queued", "running")),
    )) or 0
    if remaining <= 1:
        run.status = "completed" if run.failures == 0 else "partial"
        run.completed_at = utcnow()


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
    job.last_error = None
    session.commit()


def defer_job(session: Session, job_id: UUID, seconds: int = 5) -> None:
    job = session.get(KnowledgeJob, job_id)
    if job is None:
        return
    job.status = "queued"
    job.attempts = max(0, job.attempts - 1)
    job.available_at = utcnow() + timedelta(seconds=seconds)
    job.locked_at = None
    job.locked_by = None
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


def _median_durations(session: Session, now: datetime) -> dict[str, float]:
    """Median seconds per kind over each kind's most recent successful jobs."""
    recent = (
        select(
            KnowledgeJob.kind,
            func.extract("epoch", KnowledgeJob.updated_at - KnowledgeJob.locked_at).label("seconds"),
            func.row_number()
            .over(partition_by=KnowledgeJob.kind, order_by=KnowledgeJob.updated_at.desc())
            .label("rank"),
        )
        .where(
            KnowledgeJob.status == "succeeded",
            KnowledgeJob.locked_at.is_not(None),
            KnowledgeJob.updated_at >= now - timedelta(days=DURATION_HISTORY_DAYS),
        )
        .subquery()
    )
    return {
        kind: float(seconds)
        for kind, seconds in session.execute(
            select(recent.c.kind, func.percentile_cont(0.5).within_group(recent.c.seconds))
            .where(recent.c.rank <= DURATION_SAMPLES)
            .group_by(recent.c.kind)
        ).all()
    }


def simulate_finish(
    now: datetime, pending: list, durations: dict[str, float], workers: int, run_id: UUID,
) -> datetime | None:
    """Replays pending jobs (in claim order) on the workers: each lasts its kind's median
    duration, and a queued job never starts before its retry backoff ends."""
    default = durations.get("generate_substack")
    if default is None:
        return None
    running = [job for job in pending if job.status == "running"]
    workers = max(1, workers, len(running))
    finish: datetime | None = None
    free_at: list[datetime] = []
    for job in running:
        end = max(now, job.locked_at + timedelta(seconds=durations.get(job.kind, default)))
        heapq.heappush(free_at, end)
        if job.analysis_run_id == run_id:
            finish = max(finish or end, end)
    free_at += [now] * (workers - len(free_at))
    heapq.heapify(free_at)
    for job in pending:
        if job.status != "queued":
            continue
        end = max(heapq.heappop(free_at), job.available_at) + timedelta(seconds=durations.get(job.kind, default))
        heapq.heappush(free_at, end)
        if job.analysis_run_id == run_id:
            finish = max(finish or end, end)
    return finish


def estimate_run_finish(session: Session, run_id: UUID) -> datetime | None:
    now = utcnow()
    pending = session.execute(
        select(
            KnowledgeJob.analysis_run_id,
            KnowledgeJob.kind,
            KnowledgeJob.status,
            KnowledgeJob.available_at,
            KnowledgeJob.locked_at,
        )
        .where(KnowledgeJob.status.in_(("queued", "running")))
        .order_by(KnowledgeJob.available_at, KnowledgeJob.created_at)
        .limit(QUEUE_SCAN_LIMIT)
    ).all()
    if len(pending) == QUEUE_SCAN_LIMIT:
        return None
    workers = session.scalar(
        select(func.count(func.distinct(KnowledgeJob.locked_by))).where(
            KnowledgeJob.locked_by.is_not(None),
            KnowledgeJob.updated_at >= now - timedelta(seconds=WORKER_WINDOW_SECONDS),
        )
    ) or 0
    return simulate_finish(now, list(pending), _median_durations(session, now), workers, run_id)
