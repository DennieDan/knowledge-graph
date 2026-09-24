import re
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .extractions import CandidateMention
from .models import Document, DocumentVersion, EntityMention, Substack, SubstackSource


_NON_IDENTIFIER = re.compile(r"[^A-Z0-9]+")


def normalize_identifier(value: str) -> str:
    return _NON_IDENTIFIER.sub("", value.upper())


def identity_for_candidate(candidate: CandidateMention) -> tuple[str | None, str | None]:
    identifiers = {
        key: normalize_identifier(value)
        for key, value in candidate.identifiers.model_dump(exclude_none=True).items()
        if value.strip()
    }
    if candidate.entity_type == "clients":
        if identifiers.get("registration_number"):
            return f"registration:{identifiers['registration_number']}", "registration_number"
        if identifiers.get("customer_id"):
            return f"customer:{identifiers['customer_id']}", "customer_id"
    if candidate.entity_type == "items":
        if identifiers.get("internal_sku"):
            return f"sku:{identifiers['internal_sku']}", "internal_sku"
        if identifiers.get("client_identifier") and identifiers.get("customer_item_code"):
            return f"client-item:{identifiers['client_identifier']}:{identifiers['customer_item_code']}", "client_item_code"
    if candidate.entity_type == "sales-orders":
        if identifiers.get("customer_identifier") and identifiers.get("order_number"):
            return f"customer-order:{identifiers['customer_identifier']}:{identifiers['order_number']}", "customer_order_number"
    if candidate.entity_type == "suppliers":
        if identifiers.get("registration_number"):
            return f"registration:{identifiers['registration_number']}", "registration_number"
        if identifiers.get("supplier_id"):
            return f"supplier:{identifiers['supplier_id']}", "supplier_id"
    if candidate.entity_type == "supplier-orders":
        # This business issues its own purchase order numbers, so the number alone is unique.
        if identifiers.get("purchase_order_number"):
            return f"purchase-order:{identifiers['purchase_order_number']}", "purchase_order_number"
    if candidate.entity_type == "meetings":
        name = normalize_identifier(candidate.name)
        if identifiers.get("meeting_date") and name:
            return f"meeting:{identifiers['meeting_date']}:{name}", "meeting_date_title"
    return None, None


def candidate_key(document_id: UUID, candidate: CandidateMention) -> str:
    identity_key, _ = identity_for_candidate(candidate)
    payload = "|".join((candidate.entity_type, str(document_id), identity_key or "", candidate.name.strip().casefold()))
    return sha256(payload.encode()).hexdigest()


def resolve_candidate(
    session: Session,
    *,
    document: Document,
    version: DocumentVersion,
    candidate: CandidateMention,
    prompt_key: str,
    prompt_version: str,
    model: str,
    analysis_run_id: UUID | None,
) -> tuple[EntityMention, Substack, bool]:
    key = candidate_key(document.id, candidate)
    existing_mention = session.scalar(
        select(EntityMention).where(
            EntityMention.document_version_id == version.id,
            EntityMention.candidate_key == key,
        )
    )
    if existing_mention is not None and existing_mention.substack_id:
        existing_substack = session.get(Substack, existing_mention.substack_id)
        if existing_substack is not None:
            return existing_mention, existing_substack, False
    identity_key, identity_kind = identity_for_candidate(candidate)
    substack = None
    if identity_key:
        owner_filter = Substack.owner_user_id.is_(None) if document.owner_user_id is None else Substack.owner_user_id == document.owner_user_id
        substack = session.scalar(
            select(Substack).where(
                Substack.organization_id == document.organization_id,
                owner_filter,
                Substack.stack_type == candidate.entity_type,
                Substack.identity_key == identity_key,
            )
        )
    created = substack is None
    if substack is None:
        substack = Substack(
            organization_id=document.organization_id,
            owner_user_id=document.owner_user_id,
            stack_type=candidate.entity_type,
            name=candidate.name.strip() or "Untitled",
            status="proposed",
            review_state="pending",
            identity_key=identity_key,
            identity_kind=identity_kind,
            created_by="system",
            last_analysis_run_id=analysis_run_id,
        )
        session.add(substack)
        session.flush()
    else:
        substack.last_analysis_run_id = analysis_run_id
    source = session.scalar(
        select(SubstackSource).where(
            SubstackSource.substack_id == substack.id,
            SubstackSource.document_id == document.id,
        )
    )
    if source is None:
        session.add(SubstackSource(substack_id=substack.id, document_id=document.id))
    mention = existing_mention or EntityMention(
        organization_id=document.organization_id,
        owner_user_id=document.owner_user_id,
        document_id=document.id,
        document_version_id=version.id,
        entity_type=candidate.entity_type,
        candidate_key=key,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        model=model,
    )
    mention.identity_key = identity_key
    mention.identity_kind = identity_kind
    mention.data = candidate.model_dump()
    mention.cited_chunk_ids = candidate.citations
    mention.substack_id = substack.id
    if existing_mention is None:
        session.add(mention)
    session.flush()
    return mention, substack, created
