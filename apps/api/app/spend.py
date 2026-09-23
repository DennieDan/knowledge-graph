"""Per-organisation daily token budget."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Organization, Spend


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def add_tokens(
    session: Session,
    organization_id: UUID,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Spend:
    day = utc_today()
    row = session.scalar(
        select(Spend).where(Spend.organization_id == organization_id, Spend.day == day)
    )
    if row is None:
        row = Spend(organization_id=organization_id, day=day)
        session.add(row)
        session.flush()
    row.input_tokens += max(0, input_tokens)
    row.output_tokens += max(0, output_tokens)
    session.flush()
    return row


def tokens_used_today(session: Session, organization_id: UUID) -> int:
    row = session.scalar(
        select(Spend).where(Spend.organization_id == organization_id, Spend.day == utc_today())
    )
    if row is None:
        return 0
    return row.input_tokens + row.output_tokens


def budget_remaining(session: Session, organization_id: UUID) -> int:
    org = session.get(Organization, organization_id)
    budget = org.daily_token_budget if org is not None else 500_000
    return max(0, budget - tokens_used_today(session, organization_id))


def budget_exhausted(session: Session, organization_id: UUID) -> bool:
    return budget_remaining(session, organization_id) <= 0
