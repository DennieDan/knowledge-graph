from hashlib import sha256
from html import escape
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .entity_resolution import resolve_candidate
from .extractions import (
    ClientExtraction,
    ConversationExtraction,
    DiscoveryOutput,
    ItemExtraction,
    MeetingExtraction,
    SalesOrderExtraction,
    SupplierExtraction,
    SupplierOrderExtraction,
)
from .generation import TEMPLATE_MODEL
from .jobs import JobNotReady, complete_run_if_last, enqueue_job
from .llm import get_llm_client
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
from .spend import add_tokens
from .prompts import (
    CLIENT_PROMPT,
    CLIENT_QUERIES,
    CONVERSATION_PROMPT,
    DESCRIBED_RECORD_PROMPT,
    DISCOVERY_PROMPT,
    ITEM_PROMPT,
    ITEM_QUERIES,
    MEETING_PROMPT,
    MEETING_QUERIES,
    SALES_ORDER_PROMPT,
    SALES_ORDER_QUERIES,
    SUPPLIER_ORDER_PROMPT,
    SUPPLIER_ORDER_QUERIES,
    SUPPLIER_PROMPT,
    SUPPLIER_QUERIES,
)
from .retrieval import (
    RETRIEVAL_VERSION,
    RetrievedChunk,
    evidence_text,
    merge_retrieval,
    retrieve_chunks,
    visibility_filter,
)
from .segments import Segment


DISCOVERY_KEY = "discovery.core_entities.v2"
PROMPT_CONFIG = {
    "sales-orders": ("sales_orders.extract.v3", SALES_ORDER_PROMPT, SALES_ORDER_QUERIES, SalesOrderExtraction),
    "clients": ("clients.extract.v3", CLIENT_PROMPT, CLIENT_QUERIES, ClientExtraction),
    "items": ("items.extract.v3", ITEM_PROMPT, ITEM_QUERIES, ItemExtraction),
    "suppliers": ("suppliers.extract.v1", SUPPLIER_PROMPT, SUPPLIER_QUERIES, SupplierExtraction),
    "supplier-orders": (
        "supplier_orders.extract.v1", SUPPLIER_ORDER_PROMPT, SUPPLIER_ORDER_QUERIES, SupplierOrderExtraction,
    ),
    "meetings": ("meetings.extract.v1", MEETING_PROMPT, MEETING_QUERIES, MeetingExtraction),
    # Summarized from the chat's own transcript, not workspace retrieval, so there are no queries.
    "conversations": ("conversations.summarize.v1", CONVERSATION_PROMPT, (), ConversationExtraction),
}
# Stacks a person can create by describing a record Analyze missed.
DESCRIBABLE_STACK_TYPES = ("sales-orders", "clients", "items", "suppliers", "supplier-orders", "meetings")
# Records discovered in the same evidence are linked: anchor type -> related types.
LINKED_STACK_TYPES = {
    "sales-orders": ("clients", "items"),
    "supplier-orders": ("suppliers", "items"),
    "meetings": ("sales-orders", "clients", "items", "suppliers", "supplier-orders"),
}
# Titles shorter than this are too generic to treat as a file mention in a description.
MIN_MENTIONED_TITLE_LENGTH = 4
MAX_MENTIONED_DOCUMENTS = 5


def _user_description(substack: Substack) -> str | None:
    if substack.created_by != "user" or substack.stack_type not in DESCRIBABLE_STACK_TYPES:
        return None
    return (substack.summary or "").strip() or None


def _mentioned_document_evidence(session: Session, substack: Substack, description: str) -> list[RetrievedChunk]:
    """Chunks of visible documents whose title (with or without extension) appears in the description."""
    settings = get_settings()
    stem = func.regexp_replace(Document.title, r"\.[A-Za-z0-9]{1,5}$", "")
    haystack = func.lower(description)
    documents = session.scalars(
        select(Document)
        .where(
            Document.organization_id == substack.organization_id,
            visibility_filter(substack.owner_user_id),
            func.length(stem) >= MIN_MENTIONED_TITLE_LENGTH,
            func.strpos(haystack, func.lower(stem)) > 0,
        )
        .order_by(func.length(stem).desc())
        .limit(MAX_MENTIONED_DOCUMENTS)
    ).all()
    evidence: list[RetrievedChunk] = []
    for document in documents:
        version = session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.revision.desc())
            .limit(1)
        )
        if version is None:
            continue
        chunks = session.scalars(
            select(Chunk)
            .where(Chunk.document_version_id == version.id, Chunk.embedding_model == settings.embedding_model)
            .order_by(Chunk.position)
            .limit(settings.analysis_max_chunks_per_document)
        ).all()
        evidence.extend(RetrievedChunk(chunk=chunk, document=document) for chunk in chunks)
    return evidence


def _transcript_evidence(session: Session, substack: Substack) -> list[RetrievedChunk]:
    """The most recent chunks of the latest transcript version of each chat linked to a Conversations record."""
    documents = session.scalars(
        select(Document)
        .join(SubstackSource, SubstackSource.document_id == Document.id)
        .where(SubstackSource.substack_id == substack.id)
    ).all()
    evidence: list[RetrievedChunk] = []
    for document in documents:
        version = session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.revision.desc())
            .limit(1)
        )
        if version is None:
            continue
        recent = session.scalars(
            select(Chunk)
            .where(Chunk.document_version_id == version.id)
            .order_by(Chunk.position.desc())
            .limit(get_settings().analysis_max_chunks_per_document)
        ).all()
        evidence.extend(RetrievedChunk(chunk=chunk, document=document) for chunk in reversed(recent))
    return evidence


def _has_llm_content(session: Session, substack_id: UUID) -> bool:
    return session.scalar(
        select(func.count(SubstackContent.id)).where(
            SubstackContent.substack_id == substack_id,
            SubstackContent.model != TEMPLATE_MODEL,
        )
    ) > 0


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
    for anchor in substacks:
        for other in substacks:
            if other.stack_type not in LINKED_STACK_TYPES.get(anchor.stack_type, ()):
                continue
            left, right = sorted((anchor.id, other.id), key=str)
            exists = session.scalar(
                select(SubstackLink).where(
                    SubstackLink.substack_id == left,
                    SubstackLink.related_substack_id == right,
                )
            )
            if exists is None:
                session.add(SubstackLink(
                    substack_id=left, related_substack_id=right, reason="discovered in the same evidence",
                ))


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
    result = get_llm_client().parse(
        prompt=DISCOVERY_PROMPT, evidence=_chunk_evidence(chunks, document), schema=DiscoveryOutput,
    )
    add_tokens(
        session,
        document.organization_id,
        input_tokens=result.input_tokens or 0,
        output_tokens=result.output_tokens or 0,
    )
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
            prompt_version=DISCOVERY_KEY.rsplit(".", 1)[-1],
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
            dedupe_key=f"generate:{substack.id}:{version.id}:{generation_prompt_key}"
                       f":{settings.analysis_config_version}:{settings.openai_model}",
            analysis_run_id=run_id,
        )
    conversations = session.scalars(
        select(Substack)
        .join(SubstackSource, SubstackSource.substack_id == Substack.id)
        .where(SubstackSource.document_id == document.id, Substack.stack_type == "conversations")
    ).all()
    queued_conversations = 0
    for conversation in conversations:
        if generate != "affected" and _has_llm_content(session, conversation.id):
            continue
        enqueue_job(
            session,
            organization_id=document.organization_id,
            owner_user_id=document.owner_user_id,
            kind="generate_substack",
            payload={"substack_id": str(conversation.id)},
            dedupe_key=f"generate:{conversation.id}:{version.id}:{PROMPT_CONFIG['conversations'][0]}"
                       f":{settings.analysis_config_version}:{settings.openai_model}",
            analysis_run_id=run_id,
        )
        queued_conversations += 1
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
        run.status = "generating" if candidates or queued_conversations else "discovering"
        run.candidates_found += len(candidates)
        run.substacks_created += created_count
        run.substacks_updated += updated_count
        run.documents_processed += 1
        if not candidates and not queued_conversations:
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
    """Plain prose segments. Conversation topics carry their heading in `name`, kind and date in `locator`."""
    if isinstance(extraction, ConversationExtraction):
        return [
            Segment(
                kind="text",
                name=topic.title.strip(),
                value=topic.summary.value,
                citations=topic.summary.citations,
                locator={"kind": topic.kind, "date": topic.date},
            )
            for topic in extraction.topics
            if topic.title.strip() and topic.summary.value
        ]
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
    if isinstance(extraction, SupplierExtraction):
        return bool(extraction.name.value and extraction.name.citations and (
            extraction.registration_number.citations or extraction.supplier_id.citations
        ))
    if isinstance(extraction, SupplierOrderExtraction):
        return bool(
            extraction.order_number.value and extraction.order_number.citations
            and extraction.supplier_name.value and extraction.supplier_name.citations
            and extraction.line_items
            and all(line.quantity.value and line.quantity.citations for line in extraction.line_items)
        )
    return False


def llm_substacks(session: Session, organization_id: UUID, owner_user_id: UUID | None):
    """LLM-generated records (every PROMPT_CONFIG stack type) in one visibility scope."""
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
    is_conversation = substack.stack_type == "conversations"
    description = _user_description(substack)
    if is_conversation:
        retrieved = _transcript_evidence(session, substack)
    else:
        exact_terms = _exact_terms(session, substack)
        context = " ".join((*exact_terms, description or ""))
        groups = [
            retrieve_chunks(
                session, substack.organization_id, substack.owner_user_id,
                f"{query} {context}", exact_terms=exact_terms,
            )
            for query in queries
        ]
        if description:
            # Files the person named come first so the retrieval cap never drops them.
            groups[:0] = [
                _mentioned_document_evidence(session, substack, description),
                retrieve_chunks(
                    session, substack.organization_id, substack.owner_user_id,
                    description, exact_terms=exact_terms,
                ),
            ]
        retrieved = merge_retrieval(groups)
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
        *((description,) if description else ()),
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
    evidence = evidence_text(retrieved)
    if description:
        prompt = f"{prompt}\n\n{DESCRIBED_RECORD_PROMPT}"
        evidence = f"<user_request>\n{escape(description)}\n</user_request>\n\n{evidence}"
    result = get_llm_client().parse(prompt=prompt, evidence=evidence, schema=schema)
    add_tokens(
        session,
        substack.organization_id,
        input_tokens=result.input_tokens or 0,
        output_tokens=result.output_tokens or 0,
    )
    extraction = result.parsed
    if not is_conversation and (
        len(getattr(extraction, "report", [])) < 2 or any(not paragraph.value for paragraph in extraction.report)
    ):
        raise ValueError("generation_missing_natural_language_report")
    if not _valid_citations(extraction, allowed):
        raise ValueError("generation_citation_outside_evidence")
    if not _all_facts_cited(extraction):
        raise ValueError("generation_contains_uncited_fact")
    # Message-list template content predates LLM summaries; it is replaced, not kept as the live version.
    for obsolete in session.scalars(select(SubstackContent).where(
        SubstackContent.substack_id == substack.id,
        SubstackContent.model == TEMPLATE_MODEL,
        SubstackContent.status.in_(("confirmed", "proposed")),
    )):
        obsolete.status = "superseded"
    session.flush()
    confirmed = session.scalar(
        select(SubstackContent)
        .where(SubstackContent.substack_id == substack.id, SubstackContent.status == "confirmed")
        .order_by(SubstackContent.revision.desc())
        .limit(1)
    )
    if confirmed is None:
        substack.status = "proposed"
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
