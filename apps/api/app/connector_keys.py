"""Connector keys: one named, revocable, read-only key per AI assistant (#94 F-03).

An owner connects Claude or ChatGPT by creating a key here and giving it to the
assistant. The assistant then reads the record over MCP (connector.py) with the
walls of the person who made the key: their company, the private records and
chats only they can see, and their role's field rules.

Keys are refused for planner and supervisor. Their field rules hide prices, and
a record's prose can mention a price outside any price field, so the connector
cannot yet promise those rules on every line. They get keys once field rules
reach the prose (#101).
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .config import get_settings
from .database import get_session
from .models import ConnectorKey, User
from .record_access import PRICE_HIDDEN_ROLES, membership_role

router = APIRouter(tags=["connector"])

KEY_PREFIX = "ck_"
# Settings show this much of a key so people can tell their keys apart.
DISPLAY_CHARS = 10
# last_used_at is a hint for the settings list, not an audit log; write it at most this often.
LAST_USED_EVERY = timedelta(minutes=5)
# Roles that see and switch off every assistant in the company, not only their own.
MANAGER_ROLES = frozenset({"admin", "owner"})


@dataclass(frozen=True)
class ConnectorScope:
    """Who an assistant reads as."""

    key_id: UUID
    organization_id: UUID
    user_id: UUID
    role: str


class ConnectorKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def role_may_connect(role: str | None) -> bool:
    return role is not None and role not in PRICE_HIDDEN_ROLES


def create_key(session: Session, *, organization_id: UUID, user_id: UUID, name: str) -> tuple[ConnectorKey, str]:
    """Store a new key; return the row and the key itself, which is never stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ConnectorKey(
        organization_id=organization_id,
        user_id=user_id,
        name=name.strip()[:120] or "Assistant",
        token_hash=hash_key(key),
        prefix=key[:DISPLAY_CHARS],
    )
    session.add(row)
    session.flush()
    return row, key


def resolve_key(session: Session, key: str | None) -> ConnectorScope | None:
    """The scope a key reads as, or None if it is unknown, switched off or no longer allowed.

    The holder's current membership decides, so removing someone from the company
    or moving them to a price-hidden role cuts their assistants off at once.
    """
    if not key or not key.startswith(KEY_PREFIX):
        return None
    row = session.scalar(select(ConnectorKey).where(ConnectorKey.token_hash == hash_key(key)))
    if row is None or row.revoked_at is not None:
        return None
    role = membership_role(session, row.organization_id, row.user_id)
    if not role_may_connect(role):
        return None
    now = utcnow()
    if row.last_used_at is None or now - row.last_used_at > LAST_USED_EVERY:
        row.last_used_at = now
        session.commit()
    return ConnectorScope(key_id=row.id, organization_id=row.organization_id, user_id=row.user_id, role=role)


def connector_url(request: Request) -> str:
    base = get_settings().public_api_url or str(request.base_url)
    return base.rstrip("/") + "/mcp"


def _key_json(row: ConnectorKey, holder: User | None = None) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.prefix,
        "user_id": str(row.user_id),
        "holder": (holder.display_name or holder.email) if holder is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


@router.get("/accounts/{organization_id}/connector-keys")
def list_connector_keys(
    organization_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Each assistant's access, for the settings list. Managers see the whole company's."""
    membership = membership_for(organization_id, user, session)
    statement = (
        select(ConnectorKey, User)
        .join(User, User.id == ConnectorKey.user_id)
        .where(ConnectorKey.organization_id == organization_id)
    )
    if membership.role not in MANAGER_ROLES:
        statement = statement.where(ConnectorKey.user_id == user.id)
    rows = session.execute(statement.order_by(ConnectorKey.created_at.desc())).all()
    return {
        "url": connector_url(request),
        "can_connect": role_may_connect(membership.role),
        "keys": [_key_json(row, holder) for row, holder in rows],
    }


@router.post("/accounts/{organization_id}/connector-keys", status_code=201)
def create_connector_key(
    organization_id: UUID,
    body: ConnectorKeyIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a key for one assistant. The response is the only time the key is shown."""
    membership = membership_for(organization_id, user, session)
    if not role_may_connect(membership.role):
        raise HTTPException(status_code=403, detail="connector_not_available_for_role")
    row, key = create_key(session, organization_id=organization_id, user_id=user.id, name=body.name)
    session.commit()
    url = connector_url(request)
    return {**_key_json(row, user), "key": key, "url": url, "url_with_key": f"{url}/k/{key}"}


@router.delete("/accounts/{organization_id}/connector-keys/{key_id}")
def revoke_connector_key(
    organization_id: UUID,
    key_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Switch an assistant off. Its next call is refused."""
    membership = membership_for(organization_id, user, session)
    row = session.get(ConnectorKey, key_id)
    if (
        row is None
        or row.organization_id != organization_id
        or (row.user_id != user.id and membership.role not in MANAGER_ROLES)
    ):
        raise HTTPException(status_code=404, detail="connector_key_not_found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        session.commit()
    return _key_json(row)
