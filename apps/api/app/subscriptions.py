"""Drive/Gmail/Graph push subscriptions (#92 Step 1).

Stub only: Google `changes.watch` needs a verified webhook domain (Search Console
+ API console). Until that exists, `start_watch` logs and returns without calling
Google. Drive polling in `drive_sync.py` stays the live sync path — enhance, never
delete.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_engine
from .models import Subscription

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Drive changes.watch TTL is up to one week; renew before the last 25%.
DRIVE_WATCH_TTL = timedelta(days=7)
RENEW_WHEN_REMAINING_FRACTION = 0.25


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def renewal_due_before(now: datetime | None = None) -> datetime:
    """Subscriptions with expires_at before this instant have <25% TTL remaining."""
    now = now or utcnow()
    return now + DRIVE_WATCH_TTL * RENEW_WHEN_REMAINING_FRACTION


def is_renewal_due(subscription: Subscription, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return subscription.expires_at < renewal_due_before(now)


def start_watch(
    session: Session,
    *,
    organization_id: UUID,
    connection_id: UUID | None = None,
    provider: str = "drive",
    resource_id: str | None = None,
    subscription: Subscription | None = None,
) -> Subscription | None:
    """Stub: do not call Google changes.watch until the webhook domain is verified."""
    # Conflict with live path: drive_sync polling remains authoritative. Do not
    # replace or remove it when this stub grows into a real watch.
    logger.info(
        "start_watch deferred pending verified webhook domain "
        "(organization_id=%s connection_id=%s provider=%s resource_id=%s subscription_id=%s)",
        organization_id,
        connection_id,
        provider,
        resource_id,
        subscription.id if subscription is not None else None,
    )
    return subscription


def select_due_subscriptions(session: Session, now: datetime | None = None) -> list[Subscription]:
    """Return subscriptions whose remaining lifetime is under 25% of DRIVE_WATCH_TTL."""
    cutoff = renewal_due_before(now)
    return list(
        session.scalars(select(Subscription).where(Subscription.expires_at < cutoff).order_by(Subscription.expires_at))
    )


def renew_due_subscriptions(session: Session, now: datetime | None = None) -> list[Subscription]:
    """Call start_watch for every subscription due for renewal. Returns those selected."""
    due = select_due_subscriptions(session, now=now)
    for subscription in due:
        start_watch(
            session,
            organization_id=subscription.organization_id,
            connection_id=subscription.connection_id,
            provider=subscription.provider,
            resource_id=subscription.resource_id,
            subscription=subscription,
        )
    return due


def run_subscription_renewal() -> int:
    """Open a session and renew due subscriptions. Returns how many were selected."""
    with Session(get_engine()) as session:
        due = renew_due_subscriptions(session)
        session.commit()
        return len(due)


@router.post("/webhooks/drive")
async def drive_webhook(request: Request) -> Response:
    """Google Drive push notification stub.

    Sync handshake: return 200. Any other notification: return 200 without parsing
    the (empty) body — never do work in the webhook. Real change listing waits on
    a verified domain and a live subscription cursor.
    """
    if request.headers.get("X-Goog-Resource-State") == "sync":
        return Response(status_code=200)
    # Body is empty for Drive change notifications; do not parse.
    return Response(status_code=200)
