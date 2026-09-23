from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .config import get_settings
from .database import get_session
from .jobs import create_run, enqueue_job, retry_failed_run
from .models import AnalysisRun, Chunk, Document, DocumentVersion, KnowledgeJob, User


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


def _latest_versions(session: Session, organization_id: UUID, owner_user_id: UUID | None) -> list[tuple[Document, DocumentVersion]]:
    latest_revision = (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    owner_filter = Document.owner_user_id.is_(None) if owner_user_id is None else Document.owner_user_id == owner_user_id
    return list(session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            Document.organization_id == organization_id,
            owner_filter,
            DocumentVersion.revision == latest_revision,
        )
        .order_by(Document.created_at)
        .limit(get_settings().analysis_max_documents)
    ).all())


def _enqueue_scope(session: Session, organization_id: UUID, owner_user_id: UUID | None, trigger: str) -> AnalysisRun:
    active = session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == organization_id,
            AnalysisRun.owner_user_id.is_(None) if owner_user_id is None else AnalysisRun.owner_user_id == owner_user_id,
            AnalysisRun.status.in_(ACTIVE_STATUSES),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if active is not None:
        return active
    rows = _latest_versions(session, organization_id, owner_user_id)
    run = create_run(session, organization_id, owner_user_id, trigger, documents_total=len(rows))
    settings = get_settings()
    for document, version in rows:
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
            payload={"document_version_id": str(version.id)},
            dedupe_key=f"{kind}:{version.id}:{settings.analysis_config_version}:{settings.openai_model}:run:{run.id}",
            analysis_run_id=run.id,
        )
    if not rows:
        run.status = "completed"
    session.commit()
    return run


@router.post("/accounts/{organization_id}/analysis")
def start_analysis(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    runs = [_enqueue_scope(session, organization_id, None, "manual")]
    if _latest_versions(session, organization_id, user.id):
        runs.append(_enqueue_scope(session, organization_id, user.id, "manual"))
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
