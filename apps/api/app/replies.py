"""Reply drafts from confirmed claims (#105 / R2R F-14).

Drafts quote checked record values only — never raw source / PDF text.
Send is dry-run: email and WhatsApp are logged, not transmitted (no SMTP
domain; no WA templates). A person must tap send; nothing auto-sends.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .models import (
    Claim,
    Document,
    OrderEvent,
    Record,
    Substack,
    SubstackContent,
    SubstackLink,
    SubstackSource,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["replies"])

Channel = Literal["email", "whatsapp"]

# Field keys we prefer to surface in an acknowledgement, in order.
_ACK_FIELD_ORDER = (
    "po_number",
    "customer",
    "customer_name",
    "quantity",
    "item",
    "item_code",
    "sku",
    "due_date",
    "delivery_date",
    "revision",
)


@dataclass(frozen=True)
class StyleHints:
    greeting: str = "Hi"
    signoff: str = "Thanks"


@dataclass(frozen=True)
class DraftSource:
    field_key: str
    value: str
    claim_id: str | None = None


class ReplyDraftIn(BaseModel):
    channel: Channel | None = None


class ReplySendIn(BaseModel):
    body: str = Field(min_length=1)
    channel: Channel


def _get_substack(organization_id: UUID, substack_id: UUID, user: User, session: Session) -> Substack:
    membership_for(organization_id, user, session)
    substack = session.get(Substack, substack_id)
    if (
        substack is None
        or substack.organization_id != organization_id
        or (substack.owner_user_id is not None and substack.owner_user_id != user.id)
    ):
        raise HTTPException(status_code=404, detail="substack_not_found")
    return substack


def _claim_display_value(claim: Claim) -> str | None:
    if claim.value_type == "text":
        text = (claim.value_text or "").strip()
        return text or None
    if claim.value_type == "numeric" and claim.value_numeric is not None:
        # Prefer integer-looking quantities without trailing .0
        num = claim.value_numeric
        if num == num.to_integral_value():
            return str(int(num))
        return format(num, "f").rstrip("0").rstrip(".")
    if claim.value_type == "date" and claim.value_date is not None:
        return claim.value_date.isoformat()
    if claim.value_type == "bool" and claim.value_bool is not None:
        return "yes" if claim.value_bool else "no"
    return None


def _record_for_substack(session: Session, substack: Substack) -> Record | None:
    return session.scalar(
        select(Record)
        .where(Record.substack_id == substack.id, Record.organization_id == substack.organization_id)
        .order_by(Record.created_at.desc())
        .limit(1)
    )


def _confirmed_claims_for(
    session: Session,
    *,
    organization_id: UUID,
    record: Record | None,
    user: User,
) -> list[Claim]:
    if record is None:
        return []
    # Confirmed-by is required — proposed / auto rows must not enter a draft.
    statement = (
        select(Claim)
        .where(
            Claim.organization_id == organization_id,
            Claim.record_id == record.id,
            Claim.status == "confirmed",
            Claim.confirmed_by_user_id.is_not(None),
        )
        .order_by(Claim.asserted_at.asc())
    )
    claims = list(session.scalars(statement).all())
    visible: list[Claim] = []
    for claim in claims:
        if claim.visible_via_user_id is not None and claim.visible_via_user_id != user.id:
            continue
        visible.append(claim)
    return visible


def _confirmed_content_fields(session: Session, substack: Substack) -> list[DraftSource]:
    """Person-confirmed content field segments (fallback when claims are sparse)."""
    content = session.scalar(
        select(SubstackContent)
        .where(
            SubstackContent.substack_id == substack.id,
            SubstackContent.status == "confirmed",
            SubstackContent.confirmed_by_user_id.is_not(None),
        )
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if content is None:
        return []
    sources: list[DraftSource] = []
    for segment in (content.content or {}).get("segments", []):
        if segment.get("kind") != "field":
            continue
        name = (segment.get("name") or "").strip()
        value = (segment.get("value") or "").strip()
        if not name or not value:
            continue
        sources.append(DraftSource(field_key=name, value=value))
    return sources


def _infer_channel(session: Session, substack: Substack) -> Channel:
    sources = session.scalars(
        select(SubstackSource).where(SubstackSource.substack_id == substack.id)
    ).all()
    for source in sources:
        document = session.get(Document, source.document_id)
        if document is not None and document.source == "whatsapp":
            return "whatsapp"
    return "email"


def _style_hints(session: Session, substack: Substack, organization_id: UUID) -> StyleHints:
    """Hints from this org's own recent conversation entries only (never cross-org)."""
    related_ids = [
        link.related_substack_id
        for link in session.scalars(
            select(SubstackLink).where(SubstackLink.substack_id == substack.id)
        ).all()
    ]
    candidate_ids = list({substack.id, *related_ids})
    conversation_ids = list(
        session.scalars(
            select(Substack.id).where(
                Substack.organization_id == organization_id,
                Substack.stack_type == "conversations",
                Substack.id.in_(candidate_ids),
            )
        ).all()
    )
    if not conversation_ids:
        return StyleHints()

    openings: list[str] = []
    closings: list[str] = []
    contents = session.scalars(
        select(SubstackContent)
        .where(
            SubstackContent.substack_id.in_(conversation_ids),
            SubstackContent.status.in_(("confirmed", "proposed")),
        )
        .order_by(SubstackContent.created_at.desc())
        .limit(20)
    ).all()
    for content in contents:
        for entry in (content.content or {}).get("entries", []):
            message = (entry.get("message") or "").strip()
            if not message:
                continue
            # Prefer outbound-looking lines (company author markers are soft).
            author = (entry.get("author") or "").lower()
            if author in ("customer", "buyer", "them"):
                continue
            first = message.split(None, 1)[0].rstrip(",:")
            if first.lower() in ("hi", "hello", "dear", "hey"):
                openings.append(first if first[0].isupper() else first.capitalize())
            lower = message.lower()
            for marker in ("thanks", "thank you", "regards", "cheers"):
                if lower.rstrip(".").endswith(marker):
                    closings.append(marker.capitalize() if marker != "thank you" else "Thank you")
                    break
    return StyleHints(
        greeting=openings[0] if openings else "Hi",
        signoff=closings[0] if closings else "Thanks",
    )


def _ordered_sources(sources: list[DraftSource]) -> list[DraftSource]:
    rank = {key: index for index, key in enumerate(_ACK_FIELD_ORDER)}
    return sorted(sources, key=lambda s: (rank.get(s.field_key, 100), s.field_key))


def _render_ack(sources: list[DraftSource], style: StyleHints, channel: Channel) -> str:
    by_key = {s.field_key: s.value for s in sources}
    po = by_key.get("po_number")
    lines: list[str] = []
    qty = by_key.get("quantity")
    item = by_key.get("item") or by_key.get("item_code") or by_key.get("sku")
    if qty and item:
        lines.append(f"{qty} × {item}")
    elif qty:
        lines.append(f"quantity {qty}")
    elif item:
        lines.append(item)
    due = by_key.get("due_date") or by_key.get("delivery_date")
    if due:
        lines.append(f"delivery {due}")
    revision = by_key.get("revision")
    if revision:
        lines.append(f"revision {revision}")
    # Any remaining confirmed fields not already used.
    used = {"po_number", "quantity", "item", "item_code", "sku", "due_date", "delivery_date", "revision", "customer", "customer_name"}
    extras = [f"{s.field_key.replace('_', ' ')} {s.value}" for s in sources if s.field_key not in used]
    lines.extend(extras)

    subject = f"PO {po}" if po else "your order"
    detail = ": " + ", ".join(lines) if lines else ""
    body = f"{style.greeting}, received {subject}{detail}. {style.signoff}."
    if channel == "email":
        # Draft-only marker — no SMTP domain in this cut.
        return body
    return body


def _allowed_tokens(sources: list[DraftSource]) -> set[str]:
    tokens: set[str] = set()
    for source in sources:
        tokens.add(source.value)
        # Numeric fragments for hard-check (e.g. "40" from "40").
        for match in re.findall(r"\d+(?:\.\d+)?", source.value):
            tokens.add(match)
    return tokens


def _assert_draft_closed(body: str, sources: list[DraftSource]) -> None:
    """Fail closed: every number in the draft must appear in confirmed sources."""
    allowed = _allowed_tokens(sources)
    for number in re.findall(r"\d+(?:\.\d+)?", body):
        if number not in allowed:
            raise HTTPException(
                status_code=409,
                detail="draft_contains_unconfirmed_value",
            )


def draft_reply(
    session: Session,
    record_or_substack: Record | Substack,
    channel: Channel | None = None,
    *,
    user: User | None = None,
) -> dict:
    """Build a reply body from confirmed claims / content fields only.

    Never copies raw source or PDF text. Style hints come from this org's
    conversation segments when available.
    """
    if isinstance(record_or_substack, Substack):
        substack = record_or_substack
        record = _record_for_substack(session, substack)
    else:
        record = record_or_substack
        substack = session.get(Substack, record.substack_id) if record.substack_id else None
        if substack is None:
            raise HTTPException(status_code=404, detail="substack_not_found")

    if user is None:
        raise HTTPException(status_code=401, detail="authentication_required")

    resolved_channel: Channel = channel or _infer_channel(session, substack)
    claims = _confirmed_claims_for(
        session,
        organization_id=substack.organization_id,
        record=record,
        user=user,
    )
    sources: list[DraftSource] = []
    for claim in claims:
        value = _claim_display_value(claim)
        if value is None:
            continue
        sources.append(DraftSource(field_key=claim.field_key, value=value, claim_id=str(claim.id)))

    # Fall back / fill gaps from person-confirmed content fields — still never raw text.
    have_keys = {s.field_key for s in sources}
    for field in _confirmed_content_fields(session, substack):
        if field.field_key not in have_keys:
            sources.append(field)
            have_keys.add(field.field_key)

    if not sources:
        raise HTTPException(status_code=409, detail="no_confirmed_claims")

    sources = _ordered_sources(sources)
    style = _style_hints(session, substack, substack.organization_id)
    body = _render_ack(sources, style, resolved_channel)
    _assert_draft_closed(body, sources)

    return {
        "body": body,
        "channel": resolved_channel,
        "sources_used": [
            {"field_key": s.field_key, "value": s.value, "claim_id": s.claim_id}
            for s in sources
        ],
    }


def log_send(
    session: Session,
    *,
    substack: Substack,
    user: User,
    body: str,
    channel: Channel,
) -> dict:
    """Dry-run send: log only. Email has no SMTP domain; WhatsApp has no templates."""
    record = _record_for_substack(session, substack)
    logger.info(
        "reply_send_dry_run org=%s substack=%s channel=%s actor=%s body_len=%s",
        substack.organization_id,
        substack.id,
        channel,
        user.id,
        len(body),
    )
    if record is not None:
        session.add(
            OrderEvent(
                organization_id=substack.organization_id,
                order_id=record.id,
                kind="replied",
                actor_user_id=user.id,
                payload={
                    "channel": channel,
                    "body": body,
                    "status": "logged",
                    "dry_run": True,
                    "substack_id": str(substack.id),
                },
            )
        )
        session.flush()
    return {"status": "logged"}


@router.post("/accounts/{organization_id}/substacks/{substack_id}/reply/draft")
def create_reply_draft(
    organization_id: UUID,
    substack_id: UUID,
    body: ReplyDraftIn | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(organization_id, substack_id, user, session)
    payload = body or ReplyDraftIn()
    return draft_reply(session, substack, payload.channel, user=user)


@router.post("/accounts/{organization_id}/substacks/{substack_id}/reply/send")
def send_reply(
    organization_id: UUID,
    substack_id: UUID,
    body: ReplySendIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(organization_id, substack_id, user, session)
    # Re-validate that every number still comes from confirmed sources before logging.
    draft = draft_reply(session, substack, body.channel, user=user)
    _assert_draft_closed(body.body, [
        DraftSource(field_key=s["field_key"], value=s["value"], claim_id=s.get("claim_id"))
        for s in draft["sources_used"]
    ])
    # Also reject bodies that introduce free-form numbers not in the draft sources.
    result = log_send(
        session,
        substack=substack,
        user=user,
        body=body.body,
        channel=body.channel,
    )
    session.commit()
    return result
