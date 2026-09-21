"""Turn connector data into documents, versions, and chunks.

Chunks are stored without embeddings; `python -m scripts.reembed` fills them in.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .chunking import chunk_text
from .models import Chunk, Document, DocumentVersion


@dataclass(frozen=True)
class SourceDocument:
    """Connector output, normalized to the text that gets chunked."""

    source: str
    external_id: str
    title: str
    content: str
    source_uri: str | None = None
    drive_workspace_id: UUID | None = None
    owner_user_id: UUID | None = None


def content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _document_for(session: Session, organization_id: UUID, document: SourceDocument) -> Document:
    existing = session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.source == document.source,
            Document.external_id == document.external_id,
        )
    )
    if existing is None:
        existing = Document(
            organization_id=organization_id,
            source=document.source,
            external_id=document.external_id,
            title=document.title,
            source_uri=document.source_uri,
            drive_workspace_id=document.drive_workspace_id,
            owner_user_id=document.owner_user_id,
        )
        session.add(existing)
        session.flush()
        return existing
    existing.title = document.title
    existing.source_uri = document.source_uri
    existing.drive_workspace_id = document.drive_workspace_id
    existing.owner_user_id = document.owner_user_id
    return existing


def ingest_document(
    session: Session, organization_id: UUID, document: SourceDocument
) -> DocumentVersion | None:
    """Store a new revision and its chunks, or return None when the content is unchanged.

    Earlier revisions keep their chunks so retrieval against them stays valid.
    The caller commits.
    """
    content = document.content.strip()
    if not content:
        return None

    row = _document_for(session, organization_id, document)
    digest = content_hash(content)
    latest = session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == row.id)
        .order_by(DocumentVersion.revision.desc())
        .limit(1)
    )
    if latest is not None and latest.content_hash == digest:
        return None

    version = DocumentVersion(
        document_id=row.id,
        revision=(latest.revision + 1) if latest else 1,
        content_hash=digest,
        content=content,
    )
    session.add(version)
    session.flush()
    session.add_all(
        Chunk(document_version_id=version.id, position=position, text=text)
        for position, text in enumerate(chunk_text(content))
    )
    session.flush()
    return version


def chunk_count(session: Session, version: DocumentVersion) -> int:
    return session.scalar(
        select(func.count(Chunk.id)).where(Chunk.document_version_id == version.id)
    ) or 0
