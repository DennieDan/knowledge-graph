from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .entity_resolution import resolve_candidate
from .extractions import ClientExtraction, DiscoveryOutput, ItemExtraction, SalesOrderExtraction
from .jobs import JobNotReady, complete_run_if_last, enqueue_job
from .llm import LLMResult, get_llm_client
from .models import (
    AnalysisRun,
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    EntityMention,
    GenerationRun,
    KnowledgeJob,
    Substack,
    SubstackContent,
    SubstackLink,
    SubstackSource,
)
from .prompts import (
    CLIENT_PROMPT,
    CLIENT_QUERIES,
    DISCOVERY_PROMPT,
    ITEM_PROMPT,
    ITEM_QUERIES,
    SALES_ORDER_PROMPT,
    SALES_ORDER_QUERIES,
)
from .retrieval import RETRIEVAL_VERSION, RetrievedChunk, evidence_text, merge_retrieval, retrieve_chunks
from .segments import Segment


DISCOVERY_KEY = "discovery.core_entities.v1"
PROMPT_CONFIG = {
    "sales-orders": ("sales_orders.extract.v3", SALES_ORDER_PROMPT, SALES_ORDER_QUERIES, SalesOrderExtraction),
    "clients": ("clients.extract.v3", CLIENT_PROMPT, CLIENT_QUERIES, ClientExtraction),
    "items": ("items.extract.v3", ITEM_PROMPT, ITEM_QUERIES, ItemExtraction),
}


def _version_chunks(session: Session, version_id: UUID) -> list[Chunk]:
    settings = get_settings()
    return list(session.scalars(
        select(Chunk)
        .where(
            Chunk.document_version_id == version_id,
            Chunk.embedding_model == settings.embedding_model,
        )
        .order_by(Chunk.position)
        .limit(settings.analysis_max_chunks_per_document)
    ))


def _chunk_evidence(chunks: list[Chunk], document: Document) -> str:
    return evidence_text([RetrievedChunk(chunk=chunk, document=document) for chunk in chunks])


def _valid_citations(model: BaseModel, allowed: set[str]) -> bool:
    def visit(value) -> bool:
        if isinstance(value, dict):
            citations = value.get("citations")
            if citations is not None and any(citation not in allowed for citation in citations):
                return False
            return all(visit(item) for item in value.values())
        if isinstance(value, list):
            return all(visit(item) for item in value)
        return True
    return visit(model.model_dump())


def _all_facts_cited(model: BaseModel) -> bool:
    def visit(value) -> bool:
        if isinstance(value, dict):
            if "value" in value and value.get("value") not in (None, "") and not value.get("citations"):
                return False
            if "entity_type" in value and value.get("name") and not value.get("citations"):
                return False
            return all(visit(item) for item in value.values())
        if isinstance(value, list):
            return all(visit(item) for item in value)
        return True
    return visit(model.model_dump())


def _link_document_entities(session: Session, version_id: UUID) -> None:
    substacks = list(session.scalars(
        select(Substack)
        .join(EntityMention, EntityMention.substack_id == Substack.id)
        .where(EntityMention.document_version_id == version_id)
        .distinct()
    ))
    orders = [substack for substack in substacks if substack.stack_type == "sales-orders"]
    related = [substack for substack in substacks if substack.stack_type in ("clients", "items")]
    for order in orders:
        for other in related:
            left, right = sorted((order.id, other.id), key=str)
            exists = session.scalar(
                select(SubstackLink).where(
                    SubstackLink.substack_id == left,
                    SubstackLink.related_substack_id == right,
                )
            )
            if exists is None:
                session.add(SubstackLink(substack_id=left, related_substack_id=right, reason="discovered in the same evidence"))


def discover_document(session: Session, version_id: UUID, run_id: UUID | None, generate: str = "affected") -> int:
    """Find records in one version. `generate="affected"` regenerates every record found;
    `"new"` only generates records created here (chosen records are queued separately)."""
    settings = get_settings()
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError("document_version_not_found")
    document = session.get(Document, version.document_id)
    if document is None:
        raise ValueError("document_not_found")
    chunks = _version_chunks(session, version.id)
    if not chunks:
        raise ValueError("document_has_no_current_embeddings")
    result = get_llm_client().parse(prompt=DISCOVERY_PROMPT, evidence=_chunk_evidence(chunks, document), schema=DiscoveryOutput)
    output = result.parsed
    if not isinstance(output, DiscoveryOutput):
        raise ValueError("invalid_discovery_output")
    allowed = {str(chunk.id) for chunk in chunks}
    if not _valid_citations(output, allowed):
        raise ValueError("discovery_citation_outside_evidence")
    run = session.get(AnalysisRun, run_id) if run_id else None
    remaining_candidates = max(0, settings.analysis_max_candidates_per_run - (run.candidates_found if run else 0))
    candidate_limit = min(settings.analysis_max_candidates_per_document, remaining_candidates)
    cited_candidates = [candidate for candidate in output.candidates if candidate.citations]
    candidates = cited_candidates[:candidate_limit]
    if run is not None and len(cited_candidates) > candidate_limit:
        run.failures += 1
        run.error_summary = "Candidate limit reached; retry after reviewing current results."
    previous_mentions = session.scalars(
        select(EntityMention)
        .join(DocumentVersion, EntityMention.document_version_id == DocumentVersion.id)
        .where(
            EntityMention.document_id == document.id,
            EntityMention.status == "current",
            DocumentVersion.revision < version.revision,
        )
    ).all()
    for mention in previous_mentions:
        mention.status = "superseded"
    created_count = 0
    updated_count = 0
    for candidate in candidates:
        _, substack, created = resolve_candidate(
            session,
            document=document,
            version=version,
            candidate=candidate,
            prompt_key=DISCOVERY_KEY,
            prompt_version="v1",
            model=settings.openai_model,
            analysis_run_id=run_id,
        )
        created_count += int(created)
        updated_count += int(not created)
        if not created and generate != "affected":
            continue
        generation_prompt_key = PROMPT_CONFIG[substack.stack_type][0]
        enqueue_job(
            session,
            organization_id=document.organization_id,
            owner_user_id=document.owner_user_id,
            kind="generate_substack",
            payload={"substack_id": str(substack.id)},
            dedupe_key=f"generate:{substack.id}:{version.id}:{generation_prompt_key}:{settings.analysis_config_version}:{settings.openai_model}",
            analysis_run_id=run_id,
        )
    _link_document_entities(session, version.id)
    for substack_id in {mention.substack_id for mention in previous_mentions if mention.substack_id}:
        current_mentions = session.scalar(select(func.count(EntityMention.id)).where(
            EntityMention.substack_id == substack_id,
            EntityMention.status == "current",
        )) or 0
        if current_mentions == 0:
            unsupported = session.get(Substack, substack_id)
            if unsupported is not None:
                unsupported.review_state = "unsupported"
    if run is not None:
        run.status = "generating" if candidates else "discovering"
        run.candidates_found += len(candidates)
        run.substacks_created += created_count
        run.substacks_updated += updated_count
        run.documents_processed += 1
        if not candidates:
            complete_run_if_last(session, run.id)
    session.commit()
    return len(candidates)


def _exact_terms(session: Session, substack: Substack) -> tuple[str, ...]:
    mentions = session.scalars(
        select(EntityMention).where(
            EntityMention.substack_id == substack.id,
            EntityMention.status == "current",
        )
    ).all()
    terms: list[str] = [substack.name]
    for mention in mentions:
        data = mention.data or {}
        terms.extend(str(value) for value in data.get("identifiers", {}).values())
    return tuple(dict.fromkeys(term for term in terms if term))


def _report_segments(extraction: BaseModel) -> list[Segment]:
    return [
        Segment(kind="text", value=paragraph.value, citations=paragraph.citations)
        for paragraph in getattr(extraction, "report", [])
        if paragraph.value
    ]


def _all_citations(extraction: BaseModel) -> set[str]:
    found: set[str] = set()

    def visit(value) -> None:
        if isinstance(value, dict):
            citations = value.get("citations")
            if isinstance(citations, list):
                found.update(str(citation) for citation in citations)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(extraction.model_dump())
    return found


def _high_confidence(substack: Substack, extraction: BaseModel) -> bool:
    if not substack.identity_key:
        return False
    if isinstance(extraction, SalesOrderExtraction):
        return bool(
            extraction.order_number.value and extraction.order_number.citations
            and extraction.customer_name.value and extraction.customer_name.citations
            and extraction.line_items
            and all(line.quantity.value and line.quantity.citations for line in extraction.line_items)
        )
    if isinstance(extraction, ClientExtraction):
        return bool(extraction.name.value and extraction.name.citations and (
            extraction.registration_number.citations or extraction.customer_id.citations
        ))
    if isinstance(extraction, ItemExtraction):
        return bool(extraction.name.value and extraction.name.citations and (
            extraction.internal_sku.citations or (
                extraction.customer_item_code.citations and extraction.client_identifier.citations
            )
        ))
    return False


def llm_substacks(session: Session, organization_id: UUID, owner_user_id: UUID | None):
    """LLM-generated records (sales orders, clients, items) in one visibility scope."""
    owner_filter = (
        Substack.owner_user_id.is_(None) if owner_user_id is None else Substack.owner_user_id == owner_user_id
    )
    return select(Substack).where(
        Substack.organization_id == organization_id,
        owner_filter,
        Substack.stack_type.in_(tuple(PROMPT_CONFIG)),
    )


def regenerate_records(session: Session, job: KnowledgeJob) -> int:
    """Queue forced generation for chosen records once the run's discovery has finished."""
    blocking = session.scalar(select(func.count()).select_from(KnowledgeJob).where(
        KnowledgeJob.analysis_run_id == job.analysis_run_id,
        KnowledgeJob.kind.in_(("embed_version", "discover_document")),
        KnowledgeJob.status.in_(("queued", "running")),
    )) or 0
    if blocking:
        raise JobNotReady()
    statement = llm_substacks(session, job.organization_id, job.owner_user_id)
    if job.payload.get("mode") != "all":
        statement = statement.where(Substack.id.in_([UUID(value) for value in job.payload.get("substack_ids", [])]))
    already = {
        row.payload.get("substack_id")
        for row in session.scalars(select(KnowledgeJob).where(
            KnowledgeJob.analysis_run_id == job.analysis_run_id,
            KnowledgeJob.kind == "generate_substack",
        ))
    }
    queued = 0
    for substack in session.scalars(statement):
        if str(substack.id) in already:
            continue
        enqueue_job(
            session,
            organization_id=substack.organization_id,
            owner_user_id=substack.owner_user_id,
            kind="generate_substack",
            payload={"substack_id": str(substack.id), "force": True},
            dedupe_key=f"regenerate:{substack.id}:run:{job.analysis_run_id}",
            analysis_run_id=job.analysis_run_id,
        )
        queued += 1
    run = session.get(AnalysisRun, job.analysis_run_id) if job.analysis_run_id else None
    if run is not None and queued:
        run.status = "generating"
    complete_run_if_last(session, job.analysis_run_id)
    session.commit()
    return queued


def generate_substack(session: Session, substack_id: UUID, run_id: UUID | None, force: bool = False) -> SubstackContent:
    """Generate a record's report. Unchanged evidence is skipped unless `force` is set."""
    settings = get_settings()
    substack = session.get(Substack, substack_id)
    if substack is None or substack.stack_type not in PROMPT_CONFIG:
        raise ValueError("unsupported_substack")
    prompt_key, prompt, queries, schema = PROMPT_CONFIG[substack.stack_type]
    prompt_version = prompt_key.rsplit(".", 1)[-1]
    exact_terms = _exact_terms(session, substack)
    retrieved = merge_retrieval([
        retrieve_chunks(session, substack.organization_id, substack.owner_user_id, f"{query} {' '.join(exact_terms)}", exact_terms=exact_terms)
        for query in queries
    ])
    if not retrieved:
        substack.review_state = "unsupported"
        session.commit()
        raise ValueError("no_retrievable_evidence")
    allowed = {str(item.chunk.id) for item in retrieved}
    fingerprint = sha256("|".join((
        prompt_key,
        settings.openai_model,
        RETRIEVAL_VERSION,
        settings.analysis_config_version,
        *sorted(allowed),
    )).encode()).hexdigest()
    latest = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id)
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if latest is not None and latest.inputs_fingerprint == fingerprint and not force:
        complete_run_if_last(session, run_id)
        session.commit()
        return latest
    result = get_llm_client().parse(prompt=prompt, evidence=evidence_text(retrieved), schema=schema)
    extraction = result.parsed
    if len(getattr(extraction, "report", [])) < 2 or any(not paragraph.value for paragraph in extraction.report):
        raise ValueError("generation_missing_natural_language_report")
    if not _valid_citations(extraction, allowed):
        raise ValueError("generation_citation_outside_evidence")
    if not _all_facts_cited(extraction):
        raise ValueError("generation_contains_uncited_fact")
    confirmed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id, SubstackContent.status == "confirmed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    auto_confirm = confirmed is None and _high_confidence(substack, extraction)
    segments = _report_segments(extraction)
    content = SubstackContent(
        substack_id=substack.id,
        revision=(latest.revision + 1) if latest else 1,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        model=settings.openai_model,
        content={
            "segments": [segment.model_dump() for segment in segments],
            "entries": [],
            "extraction": extraction.model_dump(),
        },
        status="confirmed" if auto_confirm else "proposed",
        inputs_fingerprint=fingerprint,
    )
    session.add(content)
    session.flush()
    chunk_documents = {str(item.chunk.id): item.document.id for item in retrieved}
    for index, segment in enumerate(segments):
        for chunk_id in segment.citations:
            session.add(ContentCitation(
                content_id=content.id,
                segment_index=index,
                chunk_id=UUID(chunk_id),
                document_id=chunk_documents[chunk_id],
                locator=segment.locator,
            ))
    for item in retrieved:
        source = session.scalar(select(SubstackSource).where(
            SubstackSource.substack_id == substack.id,
            SubstackSource.document_id == item.document.id,
        ))
        if source is None:
            session.add(SubstackSource(substack_id=substack.id, document_id=item.document.id))
    run_record = GenerationRun(
        substack_id=substack.id,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        model=settings.openai_model,
        input_chunk_ids=sorted(allowed),
        input_fingerprint=fingerprint,
        retrieval_version=RETRIEVAL_VERSION,
        provider_request_id=result.request_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        output=extraction.model_dump(),
    )
    session.add(run_record)
    substack.last_analysis_run_id = run_id
    if auto_confirm:
        substack.status = "confirmed"
        substack.review_state = "clean"
    else:
        substack.review_state = "pending_update" if confirmed else "pending"
    complete_run_if_last(session, run_id)
    session.commit()
    return content
