"""Generator registry: prompt_key -> callable producing GeneratedContent.

Generators are pure functions over a GenerationContext. Templates ship today
(`model = "template"`); LLM generators register under new prompt keys later and
reuse the same interface. `auto_confirm` marks output `confirmed` immediately —
safe for deterministic templates, off for stubs.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Chunk, Document, Substack
from app.segments import GeneratedContent


@dataclass
class GenerationContext:
    session: Session
    substack: Substack
    documents: list[Document]
    chunks: list[Chunk]
    # chunk_id -> document_id, so a citation can name its document without a join.
    chunk_document: dict[UUID, UUID] = field(default_factory=dict)


GeneratorFn = Callable[[GenerationContext], GeneratedContent]

GENERATORS: dict[str, tuple[GeneratorFn, bool]] = {}


def register(prompt_key: str, auto_confirm: bool = False):
    def decorator(fn: GeneratorFn) -> GeneratorFn:
        GENERATORS[prompt_key] = (fn, auto_confirm)
        return fn
    return decorator


PROMPT_KEYS = {
    "files": "files.describe.v0",
    "conversations": "conversations.transcript.v0",
}
STUB_PROMPT_KEY = "generic.stub.v0"


def prompt_key_for(stack_type: str) -> str:
    return PROMPT_KEYS.get(stack_type, STUB_PROMPT_KEY)


def prompt_version(prompt_key: str) -> str:
    return prompt_key.rsplit(".", 1)[-1]
