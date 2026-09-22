"""Template generator for Conversations substacks: entries from whatsapp_messages."""
from sqlalchemy import select

from app.models import WhatsappChat, WhatsappMessage
from app.segments import ConversationEntry, GeneratedContent, Segment
from app.sources import speaker_label, transcript_line

from .registry import GenerationContext, register

MAX_ENTRIES = 100


def _chunk_for_line(ctx: GenerationContext, document_id, line: str) -> str | None:
    """Find the transcript chunk containing a rendered message line."""
    for chunk in ctx.chunks:
        if ctx.chunk_document.get(chunk.id) == document_id and line in chunk.text:
            return str(chunk.id)
    return None


@register("conversations.transcript.v0", auto_confirm=True)
def transcript(ctx: GenerationContext) -> GeneratedContent:
    segments: list[Segment] = []
    entries: list[ConversationEntry] = []
    for document in ctx.documents:
        chat = ctx.session.scalar(
            select(WhatsappChat).where(WhatsappChat.chat_jid == document.external_id)
        )
        if chat is None:
            continue
        messages = ctx.session.scalars(
            select(WhatsappMessage)
            .where(WhatsappMessage.chat_id == chat.id)
            .order_by(WhatsappMessage.sent_at)
        ).all()
        first_chunk = _first(ctx, document.id)
        segments.append(Segment(kind="token", value=document.title, citations=[first_chunk] if first_chunk else []))
        segments.append(Segment(kind="field", name="messages", value=str(len(messages)), citations=[first_chunk] if first_chunk else []))
        for message in messages[-MAX_ENTRIES:]:
            line = transcript_line(message)
            if line is None:
                continue
            citation = _chunk_for_line(ctx, document.id, line)
            entries.append(ConversationEntry(
                date=message.sent_at.isoformat(),
                author=speaker_label(message),
                message=(message.body or f"[{message.msg_type}]").strip(),
                citations=[citation] if citation else [],
                locator={"wa_message_id": message.wa_message_id},
            ))
    return GeneratedContent(segments=segments, entries=entries)


def _first(ctx: GenerationContext, document_id) -> str | None:
    for chunk in ctx.chunks:
        if ctx.chunk_document.get(chunk.id) == document_id:
            return str(chunk.id)
    return None
