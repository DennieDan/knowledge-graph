from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import get_settings
from .embeddings import embed_query
from .models import Chunk, Document, DocumentVersion


RETRIEVAL_VERSION = "hybrid-v1"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    document: Document
    score: float | None = None


def visibility_filter(owner_user_id: UUID | None):
    if owner_user_id is None:
        return Document.owner_user_id.is_(None)
    return or_(Document.owner_user_id.is_(None), Document.owner_user_id == owner_user_id)


def _latest_version_filter():
    return DocumentVersion.revision == (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )


def search_chunks(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    query: str,
    limit: int,
    *,
    document_ids: list[UUID] | None = None,
) -> list[RetrievedChunk]:
    """Rank chunks for a person's query.

    Unlike `retrieve_chunks`, which widens the set with keyword hits and
    neighbouring chunks so a generator has context, every row here is a hit the
    reader asked for, ordered by distance.

    When `document_ids` is set (ask-from-order), ranking is limited to those
    documents so this order's sources come before a company-wide sweep.
    """
    settings = get_settings()
    distance = Chunk.embedding.cosine_distance(embed_query(query))
    filters = [
        Document.organization_id == organization_id,
        visibility_filter(owner_user_id),
        _latest_version_filter(),
        Chunk.embedding.is_not(None),
        Chunk.embedding_model == settings.embedding_model,
    ]
    if document_ids is not None:
        if not document_ids:
            return []
        filters.append(Document.id.in_(document_ids))
    rows = session.execute(
        select(Chunk, Document, distance.label("distance"))
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(*filters)
        .order_by(distance, Chunk.id)
        .limit(limit)
    ).all()
    return [
        RetrievedChunk(chunk=chunk, document=document, score=float(row_distance))
        for chunk, document, row_distance in rows
    ]


def chunks_for_documents(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    document_ids: list[UUID],
    limit: int,
) -> list[RetrievedChunk]:
    """Load embedded chunks from specific documents the asker may read."""
    if not document_ids:
        return []
    settings = get_settings()
    rows = session.execute(
        select(Chunk, Document)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            Document.organization_id == organization_id,
            visibility_filter(owner_user_id),
            _latest_version_filter(),
            Document.id.in_(document_ids),
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == settings.embedding_model,
        )
        .order_by(Chunk.position, Chunk.id)
        .limit(limit)
    ).all()
    return [RetrievedChunk(chunk=chunk, document=document) for chunk, document in rows]


def retrieve_chunks(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    query: str,
    *,
    exact_terms: tuple[str, ...] = (),
) -> list[RetrievedChunk]:
    settings = get_settings()
    vector = embed_query(query)
    distance = Chunk.embedding.cosine_distance(vector)
    base = (
        select(Chunk, Document, distance.label("distance"))
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            Document.organization_id == organization_id,
            visibility_filter(owner_user_id),
            _latest_version_filter(),
            Chunk.embedding.is_not(None),
            Chunk.embedding_model == settings.embedding_model,
        )
    )
    rows = session.execute(base.order_by(distance, Chunk.id).limit(settings.retrieval_limit_per_query)).all()
    result: dict[UUID, RetrievedChunk] = {
        chunk.id: RetrievedChunk(chunk=chunk, document=document, score=float(row_distance))
        for chunk, document, row_distance in rows
    }
    cleaned_terms = tuple(
        term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        for term in exact_terms if term and term.strip()
    )
    if cleaned_terms:
        exact = session.execute(
            select(Chunk, Document)
            .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.organization_id == organization_id,
                visibility_filter(owner_user_id),
                _latest_version_filter(),
                Chunk.embedding.is_not(None),
                Chunk.embedding_model == settings.embedding_model,
                or_(*(Chunk.text.ilike(f"%{term}%", escape="\\") for term in cleaned_terms)),
            )
            .order_by(Chunk.created_at.desc(), Chunk.position)
            .limit(settings.retrieval_limit_per_query)
        ).all()
        for chunk, document in exact:
            result.setdefault(chunk.id, RetrievedChunk(chunk=chunk, document=document))
    seeds = list(result.values())
    if seeds:
        version_positions: dict[UUID, set[int]] = {}
        for item in seeds:
            positions = version_positions.setdefault(item.chunk.document_version_id, set())
            positions.update((item.chunk.position - 1, item.chunk.position + 1))
        for version_id, positions in version_positions.items():
            adjacent = session.execute(
                select(Chunk, Document)
                .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    Chunk.document_version_id == version_id,
                    Chunk.position.in_([position for position in positions if position >= 0]),
                    visibility_filter(owner_user_id),
                )
                .order_by(Chunk.position)
            ).all()
            for chunk, document in adjacent:
                result.setdefault(chunk.id, RetrievedChunk(chunk=chunk, document=document))
    ordered = sorted(result.values(), key=lambda item: (item.score is None, item.score or 0, str(item.chunk.id)))
    return ordered[: settings.retrieval_max_chunks]


def merge_retrieval(results: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    settings = get_settings()
    merged: dict[UUID, RetrievedChunk] = {}
    for group in results:
        for item in group:
            merged.setdefault(item.chunk.id, item)
    return list(merged.values())[: settings.retrieval_max_chunks]


def evidence_text(chunks: list[RetrievedChunk]) -> str:
    maximum = get_settings().retrieval_max_context_chars
    blocks: list[str] = []
    used = 0
    for item in chunks:
        block = f"<evidence chunk_id=\"{item.chunk.id}\" document_id=\"{item.document.id}\" title=\"{item.document.title}\">\n{item.chunk.text}\n</evidence>"
        if used + len(block) > maximum:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
