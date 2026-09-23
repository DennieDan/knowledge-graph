"""Embedding job creation and execution."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .embeddings import embed_passages
from .jobs import create_run, enqueue_job
from .models import AnalysisRun, Chunk, Document, DocumentVersion


def enqueue_version_embedding(session: Session, version: DocumentVersion, document: Document) -> AnalysisRun:
    settings = get_settings()
    owner_filter = AnalysisRun.owner_user_id.is_(None) if document.owner_user_id is None else AnalysisRun.owner_user_id == document.owner_user_id
    run = session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == document.organization_id,
            owner_filter,
            AnalysisRun.trigger == "ingest",
            AnalysisRun.status.in_(("queued", "embedding", "discovering", "generating")),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        run = create_run(
            session,
            document.organization_id,
            document.owner_user_id,
            "ingest",
            documents_total=1,
        )
    else:
        run.documents_total += 1
    enqueue_job(
        session,
        organization_id=document.organization_id,
        owner_user_id=document.owner_user_id,
        kind="embed_version",
        payload={"document_version_id": str(version.id)},
        dedupe_key=f"embed:{version.id}:{settings.embedding_model}",
        analysis_run_id=run.id,
    )
    return run


def embed_document_version(session: Session, version_id: UUID, run_id: UUID | None) -> int:
    settings = get_settings()
    run = session.get(AnalysisRun, run_id) if run_id else None
    if run is not None:
        run.status = "embedding"
        session.commit()
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError("document_version_not_found")
    document = session.get(Document, version.document_id)
    if document is None:
        raise ValueError("document_not_found")
    chunks = session.scalars(
        select(Chunk)
        .where(
            Chunk.document_version_id == version.id,
            (Chunk.embedding_model.is_(None) | (Chunk.embedding_model != settings.embedding_model)),
        )
        .order_by(Chunk.position)
    ).all()
    total = 0
    for start in range(0, len(chunks), settings.embedding_batch_size):
        batch = chunks[start : start + settings.embedding_batch_size]
        vectors = embed_passages(chunk.text for chunk in batch)
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector
            chunk.embedding_model = settings.embedding_model
        session.commit()
        total += len(batch)
    run = session.get(AnalysisRun, run_id) if run_id else None
    if run is not None:
        run.status = "discovering"
        run.chunks_embedded += total
    enqueue_job(
        session,
        organization_id=document.organization_id,
        owner_user_id=document.owner_user_id,
        kind="discover_document",
        payload={"document_version_id": str(version.id)},
        dedupe_key=f"discover:{version.id}:{settings.analysis_config_version}:{settings.openai_model}",
        analysis_run_id=run_id,
    )
    session.commit()
    return total
