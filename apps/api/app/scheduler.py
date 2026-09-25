"""Enqueue due schedule rows onto the knowledge_jobs queue."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .jobs import enqueue_job
from .models import DriveWorkspace, Organization, Schedule

# cron field is documentary; tick logic uses key + interval below.
DEFAULT_SCHEDULES = (
    ("drive_sync", "*/15 * * * *", timedelta(minutes=15)),
    ("run_checks", "0 2 * * *", timedelta(hours=24)),
    ("score_questions", "0 3 * * *", timedelta(hours=24)),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_default_schedules(session: Session, organization_id: UUID) -> None:
    for key, cron, _ in DEFAULT_SCHEDULES:
        existing = session.scalar(
            select(Schedule).where(
                Schedule.key == key,
                Schedule.organization_id == organization_id,
            )
        )
        if existing is None:
            session.add(
                Schedule(
                    key=key,
                    cron=cron,
                    organization_id=organization_id,
                    enabled=True,
                    next_run_at=utcnow(),
                )
            )
    session.flush()


def _interval_for(key: str) -> timedelta:
    for schedule_key, _, interval in DEFAULT_SCHEDULES:
        if schedule_key == key:
            return interval
    return timedelta(hours=24)


def _enqueue_for_schedule(session: Session, schedule: Schedule) -> int:
    if schedule.organization_id is None:
        return 0
    org_id = schedule.organization_id
    day = utcnow().date().isoformat()
    enqueued = 0
    if schedule.key == "drive_sync":
        workspaces = session.scalars(
            select(DriveWorkspace).where(
                DriveWorkspace.organization_id == org_id,
                DriveWorkspace.status == "active",
            )
        ).all()
        for workspace in workspaces:
            enqueue_job(
                session,
                organization_id=org_id,
                owner_user_id=workspace.owner_user_id,
                kind="sync_workspace",
                payload={"workspace_id": str(workspace.id)},
                dedupe_key=f"sync_workspace:{workspace.id}:{day}:{utcnow().hour}:{utcnow().minute // 15}",
            )
            enqueued += 1
    elif schedule.key == "run_checks":
        enqueue_job(
            session,
            organization_id=org_id,
            owner_user_id=None,
            kind="run_checks",
            payload={},
            dedupe_key=f"run_checks:{org_id}:{day}",
            max_attempts=1,
        )
        enqueued += 1
    elif schedule.key == "score_questions":
        enqueue_job(
            session,
            organization_id=org_id,
            owner_user_id=None,
            kind="score_questions",
            payload={},
            dedupe_key=f"score_questions:{org_id}:{day}",
            max_attempts=1,
        )
        enqueued += 1
    return enqueued


def tick(session: Session) -> dict:
    """Enqueue jobs for every due enabled schedule. Returns counts."""
    now = utcnow()
    for org in session.scalars(select(Organization)).all():
        ensure_default_schedules(session, org.id)

    due = session.scalars(
        select(Schedule).where(
            Schedule.enabled.is_(True),
            or_(Schedule.next_run_at.is_(None), Schedule.next_run_at <= now),
        )
    ).all()
    enqueued = 0
    for schedule in due:
        enqueued += _enqueue_for_schedule(session, schedule)
        schedule.last_run_at = now
        schedule.next_run_at = now + _interval_for(schedule.key)
    session.commit()
    return {"schedules_fired": len(due), "jobs_enqueued": enqueued}
