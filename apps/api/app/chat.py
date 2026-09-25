"""Chat API: ask the knowledge base a question and get a cited answer.

A thread belongs to one person in one organization and is readable only by
them, because its answers can quote their owner-only documents. Each turn
stores the question, the rewritten question actually retrieved on, the
answer, its citations, the searches the agent ran, and the model and prompt
versions behind it — so an answer can be audited later and scored against a
labelled question set.

Every answer carries a checked line: `checked` is true only when everything it
cited is a record a person confirmed, and `checked_note` names who confirmed it
and when. Content a generator confirmed on its own is *not* checked.
"""
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .chat_agent import AgentResult, answer_question, resolve_question, run_agent
from .database import get_engine, get_session
from .models import ChatMessage, ChatThread, User
from .record_retrieval import get_visible_record

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

TITLE_CHARS = 120
NO_ANSWER_TEXT = "I could not find this in the sources I can see."
UNCHECKED_NOTE = "Not confirmed by anyone yet"
SOURCE_NOTE = "From sources, not yet confirmed"


class ThreadIn(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_CHARS)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    # Ask-from-order: either field scopes retrieval to that record (#94).
    # `record_id` is an alias for `substack_id` (citations already use record_id).
    substack_id: UUID | None = None
    record_id: UUID | None = None

    def scope_substack_id(self) -> UUID | None:
        return self.substack_id or self.record_id


class FeedbackIn(BaseModel):
    rating: str
    reason: str | None = Field(default=None, max_length=500)

    def normalized(self) -> str:
        if self.rating not in ("up", "down"):
            raise HTTPException(status_code=422, detail="invalid_rating")
        return self.rating

    def normalized_reason(self) -> str | None:
        if self.reason is None:
            return None
        reason = self.reason.strip()
        return reason or None


def _thread_json(thread: ChatThread) -> dict:
    return {
        "id": str(thread.id),
        "title": thread.title,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
    }


def _checked_note(message: ChatMessage) -> str | None:
    """The line under an answer: who checked what it was built from."""
    if not message.answered:
        return None
    records = [citation for citation in message.citations or [] if citation.get("record_id")]
    if not records:
        return SOURCE_NOTE
    people = []
    for citation in records:
        if citation.get("checked") != "person":
            continue
        person = citation.get("confirmed_by")
        confirmed_at = (citation.get("confirmed_at") or "")[:10]
        label = f"{person} on {confirmed_at}" if person and confirmed_at else person or confirmed_at
        if label and label not in people:
            people.append(label)
    if not people:
        return UNCHECKED_NOTE
    note = f"Confirmed by {', '.join(people)}"
    return note if message.checked else f"{note}; other parts are not confirmed yet"


def _message_json(message: ChatMessage) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "text": message.text,
        "answered": message.answered,
        "checked": message.checked,
        "checked_note": _checked_note(message),
        "citations": message.citations,
        "steps": message.steps,
        "feedback": message.feedback,
        "feedback_reason": message.feedback_reason,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _get_thread(organization_id: UUID, thread_id: UUID, user: User, session: Session) -> ChatThread:
    membership_for(organization_id, user, session)
    thread = session.get(ChatThread, thread_id)
    if thread is None or thread.organization_id != organization_id or thread.user_id != user.id:
        raise HTTPException(status_code=404, detail="thread_not_found")
    return thread


@router.post("/accounts/{organization_id}/chat/threads", status_code=201)
def create_thread(
    organization_id: UUID,
    body: ThreadIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    thread = ChatThread(organization_id=organization_id, user_id=user.id, title=body.title)
    session.add(thread)
    session.commit()
    return _thread_json(thread)


@router.get("/accounts/{organization_id}/chat/threads")
def list_threads(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    threads = session.scalars(
        select(ChatThread)
        .where(ChatThread.organization_id == organization_id, ChatThread.user_id == user.id)
        .order_by(ChatThread.updated_at.desc())
    ).all()
    return {"threads": [_thread_json(thread) for thread in threads]}


@router.get("/accounts/{organization_id}/chat/threads/{thread_id}")
def get_thread(
    organization_id: UUID,
    thread_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    thread = _get_thread(organization_id, thread_id, user, session)
    messages = session.scalars(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(
            # A turn commits the question and answer together, so their
            # created_at ties; keep the question first on ties.
            ChatMessage.created_at,
            case((ChatMessage.role == "user", 0), else_=1),
            ChatMessage.id,
        )
    ).all()
    return {**_thread_json(thread), "messages": [_message_json(message) for message in messages]}


def _question(body: MessageIn) -> str:
    question = body.text.strip()
    if not question:
        raise HTTPException(status_code=422, detail="empty_question")
    return question


def _save_answer(
    session: Session, thread: ChatThread, question: str, resolved: str, result: AgentResult
) -> ChatMessage:
    answer = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        text=result.text if result.answered else NO_ANSWER_TEXT,
        resolved_question=resolved,
        answered=result.answered,
        checked=result.checked,
        citations=result.citations,
        steps=result.steps,
        model=result.model,
        prompt_version=result.prompt_version,
        retrieval_version=result.retrieval_version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    session.add(answer)
    if thread.title is None:
        thread.title = question[:TITLE_CHARS]
    session.commit()
    return answer


@router.post("/accounts/{organization_id}/chat/threads/{thread_id}/messages", status_code=201)
def post_message(
    organization_id: UUID,
    thread_id: UUID,
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    thread = _get_thread(organization_id, thread_id, user, session)
    question = _question(body)
    scope_id = body.scope_substack_id()
    if scope_id is not None and get_visible_record(session, organization_id, user.id, scope_id) is None:
        raise HTTPException(status_code=404, detail="scope_not_found")

    resolved = resolve_question(session, thread.id, question)
    session.add(ChatMessage(thread_id=thread.id, role="user", text=question, resolved_question=resolved))
    session.flush()

    result = answer_question(session, organization_id, user.id, resolved, scope_substack_id=scope_id)
    return _message_json(_save_answer(session, thread, question, resolved, result))


def get_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    return lambda: Session(get_engine())


def _event_line(event: dict) -> bytes:
    return (json.dumps(event, default=str) + "\n").encode()


@router.post("/accounts/{organization_id}/chat/threads/{thread_id}/messages/stream")
def stream_message(
    organization_id: UUID,
    thread_id: UUID,
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    open_session: Callable[[], AbstractContextManager[Session]] = Depends(get_session_factory),
):
    """Answer like `post_message`, streaming the agent's progress as NDJSON.

    Each line is one event from `run_agent`, then a final `message` line with
    the saved answer (or an `error` line). Access is checked before streaming
    starts, so an unknown thread is still a plain 404. The turn runs in its own
    session: the request's session is closed once the response starts.
    """
    _get_thread(organization_id, thread_id, user, session)
    question = _question(body)
    scope_id = body.scope_substack_id()
    if scope_id is not None and get_visible_record(session, organization_id, user.id, scope_id) is None:
        raise HTTPException(status_code=404, detail="scope_not_found")
    user_id = user.id

    def events() -> Iterator[bytes]:
        with open_session() as turn:
            try:
                thread = turn.get_one(ChatThread, thread_id)
                resolved = resolve_question(turn, thread.id, question)
                turn.add(ChatMessage(thread_id=thread.id, role="user", text=question, resolved_question=resolved))
                turn.flush()
                agent = run_agent(turn, organization_id, user_id, resolved, scope_substack_id=scope_id)
                while True:
                    try:
                        yield _event_line(next(agent))
                    except StopIteration as done:
                        result = done.value
                        break
                answer = _save_answer(turn, thread, question, resolved, result)
                yield _event_line({"type": "message", "message": _message_json(answer)})
            except Exception:
                logger.exception("chat_stream_failed")
                turn.rollback()
                yield _event_line({"type": "error"})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/accounts/{organization_id}/chat/messages/{message_id}/feedback")
def set_feedback(
    organization_id: UUID,
    message_id: UUID,
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rating = body.normalized()
    message = session.get(ChatMessage, message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="message_not_found")
    _get_thread(organization_id, message.thread_id, user, session)
    message.feedback = rating
    message.feedback_reason = body.normalized_reason()
    session.commit()
    return _message_json(message)
