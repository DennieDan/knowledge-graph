"""Nightly re-check of confirmed content against latest source document versions.

Intake catches arrivals; this catches quiet in-place edits (Drive / WhatsApp
document versions whose content_hash drifted after confirmation). Findings go
into the same To check queue as other checks — no separate scoring path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .findings import create_finding, observed_fingerprint
from .models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    DriveWorkspace,
    Substack,
    SubstackContent,
)


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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _confirmed_values(content: SubstackContent) -> list[tuple[str, str]]:
    """Return (label, value) pairs from confirmed field/token segments."""
    payload = content.content if isinstance(content.content, dict) else {}
    pairs: list[tuple[str, str]] = []
    for segment in payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        kind = segment.get("kind")
        if kind not in ("field", "token"):
            continue
        value = str(segment.get("value") or "").strip()
        if not value or len(value) < 2:
            continue
        label = str(segment.get("name") or kind)
        pairs.append((label, value))
    return pairs


def _workspace_reachable(session: Session, document: Document) -> bool:
    """Skip Drive docs whose workspace is disconnected or access-denied."""
    if document.drive_workspace_id is None:
        return True
    workspace = session.get(DriveWorkspace, document.drive_workspace_id)
    if workspace is None:
        return False
    if workspace.status != "active":
        return False
    err = (workspace.last_error or "").lower()
    if any(token in err for token in ("403", "401", "refused", "permission", "unauthorized", "access")):
        return False
    return True


def _latest_version(session: Session, document_id: UUID) -> DocumentVersion | None:
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.revision.desc())
        .limit(1)
    )


def _confirmed_rows(session: Session, organization_id: UUID):
    """Confirmed content rows with a cited document version (Drive / WhatsApp / upload)."""
    return session.execute(
        select(SubstackContent, Substack, Document, DocumentVersion, Chunk, ContentCitation)
        .join(Substack, SubstackContent.substack_id == Substack.id)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .join(Chunk, ContentCitation.chunk_id == Chunk.id)
        .join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(
            Substack.organization_id == organization_id,
            SubstackContent.status == "confirmed",
        )
        .distinct()
    ).all()


def source_drift(session: Session, organization_id: UUID) -> list[DraftFinding]:
    """Latest source content_hash differs from the version cited at confirmation."""
    drafts: list[DraftFinding] = []
    seen: set[tuple[UUID, UUID]] = set()
    for content, substack, document, cited_version, _chunk, _citation in _confirmed_rows(
        session, organization_id
    ):
        key = (content.id, document.id)
        if key in seen:
            continue
        seen.add(key)
        if not _workspace_reachable(session, document):
            continue
        latest = _latest_version(session, document.id)
        if latest is None:
            continue
        if latest.content_hash == cited_version.content_hash:
            continue
        drafts.append(
            DraftFinding(
                check_key="source_drift",
                subject_kind="substack",
                subject_id=substack.id,
                owner_user_id=substack.owner_user_id,
                observed_value=latest.content_hash[:16],
                threshold_value=cited_version.content_hash[:16],
                summary_sentence=(
                    f"Drawing changed after confirmation: {document.title} for {substack.name} "
                    f"(rev {cited_version.revision} → {latest.revision})."
                ),
                evidence={
                    "reason": "content_hash_drift",
                    "content_id": str(content.id),
                    "document_id": str(document.id),
                    "document_title": document.title,
                    "document_source": document.source,
                    "cited_revision": cited_version.revision,
                    "cited_content_hash": cited_version.content_hash,
                    "latest_revision": latest.revision,
                    "latest_content_hash": latest.content_hash,
                },
                fingerprint=observed_fingerprint(
                    str(content.id),
                    str(document.id),
                    "source_drift",
                    latest.content_hash,
                ),
            )
        )
    return drafts


def recheck_mismatch(session: Session, organization_id: UUID) -> list[DraftFinding]:
    """Confirmed field/token values no longer appear in the latest source text."""
    drafts: list[DraftFinding] = []
    # Group citations by content so we check each confirmed value once against
    # the union of latest source texts for its cited documents.
    by_content: dict[UUID, tuple[SubstackContent, Substack, list[Document]]] = {}
    for content, substack, document, _cited, _chunk, _citation in _confirmed_rows(
        session, organization_id
    ):
        if content.id not in by_content:
            by_content[content.id] = (content, substack, [])
        docs = by_content[content.id][2]
        if document.id not in {d.id for d in docs}:
            docs.append(document)

    for content, substack, documents in by_content.values():
        reachable_latest: list[tuple[Document, DocumentVersion]] = []
        for document in documents:
            if not _workspace_reachable(session, document):
                continue
            latest = _latest_version(session, document.id)
            if latest is None:
                continue
            reachable_latest.append((document, latest))
        if not reachable_latest:
            continue
        corpus = _normalize("\n".join(v.content for _, v in reachable_latest))
        for label, value in _confirmed_values(content):
            needle = _normalize(value)
            if not needle or needle in corpus:
                continue
            doc_titles = ", ".join(d.title for d, _ in reachable_latest)
            drafts.append(
                DraftFinding(
                    check_key="recheck_mismatch",
                    subject_kind="substack",
                    subject_id=substack.id,
                    owner_user_id=substack.owner_user_id,
                    observed_value=value[:200],
                    threshold_value=label,
                    summary_sentence=(
                        f"Confirmed {label} for {substack.name} is no longer in the latest "
                        f"source ({doc_titles})."
                    ),
                    evidence={
                        "reason": "quote_no_longer_in_source",
                        "content_id": str(content.id),
                        "field": label,
                        "value": value,
                        "document_ids": [str(d.id) for d, _ in reachable_latest],
                        "latest_hashes": [v.content_hash for _, v in reachable_latest],
                    },
                    fingerprint=observed_fingerprint(
                        str(content.id),
                        "recheck_mismatch",
                        label,
                        value,
                        *[v.content_hash for _, v in reachable_latest],
                    ),
                )
            )
    return drafts


def run_recheck(session: Session, organization_id: UUID) -> list:
    """Run nightly re-check and open findings into To check."""
    created = []
    for draft in (*source_drift(session, organization_id), *recheck_mismatch(session, organization_id)):
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
