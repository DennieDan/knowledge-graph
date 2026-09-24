"""Field-level record access by membership role (#101).

App-layer filter matching issue #9's single enforcement point. Planner and
supervisor never see price-derived claim fields. RLS belongs in a follow-up.

Conflict with main / #9: organization_memberships still accept admin|member
alongside the PRD roles owner|sales|planner|supervisor. Do not delete the
older vocabulary until callers migrate.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import OrganizationMembership

# Keys that are prices or that close over a price (quantity + line_total → unit_price).
PRICE_DERIVED_FIELDS: frozenset[str] = frozenset(
    {
        "unit_price",
        "line_total",
        "price",
        "amount",
        "total",
        "subtotal",
        "currency_amount",
    }
)

# Roles that must never see PRICE_DERIVED_FIELDS on any surface.
PRICE_HIDDEN_ROLES: frozenset[str] = frozenset({"planner", "supervisor"})

MEMBERSHIP_ROLES: frozenset[str] = frozenset(
    {"admin", "member", "owner", "sales", "planner", "supervisor"}
)


def role_may_see_field(role: str | None, field_key: str) -> bool:
    """True when this membership role may read a claim with the given field key."""
    if role in PRICE_HIDDEN_ROLES and field_key in PRICE_DERIVED_FIELDS:
        return False
    return True


def filter_claims_for_role(
    claims: Sequence[Mapping[str, Any]],
    role: str | None,
    *,
    field_key_attr: str = "field_key",
) -> list[Mapping[str, Any]]:
    """Drop claims whose field_key is hidden from the role.

    Accepts dict-like claims. Unknown / legacy roles keep all fields visible
    (admin|member office-staff behaviour from #9).
    """
    return [claim for claim in claims if role_may_see_field(role, _field_key(claim, field_key_attr))]


def membership_role(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
) -> str | None:
    """Return the user's role in the organization, or None if not a member."""
    return session.scalar(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )


def hidden_fields_for_role(role: str | None) -> frozenset[str]:
    """Field keys withheld from this role (empty when the role may see all)."""
    if role in PRICE_HIDDEN_ROLES:
        return PRICE_DERIVED_FIELDS
    return frozenset()


def _field_key(claim: Mapping[str, Any] | Any, attr: str) -> str:
    if isinstance(claim, Mapping):
        value = claim.get(attr, "")
    else:
        value = getattr(claim, attr, "")
    return str(value) if value is not None else ""
