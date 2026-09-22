"""Connector-specific normalizers producing SourceDocument values."""
from collections.abc import Iterable
from uuid import UUID

from .ingest import SourceDocument
from .models import WhatsappChat, WhatsappMessage

WHATSAPP_SOURCE = "whatsapp"
DRIVE_SOURCE = "google_drive"


def _speaker(message: WhatsappMessage) -> str:
    if message.from_me:
        return "Me"
    if message.sender_name:
        return message.sender_name
    if message.sender_jid:
        return message.sender_jid.split("@")[0]
    return "Unknown"


def _line(message: WhatsappMessage) -> str | None:
    body = (message.body or "").strip()
    if not body and message.has_media:
        body = f"[{message.msg_type}]"
    if not body:
        return None
    timestamp = message.sent_at.strftime("%Y-%m-%d %H:%M")
    return f"{timestamp} {_speaker(message)}: {body}"


def whatsapp_chat_document(chat: WhatsappChat, messages: Iterable[WhatsappMessage], owner_user_id: UUID | None = None) -> SourceDocument:
    """Render a chat as a chronological transcript, one message per line."""
    lines = [line for line in (_line(message) for message in sorted(messages, key=lambda m: m.sent_at)) if line]
    return SourceDocument(
        source=WHATSAPP_SOURCE,
        external_id=chat.chat_jid,
        title=chat.name or chat.chat_jid,
        content="\n".join(lines),
        owner_user_id=owner_user_id,
    )


def drive_file_document(
    file: dict,
    text: str,
    workspace_id: UUID | None = None,
    owner_user_id: UUID | None = None,
) -> SourceDocument:
    return SourceDocument(
        source=DRIVE_SOURCE,
        external_id=file["id"],
        title=file.get("name") or file["id"],
        content=text,
        source_uri=file.get("webViewLink"),
        drive_workspace_id=workspace_id,
        owner_user_id=owner_user_id,
    )
