import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import waha_client
from .accounts import membership_for
from .auth import get_current_user
from .config import get_settings
from .database import get_engine, get_session
from .filing import ingest_and_file
from .models import User, WhatsappChat, WhatsappConnection, WhatsappMessage
from .sources import whatsapp_chat_document

MESSAGES_PAGE_SIZE = 100
CHATS_PAGE_SIZE = 100
INGEST_DEBOUNCE_SECONDS = 30

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


class PairingRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=20)


class ImportRequest(BaseModel):
    chat_ids: list[str] = Field(min_length=1, max_length=50)
    organization_id: UUID | None = None


def get_connection(user: User, session: Session) -> WhatsappConnection | None:
    return session.scalar(
        select(WhatsappConnection).where(WhatsappConnection.user_id == user.id)
    )


def require_connection(user: User, session: Session) -> WhatsappConnection:
    conn = get_connection(user, session)
    if conn is None:
        raise HTTPException(status_code=409, detail="whatsapp_not_connected")
    return conn


def waha_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(status_code=502, detail="waha_auth_failed") from exc
        raise HTTPException(status_code=502, detail="waha_request_failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="waha_unavailable") from exc


def sync_connection_status(conn: WhatsappConnection, session: Session) -> WhatsappConnection:
    remote = waha_call(waha_client.get_session, conn.waha_session)
    if remote is None:
        conn.status = "STOPPED"
    else:
        conn.status = remote.get("status", conn.status)
        me = remote.get("me") or {}
        if me.get("id"):
            conn.phone_number = str(me["id"]).split("@")[0].lstrip("+")
    session.commit()
    return conn


def chat_type_for(jid: str) -> str:
    if jid.endswith("@g.us"):
        return "group"
    if jid.endswith("@newsletter"):
        return "channel"
    return "contact"


def remote_jid_for(msg: dict) -> str | None:
    if msg.get("chatId"):
        return msg["chatId"]
    if msg.get("fromMe"):
        return msg.get("to")
    return msg.get("from")


def upsert_message(session: Session, chat: WhatsappChat, msg: dict) -> bool:
    """Insert one WAHA message; returns True when a new row was added."""
    wa_id = msg.get("id")
    timestamp = msg.get("timestamp")
    if not wa_id or not timestamp:
        return False
    exists = session.scalar(
        select(WhatsappMessage.id).where(
            WhatsappMessage.chat_id == chat.id,
            WhatsappMessage.wa_message_id == wa_id,
        )
    )
    if exists is not None:
        return False
    from_me = bool(msg.get("fromMe"))
    session.add(
        WhatsappMessage(
            chat_id=chat.id,
            wa_message_id=wa_id,
            sent_at=datetime.fromtimestamp(int(timestamp), timezone.utc),
            sender_jid=msg.get("participant") or msg.get("author") or (None if from_me else msg.get("from")),
            sender_name=msg.get("notifyName"),
            from_me=from_me,
            msg_type=msg.get("type") or "chat",
            body=msg.get("body"),
            has_media=bool(msg.get("hasMedia")),
            raw=msg,
        )
    )
    return True


def ingest_chat_transcript(session: Session, conn: WhatsappConnection, chat: WhatsappChat) -> None:
    """Render the chat's messages into a transcript document owned by the importer."""
    if chat.organization_id is None:
        return
    messages = session.scalars(select(WhatsappMessage).where(WhatsappMessage.chat_id == chat.id)).all()
    ingest_and_file(session, chat.organization_id, whatsapp_chat_document(chat, messages, conn.user_id))


def debounced_ingest(chat_id: UUID) -> None:
    """Re-ingest a transcript once a webhook burst settles; pending_ingest coalesces messages."""
    time.sleep(INGEST_DEBOUNCE_SECONDS)
    with Session(get_engine()) as session:
        chat = session.get(WhatsappChat, chat_id)
        if chat is None or not chat.pending_ingest:
            return
        conn = session.get(WhatsappConnection, chat.connection_id)
        chat.pending_ingest = False
        if conn is not None and chat.import_status == "imported":
            ingest_chat_transcript(session, conn, chat)
        session.commit()


def run_import(connection_id: UUID, chat_jids: list[str]) -> None:
    """Background import of full chat history; idempotent via wa_message_id."""
    with Session(get_engine()) as session:
        conn = session.get(WhatsappConnection, connection_id)
        if conn is None:
            return
        chats = session.scalars(
            select(WhatsappChat).where(
                WhatsappChat.connection_id == conn.id,
                WhatsappChat.chat_jid.in_(chat_jids),
            )
        ).all()
        for chat in chats:
            try:
                offset = 0
                while True:
                    page = waha_client.get_messages(conn.waha_session, chat.chat_jid, MESSAGES_PAGE_SIZE, offset)
                    for msg in page:
                        upsert_message(session, chat, msg)
                    session.commit()
                    if len(page) < MESSAGES_PAGE_SIZE:
                        break
                    offset += len(page)
                chat.import_status = "imported"
                chat.import_error = None
                chat.message_count = session.scalar(
                    select(func.count(WhatsappMessage.id)).where(WhatsappMessage.chat_id == chat.id)
                ) or 0
                ingest_chat_transcript(session, conn, chat)
            except httpx.HTTPError as exc:
                chat.import_status = "failed"
                chat.import_error = f"{type(exc).__name__}: {exc}"[:500]
            session.commit()


@router.post("/connect")
def connect(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = get_connection(user, session)
    if conn is None:
        conn = WhatsappConnection(user_id=user.id, waha_session=waha_client.session_name_for(user.id))
        session.add(conn)
        session.commit()
    waha_call(waha_client.create_session, conn.waha_session)
    conn = sync_connection_status(conn, session)
    return {"status": conn.status, "phone_number": conn.phone_number}


@router.get("/connect/status")
def connect_status(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = require_connection(user, session)
    conn = sync_connection_status(conn, session)
    return {"status": conn.status, "phone_number": conn.phone_number}


@router.get("/connect/qr")
def connect_qr(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = require_connection(user, session)
    qr = waha_call(waha_client.get_qr, conn.waha_session)
    return {"mimetype": qr.get("mimetype", "image/png"), "data": qr["data"]}


@router.post("/connect/pairing")
def connect_pairing(
    body: PairingRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conn = require_connection(user, session)
    code = waha_call(waha_client.request_pairing_code, conn.waha_session, body.phone_number)
    return {"code": code}


@router.delete("/connect")
def disconnect(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = require_connection(user, session)
    try:
        waha_client.delete_session(conn.waha_session)
    except httpx.HTTPError:
        pass
    session.delete(conn)  # cascades to chats and imported messages
    session.commit()
    return {"status": "ok"}


@router.get("/chats")
def list_chats(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = require_connection(user, session)
    offset = 0
    overview: list[dict] = []
    while True:
        page = waha_call(waha_client.chats_overview, conn.waha_session, CHATS_PAGE_SIZE, offset)
        overview.extend(page)
        if len(page) < CHATS_PAGE_SIZE:
            break
        offset += len(page)

    existing = {
        chat.chat_jid: chat
        for chat in session.scalars(
            select(WhatsappChat).where(WhatsappChat.connection_id == conn.id)
        )
    }
    result = []
    for item in overview:
        jid = item.get("id")
        if not jid:
            continue
        last = item.get("lastMessage") or {}
        last_at = (
            datetime.fromtimestamp(int(last["timestamp"]), timezone.utc)
            if last.get("timestamp")
            else None
        )
        chat = existing.get(jid)
        if chat is None:
            chat = WhatsappChat(connection_id=conn.id, chat_jid=jid)
            session.add(chat)
        chat.name = item.get("name")
        chat.chat_type = chat_type_for(jid)
        if last_at and (chat.last_message_at is None or last_at > chat.last_message_at):
            chat.last_message_at = last_at
        result.append(chat)
    session.commit()
    result.sort(key=lambda c: c.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [
        {
            "chat_jid": c.chat_jid,
            "name": c.name,
            "chat_type": c.chat_type,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            "import_status": c.import_status,
            "message_count": c.message_count,
        }
        for c in result
    ]


@router.post("/imports")
def start_import(
    body: ImportRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conn = require_connection(user, session)
    if body.organization_id is not None:
        membership_for(body.organization_id, user, session)
    chats = session.scalars(
        select(WhatsappChat).where(
            WhatsappChat.connection_id == conn.id,
            WhatsappChat.chat_jid.in_(body.chat_ids),
        )
    ).all()
    found = {chat.chat_jid for chat in chats}
    missing = [jid for jid in body.chat_ids if jid not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"unknown_chats: {missing}")
    queued = []
    for chat in chats:
        if body.organization_id is not None:
            chat.organization_id = body.organization_id
        if chat.import_status != "importing":
            chat.import_status = "importing"
            chat.import_error = None
            queued.append(chat.chat_jid)
    session.commit()
    if queued:
        background_tasks.add_task(run_import, conn.id, queued)
    return {"queued": queued}


@router.get("/imports")
def import_status(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    conn = require_connection(user, session)
    chats = session.scalars(
        select(WhatsappChat).where(
            WhatsappChat.connection_id == conn.id,
            WhatsappChat.import_status.in_(["importing", "imported", "failed"]),
        )
    ).all()
    return [
        {
            "chat_jid": c.chat_jid,
            "name": c.name,
            "import_status": c.import_status,
            "import_error": c.import_error,
            "message_count": c.message_count,
        }
        for c in chats
    ]


@router.post("/webhooks")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    settings = get_settings()
    if settings.waha_webhook_secret is not None and (
        x_webhook_token != settings.waha_webhook_secret.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail="invalid_webhook_token")

    event = await request.json()
    session_name = event.get("session")
    if not session_name:
        return {"status": "ignored"}

    conn = session.scalar(
        select(WhatsappConnection).where(WhatsappConnection.waha_session == session_name)
    )
    if conn is None:
        return {"status": "ignored"}

    if event.get("event") == "session.status":
        payload = event.get("payload") or {}
        conn.status = payload.get("status", conn.status)
        me = event.get("me") or {}
        if me.get("id"):
            conn.phone_number = str(me["id"]).split("@")[0].lstrip("+")
        session.commit()
        return {"status": "ok"}

    if event.get("event") in ("message", "message.any"):
        msg = event.get("payload") or {}
        jid = remote_jid_for(msg)
        chat = session.scalar(
            select(WhatsappChat).where(
                WhatsappChat.connection_id == conn.id,
                WhatsappChat.chat_jid == jid,
                WhatsappChat.import_status == "imported",
            )
        )
        if chat is not None and upsert_message(session, chat, msg):
            chat.message_count += 1
            if msg.get("timestamp"):
                sent_at = datetime.fromtimestamp(int(msg["timestamp"]), timezone.utc)
                if chat.last_message_at is None or sent_at > chat.last_message_at:
                    chat.last_message_at = sent_at
            schedule_ingest = not chat.pending_ingest and chat.organization_id is not None
            chat.pending_ingest = schedule_ingest or chat.pending_ingest
            session.commit()
            if schedule_ingest:
                background_tasks.add_task(debounced_ingest, chat.id)
        return {"status": "ok"}

    return {"status": "ignored"}
