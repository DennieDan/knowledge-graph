"""Generic claim validation against stack field definitions (#97 Step 3).

No per-Stack branches. Returns Finding *specs* only — callers decide whether
to insert findings. UI paths must read via current_claims / current_values,
never by self-joining the claims version table per field.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Claim


@runtime_checkable
class ClaimLike(Protocol):
    value_type: str
    value_text: Optional[str]
    value_numeric: Optional[Decimal]
    value_date: Optional[date]
    value_bool: Optional[bool]


@runtime_checkable
class FieldLike(Protocol):
    key: str
    value_type: str
    required: bool


@dataclass(frozen=True)
class FindingSpec:
    """Lightweight finding proposal — not a DB row."""

    check_key: str
    summary_sentence: str
    field_key: str
    observed_value: str | None = None
    threshold_value: str | None = None


def claim_value(claim: ClaimLike) -> Any | None:
    """Typed column for claim.value_type, or None if missing."""
    if claim.value_type == "text":
        return claim.value_text
    if claim.value_type == "numeric":
        return claim.value_numeric
    if claim.value_type == "date":
        return claim.value_date
    if claim.value_type == "bool":
        return claim.value_bool
    return None


def castable(claim: ClaimLike, value_type: str) -> bool:
    """True when the claim discriminator matches the field's value_type.

    Missing values are not type errors — required_value_missing covers that.
    A mismatched discriminator (e.g. text claim vs numeric field) is not castable.
    """
    if value_type not in ("text", "numeric", "date", "bool"):
        return False
    return claim.value_type == value_type


def validate(claim: ClaimLike | None, field: FieldLike) -> FindingSpec | None:
    """Validate one claim against one field definition. No DB access."""
    if claim is None:
        if field.required:
            return FindingSpec(
                check_key="required_value_missing",
                summary_sentence=f"Required field '{field.key}' has no value.",
                field_key=field.key,
            )
        return None

    value = claim_value(claim)
    if field.required and value is None:
        return FindingSpec(
            check_key="required_value_missing",
            summary_sentence=f"Required field '{field.key}' has no value.",
            field_key=field.key,
            observed_value=None,
            threshold_value=field.value_type,
        )

    if value is not None and not castable(claim, field.value_type):
        return FindingSpec(
            check_key=f"not_a_{field.value_type}",
            summary_sentence=(
                f"Field '{field.key}' expects {field.value_type}, "
                f"got {claim.value_type}."
            ),
            field_key=field.key,
            observed_value=claim.value_type,
            threshold_value=field.value_type,
        )

    return None


def current_claims(session: Session, record_id: UUID) -> list[Claim]:
    """Latest non-retracted claim per field_key (DISTINCT ON).

    Prefer this (or the current_values view) over querying the version table
    from any UI path — reconstructing a record as a self-join per field is
    where the generic value model dies (#97).
    """
    return list(
        session.scalars(
            select(Claim)
            .where(Claim.record_id == record_id, Claim.retracted_at.is_(None))
            .distinct(Claim.field_key)
            .order_by(Claim.field_key, Claim.asserted_at.desc())
        ).all()
    )
