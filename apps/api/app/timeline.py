"""Order timeline helpers and API (#93 Step 4).

Append-only ``order_events``. The screen is a SELECT ordered by ``at``.
Browser IndexedDB outbox (decision H) is deferred — server is the authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .models import ORDER_EVENT_KINDS, OrderEvent, Record, User

router = APIRouter(tags=["timeline"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def append_order_event(
    session: Session,
    *,
    organization_id: UUID,
    order_id: UUID,
    kind: str,
    actor_user_id: UUID,
    payload: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> OrderEvent:
    """Append one timeline row. ``actor_user_id`` is required — no anonymous events."""
    if kind not in ORDER_EVENT_KINDS:
        raise ValueError(f"invalid_order_event_kind:{kind}")
    if actor_user_id is None:
        raise ValueError("order_event_requires_actor")
    event = OrderEvent(
        organization_id=organization_id,
        order_id=order_id,
        kind=kind,
        actor_user_id=actor_user_id,
        at=at or utcnow(),
        payload=payload or {},
    )
    session.add(event)
    session.flush()
    return event


def list_order_events(session: Session, *, organization_id: UUID, order_id: UUID) -> list[OrderEvent]:
    return list(
        session.scalars(
            select(OrderEvent)
            .where(
                OrderEvent.organization_id == organization_id,
                OrderEvent.order_id == order_id,
            )
            .order_by(OrderEvent.at.asc(), OrderEvent.id.asc())
        ).all()
    )


@router.get("/accounts/{organization_id}/records/{record_id}/timeline")
def get_record_timeline(
    organization_id: UUID,
    record_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    record = session.get(Record, record_id)
    if record is None or record.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="record_not_found")
    events = list_order_events(session, organization_id=organization_id, order_id=record_id)
    return {
        "record_id": str(record_id),
        "events": [
            {
                "id": str(e.id),
                "kind": e.kind,
                "actor_user_id": str(e.actor_user_id),
                "at": e.at.isoformat(),
                "payload": e.payload or {},
            }
            for e in events
        ],
    }
