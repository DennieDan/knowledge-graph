"""Gap alerts for clients and sales-orders (#103 / F-12).

Findings land in the same To-check queue as other checks. Scope is supplier
record types only (clients, sales-orders) — not event-organiser catalogue keys.
Framed on the record ("this client has one confirmer"), never as a person score.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .checks import DraftFinding
from .findings import create_finding, observed_fingerprint
from .models import Substack, SubstackContent, SubstackLink, User

# Locked scope for F-12: clients and orders only.
GAP_STACK_TYPES = frozenset({"clients", "sales-orders"})

# Required extraction fields (EvidenceValue.value must be non-empty).
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "sales-orders": ("order_number", "customer_name"),
    "clients": ("name",),
}

# Clients also need at least one durable identity field.
CLIENT_IDENTITY_FIELDS = ("registration_number", "customer_id")

# Degree-of-authorship weights (ticket §9). Plain confirms are cheap; we only
# have confirm attribution today, so concentration uses confirm events only.
CONFIRM_WEIGHT = 0.3
CONCENTRATION_THRESHOLD = 0.5
MIN_CONFIRM_EVENTS = 2


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extraction(content: SubstackContent) -> dict:
    payload = content.content if isinstance(content.content, dict) else {}
    extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else payload
    return extraction if isinstance(extraction, dict) else {}


def _field_value(extraction: dict, key: str) -> str | None:
    raw = extraction.get(key)
    if isinstance(raw, dict):
        value = raw.get("value")
        return str(value).strip() if value is not None and str(value).strip() else None
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _missing_required(stack_type: str, extraction: dict) -> list[str]:
    missing = [key for key in REQUIRED_FIELDS.get(stack_type, ()) if not _field_value(extraction, key)]
    if stack_type == "clients":
        if not any(_field_value(extraction, key) for key in CLIENT_IDENTITY_FIELDS):
            missing.append("registration_number_or_customer_id")
    if stack_type == "sales-orders":
        lines = extraction.get("line_items")
        if not isinstance(lines, list) or len(lines) == 0:
            missing.append("line_items")
        elif any(
            not (isinstance(line, dict) and _field_value(line, "quantity"))
            for line in lines
        ):
            missing.append("line_items.quantity")
    return missing


def gap_missing_field(session: Session, organization_id: UUID) -> list[DraftFinding]:
    """Confirmed clients/orders whose latest content lacks required fields."""
    drafts: list[DraftFinding] = []
    substacks = session.scalars(
        select(Substack).where(
            Substack.organization_id == organization_id,
            Substack.stack_type.in_(GAP_STACK_TYPES),
        )
    ).all()
    for substack in substacks:
        latest = session.scalar(
            select(SubstackContent)
            .where(
                SubstackContent.substack_id == substack.id,
                SubstackContent.status.in_(("confirmed", "proposed")),
            )
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        if latest is None:
            continue
        missing = _missing_required(substack.stack_type, _extraction(latest))
        if not missing:
            continue
        fields = ", ".join(missing)
        drafts.append(
            DraftFinding(
                check_key="gap_missing_field",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                observed_value=fields,
                threshold_value=",".join(REQUIRED_FIELDS.get(substack.stack_type, ())),
                summary_sentence=(
                    f"{substack.name} is missing required field(s): {fields}."
                ),
                evidence={
                    "stack_type": substack.stack_type,
                    "missing_fields": missing,
                    "content_id": str(latest.id),
                    "content_status": latest.status,
                },
                fingerprint=observed_fingerprint(
                    str(substack.id), "gap_missing_field", *sorted(missing)
                ),
            )
        )
    return drafts


def _client_key_for_order(session: Session, order: Substack, extraction: dict) -> str | None:
    """Best-effort cell key: linked client id, else normalized customer_name."""
    link = session.scalar(
        select(SubstackLink)
        .join(Substack, Substack.id == SubstackLink.related_substack_id)
        .where(
            SubstackLink.substack_id == order.id,
            Substack.stack_type == "clients",
        )
        .limit(1)
    )
    if link is not None:
        return f"client:{link.related_substack_id}"
    name = _field_value(extraction, "customer_name")
    if name:
        return f"customer_name:{name.lower()}"
    return None


def gap_knowledge_concentration(
    session: Session, organization_id: UUID
) -> list[DraftFinding]:
    """Single-person confirmation concentration per client cell.

    Cell = clients record, or (sales-orders × that client). Uses
    confirmed_by_user_id when present; skips system auto-confirms (NULL).
    """
    # cell_key -> user_id -> weighted score; also track subject substack for framing
    scores: dict[str, dict[UUID, float]] = defaultdict(lambda: defaultdict(float))
    event_counts: dict[str, int] = defaultdict(int)
    cell_subjects: dict[str, UUID] = {}
    cell_labels: dict[str, str] = {}
    cell_owner: dict[str, UUID | None] = {}

    clients = session.scalars(
        select(Substack).where(
            Substack.organization_id == organization_id,
            Substack.stack_type == "clients",
        )
    ).all()
    for client in clients:
        cell = f"client:{client.id}"
        cell_subjects[cell] = client.id
        cell_labels[cell] = client.name
        cell_owner[cell] = client.owner_user_id
        contents = session.scalars(
            select(SubstackContent).where(
                SubstackContent.substack_id == client.id,
                SubstackContent.status.in_(("confirmed", "superseded")),
                SubstackContent.confirmed_by_user_id.is_not(None),
            )
        ).all()
        for content in contents:
            assert content.confirmed_by_user_id is not None
            scores[cell][content.confirmed_by_user_id] += CONFIRM_WEIGHT
            event_counts[cell] += 1

    orders = session.scalars(
        select(Substack).where(
            Substack.organization_id == organization_id,
            Substack.stack_type == "sales-orders",
        )
    ).all()
    for order in orders:
        contents = session.scalars(
            select(SubstackContent).where(
                SubstackContent.substack_id == order.id,
                SubstackContent.status.in_(("confirmed", "superseded")),
                SubstackContent.confirmed_by_user_id.is_not(None),
            )
        ).all()
        for content in contents:
            cell = _client_key_for_order(session, order, _extraction(content))
            if cell is None:
                # Order with no client link: its own cell, still framed on the order.
                cell = f"order:{order.id}"
                cell_subjects.setdefault(cell, order.id)
                cell_labels.setdefault(cell, order.name)
                cell_owner.setdefault(cell, order.owner_user_id)
            elif cell.startswith("customer_name:"):
                cell_subjects.setdefault(cell, order.id)
                cell_labels.setdefault(cell, _field_value(_extraction(content), "customer_name") or order.name)
                cell_owner.setdefault(cell, order.owner_user_id)
            assert content.confirmed_by_user_id is not None
            scores[cell][content.confirmed_by_user_id] += CONFIRM_WEIGHT
            event_counts[cell] += 1

    drafts: list[DraftFinding] = []
    for cell, by_user in scores.items():
        if event_counts[cell] < MIN_CONFIRM_EVENTS:
            continue
        total = sum(by_user.values())
        if total <= 0:
            continue
        top_user_id, top_score = max(by_user.items(), key=lambda item: item[1])
        coverage = top_score / total
        if coverage <= CONCENTRATION_THRESHOLD:
            continue
        label = cell_labels.get(cell, cell)
        person = session.get(User, top_user_id)
        who = (person.display_name or person.email) if person else str(top_user_id)
        subject_id = cell_subjects.get(cell)
        if subject_id is None:
            continue
        drafts.append(
            DraftFinding(
                check_key="gap_knowledge_concentration",
                subject_kind="substack",
                subject_id=subject_id,
                owner_user_id=cell_owner.get(cell),
                observed_value=f"{coverage:.2f}",
                threshold_value=str(CONCENTRATION_THRESHOLD),
                summary_sentence=(
                    f"Facts for {label} mostly come from one confirmer ({who}, "
                    f"{int(coverage * 100)}% of confirms)."
                ),
                evidence={
                    "cell": cell,
                    "coverage": round(coverage, 3),
                    "top_confirmer_user_id": str(top_user_id),
                    "confirm_events": event_counts[cell],
                    "confirmer_user_ids": [str(uid) for uid in by_user],
                },
                fingerprint=observed_fingerprint(
                    cell, "gap_knowledge_concentration", str(top_user_id), f"{coverage:.2f}"
                ),
            )
        )
    return drafts


ALL_GAP_CHECKS = (
    gap_missing_field,
    gap_knowledge_concentration,
)


def run_gap_checks(session: Session, organization_id: UUID) -> list:
    """Propose gap findings into the shared To-check queue; commit like run_all_checks."""
    created = []
    for check in ALL_GAP_CHECKS:
        for draft in check(session, organization_id):
            finding = create_finding(
                session,
                organization_id=organization_id,
                check_key=draft.check_key,
                subject_kind=draft.subject_kind,
                subject_id=draft.subject_id,
                summary_sentence=draft.summary_sentence,
                observed_value=draft.observed_value,
                threshold_value=draft.threshold_value,
                evidence=draft.evidence,
                owner_user_id=draft.owner_user_id,
                fingerprint=draft.fingerprint,
            )
            if finding is not None:
                created.append(finding)
    session.commit()
    return created
