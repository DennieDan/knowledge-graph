from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .config import get_settings
from .database import get_session
from .jobs import create_run, enqueue_job, retry_failed_run
from .knowledge_analysis import llm_substacks
from .models import (
    AnalysisRun,
    Chunk,
    Document,
    DocumentVersion,
    EntityMention,
    KnowledgeJob,
    Substack,
    SubstackSource,
    User,
)


router = APIRouter(tags=["analysis"])
ACTIVE_STATUSES = ("queued", "embedding", "discovering", "generating")


def _visible_run(run: AnalysisRun, user: User) -> bool:
    return run.owner_user_id is None or run.owner_user_id == user.id


def _run_json(session: Session, run: AnalysisRun) -> dict:
    generation_counts = dict(session.execute(
        select(KnowledgeJob.status, func.count(KnowledgeJob.id))
        .where(
            KnowledgeJob.analysis_run_id == run.id,
            KnowledgeJob.kind == "generate_substack",
        )
        .group_by(KnowledgeJob.status)
    ).all())
    generation_total = sum(generation_counts.values())
    return {
        "id": str(run.id),
        "organization_id": str(run.organization_id),
        "scope": "mine" if run.owner_user_id else "workspace",
        "trigger": run.trigger,
        "status": run.status,
        "documents_total": run.documents_total,
        "documents_processed": run.documents_processed,
        "chunks_embedded": run.chunks_embedded,
        "candidates_found": run.candidates_found,
        "substacks_created": run.substacks_created,
        "substacks_updated": run.substacks_updated,
        "generation_total": generation_total,
        "generation_completed": generation_counts.get("succeeded", 0),
        "generation_running": generation_counts.get("running", 0),
        "generation_queued": generation_counts.get("queued", 0),
        "generation_failed": generation_counts.get("failed", 0),
        "failures": run.failures,
        "error": run.error_summary,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


class AnalysisRequest(BaseModel):
    # affected: regenerate records found in changed files; selected: substack_ids; all: every LLM record.
    regenerate: Literal["affected", "selected", "all"] = "affected"
    substack_ids: list[UUID] = Field(default_factory=list)


def _owner_filter(column, owner_user_id: UUID | None):
    return column.is_(None) if owner_user_id is None else column == owner_user_id


def _pending_versions(
    session: Session, organization_id: UUID, owner_user_id: UUID | None
) -> list[tuple[Document, DocumentVersion]]:
    """Latest versions whose content has not been discovered yet (new or changed files)."""
    latest_revision = (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    discovered = (
        select(KnowledgeJob.id)
        .where(
            KnowledgeJob.kind == "discover_document",
            KnowledgeJob.status == "succeeded",
            KnowledgeJob.payload["document_version_id"].astext == cast(DocumentVersion.id, String),
        )
        .exists()
    )
    return list(session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Document.organization_id == organization_id,
            _owner_filter(Document.owner_user_id, owner_user_id),
            DocumentVersion.revision == latest_revision,
            ~discovered,
        )
        .order_by(Document.created_at)
        .limit(get_settings().analysis_max_documents)
    ).all())


def _record_json(substack: Substack) -> dict:
    return {
        "id": str(substack.id),
        "name": substack.name,
        "type_id": substack.stack_type,
        "status": substack.status,
        "review_state": substack.review_state,
        "scope": "mine" if substack.owner_user_id else "workspace",
    }


def _enqueue_scope(
    session: Session, organization_id: UUID, owner_user_id: UUID | None, request: AnalysisRequest
) -> AnalysisRun | None:
    active = session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == organization_id,
            _owner_filter(AnalysisRun.owner_user_id, owner_user_id),
            AnalysisRun.trigger == "manual",
            AnalysisRun.status.in_(ACTIVE_STATUSES),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if active is not None:
        return active
    rows = _pending_versions(session, organization_id, owner_user_id)
    regenerate = request.regenerate != "affected"
    if request.regenerate == "selected":
        in_scope = session.scalars(
            llm_substacks(session, organization_id, owner_user_id).where(Substack.id.in_(request.substack_ids))
        ).all() if request.substack_ids else []
        regenerate = bool(in_scope)
    if not rows and not regenerate:
        return None
    run = create_run(session, organization_id, owner_user_id, "manual", documents_total=len(rows))
    settings = get_settings()
    generate = "affected" if request.regenerate == "affected" else "new"
    for _document, version in rows:
        missing = session.scalar(select(func.count(Chunk.id)).where(
            Chunk.document_version_id == version.id,
            or_(Chunk.embedding_model.is_(None), Chunk.embedding_model != settings.embedding_model),
        )) or 0
        kind = "embed_version" if missing else "discover_document"
        enqueue_job(
            session,
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            kind=kind,
            payload={"document_version_id": str(version.id), "generate": generate},
            dedupe_key=f"{kind}:{version.id}:{settings.analysis_config_version}:{settings.openai_model}:run:{run.id}",
            analysis_run_id=run.id,
        )
    if regenerate:
        enqueue_job(
            session,
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            kind="reconcile_scope",
            payload={"mode": request.regenerate, "substack_ids": [str(value) for value in request.substack_ids]},
            dedupe_key=f"regenerate:run:{run.id}",
            analysis_run_id=run.id,
        )
        if not rows:
            run.status = "generating"
    session.commit()
    return run


@router.get("/accounts/{organization_id}/analysis/plan")
def analysis_plan(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """What Analyze would do: changed files, the records they affect, and every regenerable record."""
    membership_for(organization_id, user, session)
    changed = [
        *_pending_versions(session, organization_id, None),
        *_pending_versions(session, organization_id, user.id),
    ]
    records = [
        *session.scalars(llm_substacks(session, organization_id, None)),
        *session.scalars(llm_substacks(session, organization_id, user.id)),
    ]
    records.sort(key=lambda substack: (substack.stack_type, substack.name.lower()))
    changed_ids = [document.id for document, _ in changed]
    affected_ids = set(session.scalars(
        select(EntityMention.substack_id).where(
            EntityMention.document_id.in_(changed_ids),
            EntityMention.substack_id.is_not(None),
        ).union(
            select(SubstackSource.substack_id)
            .join(Substack, Substack.id == SubstackSource.substack_id)
            .where(SubstackSource.document_id.in_(changed_ids), Substack.stack_type == "conversations")
        )
    )) if changed_ids else set()
    return {
        "changed_documents": [
            {
                "id": str(document.id),
                "title": document.title,
                "source": document.source,
                "revision": version.revision,
                "change": "new" if version.revision == 1 else "updated",
            }
            for document, version in changed
        ],
        "affected_records": [_record_json(substack) for substack in records if substack.id in affected_ids],
        "records": [_record_json(substack) for substack in records],
    }


@router.post("/accounts/{organization_id}/analysis")
def start_analysis(
    organization_id: UUID,
    request: AnalysisRequest | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    request = request or AnalysisRequest()
    if request.regenerate == "selected" and not request.substack_ids:
        raise HTTPException(status_code=422, detail="no_records_selected")
    runs = [
        run for run in (
            _enqueue_scope(session, organization_id, None, request),
            _enqueue_scope(session, organization_id, user.id, request),
        )
        if run is not None
    ]
    return [_run_json(session, run) for run in runs]


@router.get("/accounts/{organization_id}/analysis")
def list_analysis(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    runs = session.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == organization_id,
            or_(AnalysisRun.owner_user_id.is_(None), AnalysisRun.owner_user_id == user.id),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(20)
    ).all()
    return [_run_json(session, run) for run in runs]


@router.get("/analysis/{run_id}")
def analysis_detail(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analysis_not_found")
    membership_for(run.organization_id, user, session)
    if not _visible_run(run, user):
        raise HTTPException(status_code=404, detail="analysis_not_found")
    return _run_json(session, run)


@router.post("/analysis/{run_id}/retry")
def retry_analysis(
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analysis_not_found")
    membership_for(run.organization_id, user, session)
    if not _visible_run(run, user):
        raise HTTPException(status_code=404, detail="analysis_not_found")
    queued = retry_failed_run(session, run)
    session.commit()
    return {"queued": queued, "run": _run_json(session, run)}
