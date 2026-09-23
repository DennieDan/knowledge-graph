"""Nightly / scheduled checks. Every check only proposes findings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from .findings import create_finding, observed_fingerprint
from .models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    EntityMention,
    Substack,
    SubstackContent,
    SubstackLink,
)

STALE_DAYS = {
    "sales-orders": 14,
    "clients": 90,
    "items": 180,
}
DEFAULT_STALE_DAYS = 60
ENTITY_MENTION_DOCS = 3
ENTITY_MENTION_WINDOW_DAYS = 30


@dataclass(frozen=True)
class DraftFinding:
    check_key: str
    subject_kind: str
    subject_id: UUID
    summary_sentence: str
    observed_value: str | None = None
    threshold_value: str | None = None
    evidence: dict | None = None
    owner_user_id: UUID | None = None
    fingerprint: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def source_changed(session: Session, organization_id: UUID) -> list[DraftFinding]:
    """Content citing a superseded document version, or a missing document."""
    drafts: list[DraftFinding] = []
    latest = (
        select(func.max(DocumentVersion.revision))
        .where(DocumentVersion.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    rows = session.execute(
        select(SubstackContent, Substack, Document, DocumentVersion)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .join(Chunk, ContentCitation.chunk_id == Chunk.id)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            Substack.organization_id == organization_id,
            SubstackContent.status.in_(("confirmed", "proposed")),
            DocumentVersion.revision < latest,
        )
        .distinct()
    ).all()
    for content, substack, document, version in rows:
        reason = "revised"
        drafts.append(
            DraftFinding(
                check_key="source_changed",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                observed_value=reason,
                threshold_value="latest_revision",
                summary_sentence=(
                    f"The source for {substack.name} changed after this record was confirmed "
                    f"({document.title} rev {version.revision} superseded)."
                ),
                evidence={
                    "reason": reason,
                    "document_id": str(document.id),
                    "document_title": document.title,
                    "cited_revision": version.revision,
                    "content_id": str(content.id),
                },
                fingerprint=observed_fingerprint(str(content.id), str(document.id), reason, str(version.revision)),
            )
        )

    orphan_citations = session.execute(
        select(SubstackContent, Substack, ContentCitation)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .outerjoin(Document, ContentCitation.document_id == Document.id)
        .where(
            Substack.organization_id == organization_id,
            SubstackContent.status.in_(("confirmed", "proposed")),
            Document.id.is_(None),
        )
    ).all()
    for content, substack, citation in orphan_citations:
        drafts.append(
            DraftFinding(
                check_key="source_changed",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                observed_value="deleted",
                summary_sentence=f"A cited source for {substack.name} is gone or unreachable.",
                evidence={"reason": "deleted", "content_id": str(content.id), "citation_id": str(citation.id)},
                fingerprint=observed_fingerprint(str(content.id), "deleted", str(citation.id)),
            )
        )

    # Extractor changed: content still cites evidence but its prompt_version is
    # behind the latest generation_run for that substack.
    from .models import GenerationRun
    contents = session.execute(
        select(SubstackContent, Substack)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .where(
            Substack.organization_id == organization_id,
            SubstackContent.status.in_(("confirmed", "proposed")),
        )
    ).all()
    for content, substack in contents:
        latest_run = session.scalar(
            select(GenerationRun)
            .where(GenerationRun.substack_id == substack.id, GenerationRun.status == "ok")
            .order_by(GenerationRun.created_at.desc())
            .limit(1)
        )
        if latest_run is None:
            continue
        if latest_run.prompt_version != content.prompt_version or latest_run.prompt_key != content.prompt_key:
            drafts.append(
                DraftFinding(
                    check_key="source_changed",
                    subject_kind="substack",
                    subject_id=substack.id,
                    owner_user_id=substack.owner_user_id,
                    observed_value="extractor_changed",
                    summary_sentence=(
                        f"The extractor for {substack.name} changed "
                        f"({content.prompt_version} → {latest_run.prompt_version})."
                    ),
                    evidence={
                        "reason": "extractor_changed",
                        "content_prompt_version": content.prompt_version,
                        "run_prompt_version": latest_run.prompt_version,
                    },
                    fingerprint=observed_fingerprint(str(content.id), "extractor_changed", latest_run.prompt_version),
                )
            )
    return drafts


def record_not_updated_since_threshold(session: Session, organization_id: UUID) -> list[DraftFinding]:
    drafts: list[DraftFinding] = []
    now = utcnow()
    substacks = session.scalars(select(Substack).where(Substack.organization_id == organization_id)).all()
    for substack in substacks:
        latest = session.scalar(
            select(SubstackContent)
            .where(SubstackContent.substack_id == substack.id)
            .order_by(SubstackContent.created_at.desc())
            .limit(1)
        )
        if latest is None:
            continue
        threshold_days = STALE_DAYS.get(substack.stack_type, DEFAULT_STALE_DAYS)
        age = now - latest.created_at
        if age < timedelta(days=threshold_days):
            continue
        days = age.days
        drafts.append(
            DraftFinding(
                check_key="record_not_updated_since_threshold",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                observed_value=str(days),
                threshold_value=str(threshold_days),
                summary_sentence=f"Nothing about {substack.name} has changed in {days} days.",
                evidence={"stack_type": substack.stack_type, "latest_content_id": str(latest.id)},
                fingerprint=observed_fingerprint(str(substack.id), str(threshold_days), latest.created_at.date().isoformat()),
            )
        )
    return drafts


def entity_mentioned_often_but_has_no_record(session: Session, organization_id: UUID) -> list[DraftFinding]:
    cutoff = utcnow() - timedelta(days=ENTITY_MENTION_WINDOW_DAYS)
    mentions = session.scalars(
        select(EntityMention).where(
            EntityMention.organization_id == organization_id,
            EntityMention.identity_key.is_(None),
            EntityMention.status == "current",
            EntityMention.created_at >= cutoff,
        )
    ).all()
    by_name: dict[tuple[str, str], set[UUID]] = {}
    samples: dict[tuple[str, str], EntityMention] = {}
    for mention in mentions:
        name = str((mention.data or {}).get("name") or (mention.data or {}).get("display_name") or "").strip().lower()
        if not name:
            continue
        key = (mention.entity_type, name)
        by_name.setdefault(key, set()).add(mention.document_id)
        samples.setdefault(key, mention)

    drafts: list[DraftFinding] = []
    for (entity_type, name), docs in by_name.items():
        if len(docs) < ENTITY_MENTION_DOCS:
            continue
        existing = session.scalar(
            select(Substack).where(
                Substack.organization_id == organization_id,
                Substack.stack_type == entity_type,
                func.lower(Substack.name) == name,
            )
        )
        if existing is not None:
            continue
        sample = samples[(entity_type, name)]
        display = (sample.data or {}).get("name") or name
        drafts.append(
            DraftFinding(
                check_key="entity_mentioned_often_but_has_no_record",
                subject_kind="entity_mention",
                subject_id=sample.id,
                owner_user_id=sample.owner_user_id,
                observed_value=str(len(docs)),
                threshold_value=str(ENTITY_MENTION_DOCS),
                summary_sentence=(
                    f"{display} appears in {len(docs)} documents but has no {entity_type} record."
                ),
                evidence={"entity_type": entity_type, "name": display, "document_ids": [str(d) for d in docs]},
                fingerprint=observed_fingerprint(entity_type, name, str(sorted(str(d) for d in docs))),
            )
        )
    return drafts


def referenced_record_not_found(session: Session, organization_id: UUID) -> list[DraftFinding]:
    drafts: list[DraftFinding] = []
    Related = aliased(Substack)
    dangling = session.execute(
        select(SubstackLink, Substack)
        .join(Substack, SubstackLink.substack_id == Substack.id)
        .outerjoin(Related, SubstackLink.related_substack_id == Related.id)
        .where(
            Substack.organization_id == organization_id,
            Related.id.is_(None),
        )
    ).all()
    for link, substack in dangling:
        drafts.append(
            DraftFinding(
                check_key="referenced_record_not_found",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                summary_sentence=f"{substack.name} refers to a record that is not in any connected folder.",
                evidence={"link_id": str(link.id), "related_substack_id": str(link.related_substack_id)},
                fingerprint=observed_fingerprint(str(link.id), "missing_related"),
            )
        )

    orphan_chunk_cites = session.execute(
        select(SubstackContent, Substack, ContentCitation)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .outerjoin(Chunk, ContentCitation.chunk_id == Chunk.id)
        .where(
            Substack.organization_id == organization_id,
            Chunk.id.is_(None),
        )
    ).all()
    for content, substack, citation in orphan_chunk_cites:
        drafts.append(
            DraftFinding(
                check_key="referenced_record_not_found",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                summary_sentence=f"{substack.name} cites a passage whose document no longer exists.",
                evidence={"content_id": str(content.id), "citation_id": str(citation.id)},
                fingerprint=observed_fingerprint(str(citation.id), "missing_chunk"),
            )
        )

    # EntityReference targets stored in extraction JSON with no matching substack.
    latest_by_substack = session.execute(
        select(SubstackContent, Substack)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .where(Substack.organization_id == organization_id)
        .order_by(SubstackContent.substack_id, SubstackContent.revision.desc())
    ).all()
    seen_substack: set[UUID] = set()
    for content, substack in latest_by_substack:
        if substack.id in seen_substack:
            continue
        seen_substack.add(substack.id)
        payload = content.content if isinstance(content.content, dict) else {}
        extraction = payload.get("extraction") if isinstance(payload.get("extraction"), dict) else payload
        references = extraction.get("references") if isinstance(extraction, dict) else None
        if not isinstance(references, list):
            continue
        for index, ref in enumerate(references):
            if not isinstance(ref, dict):
                continue
            name = str(ref.get("name") or "").strip()
            entity_type = ref.get("entity_type")
            if not name or not entity_type:
                continue
            match = session.scalar(
                select(Substack).where(
                    Substack.organization_id == organization_id,
                    Substack.stack_type == entity_type,
                    func.lower(Substack.name) == name.lower(),
                )
            )
            if match is not None:
                continue
            drafts.append(
                DraftFinding(
                    check_key="referenced_record_not_found",
                    subject_kind="substack",
                    subject_id=substack.id,
                    owner_user_id=substack.owner_user_id,
                    summary_sentence=(
                        f"{substack.name} refers to {name}, which is not in any connected folder."
                    ),
                    evidence={
                        "content_id": str(content.id),
                        "reference_index": index,
                        "entity_type": entity_type,
                        "name": name,
                        "identifier": ref.get("identifier"),
                    },
                    fingerprint=observed_fingerprint(str(content.id), entity_type, name.lower()),
                )
            )
    return drafts


def sources_disagree(session: Session, organization_id: UUID) -> list[DraftFinding]:
    """Raise findings from conflicts already stored in latest extraction content."""
    drafts: list[DraftFinding] = []
    substacks = session.scalars(select(Substack).where(Substack.organization_id == organization_id)).all()
    for substack in substacks:
        latest = session.scalar(
            select(SubstackContent)
            .where(SubstackContent.substack_id == substack.id)
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        if latest is None or not isinstance(latest.content, dict):
            continue
        conflicts = latest.content.get("conflicts") or latest.content.get("evidence_conflicts") or []
        if not isinstance(conflicts, list):
            continue
        for index, conflict in enumerate(conflicts):
            if not isinstance(conflict, dict):
                continue
            values = conflict.get("values") or [conflict.get("value_a"), conflict.get("value_b")]
            values = [v for v in values if v is not None]
            explanation = conflict.get("explanation") or conflict.get("reason") or ""
            if len(values) < 2:
                continue
            drafts.append(
                DraftFinding(
                    check_key="sources_disagree",
                    subject_kind="substack",
                    subject_id=substack.id,
                    owner_user_id=substack.owner_user_id,
                    observed_value=str(values[0]),
                    threshold_value=str(values[1]),
                    summary_sentence=(
                        f"Two sources give conflicting values for {substack.name}: "
                        f"{values[0]} and {values[1]}."
                    ),
                    evidence={
                        "content_id": str(latest.id),
                        "conflict_index": index,
                        "values": values,
                        "explanation": explanation,
                        "citations": conflict.get("citations") or conflict.get("quotes") or [],
                    },
                    fingerprint=observed_fingerprint(str(latest.id), str(index), str(values)),
                )
            )
    return drafts


ALL_CHECKS = (
    source_changed,
    record_not_updated_since_threshold,
    entity_mentioned_often_but_has_no_record,
    referenced_record_not_found,
    sources_disagree,
)


def run_all_checks(session: Session, organization_id: UUID) -> list:
    created = []
    for check in ALL_CHECKS:
        for draft in check(session, organization_id):
            finding = create_finding(
                session,
                organization_id=organization_id,
                check_key=draft.check_key,
                subject_kind=draft.subject_kind,
                subject_id=draft.subject_id,
                summary_sentence=draft.summary_sentence,
                observed_value=draft.observed_value,
                threshold_value=draft.threshold_value,
                evidence=draft.evidence,
                owner_user_id=draft.owner_user_id,
                fingerprint=draft.fingerprint,
            )
            if finding is not None:
                created.append(finding)
    session.commit()
    return created
