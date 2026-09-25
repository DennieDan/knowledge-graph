"""Stacks read API: All Stacks for an organization.

Substacks are org-scoped; visibility is owner-only (`owner_user_id` set) or
org-wide (NULL). Responses mirror the frontend's Substack/SubstackDetail
shapes so the Stacks tab can swap mock data for real rows 1:1.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .filing import file_document, substack_for_document
from .jobs import enqueue_job
from .knowledge_analysis import DESCRIBABLE_STACK_TYPES
from .models import (
    ACTIVE_STACK_TYPES,
    ConfirmEvent,
    ContentCitation,
    Document,
    DocumentVersion,
    DriveWorkspace,
    KnowledgeJob,
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
    # Generate the record's content from the knowledge base, using `summary` as the user's description.
    generate: bool = False


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
        # The document id is the source id: token source_ids reference it directly.
        "id": str(document.id),
        "document_id": str(document.id),
        "substack_id": str(filed.id) if filed is not None and filed.id != current_substack_id else None,
        "name": document.title,
        "type": "Conversations" if document.source == "whatsapp" else "Files",
        "origin": origin,
        "updated": (latest or document.created_at).isoformat() if (latest or document.created_at) else None,
        "role": source.role,
    }


def _generating_ids(session: Session, substack_ids: list[UUID]) -> set[str]:
    """Substacks with a queued or running generation job."""
    if not substack_ids:
        return set()
    substack_id = KnowledgeJob.payload["substack_id"].astext
    return set(session.scalars(
        select(substack_id).where(
            KnowledgeJob.kind == "generate_substack",
            KnowledgeJob.status.in_(("queued", "running")),
            substack_id.in_([str(value) for value in substack_ids]),
        )
    ))


def _substack_json(session: Session, substack: Substack, user: User, generating: set[str] | None = None) -> dict:
    sources = session.scalars(
        select(SubstackSource).where(SubstackSource.substack_id == substack.id)
    ).all()
    if generating is None:
        generating = _generating_ids(session, [substack.id])
    return {
        "id": str(substack.id),
        "type_id": substack.stack_type,
        "name": substack.name,
        "desc": substack.summary,
        "scope": "mine" if substack.owner_user_id == user.id else "workspace",
        "status": substack.status,
        "review_state": substack.review_state,
        "generating": str(substack.id) in generating,
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
    return [{"type": stack_type, "count": counts.get(stack_type, 0)} for stack_type in ACTIVE_STACK_TYPES]


@router.get("/accounts/{organization_id}/substacks")
def list_substacks(
    organization_id: UUID,
    type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    statement = select(Substack).where(
        Substack.organization_id == organization_id, _visible(user), Substack.stack_type.in_(ACTIVE_STACK_TYPES),
    )
    if type:
        statement = statement.where(Substack.stack_type == type)
    if q:
        statement = statement.where(Substack.name.ilike(f"%{q}%"))
    substacks = session.scalars(statement.order_by(Substack.updated_at.desc())).all()
    generating = _generating_ids(session, [substack.id for substack in substacks])
    return [_substack_json(session, substack, user, generating) for substack in substacks]


def _content_payload(session: Session, content: SubstackContent | None) -> dict:
    payload = dict(content.content) if content else {"segments": [], "entries": []}
    if content is None:
        return payload
    segment_documents: dict[int, set[str]] = {}
    for segment_index, document_id in session.execute(
        select(ContentCitation.segment_index, ContentCitation.document_id)
        .where(ContentCitation.content_id == content.id)
    ).all():
        segment_documents.setdefault(segment_index, set()).add(str(document_id))
    offset = len(payload.get("segments", []))
    for index, item in enumerate(payload.get("segments", [])):
        item["source_ids"] = sorted(segment_documents.get(index, set()))
    for index, item in enumerate(payload.get("entries", [])):
        item["source_ids"] = sorted(segment_documents.get(offset + index, set()))
    payload["id"] = str(content.id)
    payload["revision"] = content.revision
    payload["status"] = content.status
    payload["confirmed_at"] = content.confirmed_at.isoformat() if content.confirmed_at else None
    confirmer = (
        session.get(User, content.confirmed_by_user_id)
        if content.confirmed_by_user_id is not None
        else None
    )
    payload["confirmed_by"] = (
        (confirmer.display_name or confirmer.email) if confirmer is not None else None
    )
    return payload


def _content_pair(session: Session, substack_id: UUID) -> tuple[SubstackContent | None, SubstackContent | None]:
    confirmed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack_id, SubstackContent.status == "confirmed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    proposed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack_id, SubstackContent.status == "proposed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if confirmed is None:
        return proposed, None
    if proposed is not None and proposed.revision > confirmed.revision:
        return confirmed, proposed
    return confirmed, None


@router.get("/substacks/{substack_id}")
def substack_detail(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    content, pending = _content_pair(session, substack.id)
    sources = session.scalars(
        select(SubstackSource).where(SubstackSource.substack_id == substack.id)
    ).all()

    # Attach the cited document ids to each segment/entry so the UI can filter
    # the Sources panel on token hover. Entries are indexed after segments.
    content_payload = _content_payload(session, content)

    # Related = explicit links both ways, plus substacks whose generated
    # content cites this substack's evidence documents (e.g. a Files record
    # sees every record built on its file).
    related_ids = {
        row[0]
        for row in session.execute(
            select(SubstackLink.related_substack_id).where(SubstackLink.substack_id == substack.id)
            .union(
                select(SubstackLink.substack_id).where(SubstackLink.related_substack_id == substack.id)
            )
        ).all()
    }
    document_ids = [source.document_id for source in sources]
    if document_ids:
        citing = session.scalars(
            select(Substack.id)
            .join(SubstackContent, SubstackContent.substack_id == Substack.id)
            .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
            .where(ContentCitation.document_id.in_(document_ids), Substack.id != substack.id)
            .distinct()
        ).all()
        related_ids.update(citing)
    related = [
        {"id": str(other.id), "type_id": other.stack_type, "name": other.name}
        for other in session.scalars(
            select(Substack).where(Substack.id.in_(related_ids), _visible(user))
        ).all()
    ] if related_ids else []
    detail = _substack_json(session, substack, user)
    detail.update({
        "content": content_payload,
        "content_status": content.status if content else None,
        "pending_content": _content_payload(session, pending) if pending else None,
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
    if body.stack_type not in ACTIVE_STACK_TYPES:
        raise HTTPException(status_code=422, detail="invalid_stack_type")
    description = (body.summary or "").strip()
    if body.generate:
        if body.stack_type not in DESCRIBABLE_STACK_TYPES:
            raise HTTPException(status_code=422, detail="generation_unsupported_stack_type")
        if not description:
            raise HTTPException(status_code=422, detail="description_required")
    substack = Substack(
        organization_id=organization_id,
        # Generated records may draw on the creator's private files, so they start owner-only.
        owner_user_id=user.id if body.generate else None,
        stack_type=body.stack_type,
        name=body.name.strip() or "Untitled",
        summary=description if body.generate else body.summary,
        created_by="user",
        created_by_user_id=user.id,
        status="proposed" if body.generate else "confirmed",
        review_state="pending" if body.generate else "clean",
    )
    session.add(substack)
    session.flush()
    if body.generate:
        enqueue_job(
            session,
            organization_id=organization_id,
            owner_user_id=user.id,
            kind="generate_substack",
            payload={"substack_id": str(substack.id), "force": True},
            dedupe_key=f"describe:{substack.id}",
        )
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


@router.post("/substacks/{substack_id}/retry-generation")
def retry_generation(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Queue a fresh forced generation for a record whose last generation failed."""
    substack = _get_substack(substack_id, user, session)
    if substack.review_state != "generation_error":
        raise HTTPException(status_code=409, detail="generation_not_failed")
    if not _generating_ids(session, [substack.id]):
        enqueue_job(
            session,
            organization_id=substack.organization_id,
            owner_user_id=substack.owner_user_id,
            kind="generate_substack",
            payload={"substack_id": str(substack.id), "force": True},
            dedupe_key=f"retry:{substack.id}:{uuid4()}",
        )
        session.commit()
    return _substack_json(session, substack, user)


@router.delete("/substacks/{substack_id}")
def delete_substack(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    session.delete(substack)
    session.commit()
    return {"status": "deleted"}


def _confirm_content(
    session: Session,
    substack: Substack,
    content: SubstackContent,
    user: User | None = None,
    *,
    kind: str = "person",
) -> None:
    """kind is 'person' (one item), 'bulk' (confirm-all) or 'auto' (a generator confirmed its own output)."""
    latest_proposed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id, SubstackContent.status == "proposed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if content.status != "proposed" or latest_proposed is None or latest_proposed.id != content.id:
        raise HTTPException(status_code=409, detail="content_not_current_proposal")
    confirmed = session.scalars(
        select(SubstackContent).where(
            SubstackContent.substack_id == substack.id,
            SubstackContent.status == "confirmed",
        )
    ).all()
    for previous in confirmed:
        previous.status = "superseded"
    content.status = "confirmed"
    content.confirmed_by_user_id = user.id if user is not None else None
    content.confirmed_at = datetime.now(timezone.utc)
    substack.status = "confirmed"
    substack.review_state = "clean"
    session.add(
        ConfirmEvent(
            organization_id=substack.organization_id,
            substack_id=substack.id,
            content_id=content.id,
            kind=kind,
            by_user_id=user.id if user is not None else None,
        )
    )


@router.post("/substacks/{substack_id}/contents/{content_id}/confirm")
def confirm_content(
    substack_id: UUID,
    content_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    content = session.get(SubstackContent, content_id)
    if content is None or content.substack_id != substack.id:
        raise HTTPException(status_code=404, detail="content_not_found")
    _confirm_content(session, substack, content, user)
    session.commit()
    return _substack_json(session, substack, user)


@router.post("/substacks/{substack_id}/contents/{content_id}/keep-current")
def keep_current_content(
    substack_id: UUID,
    content_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Dismiss a proposed update; the confirmed content stays current."""
    substack = _get_substack(substack_id, user, session)
    confirmed, pending = _content_pair(session, substack.id)
    if pending is None or pending.id != content_id or confirmed is None or confirmed.status != "confirmed":
        raise HTTPException(status_code=409, detail="content_not_current_proposal")
    pending.status = "superseded"
    substack.review_state = "clean"
    session.commit()
    return _substack_json(session, substack, user)


@router.post("/substacks/{substack_id}/confirm")
def confirm_substack(
    substack_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    substack = _get_substack(substack_id, user, session)
    proposed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id, SubstackContent.status == "proposed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if proposed is not None:
        _confirm_content(session, substack, proposed, user)
    else:
        substack.status = "confirmed"
        substack.review_state = "clean"
        session.add(
            ConfirmEvent(
                organization_id=substack.organization_id,
                substack_id=substack.id,
                content_id=None,
                kind="person",
                by_user_id=user.id,
            )
        )
    session.commit()
    return _substack_json(session, substack, user)


@router.post("/accounts/{organization_id}/substacks/confirm-all")
def confirm_all(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Dev helper: confirm every substack's latest proposed content."""
    membership_for(organization_id, user, session)
    substacks = session.scalars(
        select(Substack).where(Substack.organization_id == organization_id)
    ).all()
    confirmed_count = 0
    for substack in substacks:
        proposed = session.scalar(
            select(SubstackContent)
            .where(SubstackContent.substack_id == substack.id, SubstackContent.status == "proposed")
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        if proposed is not None:
            _confirm_content(session, substack, proposed, user, kind="bulk")
            confirmed_count += 1
        elif substack.status != "confirmed" or substack.review_state in ("pending", "pending_update"):
            substack.status = "confirmed"
            if substack.review_state in ("pending", "pending_update"):
                substack.review_state = "clean"
            session.add(
                ConfirmEvent(
                    organization_id=substack.organization_id,
                    substack_id=substack.id,
                    content_id=None,
                    kind="bulk",
                    by_user_id=user.id,
                )
            )
            confirmed_count += 1
    session.commit()
    return {"confirmed": confirmed_count}


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
