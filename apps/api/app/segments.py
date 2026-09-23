"""Structured generated content: token streams with chunk-level citations.

Substack content is stored as JSONB matching GeneratedContent, not flat text:
- `segments` render as prose where `token`/`field` parts are highlighted and
  hover-filter the Sources panel (maps to the frontend's DetailToken/sourceIds).
- `entries` are conversation items (WhatsApp messages today), each citing the
  transcript chunk containing its line and carrying a `locator` (wa_message_id)
  for deep-linking.
- `citations` list chunk ids; `generation.run_generation` validates every id
  against the input evidence set before storing.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Segment(BaseModel):
    kind: Literal["text", "token", "field"]
    value: str
    # kind="field": machine label, e.g. "quantity"; kind="token": display label = value.
    name: Optional[str] = None
    # kind="token": optional related substack id for click-through navigation.
    ref: Optional[str] = None
    citations: list[str] = Field(default_factory=list)
    locator: Optional[dict] = None


class ConversationEntry(BaseModel):
    date: str
    author: str
    message: str
    citations: list[str] = Field(default_factory=list)
    locator: Optional[dict] = None


class GeneratedContent(BaseModel):
    segments: list[Segment] = Field(default_factory=list)
    entries: list[ConversationEntry] = Field(default_factory=list)

    def cited_chunk_ids(self) -> list[str]:
        seen: list[str] = []
        for item in (*self.segments, *self.entries):
            seen.extend(c for c in item.citations if c not in seen)
        return seen
