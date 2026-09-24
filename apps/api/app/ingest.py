"""Turn connector data into documents, versions, and chunks.

Chunks are stored without embeddings; `python -m scripts.reembed` fills them in.

#92 Step 3: hash idempotency (skip unchanged content_hash), PDF text-layer
extraction (no OCR), and share-gated callers in drive_sync (`may_see`).
"""
import io
import re
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .chunking import chunk_text
from .models import Chunk, Document, DocumentVersion

PDF_MIME = "application/pdf"


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


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Postgres text columns reject NUL bytes; other C0 controls are noise."""
    return _CONTROL_CHARS.sub("", text)


def content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _minimal_pdf_text_fallback(data: bytes) -> str:
    """Best-effort pull of parentheses strings from a text-layer PDF (no OCR)."""
    # Tj / TJ operands: (...); keep latin-1 so binary noise does not crash.
    text = data.decode("latin-1", errors="replace")
    parts = re.findall(r"\((?:\\.|[^\\)])*\)\s*Tj", text)
    lines: list[str] = []
    for part in parts:
        inner = part[1 : part.rfind(")")]
        inner = (
            inner.replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\\\", "\\")
            .replace("\\n", "\n")
        )
        if inner.strip():
            lines.append(inner)
    return "\n".join(lines)


def extract_pdf_text(data: bytes) -> str:
    """Text-layer PDF extraction only — never OCR. Prefer pypdf when installed."""
    if not data.startswith(b"%PDF"):
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()
    except Exception:
        return _minimal_pdf_text_fallback(data).strip()


def text_from_bytes(data: bytes, mime_type: str | None = None) -> str:
    """Decode download bytes; PDF mime or magic → text-layer extract."""
    if mime_type == PDF_MIME or data.startswith(b"%PDF"):
        return extract_pdf_text(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


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

    Earlier revisions keep their chunks here; `ingest_and_file` drops them once
    stale content has been flagged. The caller commits.
    """
    content = clean_text(document.content).strip()
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


def drop_superseded_chunks(session: Session, document_id: UUID) -> int:
    """Delete chunks of every revision except the latest, so only current text is retrievable."""
    latest_revision = (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == document_id)
        .scalar_subquery()
    )
    superseded = select(DocumentVersion.id).where(
        DocumentVersion.document_id == document_id,
        DocumentVersion.revision < latest_revision,
    )
    return session.execute(delete(Chunk).where(Chunk.document_version_id.in_(superseded))).rowcount or 0


def chunk_count(session: Session, version: DocumentVersion) -> int:
    return session.scalar(
        select(func.count(Chunk.id)).where(Chunk.document_version_id == version.id)
    ) or 0
