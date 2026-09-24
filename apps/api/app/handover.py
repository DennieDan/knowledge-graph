"""Handover pack export for clients and sales-orders (#103 / F-12).

The pack surfaces overrides and claims from the record — every item links to a
real claim, content revision, or finding decision. No PDF; JSON and markdown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .gaps import GAP_STACK_TYPES, _extraction, _field_value
from .models import Finding, Substack, SubstackContent, User

Focus = Literal["client", "orders"]

FOCUS_STACK_TYPES: dict[Focus, frozenset[str]] = {
    "client": frozenset({"clients"}),
    "orders": frozenset({"sales-orders"}),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_label(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.email


def _claim_fields(stack_type: str, extraction: dict) -> dict[str, str]:
    """Key claim values for the pack — only non-empty scalar EvidenceValues."""
    keys = {
        "clients": ("name", "registration_number", "customer_id", "payment_terms", "delivery_terms"),
        "sales-orders": (
            "order_number",
            "customer_name",
            "order_date",
            "requested_delivery_date",
            "status",
            "payment_terms",
            "delivery_location",
        ),
    }.get(stack_type, ())
    out: dict[str, str] = {}
    for key in keys:
        value = _field_value(extraction, key)
        if value:
            out[key] = value
    return out


def _field_map(extraction: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in extraction.items():
        if key in ("report", "line_items", "references", "conflicts", "open_questions", "changes", "approvals"):
            continue
        if isinstance(raw, dict) and "value" in raw:
            value = _field_value(extraction, key)
            if value is not None:
                out[key] = value
    return out


def _overrides_for_substack(
    session: Session,
    substack: Substack,
    *,
    user_id: UUID | None,
) -> list[dict]:
    """Field values that changed between a prior revision and a person-confirmed one."""
    revisions = session.scalars(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id)
        .order_by(SubstackContent.revision.asc())
    ).all()
    by_rev = {c.revision: c for c in revisions}
    overrides: list[dict] = []
    for content in revisions:
        if content.status not in ("confirmed", "superseded"):
            continue
        if content.confirmed_by_user_id is None:
            continue
        if user_id is not None and content.confirmed_by_user_id != user_id:
            continue
        prior = by_rev.get(content.revision - 1)
        if prior is None:
            continue
        before = _field_map(_extraction(prior))
        after = _field_map(_extraction(content))
        for key, new_value in after.items():
            old_value = before.get(key)
            if old_value is None or old_value == new_value:
                continue
            confirmer = session.get(User, content.confirmed_by_user_id)
            overrides.append(
                {
                    "substack_id": str(substack.id),
                    "substack_name": substack.name,
                    "stack_type": substack.stack_type,
                    "field": key,
                    "proposed_value": old_value,
                    "confirmed_value": new_value,
                    "content_id": str(content.id),
                    "confirmed_by_user_id": str(content.confirmed_by_user_id),
                    "confirmed_by": _user_label(confirmer),
                    "confirmed_at": content.confirmed_at.isoformat() if content.confirmed_at else None,
                }
            )
    return overrides


def build_handover_pack(
    session: Session,
    organization_id: UUID,
    *,
    focus: Focus,
    user_id: UUID | None = None,
) -> dict:
    stack_types = FOCUS_STACK_TYPES[focus]
    substacks = session.scalars(
        select(Substack).where(
            Substack.organization_id == organization_id,
            Substack.stack_type.in_(stack_types),
        )
    ).all()

    key_claims: list[dict] = []
    overrides: list[dict] = []
    open_work: list[dict] = []
    sole_owner_cells: list[dict] = []

    for substack in substacks:
        confirmed = session.scalar(
            select(SubstackContent)
            .where(
                SubstackContent.substack_id == substack.id,
                SubstackContent.status == "confirmed",
            )
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        if confirmed is not None:
            if user_id is None or confirmed.confirmed_by_user_id == user_id:
                confirmer = (
                    session.get(User, confirmed.confirmed_by_user_id)
                    if confirmed.confirmed_by_user_id
                    else None
                )
                key_claims.append(
                    {
                        "substack_id": str(substack.id),
                        "substack_name": substack.name,
                        "stack_type": substack.stack_type,
                        "content_id": str(confirmed.id),
                        "claims": _claim_fields(substack.stack_type, _extraction(confirmed)),
                        "confirmed_by_user_id": (
                            str(confirmed.confirmed_by_user_id)
                            if confirmed.confirmed_by_user_id
                            else None
                        ),
                        "confirmed_by": _user_label(confirmer),
                    }
                )
        overrides.extend(_overrides_for_substack(session, substack, user_id=user_id))

        if substack.status == "proposed" or substack.review_state in (
            "pending",
            "pending_update",
            "unsupported",
            "generation_error",
        ):
            if user_id is None or substack.created_by_user_id == user_id or substack.owner_user_id == user_id:
                open_work.append(
                    {
                        "substack_id": str(substack.id),
                        "substack_name": substack.name,
                        "stack_type": substack.stack_type,
                        "status": substack.status,
                        "review_state": substack.review_state,
                    }
                )

    # Concentration findings already in the queue for this focus.
    gap_findings = session.scalars(
        select(Finding).where(
            Finding.organization_id == organization_id,
            Finding.check_key == "gap_knowledge_concentration",
            Finding.decision.is_(None),
        )
    ).all()
    focus_ids = {s.id for s in substacks}
    for finding in gap_findings:
        if finding.subject_id not in focus_ids:
            continue
        if user_id is not None:
            top = (finding.evidence or {}).get("top_confirmer_user_id")
            if top != str(user_id):
                continue
        sole_owner_cells.append(
            {
                "finding_id": str(finding.id),
                "subject_id": str(finding.subject_id),
                "summary_sentence": finding.summary_sentence,
                "evidence": finding.evidence or {},
            }
        )

    dismissed = session.scalars(
        select(Finding)
        .where(
            Finding.organization_id == organization_id,
            Finding.decision == "dismissed",
            Finding.check_key.in_(
                (
                    "gap_missing_field",
                    "gap_knowledge_concentration",
                    "source_changed",
                    "record_not_updated_since_threshold",
                    "entity_mentioned_often_but_has_no_record",
                    "referenced_record_not_found",
                    "sources_disagree",
                )
            ),
        )
        .order_by(Finding.decided_at.desc())
        .limit(100)
    ).all()
    # Keep dismissals whose subject is in focus stacks (or gap checks generally).
    dismissed_rows = []
    for finding in dismissed:
        if finding.subject_id in focus_ids or finding.check_key.startswith("gap_"):
            if user_id is not None and finding.decided_by_user_id != user_id:
                # Still include dismissals about this person's sole cells.
                top = (finding.evidence or {}).get("top_confirmer_user_id")
                if top != str(user_id):
                    continue
            dismissed_rows.append(
                {
                    "finding_id": str(finding.id),
                    "check_key": finding.check_key,
                    "summary_sentence": finding.summary_sentence,
                    "dismissal_reason": finding.dismissal_reason,
                    "decided_by_user_id": str(finding.decided_by_user_id) if finding.decided_by_user_id else None,
                    "decided_at": finding.decided_at.isoformat() if finding.decided_at else None,
                    "subject_id": str(finding.subject_id),
                }
            )

    acted = session.scalars(
        select(Finding)
        .where(
            Finding.organization_id == organization_id,
            Finding.decision.in_(("acted", "confirmed")),
        )
        .order_by(Finding.decided_at.desc())
        .limit(100)
    ).all()
    confirmed_fixes = []
    for finding in acted:
        if finding.subject_id not in focus_ids and not finding.check_key.startswith("gap_"):
            continue
        if user_id is not None and finding.decided_by_user_id != user_id:
            continue
        confirmed_fixes.append(
            {
                "finding_id": str(finding.id),
                "check_key": finding.check_key,
                "summary_sentence": finding.summary_sentence,
                "decision": finding.decision,
                "decided_by_user_id": str(finding.decided_by_user_id) if finding.decided_by_user_id else None,
                "decided_at": finding.decided_at.isoformat() if finding.decided_at else None,
                "subject_id": str(finding.subject_id),
            }
        )

    focus_user = session.get(User, user_id) if user_id else None
    return {
        "organization_id": str(organization_id),
        "focus": focus,
        "stack_types": sorted(stack_types),
        "generated_at": utcnow().isoformat(),
        "user_id": str(user_id) if user_id else None,
        "user_label": _user_label(focus_user),
        "sole_owner_cells": sole_owner_cells,
        "overrides": overrides,
        "confirmed_fixes": confirmed_fixes,
        "dismissed_findings": dismissed_rows,
        "key_claims": key_claims,
        "open_work": open_work,
        # Gap scope constant kept for clients of the pack.
        "gap_stack_types": sorted(GAP_STACK_TYPES),
    }


def pack_to_markdown(pack: dict) -> str:
    focus = pack["focus"]
    title = "Clients" if focus == "client" else "Sales orders"
    who = pack.get("user_label") or "org"
    lines = [
        f"# Handover pack — {title}",
        "",
        f"Generated: {pack['generated_at']}",
        f"Focus: {focus} · Subject: {who}",
        "",
        "## Overrides (confirmed value ≠ prior proposal)",
        "",
    ]
    if not pack["overrides"]:
        lines.append("_None._")
    else:
        for row in pack["overrides"]:
            lines.append(
                f"- **{row['substack_name']}** `{row['field']}`: "
                f"`{row['proposed_value']}` → `{row['confirmed_value']}` "
                f"(content `{row['content_id']}`, by {row.get('confirmed_by') or 'unknown'})"
            )
    lines.extend(["", "## Confirmed fixes (acted findings)", ""])
    if not pack["confirmed_fixes"]:
        lines.append("_None._")
    else:
        for row in pack["confirmed_fixes"]:
            lines.append(
                f"- [{row['check_key']}] {row['summary_sentence']} "
                f"(finding `{row['finding_id']}`, decision `{row['decision']}`)"
            )
    lines.extend(["", "## Dismissed findings", ""])
    if not pack["dismissed_findings"]:
        lines.append("_None._")
    else:
        for row in pack["dismissed_findings"]:
            lines.append(
                f"- [{row['check_key']}] {row['summary_sentence']} "
                f"— reason: `{row['dismissal_reason']}` (finding `{row['finding_id']}`)"
            )
    lines.extend(["", "## Key claims", ""])
    if not pack["key_claims"]:
        lines.append("_None._")
    else:
        for row in pack["key_claims"]:
            claims = ", ".join(f"{k}={v}" for k, v in (row.get("claims") or {}).items()) or "(no scalar claims)"
            lines.append(
                f"- **{row['substack_name']}** (`{row['stack_type']}`, content `{row['content_id']}`): {claims}"
            )
    lines.extend(["", "## Sole-owner cells (open gap findings)", ""])
    if not pack["sole_owner_cells"]:
        lines.append("_None._")
    else:
        for row in pack["sole_owner_cells"]:
            lines.append(f"- {row['summary_sentence']} (finding `{row['finding_id']}`)")
    lines.extend(["", "## Open work", ""])
    if not pack["open_work"]:
        lines.append("_None._")
    else:
        for row in pack["open_work"]:
            lines.append(
                f"- **{row['substack_name']}** — status `{row['status']}`, review `{row['review_state']}`"
            )
    lines.append("")
    return "\n".join(lines)
