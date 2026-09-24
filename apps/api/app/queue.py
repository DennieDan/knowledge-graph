"""Review queue API (#93 Step 3 / #45).

Extends the existing findings queue (#15 / ``health_api``); does not replace it.
Old paths ``GET/POST …/findings…`` stay for the To check UI. New paths:

- ``GET  /accounts/{org}/queue``
- ``POST /accounts/{org}/queue/{id}/confirm``
- ``POST /accounts/{org}/queue/{id}/fix``
- ``POST /accounts/{org}/queue/{id}/dismiss``

Confirm / fix / dismiss write finding decision + claims + change_event (+
order_event when an order record is known) in ONE transaction. If the
transaction fails, the queue item stays open — no half-approvals.

Maps onto existing Finding fields: open = ``decision IS NULL`` (there is no
separate ``dismissed_at``; dismissal uses ``decision='dismissed'`` +
``decided_at`` + ``dismissal_reason``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .claims import (
    claim_value_payload,
    confirm_claim,
    create_claim,
    set_claim_value,
)
from .database import get_session
from .findings import dismiss_finding
from .models import (
    CLAIM_VALUE_TYPES,
    DISMISSAL_REASONS,
    ChangeEvent,
    Claim,
    Finding,
    Record,
    User,
)
from .timeline import append_order_event

router = APIRouter(tags=["queue"])

# Checks that block building / confirmation until a person acts — sort first.
BLOCKING_CHECK_KEYS = frozenset(
    {
        "source_changed",
        "sources_disagree",
        "referenced_record_not_found",
        "po_revision_changed",
        "quantity_changed",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_blocking(finding: Finding) -> bool:
    if finding.check_key in BLOCKING_CHECK_KEYS:
        return True
    evidence = finding.evidence or {}
    return bool(evidence.get("blocking"))


def next_change_sequence(session: Session, organization_id: UUID) -> int:
    current = session.scalar(
        select(func.coalesce(func.max(ChangeEvent.sequence_no), 0)).where(
            ChangeEvent.organization_id == organization_id
        )
    )
    return int(current or 0) + 1


def open_queue_query(organization_id: UUID, user_id: UUID):
    """Open findings the caller may see, blocking first then newest."""
    # evidence.blocking is reflected in serialize_finding; ORDER BY uses check_key
    # so the sort stays index-friendly and JSONB-safe.
    blocking_rank = case((Finding.check_key.in_(tuple(BLOCKING_CHECK_KEYS)), 0), else_=1)
    return (
        select(Finding)
        .where(
            Finding.organization_id == organization_id,
            Finding.decision.is_(None),
            or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == user_id),
        )
        .order_by(blocking_rank.asc(), Finding.detected_at.desc())
    )


def finding_for_queue(
    session: Session,
    *,
    organization_id: UUID,
    finding_id: UUID,
    user: User,
) -> Finding:
    finding = session.get(Finding, finding_id)
    if finding is None or finding.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="finding_not_found")
    if finding.owner_user_id is not None and finding.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="finding_not_found")
    return finding


def claims_for_finding(session: Session, finding_id: UUID) -> list[Claim]:
    return list(
        session.scalars(select(Claim).where(Claim.finding_id == finding_id)).all()
    )


def resolve_order_id(session: Session, finding: Finding, claims: list[Claim]) -> UUID | None:
    if finding.subject_kind == "record":
        record = session.get(Record, finding.subject_id)
        if record is not None:
            return record.id
    for claim in claims:
        return claim.record_id
    return None


def append_change_event(
    session: Session,
    *,
    organization_id: UUID,
    finding_id: UUID,
    user_id: UUID,
    change_kind: str,
    before_json: dict | None,
    after_json: dict | None,
) -> ChangeEvent:
    event = ChangeEvent(
        organization_id=organization_id,
        sequence_no=next_change_sequence(session, organization_id),
        caused_by_finding_id=finding_id,
        caused_by_user_id=user_id,
        occurred_at=utcnow(),
        change_kind=change_kind,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(event)
    session.flush()
    return event


def serialize_finding(finding: Finding) -> dict[str, Any]:
    return {
        "id": str(finding.id),
        "check_key": finding.check_key,
        "summary_sentence": finding.summary_sentence,
        "detected_at": finding.detected_at.isoformat(),
        "subject_kind": finding.subject_kind,
        "subject_id": str(finding.subject_id),
        "blocking": is_blocking(finding),
        "decision": finding.decision,
        "dismissal_reason": finding.dismissal_reason,
    }


class FixBody(BaseModel):
    field: str = Field(min_length=1)
    new_value: Any
    value_type: str | None = None


class DismissBody(BaseModel):
    reason: str


@router.get("/accounts/{organization_id}/queue")
def list_queue(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    rows = session.scalars(open_queue_query(organization_id, user.id).limit(100)).all()
    return {
        "items": [serialize_finding(f) for f in rows],
        # Alias kept for callers that already speak "findings".
        "findings": [serialize_finding(f) for f in rows],
        "dismissal_reasons": list(DISMISSAL_REASONS),
    }


@router.post("/accounts/{organization_id}/queue/{finding_id}/confirm")
def confirm_queue_item(
    organization_id: UUID,
    finding_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Confirm finding + linked proposed claims + change_event + order_event."""
    membership_for(organization_id, user, session)
    finding = finding_for_queue(
        session, organization_id=organization_id, finding_id=finding_id, user=user
    )
    if finding.decision is not None:
        raise HTTPException(status_code=409, detail="finding_already_decided")

    # Nested savepoint: any failure leaves the queue item open (no half-approvals).
    with session.begin_nested():
        now = utcnow()
        claims = claims_for_finding(session, finding.id)
        before = {"claims": [claim_value_payload(c) for c in claims]}

        confirmed: list[Claim] = []
        for claim in claims:
            if claim.status == "proposed":
                confirm_claim(claim, user_id=user.id, at=now)
                confirmed.append(claim)

        finding.decision = "confirmed"
        finding.decided_by_user_id = user.id
        finding.decided_at = now

        after = {"claims": [claim_value_payload(c) for c in confirmed], "decision": "confirmed"}
        change = append_change_event(
            session,
            organization_id=organization_id,
            finding_id=finding.id,
            user_id=user.id,
            change_kind="confirm",
            before_json=before,
            after_json=after,
        )

        order_id = resolve_order_id(session, finding, claims)
        order_event = None
        if order_id is not None:
            order_event = append_order_event(
                session,
                organization_id=organization_id,
                order_id=order_id,
                kind="confirmed",
                actor_user_id=user.id,
                at=now,
                payload={
                    "finding_id": str(finding.id),
                    "change_event_id": str(change.id),
                    "claim_ids": [str(c.id) for c in confirmed],
                },
            )

        result = {
            "id": str(finding.id),
            "decision": finding.decision,
            "confirmed_claim_ids": [str(c.id) for c in confirmed],
            "change_event_id": str(change.id),
            "order_event_id": str(order_event.id) if order_event else None,
        }

    session.commit()
    return result


@router.post("/accounts/{organization_id}/queue/{finding_id}/fix")
def fix_queue_item(
    organization_id: UUID,
    finding_id: UUID,
    body: FixBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Fix: old claim kept (superseded), new confirmed value + history in one txn."""
    membership_for(organization_id, user, session)
    finding = finding_for_queue(
        session, organization_id=organization_id, finding_id=finding_id, user=user
    )
    if finding.decision is not None:
        raise HTTPException(status_code=409, detail="finding_already_decided")

    claims = claims_for_finding(session, finding.id)
    field_claims = [c for c in claims if c.field_key == body.field]
    old_claim = next((c for c in field_claims if c.status == "proposed"), None)
    if old_claim is None:
        old_claim = next((c for c in field_claims if c.status == "confirmed"), None)

    order_id = resolve_order_id(session, finding, claims)
    if order_id is None and finding.subject_kind == "record":
        order_id = finding.subject_id
    if order_id is None:
        raise HTTPException(status_code=422, detail="fix_requires_record_subject")

    value_type = body.value_type or (old_claim.value_type if old_claim else "text")
    if value_type not in CLAIM_VALUE_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid_claim_value_type:{value_type}")

    with session.begin_nested():
        now = utcnow()
        before = {"claims": [claim_value_payload(c) for c in field_claims]}

        if old_claim is not None and old_claim.status != "superseded":
            old_claim.status = "superseded"

        new_claim = create_claim(
            session,
            organization_id=organization_id,
            record_id=old_claim.record_id if old_claim else order_id,
            field_key=body.field,
            value_type=value_type,
            origin="user",
            visible_via_user_id=old_claim.visible_via_user_id if old_claim else None,
            finding_id=finding.id,
            status="proposed",
            quote=old_claim.quote if old_claim else None,
            location=old_claim.location if old_claim else None,
        )
        set_claim_value(new_claim, value_type, body.new_value)
        confirm_claim(new_claim, user_id=user.id, at=now)

        finding.decision = "confirmed"
        finding.decided_by_user_id = user.id
        finding.decided_at = now

        after = {
            "claims": [claim_value_payload(new_claim)],
            "superseded_claim_id": str(old_claim.id) if old_claim else None,
            "decision": "confirmed",
        }
        change = append_change_event(
            session,
            organization_id=organization_id,
            finding_id=finding.id,
            user_id=user.id,
            change_kind="fix",
            before_json=before,
            after_json=after,
        )
        order_event = append_order_event(
            session,
            organization_id=organization_id,
            order_id=new_claim.record_id,
            kind="edited",
            actor_user_id=user.id,
            at=now,
            payload={
                "finding_id": str(finding.id),
                "change_event_id": str(change.id),
                "field": body.field,
                "claim_id": str(new_claim.id),
                "superseded_claim_id": str(old_claim.id) if old_claim else None,
            },
        )

        result = {
            "id": str(finding.id),
            "decision": finding.decision,
            "claim_id": str(new_claim.id),
            "superseded_claim_id": str(old_claim.id) if old_claim else None,
            "change_event_id": str(change.id),
            "order_event_id": str(order_event.id),
        }

    session.commit()
    return result


@router.post("/accounts/{organization_id}/queue/{finding_id}/dismiss")
def dismiss_queue_item(
    organization_id: UUID,
    finding_id: UUID,
    body: DismissBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Dismiss with a fixed reason; retract linked proposed claims + history in one txn."""
    membership_for(organization_id, user, session)
    finding = finding_for_queue(
        session, organization_id=organization_id, finding_id=finding_id, user=user
    )
    if finding.decision is not None:
        raise HTTPException(status_code=409, detail="finding_already_decided")
    if body.reason not in DISMISSAL_REASONS:
        raise HTTPException(status_code=400, detail=f"invalid_dismissal_reason:{body.reason}")

    with session.begin_nested():
        now = utcnow()
        claims = claims_for_finding(session, finding.id)
        before = {"claims": [claim_value_payload(c) for c in claims]}

        dismiss_finding(session, finding, user_id=user.id, reason=body.reason)

        retracted: list[Claim] = []
        for claim in claims:
            if claim.status == "proposed":
                claim.status = "retracted"
                claim.retracted_at = now
                retracted.append(claim)

        after = {
            "decision": "dismissed",
            "dismissal_reason": finding.dismissal_reason,
            "retracted_claims": [claim_value_payload(c) for c in retracted],
        }
        change = append_change_event(
            session,
            organization_id=organization_id,
            finding_id=finding.id,
            user_id=user.id,
            change_kind="dismiss",
            before_json=before,
            after_json=after,
        )

        order_id = resolve_order_id(session, finding, claims)
        order_event = None
        if order_id is not None:
            order_event = append_order_event(
                session,
                organization_id=organization_id,
                order_id=order_id,
                kind="rechecked",
                actor_user_id=user.id,
                at=now,
                payload={
                    "finding_id": str(finding.id),
                    "change_event_id": str(change.id),
                    "dismissal_reason": finding.dismissal_reason,
                },
            )

        result = {
            "id": str(finding.id),
            "decision": finding.decision,
            "dismissal_reason": finding.dismissal_reason,
            "change_event_id": str(change.id),
            "order_event_id": str(order_event.id) if order_event else None,
        }

    session.commit()
    return result
