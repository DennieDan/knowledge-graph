"""Chat agent: answer a question from source passages, with citations.

The loop is deliberately small and closed:

- The model chooses *what* to search for; it never chooses *where*. Tools are
  called with the organization and user of the request, so a query can only
  ever reach passages the asker may already read.
- Evidence is untrusted text. It travels in the input channel wrapped in
  `<evidence>` tags, never in the instructions, and the agent has no tool that
  writes — the worst an injected document can do is produce a wrong answer,
  not confirm a record.
- Every sentence must cite record or chunk IDs from the retrieved set.
  Citations outside it are dropped, and an answer left with no citation at all
  is downgraded to "not answered" rather than returned as prose.
- Records come before passages: `search_records` is offered first and its
  results are ranked confirmed-first, so the answer is built from what a person
  checked where that exists. Whether the asker can trust it is not left to the
  model's wording: `AgentResult.checked` is true only when every citation is a
  record a *person* confirmed, computed from the rows, not from the answer text.
"""
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .llm import get_llm_client
from .models import ChatMessage, ContentCitation
from .prompts import AGENT_PROMPT, CHAT_PROMPT_VERSION, FINAL_PROMPT, REWRITE_PROMPT
from .record_retrieval import (
    RECORD_RETRIEVAL_VERSION,
    RetrievedRecord,
    get_visible_record,
    record_evidence_text,
    search_records,
    source_document_ids,
    who_confirmed,
)
from .retrieval import (
    RETRIEVAL_VERSION,
    RetrievedChunk,
    chunks_for_documents,
    evidence_text,
    search_chunks,
)

SNIPPET_CHARS = 600
RECORD_EVIDENCE_CHARS = 20000


class StandaloneQuestion(BaseModel):
    question: str


class AnswerSentence(BaseModel):
    text: str
    citations: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    answered: bool
    sentences: list[AnswerSentence] = Field(default_factory=list)


class AgentStep(BaseModel):
    """One turn of the loop: search for more evidence, or answer with what is there."""

    tool: Literal["search_records", "search_sources", "answer"]
    query: str | None = None
    answer: Answer | None = None


@dataclass
class AgentResult:
    text: str
    answered: bool
    citations: list[dict]
    steps: list[dict]
    resolved_question: str
    model: str
    # True only when every citation is a record a person confirmed.
    checked: bool = False
    prompt_version: str = CHAT_PROMPT_VERSION
    retrieval_version: str = f"{RETRIEVAL_VERSION}+{RECORD_RETRIEVAL_VERSION}"
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class _Evidence:
    """Everything retrieved so far this turn, keyed by chunk and record id."""

    chunks: dict[UUID, RetrievedChunk] = field(default_factory=dict)
    records: dict[UUID, RetrievedRecord] = field(default_factory=dict)

    def add(self, hits: list[RetrievedChunk]) -> int:
        new = 0
        for hit in hits:
            if hit.chunk.id not in self.chunks:
                self.chunks[hit.chunk.id] = hit
                new += 1
        return new

    def add_records(self, hits: list[RetrievedRecord]) -> int:
        new = 0
        for hit in hits:
            if hit.substack.id not in self.records:
                self.records[hit.substack.id] = hit
                new += 1
        return new

    def ordered(self) -> list[RetrievedChunk]:
        return sorted(
            self.chunks.values(),
            key=lambda item: (item.score is None, item.score or 0.0, str(item.chunk.id)),
        )

    def ordered_records(self) -> list[RetrievedRecord]:
        return sorted(self.records.values(), key=lambda item: item.rank)

    def allowed_ids(self) -> set[str]:
        return {str(chunk_id) for chunk_id in self.chunks} | {
            str(record_id) for record_id in self.records
        }


def _snippet(text: str) -> str:
    return text if len(text) <= SNIPPET_CHARS else f"{text[:SNIPPET_CHARS].rstrip()}…"


def _citation_json(hit: RetrievedChunk) -> dict:
    return {
        "chunk_id": str(hit.chunk.id),
        "document_id": str(hit.document.id),
        "title": hit.document.title,
        "source": hit.document.source,
        "source_uri": hit.document.source_uri,
        "snippet": _snippet(hit.chunk.text),
    }


def _record_citation_json(session: Session, record: RetrievedRecord) -> dict:
    document_ids: list[str] = []
    if record.content is not None:
        document_ids = [
            str(document_id)
            for (document_id,) in session.execute(
                select(ContentCitation.document_id)
                .where(ContentCitation.content_id == record.content.id)
                .distinct()
            ).all()
        ]
    return {
        "record_id": str(record.substack.id),
        "name": record.substack.name,
        "stack_type": record.substack.stack_type,
        "checked": record.checked,
        "confirmed_by": who_confirmed(record),
        "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
        "revision": record.content.revision if record.content else None,
        "source_ids": sorted(document_ids),
    }


def _history(session: Session, thread_id: UUID) -> list[ChatMessage]:
    turns = get_settings().chat_history_turns * 2
    messages = (
        session.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id)
        .limit(turns)
        .all()
    )
    return list(reversed(messages))


def resolve_question(session: Session, thread_id: UUID, question: str) -> str:
    """Turn a follow-up ("and its due date?") into something retrievable."""
    history = _history(session, thread_id)
    if not history:
        return question
    transcript = "\n".join(f"{message.role}: {message.text}" for message in history)
    result = get_llm_client().parse(
        prompt=REWRITE_PROMPT,
        evidence=f"<conversation>\n{transcript}\n</conversation>\n\n<question>\n{question}\n</question>",
        schema=StandaloneQuestion,
        effort=get_settings().chat_reasoning_effort,
    )
    rewritten = result.parsed.question.strip()
    return rewritten or question


def _agent_input(
    question: str,
    evidence: _Evidence,
    searches: list[str],
    *,
    scope: RetrievedRecord | None = None,
) -> str:
    blocks = [f"<question>\n{question}\n</question>"]
    if scope is not None:
        blocks.append(
            f"<scope record_id=\"{scope.substack.id}\" name=\"{scope.substack.name}\" "
            f"stack=\"{scope.substack.stack_type}\">"
            "The asker opened this record. Prefer it and its sources; search further only "
            "for context this record does not cover."
            "</scope>"
        )
    if searches:
        blocks.append("<searches_already_run>\n" + "\n".join(searches) + "\n</searches_already_run>")
    records = record_evidence_text(evidence.ordered_records(), RECORD_EVIDENCE_CHARS)
    blocks.append(f"<records>\n{records}\n</records>" if records else "<records>none</records>")
    body = evidence_text(evidence.ordered())
    blocks.append(f"<evidence>\n{body}\n</evidence>" if body else "<evidence>none</evidence>")
    return "\n\n".join(blocks)


def _search_note(label: str, hits: int, new: int) -> str:
    if hits == 0:
        return f"{label} -> nothing found"
    if new == 0:
        return f"{label} -> {hits} hit(s), none new"
    return f"{label} -> {new} new"


class _Searcher:
    """Runs the two retrieval tools, remembers what was asked, and narrates it.

    The narration goes back to the model as `<searches_already_run>`: without
    it the model repeats one query until the step budget runs out.
    """

    def __init__(self, session: Session, organization_id: UUID, user_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id
        self._user_id = user_id
        self._limit = get_settings().chat_search_limit
        self.evidence = _Evidence()
        self.notes: list[str] = []
        self._seen: set[tuple[str, str]] = set()
        # Ask-from-order (#94): while set, `search_sources` stays on these documents.
        self.scoped_document_ids: list[UUID] | None = None

    def scope_to(self, document_ids: list[UUID]) -> None:
        self.scoped_document_ids = document_ids

    def already_run(self, tool: str, query: str) -> bool:
        return (tool, query.casefold()) in self._seen

    def run(self, tool: str, query: str, *, widen: bool = True) -> dict:
        self._seen.add((tool, query.casefold()))
        if tool == "search_records":
            records = search_records(
                self._session, self._organization_id, self._user_id, query, self._limit
            )
            new = self.evidence.add_records(records)
            self.notes.append(_search_note(f"records: {query}", len(records), new))
            if widen:
                # Related records may need company-wide sources; drop the document filter.
                self.scoped_document_ids = None
            return {
                "tool": "search_records",
                "query": query,
                "hits": len(records),
                "new_records": new,
            }
        scoped = self.scoped_document_ids is not None
        hits = search_chunks(
            self._session,
            self._organization_id,
            self._user_id,
            query,
            self._limit,
            document_ids=self.scoped_document_ids,
        )
        new = self.evidence.add(hits)
        self.notes.append(_search_note(f"{'scoped sources' if scoped else 'sources'}: {query}", len(hits), new))
        return {"tool": "search_sources", "query": query, "hits": len(hits), "new_chunks": new, "scoped": scoped}


def _validated(answer: Answer, allowed: set[str]) -> Answer:
    """Drop citations outside the evidence set; an uncited answer is no answer."""
    for sentence in answer.sentences:
        sentence.citations = [citation for citation in sentence.citations if citation in allowed]
    answer.sentences = [sentence for sentence in answer.sentences if sentence.text.strip() and sentence.citations]
    if not answer.sentences:
        return Answer(answered=False, sentences=[])
    return Answer(answered=True, sentences=answer.sentences)


def _result(
    session: Session,
    answer: Answer,
    evidence: _Evidence,
    steps: list[dict],
    question: str,
    usage: list,
) -> AgentResult:
    settings = get_settings()
    cited: dict[str, dict] = {}
    checked = answer.answered
    for sentence in answer.sentences:
        for citation in sentence.citations:
            identifier = UUID(citation)
            record = evidence.records.get(identifier)
            if record is not None:
                cited.setdefault(citation, _record_citation_json(session, record))
                checked = checked and record.checked == "person"
                continue
            hit = evidence.chunks.get(identifier)
            if hit is not None:
                cited.setdefault(citation, _citation_json(hit))
                checked = False
    text = " ".join(sentence.text.strip() for sentence in answer.sentences)
    input_tokens = sum(tokens for tokens, _ in usage if tokens is not None) or None
    output_tokens = sum(tokens for _, tokens in usage if tokens is not None) or None
    return AgentResult(
        text=text,
        answered=answer.answered,
        citations=list(cited.values()),
        steps=steps,
        resolved_question=question,
        model=settings.openai_model,
        checked=checked,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def run_agent(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    question: str,
    *,
    scope_substack_id: UUID | None = None,
) -> Generator[dict, None, AgentResult]:
    """Run the loop for one question, yielding progress events as it goes.

    When `scope_substack_id` is set (ask from this order), that record and its
    sources are seeded into evidence first. Further `search_sources` calls stay
    on those documents until a model-requested records search widens the set —
    records-first still applies for related confirmed orders.

    Events are what the asker can be shown while waiting: `searching` before a
    search runs, `step` once it has, and `thinking` before each model call. The
    generator's return value is the finished answer.
    """
    settings = get_settings()
    client = get_llm_client()
    searcher = _Searcher(session, organization_id, user_id)
    evidence = searcher.evidence
    usage: list[tuple[int | None, int | None]] = []
    answer: Answer | None = None
    steps: list[dict] = []
    scope: RetrievedRecord | None = None
    if scope_substack_id is not None:
        scope = get_visible_record(session, organization_id, user_id, scope_substack_id)
        if scope is not None:
            for seeded in _seed_scope(
                session, organization_id, user_id, evidence, scope, settings.chat_search_limit
            ):
                steps.append(seeded)
                yield {"type": "step", **seeded}
            searcher.scope_to(source_document_ids(session, scope.substack.id))

    def search(tool: str, query: str, **extra) -> Generator[dict, None, None]:
        yield {"type": "searching", "tool": tool, "query": query}
        # The opening searches never widen a scope; only the model's own records search does.
        step = {**searcher.run(tool, query, widen=not extra.get("opening", False)), **extra}
        steps.append(step)
        yield {"type": "step", **step}

    def record(step: dict) -> dict:
        steps.append(step)
        return {"type": "step", **step}

    # Both stores are searched for the question itself before the model is asked
    # anything: a record lookup and a passage lookup answer most questions
    # between them, and the model cannot leave one of them unsearched.
    yield from search("search_records", question, opening=True)
    yield from search("search_sources", question, opening=True)

    for _ in range(settings.chat_max_steps):
        yield {"type": "thinking", "stage": "deciding"}
        result = client.parse(
            prompt=AGENT_PROMPT,
            evidence=_agent_input(question, evidence, searcher.notes, scope=scope),
            schema=AgentStep,
            effort=settings.chat_reasoning_effort,
        )
        usage.append((result.input_tokens, result.output_tokens))
        step = result.parsed
        if step.tool == "answer" and step.answer is not None:
            answer = _validated(step.answer, evidence.allowed_ids())
            yield record({"tool": "answer", "answered": answer.answered})
            break
        query = (step.query or "").strip()
        if not query:
            break
        if searcher.already_run(step.tool, query):
            # Re-running a query cannot add evidence, so spend the step on the
            # answer instead of letting the model loop on it.
            yield record({"tool": step.tool, "query": query, "skipped": "duplicate"})
            break
        yield from search(step.tool, query)

    if answer is None:
        # Out of steps: answer once from whatever the searches found.
        yield {"type": "thinking", "stage": "answering"}
        final = client.parse(
            prompt=FINAL_PROMPT,
            evidence=_agent_input(question, evidence, searcher.notes, scope=scope),
            schema=Answer,
            effort=settings.chat_reasoning_effort,
        )
        usage.append((final.input_tokens, final.output_tokens))
        answer = _validated(final.parsed, evidence.allowed_ids())
        yield record({"tool": "answer", "answered": answer.answered, "forced": True})

    return _result(session, answer, evidence, steps, question, usage)


def _seed_scope(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    evidence: _Evidence,
    scope: RetrievedRecord,
    limit: int,
) -> list[dict]:
    """Pre-load the open record and its sources so ask-from-order starts records-first."""
    evidence.add_records([scope])
    document_ids = source_document_ids(session, scope.substack.id)
    seeded = chunks_for_documents(session, organization_id, user_id, document_ids, limit)
    evidence.add(seeded)
    return [
        {
            "tool": "scope_record",
            "record_id": str(scope.substack.id),
            "name": scope.substack.name,
            "source_documents": len(document_ids),
            "source_chunks": len(seeded),
        }
    ]


def answer_question(
    session: Session,
    organization_id: UUID,
    user_id: UUID,
    question: str,
    *,
    scope_substack_id: UUID | None = None,
) -> AgentResult:
    """Run the loop for one question and return an answer with its citations.

    `scope_substack_id` is the ask-from-order scope; see `run_agent`.
    """
    events = run_agent(session, organization_id, user_id, question, scope_substack_id=scope_substack_id)
    while True:
        try:
            next(events)
        except StopIteration as done:
            return done.value
