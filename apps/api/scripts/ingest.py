"""Ingest connector data into documents, versions, and chunks.

Run from apps/api with the virtual environment active:

    python -m scripts.ingest --organization-id UUID whatsapp --user-email me@example.com
    python -m scripts.ingest --organization-id UUID drive --user-email me@example.com --workspace-id UUID --file-id ID

Chunks land without embeddings; follow with `python -m scripts.reembed`.
"""
import argparse
import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.drive import UnsupportedFileType, ensure_access_token, fetch_file_metadata, fetch_file_text
from app.filing import ingest_and_file
from app.ingest import chunk_count
from app.models import DriveConnection, DriveWorkspace, Organization, User, WhatsappChat, WhatsappConnection, WhatsappMessage
from app.sources import drive_file_document, whatsapp_chat_document


def require_user(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise SystemExit(f"no user with email {email}")
    return user


def require_organization(session: Session, organization_id: UUID) -> Organization:
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise SystemExit(f"no organization {organization_id}")
    return organization


def report(session: Session, label: str, version) -> None:
    if version is None:
        print(f"{label}: unchanged")
    else:
        print(f"{label}: revision {version.revision}, {chunk_count(session, version)} chunk(s)")


def ingest_whatsapp(session: Session, organization_id: UUID, email: str, chat_jids: list[str]) -> None:
    user = require_user(session, email)
    connection = session.scalar(select(WhatsappConnection).where(WhatsappConnection.user_id == user.id))
    if connection is None:
        raise SystemExit(f"{email} has no WhatsApp connection")

    statement = select(WhatsappChat).where(
        WhatsappChat.connection_id == connection.id,
        WhatsappChat.import_status == "imported",
    )
    if chat_jids:
        statement = statement.where(WhatsappChat.chat_jid.in_(chat_jids))
    for chat in session.scalars(statement):
        messages = session.scalars(select(WhatsappMessage).where(WhatsappMessage.chat_id == chat.id)).all()
        version = ingest_and_file(session, organization_id, whatsapp_chat_document(chat, messages, connection.user_id))
        session.commit()
        report(session, chat.name or chat.chat_jid, version)


def ingest_drive(
    session: Session,
    organization_id: UUID,
    workspace_id: UUID,
    email: str,
    file_ids: list[str],
) -> None:
    user = require_user(session, email)
    workspace = session.get(DriveWorkspace, workspace_id)
    if workspace is None or workspace.organization_id != organization_id:
        raise SystemExit(f"no Drive workspace {workspace_id} in organization {organization_id}")
    connection = session.scalar(
        select(DriveConnection).where(
            DriveConnection.organization_id == organization_id,
            DriveConnection.user_id == user.id,
        )
    )
    if connection is None:
        raise SystemExit(f"{email} has no linked Google Drive")

    access_token = ensure_access_token(connection, session)
    for file_id in file_ids:
        file = fetch_file_metadata(access_token, file_id)
        if workspace.kind == "shared_drive" and file.get("driveId") != workspace.google_drive_id:
            raise SystemExit(f"{file_id} does not belong to {workspace.name}")
        if workspace.kind == "my_drive" and file.get("driveId"):
            raise SystemExit(f"{file_id} does not belong to My Drive")
        try:
            text = fetch_file_text(access_token, file)
        except UnsupportedFileType as exc:
            print(f"{file.get('name', file_id)}: skipped ({exc})")
            continue
        owner_user_id = user.id if workspace.kind == "my_drive" else None
        version = ingest_and_file(
            session,
            organization_id,
            drive_file_document(file, text, workspace.id, owner_user_id),
        )
        session.commit()
        report(session, file.get("name", file_id), version)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=UUID, required=True)
    subparsers = parser.add_subparsers(dest="source", required=True)

    whatsapp = subparsers.add_parser("whatsapp", help="ingest imported chats as transcripts")
    whatsapp.add_argument("--user-email", required=True)
    whatsapp.add_argument("--chat-jid", action="append", default=[], help="defaults to every imported chat")

    drive = subparsers.add_parser("drive", help="ingest Drive files by ID")
    drive.add_argument("--user-email", required=True)
    drive.add_argument("--workspace-id", type=UUID, required=True)
    drive.add_argument("--file-id", action="append", required=True)

    arguments = parser.parse_args()
    with Session(get_engine()) as session:
        require_organization(session, arguments.organization_id)
        if arguments.source == "whatsapp":
            ingest_whatsapp(session, arguments.organization_id, arguments.user_email, arguments.chat_jid)
        else:
            ingest_drive(
                session,
                arguments.organization_id,
                arguments.workspace_id,
                arguments.user_email,
                arguments.file_id,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
