"""Stub generator for stack types without a dedicated template yet.

Produces a minimal segment list (name + evidence titles) so every substack
type proves the pipeline end-to-end before LLM extraction replaces it.
"""
from app.segments import GeneratedContent, Segment

from .registry import STUB_PROMPT_KEY, GenerationContext, register


@register(STUB_PROMPT_KEY)
def stub(ctx: GenerationContext) -> GeneratedContent:
    segments = [Segment(kind="text", value=ctx.substack.name)]
    for document in ctx.documents:
        chunk_id = next(
            (str(c.id) for c in ctx.chunks if ctx.chunk_document.get(c.id) == document.id),
            None,
        )
        segments.append(Segment(kind="token", value=document.title, citations=[chunk_id] if chunk_id else []))
    return GeneratedContent(segments=segments)
