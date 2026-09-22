"""Stacks read API: All Stacks for an organization.

Substacks are org-scoped; visibility is owner-only (`owner_user_id` set) or
org-wide (NULL). Responses mirror the frontend's Substack/SubstackDetail
shapes so the Stacks tab can swap mock data for real rows 1:1.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .filing import file_document, substack_for_document
from .models import (
    STACK_TYPES,
    Document,
    DocumentVersion,
    DriveWorkspace,
    Substack,
    SubstackContent,
    SubstackLink,
    SubstackSource,
    User,
)

router = APIRouter(tags=["stacks"])

SOURCE_LABELS = {"google_drive": "Google Drive", "whatsapp": "WhatsApp"}


class SubstackIn(BaseModel):
    stack_type: str
    name: str
    summary: str | None = None


class SubstackPatch(BaseModel):
    name: str | None = None
    summary: str | None = None


def _visible(user: User):
    return or_(Substack.owner_user_id.is_(None), Substack.owner_user_id == user.id)


def _get_substack(substack_id: UUID, user: User, session: Session) -> Substack:
    substack = session.get(Substack, substack_id)
    if substack is None:
        raise HTTPException(status_code=404, detail="substack_not_found")
    membership_for(substack.organization_id, user, session)
    if substack.owner_user_id is not None and substack.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="substack_not_found")
    return substack


def _source_json(session: Session, source: SubstackSource, current_substack_id: UUID) -> dict:
    document = session.get(Document, source.document_id)
    if document is None:
        return {"id": str(source.id), "role": source.role}
    origin = SOURCE_LABELS.get(document.source, document.source)
    if document.drive_workspace_id:
        workspace = session.get(DriveWorkspace, document.drive_workspace_id)
        if workspace is not None:
            origin = f"{origin} · {workspace.name}"
    latest = session.scalar(
        select(DocumentVersion.created_at)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.revision.desc())
        .limit(1)
    )
    filed = substack_for_document(session, document)
    return {
        "id": str(source.id),
        "document_id": str(document.id),
        "substack_id": str(filed.id) if filed is not None and filed.id != current_substack_id else None,
        "name": document.title,
        "origin": origin,
        "updated": (latest or document.created_at).isoformat() if (latest or document.created_at) else None,
        "role": source.role,
    }


def _substack_json(session: Session, substack: Substack, user: User) -> dict:
    sources = session.scalars(
        select(SubstackSource).where(SubstackSource.substack_id == substack.id)
    ).all()
    return {
        "id": str(substack.id),
        "type_id": substack.stack_type,
        "name": substack.name,
        "desc": substack.summary,
        "scope": "mine" if substack.owner_user_id == user.id else "workspace",
        "status": substack.status,
        "updated_at": substack.updated_at.isoformat() if substack.updated_at else None,
        "count": len(sources),
        "docs": [_source_json(session, s, substack.id)["name"] for s in sources],
    }


@router.get("/accounts/{organization_id}/stacks")
def list_stacks(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    counts = dict(
        session.execute(
            select(Substack.stack_type, func.count(Substack.id))
            .where(Substack.organization_id == organization_id, _visible(user))
            .group_by(Substack.stack_type)
        ).all()
    )
    return [{"type": stack_type, "count": counts.get(stack_type, 0)} for stack_type in STACK_TYPES]


@router.get("/accounts/{organization_id}/substacks")
def list_substacks(
    organization_id: UUID,
    type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    statement = select(Substack).where(Substack.organization_id == organization_id, _visible(user))
    if type:
        statement = statement.where(Substack.stack_type == type)
    if q:
        statement = statement.where(Substack.name.ilike(f"%{q}%"))
    substacks = session.scalars(statement.order_by(Substack.updated_at.desc())).all()
    return [_substack_json(session, substack, user) for substack in substacks]


@router.get("/substacks/{substack_id}")
def substack_detail(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    content = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id)
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    sources = session.scalars(
        select(SubstackSource).where(SubstackSource.substack_id == substack.id)
    ).all()
    related_ids = {
        row[0]
        for row in session.execute(
            select(SubstackLink.related_substack_id).where(SubstackLink.substack_id == substack.id)
            .union(
                select(SubstackLink.substack_id).where(SubstackLink.related_substack_id == substack.id)
            )
        ).all()
    }
    related = [
        {"id": str(other.id), "type_id": other.stack_type, "name": other.name}
        for other in session.scalars(
            select(Substack).where(Substack.id.in_(related_ids), _visible(user))
        ).all()
    ] if related_ids else []
    detail = _substack_json(session, substack, user)
    detail.update({
        "content": content.content if content else {"segments": [], "entries": []},
        "content_status": content.status if content else None,
        "sources": [_source_json(session, s, substack.id) for s in sources],
        "related": related,
    })
    return detail


@router.post("/accounts/{organization_id}/substacks")
def create_substack(
    organization_id: UUID,
    body: SubstackIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    if body.stack_type not in STACK_TYPES:
        raise HTTPException(status_code=422, detail="invalid_stack_type")
    substack = Substack(
        organization_id=organization_id,
        stack_type=body.stack_type,
        name=body.name.strip() or "Untitled",
        summary=body.summary,
        created_by="user",
        created_by_user_id=user.id,
        status="confirmed",
    )
    session.add(substack)
    session.commit()
    return _substack_json(session, substack, user)


@router.patch("/substacks/{substack_id}")
def update_substack(
    substack_id: UUID,
    body: SubstackPatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    if body.name is not None:
        substack.name = body.name.strip() or substack.name
    if body.summary is not None:
        substack.summary = body.summary
    session.commit()
    return _substack_json(session, substack, user)


@router.post("/substacks/{substack_id}/confirm")
def confirm_substack(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    substack.status = "confirmed"
    latest = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id)
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if latest is not None and latest.status == "proposed":
        latest.status = "confirmed"
    session.commit()
    return _substack_json(session, substack, user)


@router.post("/accounts/{organization_id}/stacks/file-all")
def file_all(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Backfill: file every org document that has no substack yet."""
    membership_for(organization_id, user, session)
    unfiled = session.scalars(
        select(Document)
        .outerjoin(SubstackSource, SubstackSource.document_id == Document.id)
        .where(Document.organization_id == organization_id, SubstackSource.id.is_(None))
    ).all()
    filed = [substack.id for document in unfiled if (substack := file_document(session, document)) is not None]
    session.commit()
    return {"filed": len(filed)}
