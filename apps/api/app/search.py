"""Search API: ranked source passages for a question.

Hits come from the latest revision of each document the asker may see, ordered
by embedding distance. Every hit carries its document and, when the document is
filed, the substack it belongs to, so a reader can walk from a passage to the
record it supports.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import get_current_user
from .database import get_session
from .filing import substack_for_document
from .models import User
from .retrieval import RetrievedChunk, search_chunks

router = APIRouter(tags=["search"])

SOURCE_LABELS = {"google_drive": "Google Drive", "whatsapp": "WhatsApp"}
SNIPPET_CHARS = 600
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return f"{text[:SNIPPET_CHARS].rstrip()}…"


def _hit_json(session: Session, hit: RetrievedChunk) -> dict:
    substack = substack_for_document(session, hit.document)
    return {
        "chunk_id": str(hit.chunk.id),
        "document_id": str(hit.document.id),
        "title": hit.document.title,
        "source": hit.document.source,
        "source_label": SOURCE_LABELS.get(hit.document.source, hit.document.source),
        "source_uri": hit.document.source_uri,
        "snippet": _snippet(hit.chunk.text),
        "position": hit.chunk.position,
        # Cosine distance, so 1.0 is identical and lower similarity sorts last.
        "similarity": None if hit.score is None else round(1.0 - hit.score, 4),
        "substack": None
        if substack is None
        else {
            "id": str(substack.id),
            "name": substack.name,
            "type_id": substack.stack_type,
            "status": substack.status,
            "review_state": substack.review_state,
        },
    }


@router.get("/accounts/{organization_id}/search")
def search(
    organization_id: UUID,
    q: str = Query(min_length=1, max_length=1000),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    query = q.strip()
    if not query:
        return {"query": q, "results": []}
    hits = search_chunks(session, organization_id, user.id, query, limit)
    return {"query": query, "results": [_hit_json(session, hit) for hit in hits]}
