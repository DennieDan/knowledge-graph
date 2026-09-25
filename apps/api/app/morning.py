"""Morning message (#95 / F-04): in-app digest + email dry-run over open findings.

Built over the findings list API until the review queue (#113) lands on main.
Permission filter matches ``GET /accounts/{org}/findings``: org-wide findings
plus the caller's own owner-only ones. A revoked / non-member user never reaches
this code (membership_for 404s at the endpoint).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .models import Finding, MorningDelivery, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["morning"])

# Cap matches the findings list endpoint so the morning view stays a thin slice.
MORNING_ITEM_LIMIT = 100


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _visible_open_findings(session: Session, organization_id: UUID, user_id: UUID) -> list[Finding]:
    """Open findings the user may see — same filter as the findings list API."""
    return list(
        session.scalars(
            select(Finding)
            .where(
                Finding.organization_id == organization_id,
                Finding.decision.is_(None),
                or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == user_id),
            )
            .order_by(Finding.detected_at.desc())
            .limit(MORNING_ITEM_LIMIT)
        ).all()
    )


def _item_summary(finding: Finding) -> dict[str, Any]:
    return {
        "id": str(finding.id),
        "check_key": finding.check_key,
        "summary_sentence": finding.summary_sentence,
        "detected_at": finding.detected_at.isoformat(),
        "subject_kind": finding.subject_kind,
        "subject_id": str(finding.subject_id),
    }


def build_morning_message(session: Session, org_id: UUID, user: User) -> dict[str, Any]:
    """In-app morning payload: waiting open findings the user may see."""
    findings = _visible_open_findings(session, org_id, user.id)
    items = [_item_summary(f) for f in findings]
    return {
        "waiting_count": len(items),
        "items": items,
        "generated_at": utcnow().isoformat(),
    }


def deliver_morning_dry_run(session: Session, org_id: UUID, user: User) -> dict[str, Any]:
    """Build the morning message, log an email dry-run, and store a delivery row.

    No SMTP send. No WhatsApp. Logging + optional ``morning_deliveries`` row
    satisfy the locked Done criteria for this ticket.
    """
    message = build_morning_message(session, org_id, user)
    payload = {
        "channel": "email",
        "dry_run": True,
        "to": user.email,
        "waiting_count": message["waiting_count"],
        "items": message["items"],
        "generated_at": message["generated_at"],
    }
    # Explicit dry-run marker — tests assert smtplib is never touched.
    logger.info(
        "morning_email_dry_run org=%s user=%s to=%s waiting=%s",
        org_id,
        user.id,
        user.email,
        message["waiting_count"],
    )
    delivery = MorningDelivery(
        organization_id=org_id,
        user_id=user.id,
        channel="email",
        payload=payload,
    )
    session.add(delivery)
    session.flush()
    return {
        "channel": "email",
        "dry_run": True,
        "delivery_id": str(delivery.id),
        "waiting_count": message["waiting_count"],
        "generated_at": message["generated_at"],
    }


@router.get("/accounts/{organization_id}/morning")
def get_morning(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    return build_morning_message(session, organization_id, user)


@router.post("/accounts/{organization_id}/morning/deliver")
def post_morning_deliver(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    result = deliver_morning_dry_run(session, organization_id, user)
    session.commit()
    return result
