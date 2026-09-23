"""Find records (substacks and their content) for a question.

Records have no embeddings of their own, and they do not need any: a record is
built from passages that are already indexed, so the cheapest way to reach it
semantically is to rank chunks and then follow their citations back up. Two
paths feed one ranked list:

- identifiers — `PO2431`, a client name — match `name`/`identity_key` directly,
  which vectors are bad at and which is how people actually ask;
- everything else — rank chunks with the existing index, then take the
  substacks whose content cites those documents, or that the document is filed
  into, scored by their best chunk.

Confirmed content outranks proposed content. Confirmation is reported as who
did it, not just that it happened: a generator that auto-confirms its own
output (`files.describe.v0`, high-confidence extractions) leaves
`confirmed_by_user_id` NULL, and that is *not* a person having checked the
record — the answer has to say so.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    ContentCitation,
    Substack,
    SubstackContent,
    SubstackSource,
    User,
)
from .retrieval import search_chunks

RECORD_RETRIEVAL_VERSION = "records-v1"

# Short words match too much to be worth a LIKE scan; identifiers ("PO2431",
# "A12") are kept whatever their length because they are the precise part.
MIN_TERM_CHARS = 4
MAX_TERMS = 6
MAX_VALUE_CHARS = 400


@dataclass(frozen=True)
class RetrievedRecord:
    substack: Substack
    content: SubstackContent | None
    confirmed_by: User | None = None
    # Best chunk distance behind this record; None when matched by name.
    score: float | None = None

    @property
    def confirmed(self) -> bool:
        return self.content is not None and self.content.status == "confirmed"

    @property
    def confirmed_at(self) -> datetime | None:
        return self.content.confirmed_at if self.confirmed and self.content else None

    @property
    def checked(self) -> str:
        """Who checked this record: a person, the system itself, or nobody."""
        if not self.confirmed:
            return "no"
        return "person" if self.confirmed_by is not None else "system"

    @property
    def rank(self) -> tuple:
        # Confirmed first, then name matches, then by chunk distance.
        return (not self.confirmed, self.score is not None, self.score or 0.0, str(self.substack.id))


def visible_records(organization_id: UUID, owner_user_id: UUID | None):
    owner = (
        Substack.owner_user_id.is_(None)
        if owner_user_id is None
        else or_(Substack.owner_user_id.is_(None), Substack.owner_user_id == owner_user_id)
    )
    return (Substack.organization_id == organization_id, owner)


def latest_content(session: Session, substack_id: UUID) -> SubstackContent | None:
    """The revision a reader should be answered from: confirmed, else proposed."""
    for status in ("confirmed", "proposed"):
        content = session.scalar(
            select(SubstackContent)
            .where(SubstackContent.substack_id == substack_id, SubstackContent.status == status)
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        if content is not None:
            return content
    return None


def _terms(query: str) -> list[str]:
    seen: list[str] = []
    for raw in query.replace("/", " ").replace(",", " ").split():
        term = raw.strip("?!.:;\"'()[]")
        if not term or term in seen:
            continue
        if len(term) >= MIN_TERM_CHARS or any(character.isdigit() for character in term):
            seen.append(term)
    return seen[:MAX_TERMS]


def _escaped(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _by_name(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    query: str,
    limit: int,
) -> list[Substack]:
    terms = _terms(query)
    if not terms:
        return []
    patterns = [f"%{_escaped(term)}%" for term in terms]
    return list(
        session.scalars(
            select(Substack)
            .where(
                *visible_records(organization_id, owner_user_id),
                or_(
                    *(Substack.name.ilike(pattern, escape="\\") for pattern in patterns),
                    *(Substack.identity_key.ilike(pattern, escape="\\") for pattern in patterns),
                ),
            )
            .order_by(Substack.updated_at.desc())
            .limit(limit)
        ).all()
    )


def _by_citation(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    document_scores: dict[UUID, float],
) -> dict[UUID, tuple[Substack, float]]:
    """Substacks reachable from the documents the chunk search matched."""
    if not document_scores:
        return {}
    document_ids = list(document_scores)
    found: dict[UUID, tuple[Substack, float]] = {}
    citing = session.execute(
        select(Substack, ContentCitation.document_id)
        .join(SubstackContent, SubstackContent.substack_id == Substack.id)
        .join(ContentCitation, ContentCitation.content_id == SubstackContent.id)
        .where(
            *visible_records(organization_id, owner_user_id),
            ContentCitation.document_id.in_(document_ids),
            SubstackContent.status.in_(("confirmed", "proposed")),
        )
    ).all()
    filed = session.execute(
        select(Substack, SubstackSource.document_id)
        .join(SubstackSource, SubstackSource.substack_id == Substack.id)
        .where(
            *visible_records(organization_id, owner_user_id),
            SubstackSource.document_id.in_(document_ids),
        )
    ).all()
    for substack, document_id in [*citing, *filed]:
        score = document_scores[document_id]
        current = found.get(substack.id)
        if current is None or score < current[1]:
            found[substack.id] = (substack, score)
    return found


def search_records(
    session: Session,
    organization_id: UUID,
    owner_user_id: UUID | None,
    query: str,
    limit: int,
) -> list[RetrievedRecord]:
    candidates: dict[UUID, tuple[Substack, float | None]] = {}
    for substack in _by_name(session, organization_id, owner_user_id, query, limit):
        candidates[substack.id] = (substack, None)

    hits = search_chunks(session, organization_id, owner_user_id, query, limit * 2)
    document_scores: dict[UUID, float] = {}
    for hit in hits:
        score = hit.score if hit.score is not None else 1.0
        best = document_scores.get(hit.document.id)
        if best is None or score < best:
            document_scores[hit.document.id] = score
    for substack_id, (substack, score) in _by_citation(
        session, organization_id, owner_user_id, document_scores
    ).items():
        if substack_id not in candidates:
            candidates[substack_id] = (substack, score)

    records: list[RetrievedRecord] = []
    for substack, score in candidates.values():
        content = latest_content(session, substack.id)
        confirmed_by = (
            session.get(User, content.confirmed_by_user_id)
            if content is not None and content.confirmed_by_user_id is not None
            else None
        )
        records.append(
            RetrievedRecord(substack=substack, content=content, confirmed_by=confirmed_by, score=score)
        )
    records.sort(key=lambda record: record.rank)
    return records[:limit]


def _content_lines(content: SubstackContent) -> list[str]:
    payload = content.content or {}
    lines: list[str] = []
    text: list[str] = []
    for segment in payload.get("segments", []):
        value = str(segment.get("value", ""))[:MAX_VALUE_CHARS]
        if not value:
            continue
        if segment.get("kind") == "field":
            lines.append(f"{segment.get('name') or 'field'}: {value}")
        elif segment.get("kind") == "token":
            lines.append(f"{segment.get('name') or 'name'}: {value}")
        else:
            text.append(value)
    if text:
        lines.append(" ".join(text)[:MAX_VALUE_CHARS])
    for entry in payload.get("entries", []):
        lines.append(
            f"{entry.get('date', '')} {entry.get('author', '')}: "
            f"{str(entry.get('message', ''))[:MAX_VALUE_CHARS]}".strip()
        )
    return lines


def who_confirmed(record: RetrievedRecord) -> str | None:
    if not record.confirmed:
        return None
    person = record.confirmed_by
    if person is None:
        return None
    return person.display_name or person.email


def record_evidence_text(records: list[RetrievedRecord], maximum: int) -> str:
    """Render records for the model, same untrusted-input framing as passages."""
    blocks: list[str] = []
    used = 0
    for record in records:
        substack = record.substack
        header = (
            f"<record record_id=\"{substack.id}\" name=\"{substack.name}\" "
            f"stack=\"{substack.stack_type}\" checked=\"{record.checked}\""
        )
        person = who_confirmed(record)
        if person:
            header += f" confirmed_by=\"{person}\""
        if record.confirmed_at is not None:
            header += f" confirmed_at=\"{record.confirmed_at.date().isoformat()}\""
        header += ">"
        body_lines = [substack.summary] if substack.summary else []
        if record.content is not None:
            body_lines.extend(_content_lines(record.content))
        block = "\n".join([header, *body_lines, "</record>"])
        if used + len(block) > maximum:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
