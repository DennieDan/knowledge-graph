"""Deterministic filing: every ingested document becomes a substack.

One document -> one substack (1:1 today; LLM-stage merging is future work):
- google_drive documents -> "files" substacks
- whatsapp documents     -> "conversations" substacks

`ingest_and_file` is the post-ingest hook: after a new document_revision
lands it files the document, regenerates its substack's content, and
marks+regenerates any other substack citing the superseded revision.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .embedding_jobs import enqueue_version_embedding
from .generation import mark_stale_for_document, run_generation
from .ingest import SourceDocument, ingest_document
from .models import Document, DocumentVersion, Substack, SubstackSource

STACK_TYPE_FOR_SOURCE = {
    "google_drive": "files",
    "whatsapp": "conversations",
}


def _document(session: Session, organization_id: UUID, source: str, external_id: str) -> Document | None:
    return session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.source == source,
            Document.external_id == external_id,
        )
    )


def substack_for_document(session: Session, document: Document) -> Substack | None:
    return session.scalar(
        select(Substack)
        .join(SubstackSource, SubstackSource.substack_id == Substack.id)
        .where(SubstackSource.document_id == document.id)
    )


def file_document(session: Session, document: Document) -> Substack | None:
    """File a document into its stack type and (re)generate content. Idempotent."""
    stack_type = STACK_TYPE_FOR_SOURCE.get(document.source)
    if stack_type is None:
        return None
    substack = substack_for_document(session, document)
    if substack is None:
        substack = Substack(
            organization_id=document.organization_id,
            stack_type=stack_type,
            name=document.title,
            owner_user_id=document.owner_user_id,
            created_by="system",
        )
        session.add(substack)
        session.flush()
        session.add(SubstackSource(substack_id=substack.id, document_id=document.id))
        session.flush()
    else:
        substack.name = document.title
    run_generation(session, substack)
    return substack


def ingest_and_file(session: Session, organization_id: UUID, source_document: SourceDocument) -> DocumentVersion | None:
    """Ingest a document, then file it and refresh everything citing it. Caller commits."""
    version = ingest_document(session, organization_id, source_document)
    if version is None:
        return None
    document = _document(session, organization_id, source_document.source, source_document.external_id)
    if document is not None:
        file_document(session, document)
        for substack_id in mark_stale_for_document(session, document.id):
            stale = session.get(Substack, substack_id)
            if stale is not None and stale.stack_type in ("files", "conversations"):
                run_generation(session, stale)
        enqueue_version_embedding(session, version, document)
    return version
