"""Turn connector data into documents, versions, and chunks."""
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .chunking import chunk_text
from .config import get_settings
from .embeddings import embed_passages
from .models import Chunk, Document, DocumentVersion


@dataclass(frozen=True)
class SourceDocument:
    """Connector output, normalized to the text that gets chunked."""

    source: str
    external_id: str
    title: str
    content: str
    source_uri: str | None = None


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
        )
        session.add(existing)
        session.flush()
        return existing
    existing.title = document.title
    existing.source_uri = document.source_uri
    return existing


def embed_chunks(chunks: Sequence[Chunk]) -> None:
    """Attach vectors from the configured model. Loads the encoder, so it is slow."""
    if not chunks:
        return
    model = get_settings().embedding_model
    for chunk, vector in zip(chunks, embed_passages(chunk.text for chunk in chunks)):
        chunk.embedding = vector
        chunk.embedding_model = model


def ingest_document(
    session: Session, organization_id: UUID, document: SourceDocument, embed: bool = True
) -> DocumentVersion | None:
    """Store a new revision and its chunks, or return None when the content is unchanged.

    Earlier revisions keep their chunks so retrieval against them stays valid.
    With embed=False the chunks are left for `python -m scripts.reembed`.
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
    chunks = [
        Chunk(document_version_id=version.id, position=position, text=text)
        for position, text in enumerate(chunk_text(content))
    ]
    if embed:
        embed_chunks(chunks)
    session.add_all(chunks)
    session.flush()
    return version


def chunk_count(session: Session, version: DocumentVersion) -> int:
    return session.scalar(
        select(func.count(Chunk.id)).where(Chunk.document_version_id == version.id)
    ) or 0
