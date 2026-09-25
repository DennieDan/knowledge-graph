"""Mirror Drive file metadata and ingest new or changed files into documents.

`POST /drive/workspaces/{id}/sync` lists the workspace, upserts `drive_files`,
and ingests every selected file whose content may have changed. Re-ingestion is
idempotent: `document_versions` skips unchanged content via `content_hash`.

Live sync path (#92): keep this polling until a verified webhook domain exists
and `subscriptions.start_watch` can call Google `changes.watch`. The subscription
table and renewal stub sit beside this module — do not delete or replace polling.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_session
from .drive import (
    DOWNLOADABLE_MIME_TYPES,
    EXPORTABLE_MIME_TYPES,
    FOLDER_MIME,
    UnsupportedFileType,
    ensure_access_token,
    fetch_file_text,
    list_workspace_items,
    selection_covers,
    workspace_context,
)
from .filing import ingest_and_file
from .jobs import enqueue_job, utcnow
from .models import DriveConnection, DriveFile, DriveSelection, DriveWorkspace, User
from .sources import drive_file_document

router = APIRouter(tags=["drive"])

FOLDER_FIELDS = "files(id,parents),nextPageToken"
FILE_FIELDS = "files(id,name,mimeType,parents,modifiedTime,webViewLink,md5Checksum,trashed,driveId),nextPageToken"


def _is_supported(mime_type: str) -> bool:
    return (
        mime_type in EXPORTABLE_MIME_TYPES
        or mime_type in DOWNLOADABLE_MIME_TYPES
        or mime_type.startswith("text/")
    )


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _selected_ids(session: Session, workspace: DriveWorkspace, user: User) -> set[str] | None:
    """None = everything is shared; a set = explicit file/folder ids; empty = nothing."""
    selection = session.scalar(
        select(DriveSelection).where(
            DriveSelection.workspace_id == workspace.id,
            DriveSelection.user_id == user.id,
        )
    )
    if selection is None or not selection.configured:
        return set()
    if selection.share_all:
        return None
    return set(selection.selected_file_ids)


def _needs_ingest(row: DriveFile, file: dict) -> bool:
    if row.ingested_modified_time is None:
        return True
    modified = _parse_time(file.get("modifiedTime"))
    if modified is not None:
        return modified > row.ingested_modified_time
    return bool(file.get("md5Checksum")) and file["md5Checksum"] != row.md5_checksum


def sync_workspace(session: Session, workspace: DriveWorkspace, connection: DriveConnection, user: User) -> dict:
    remote = list_workspace_items(workspace, connection, session, FILE_FIELDS)
    selected = _selected_ids(session, workspace, user)
    parents_of: dict[str, list[str]] = {}
    if selected:
        folders = list_workspace_items(workspace, connection, session, FOLDER_FIELDS, f"mimeType = '{FOLDER_MIME}' and trashed = false")
        parents_of = {folder["id"]: folder.get("parents") or [] for folder in folders}

    rows = {
        row.file_id: row
        for row in session.scalars(select(DriveFile).where(DriveFile.workspace_id == workspace.id))
    }
    seen: set[str] = set()
    now = datetime.now(timezone.utc)
    for file in remote:
        seen.add(file["id"])
        row = rows.get(file["id"])
        if row is None:
            row = DriveFile(workspace_id=workspace.id, file_id=file["id"], name=file.get("name") or file["id"], mime_type=file.get("mimeType") or "")
            session.add(row)
            rows[file["id"]] = row
        row.name = file.get("name") or file["id"]
        row.mime_type = file.get("mimeType") or ""
        row.parents = file.get("parents") or []
        row.modified_time = _parse_time(file.get("modifiedTime"))
        row.md5_checksum = file.get("md5Checksum")
        row.web_view_link = file.get("webViewLink")
        row.trashed = bool(file.get("trashed"))
        row.last_synced_at = now
    for file_id, row in rows.items():
        if file_id not in seen:
            row.trashed = True
    session.flush()
    # Persist the mirror first so a per-file ingest rollback below cannot lose it.
    session.commit()

    owner_user_id = connection.user_id if workspace.kind == "my_drive" else None
    ingested = skipped = 0
    errors: list[str] = []
    for file in remote:
        mime_type = file.get("mimeType") or ""
        if file.get("trashed") or mime_type == FOLDER_MIME:
            continue
        row = rows[file["id"]]
        if not _is_supported(mime_type) or not (selected is None or selection_covers(file, selected, parents_of)):
            skipped += 1
            continue
        if not _needs_ingest(row, file):
            continue
        try:
            text = fetch_file_text(ensure_access_token(connection, session), file)
        except UnsupportedFileType:
            skipped += 1
            continue
        except HTTPException as exc:
            errors.append(f"{file.get('name', file['id'])}: {exc.detail}")
            continue
        try:
            ingest_and_file(session, workspace.organization_id, drive_file_document(file, text, workspace.id, owner_user_id))
        except SQLAlchemyError as exc:
            session.rollback()
            errors.append(f"{file.get('name', file['id'])}: {type(exc).__name__}")
            continue
        row.ingested_modified_time = row.modified_time or now
        ingested += 1
    session.commit()
    return {"synced": len(seen), "ingested": ingested, "skipped": skipped, "errors": errors}


@router.post("/drive/workspaces/{workspace_id}/sync")
def sync_workspace_files(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    workspace, connection = workspace_context(workspace_id, user, session)
    now = utcnow()
    job = enqueue_job(
        session,
        organization_id=workspace.organization_id,
        owner_user_id=workspace.owner_user_id,
        kind="sync_workspace",
        payload={"workspace_id": str(workspace.id)},
        dedupe_key=f"sync_workspace:{workspace.id}:{now.date().isoformat()}:{now.hour}:{now.minute // 5}",
    )
    session.commit()
    return {
        "queued": True,
        "job_id": str(job.id),
        "workspace_id": str(workspace.id),
        "status": job.status,
    }
