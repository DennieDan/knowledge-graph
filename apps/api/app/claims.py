"""Claim helpers (#93 Step 2).

WhatsApp user/org seam
----------------------
``whatsapp_connections`` is USER-scoped by design: an imported chat belongs to
the person, never to the organization. A claim read out of a chat therefore has
TWO owners:

- ``claim.organization_id`` — who owns the record (the company wall)
- ``claim.visible_via_user_id`` — who was allowed to see the source
  (``WhatsappConnection.user_id``)

Feature 10's permission check must honour BOTH, or one person's private chat
leaks to the whole company through a confirmed record. Non-WhatsApp origins
leave ``visible_via_user_id`` null (org-wide visibility once confirmed).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .models import CLAIM_VALUE_TYPES, Claim

# Origins that come from a user-scoped WhatsApp connection.
WHATSAPP_ORIGINS = frozenset({"whatsapp", "whatsapp_message", "whatsapp_chat"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_whatsapp_origin(origin: str) -> bool:
    return origin in WHATSAPP_ORIGINS or origin.startswith("whatsapp")


def create_claim(
    session: Session,
    *,
    organization_id: UUID,
    record_id: UUID,
    field_key: str,
    value_type: str,
    origin: str,
    value_text: str | None = None,
    value_numeric: Decimal | None = None,
    value_date: date | None = None,
    value_bool: bool | None = None,
    quote: str | None = None,
    location: dict | None = None,
    status: str = "proposed",
    visible_via_user_id: UUID | None = None,
    finding_id: UUID | None = None,
    confirmed_by_user_id: UUID | None = None,
    confirmed_at: datetime | None = None,
    asserted_at: datetime | None = None,
) -> Claim:
    """Insert a claim, enforcing the WhatsApp user/org seam on creation.

    Always sets ``organization_id``. When ``origin`` is WhatsApp-derived,
    ``visible_via_user_id`` is required (the connection's user).
    """
    if value_type not in CLAIM_VALUE_TYPES:
        raise ValueError(f"invalid_claim_value_type:{value_type}")
    if is_whatsapp_origin(origin) and visible_via_user_id is None:
        raise ValueError("whatsapp_claims_require_visible_via_user_id")

    claim = Claim(
        organization_id=organization_id,
        record_id=record_id,
        field_key=field_key,
        value_type=value_type,
        value_text=value_text,
        value_numeric=value_numeric,
        value_date=value_date,
        value_bool=value_bool,
        quote=quote,
        location=location,
        origin=origin,
        status=status,
        visible_via_user_id=visible_via_user_id,
        finding_id=finding_id,
        confirmed_by_user_id=confirmed_by_user_id,
        confirmed_at=confirmed_at,
        asserted_at=asserted_at or utcnow(),
    )
    session.add(claim)
    session.flush()
    return claim


def claim_value_payload(claim: Claim) -> dict[str, Any]:
    """Serialize a claim's typed value for change_event before/after JSON."""
    payload: dict[str, Any] = {
        "claim_id": str(claim.id),
        "field_key": claim.field_key,
        "value_type": claim.value_type,
        "status": claim.status,
    }
    if claim.value_type == "text":
        payload["value"] = claim.value_text
    elif claim.value_type == "numeric":
        payload["value"] = str(claim.value_numeric) if claim.value_numeric is not None else None
    elif claim.value_type == "date":
        payload["value"] = claim.value_date.isoformat() if claim.value_date is not None else None
    elif claim.value_type == "bool":
        payload["value"] = claim.value_bool
    return payload


def set_claim_value(claim: Claim, value_type: str, new_value: Any) -> None:
    """Overwrite typed value columns from a fix payload."""
    claim.value_type = value_type
    claim.value_text = None
    claim.value_numeric = None
    claim.value_date = None
    claim.value_bool = None
    if value_type == "text":
        claim.value_text = None if new_value is None else str(new_value)
    elif value_type == "numeric":
        claim.value_numeric = None if new_value is None else Decimal(str(new_value))
    elif value_type == "date":
        if new_value is None:
            claim.value_date = None
        elif isinstance(new_value, date):
            claim.value_date = new_value
        else:
            claim.value_date = date.fromisoformat(str(new_value))
    elif value_type == "bool":
        if isinstance(new_value, bool):
            claim.value_bool = new_value
        elif new_value is None:
            claim.value_bool = None
        else:
            claim.value_bool = str(new_value).lower() in {"1", "true", "yes"}
    else:
        raise ValueError(f"invalid_claim_value_type:{value_type}")


def confirm_claim(claim: Claim, *, user_id: UUID, at: datetime | None = None) -> Claim:
    claim.status = "confirmed"
    claim.confirmed_by_user_id = user_id
    claim.confirmed_at = at or utcnow()
    return claim
