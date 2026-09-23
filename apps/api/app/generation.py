"""Generation pipeline: evidence -> generator -> stored, citable content.

- Evidence is the latest document_version's chunks for each source document.
- `inputs_fingerprint` hashes the input revision ids so unchanged evidence
  skips regeneration.
- Every citation in generator output must reference an input chunk; anything
  else is dropped and logged on the generation run — this is the guardrail
  that stops a future LLM generator from fabricating evidence.
- `mark_stale_for_document` flags content citing a document's older revisions
  so the next ingest of that document triggers regeneration.
"""
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import generators
from .models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    GenerationRun,
    Substack,
    SubstackContent,
    SubstackSource,
)
from .segments import GeneratedContent

TEMPLATE_MODEL = "template"


def _evidence(session: Session, substack: Substack) -> tuple[list[Document], list[DocumentVersion], list[Chunk]]:
    """Source documents plus their latest revision and that revision's chunks."""
    documents = session.scalars(
        select(Document)
        .join(SubstackSource, SubstackSource.document_id == Document.id)
        .where(SubstackSource.substack_id == substack.id)
    ).all()
    versions: list[DocumentVersion] = []
    chunks: list[Chunk] = []
    for document in documents:
        version = session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.revision.desc())
            .limit(1)
        )
        if version is None:
            continue
        versions.append(version)
        chunks.extend(
            session.scalars(
                select(Chunk)
                .where(Chunk.document_version_id == version.id)
                .order_by(Chunk.position)
            ).all()
        )
    return documents, versions, chunks


def _fingerprint(versions: list[DocumentVersion]) -> str:
    return sha256("|".join(sorted(str(v.id) for v in versions)).encode()).hexdigest()


def _validate(output: GeneratedContent, input_chunk_ids: set[str]) -> int:
    """Drop citations that are not in the input evidence set; returns drop count."""
    dropped = 0
    for item in (*output.segments, *output.entries):
        valid = [c for c in item.citations if c in input_chunk_ids]
        dropped += len(item.citations) - len(valid)
        item.citations = valid
    return dropped


def _latest_content(session: Session, substack_id: UUID) -> SubstackContent | None:
    return session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack_id)
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )


def run_generation(session: Session, substack: Substack) -> SubstackContent | None:
    """Generate and store the next content revision. The caller commits."""
    prompt_key = generators.prompt_key_for(substack.stack_type)
    generate, auto_confirm = generators.GENERATORS[prompt_key]
    version_label = generators.prompt_version(prompt_key)
    documents, versions, chunks = _evidence(session, substack)
    fingerprint = _fingerprint(versions)
    latest = _latest_content(session, substack.id)
    if latest is not None and latest.inputs_fingerprint == fingerprint and latest.status != "stale":
        return latest

    version_document = {version.id: version.document_id for version in versions}
    context = generators.GenerationContext(
        session=session,
        substack=substack,
        documents=documents,
        chunks=chunks,
        chunk_document={chunk.id: version_document[chunk.document_version_id] for chunk in chunks},
    )
    input_chunk_ids = sorted(str(chunk.id) for chunk in chunks)
    run = GenerationRun(
        substack_id=substack.id,
        prompt_key=prompt_key,
        prompt_version=version_label,
        model=TEMPLATE_MODEL,
        input_chunk_ids=input_chunk_ids,
    )
    try:
        output = generate(context)
    except Exception as exc:  # a failed template must not break ingestion
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"[:500]
        session.add(run)
        session.flush()
        return None

    dropped = _validate(output, set(input_chunk_ids))
    content = SubstackContent(
        substack_id=substack.id,
        revision=(latest.revision + 1) if latest else 1,
        prompt_key=prompt_key,
        prompt_version=version_label,
        model=TEMPLATE_MODEL,
        content=output.model_dump(),
        status="confirmed" if auto_confirm else "proposed",
        inputs_fingerprint=fingerprint,
    )
    session.add(content)
    session.flush()
    if latest is not None:
        latest.status = "stale"

    chunk_document = {str(chunk_id): document_id for chunk_id, document_id in context.chunk_document.items()}
    index = 0
    for item in (*output.segments, *output.entries):
        for chunk_id in item.citations:
            session.add(ContentCitation(
                content_id=content.id,
                segment_index=index,
                chunk_id=UUID(chunk_id),
                document_id=chunk_document[chunk_id],
                locator=item.locator,
            ))
        index += 1

    run.output = output.model_dump()
    if dropped:
        run.error = f"dropped {dropped} citation(s) outside the evidence set"
    session.add(run)
    session.flush()
    return content


def mark_stale_for_document(session: Session, document_id: UUID) -> list[UUID]:
    """Flag contents citing a document's older revisions after a new one lands.

    Only citations pointing at chunks from superseded revisions count — content
    already regenerated against the latest revision is left alone. Returns the
    affected substack ids so the caller can regenerate them.
    """
    latest_revision = (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == document_id)
        .scalar_subquery()
    )
    contents = session.scalars(
        select(SubstackContent)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .join(Chunk, ContentCitation.chunk_id == Chunk.id)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.revision < latest_revision,
            SubstackContent.status != "stale",
        )
    ).all()
    substacks: dict[UUID, None] = {}
    for content in contents:
        substack = session.get(Substack, content.substack_id)
        if substack is not None and substack.stack_type in ("sales-orders", "clients", "items"):
            substack.review_state = "pending_update" if substack.status == "confirmed" else "pending"
        else:
            content.status = "stale"
        substacks[content.substack_id] = None
    return list(substacks)
