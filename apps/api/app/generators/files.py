"""Template generator for Files substacks: describe each evidence document."""
from sqlalchemy import select

from app.models import DriveWorkspace
from app.segments import GeneratedContent, Segment

from .registry import GenerationContext, register

SOURCE_LABELS = {"google_drive": "Google Drive", "whatsapp": "WhatsApp"}


def _first_chunk_id(ctx: GenerationContext, document_id) -> str | None:
    for chunk in ctx.chunks:
        if ctx.chunk_document.get(chunk.id) == document_id:
            return str(chunk.id)
    return None


@register("files.describe.v0", auto_confirm=True)
def describe_file(ctx: GenerationContext) -> GeneratedContent:
    segments: list[Segment] = []
    for document in ctx.documents:
        citation = _first_chunk_id(ctx, document.id)
        citations = [citation] if citation else []
        segments.append(Segment(kind="token", value=document.title, citations=citations))
        origin = SOURCE_LABELS.get(document.source, document.source)
        if document.drive_workspace_id:
            workspace = ctx.session.get(DriveWorkspace, document.drive_workspace_id)
            if workspace is not None:
                origin = f"{origin} · {workspace.name}"
        segments.append(Segment(kind="field", name="origin", value=origin, citations=citations))
        if document.source_uri:
            segments.append(Segment(kind="field", name="link", value=document.source_uri, citations=citations))
    return GeneratedContent(segments=segments)
