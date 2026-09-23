"""Findings queue (#15) and job observability (#31) endpoints. Health (#21) joins later."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .findings import dismiss_finding
from .models import DISMISSAL_REASONS, Finding, KnowledgeJob, User

router = APIRouter(tags=["health"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DismissBody(BaseModel):
    reason: str


@router.get("/accounts/{organization_id}/findings")
def list_findings(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Open findings the caller may see: org-wide ones plus their own owner-only ones."""
    membership_for(organization_id, user, session)
    rows = session.scalars(
        select(Finding)
        .where(
            Finding.organization_id == organization_id,
            Finding.decision.is_(None),
            or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == user.id),
        )
        .order_by(Finding.detected_at.desc())
        .limit(100)
    ).all()
    return {
        "findings": [
            {
                "id": str(f.id),
                "check_key": f.check_key,
                "summary_sentence": f.summary_sentence,
                "detected_at": f.detected_at.isoformat(),
                "subject_kind": f.subject_kind,
                "subject_id": str(f.subject_id),
            }
            for f in rows
        ],
        "dismissal_reasons": list(DISMISSAL_REASONS),
    }


@router.post("/accounts/{organization_id}/findings/{finding_id}/dismiss")
def dismiss(
    organization_id: UUID,
    finding_id: UUID,
    body: DismissBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    finding = session.get(Finding, finding_id)
    if finding is None or finding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="finding_not_found")
    try:
        dismiss_finding(session, finding, user_id=user.id, reason=body.reason)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    session.commit()
    return {"id": str(finding.id), "decision": finding.decision, "dismissal_reason": finding.dismissal_reason}


@router.get("/accounts/{organization_id}/jobs")
def get_jobs(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Queue depth, oldest queued age, failures in the last 24h, counts per kind and status."""
    membership_for(organization_id, user, session)
    now = utcnow()
    queued = session.scalars(
        select(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status == "queued",
        )
    ).all()
    oldest_age = None
    if queued:
        oldest = min(job.created_at for job in queued)
        oldest_age = int((now - oldest).total_seconds())
    failures = session.scalar(
        select(func.count()).select_from(KnowledgeJob).where(
            KnowledgeJob.organization_id == organization_id,
            KnowledgeJob.status == "failed",
            KnowledgeJob.updated_at >= now - timedelta(hours=24),
        )
    ) or 0
    by_kind = session.execute(
        select(KnowledgeJob.kind, KnowledgeJob.status, func.count())
        .where(KnowledgeJob.organization_id == organization_id)
        .group_by(KnowledgeJob.kind, KnowledgeJob.status)
    ).all()
    return {
        "queue_depth": len(queued),
        "oldest_queued_age_seconds": oldest_age,
        "failures_last_24h": failures,
        "by_kind_status": [
            {"kind": kind, "status": status, "count": count}
            for kind, status, count in by_kind
        ],
    }
