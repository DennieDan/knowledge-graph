import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .accounts import membership_for
from .auth import GOOGLE_AUTHORIZATION_URL, GOOGLE_DRIVE_SCOPES, GOOGLE_TOKEN_URL, exchange_code, get_current_user
from .config import get_settings
from .database import get_session
from .models import (
    DriveConnection,
    DriveSelection,
    DriveWorkspace,
    DriveWorkspaceConnection,
    GoogleIdentity,
    Organization,
    User,
)

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_DRIVES_URL = "https://www.googleapis.com/drive/v3/drives"
FOLDER_MIME = "application/vnd.google-apps.folder"
EXPORTABLE_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
DOWNLOADABLE_MIME_TYPES = {"application/json", "application/xml"}

router = APIRouter(tags=["drive"])


class UnsupportedFileType(Exception):
    pass


class SelectionIn(BaseModel):
    share_all: bool
    file_ids: list[str] = []


def google_get(url: str, params: dict, access_token: str, timeout: int = 15) -> dict:
    try:
        response = httpx.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="drive_request_failed") from exc
    if response.status_code == 401:
        raise HTTPException(status_code=409, detail="google_token_revoked_relink_required")
    if response.status_code in {403, 404}:
        raise HTTPException(status_code=404, detail="drive_item_not_found")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="drive_request_failed")
    return response.json()


def refresh_access_token(connection: DriveConnection, session: Session) -> None:
    if not connection.refresh_token:
        connection.status = "relink_required"
        session.commit()
        raise HTTPException(status_code=409, detail="google_token_expired_relink_required")
    settings = get_settings()
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": connection.refresh_token,
            "client_id": settings.google_client_id.get_secret_value(),
            "client_secret": settings.google_client_secret.get_secret_value(),
        },
        timeout=10,
    )
    if response.status_code != 200:
        connection.status = "relink_required"
        session.commit()
        raise HTTPException(status_code=409, detail="google_token_revoked_relink_required")
    token = response.json()
    connection.access_token = token["access_token"]
    connection.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 3600)))
    connection.status = "connected"
    if token.get("refresh_token"):
        connection.refresh_token = token["refresh_token"]
    session.commit()


def ensure_access_token(connection: DriveConnection, session: Session) -> str:
    if not connection.access_token or connection.access_token_expires_at is None or connection.access_token_expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60):
        refresh_access_token(connection, session)
    return connection.access_token


def fetch_file_metadata(access_token: str, file_id: str) -> dict:
    return google_get(
        f"{DRIVE_FILES_URL}/{file_id}",
        {"fields": "id,name,mimeType,modifiedTime,webViewLink,parents,driveId,shared,capabilities,inheritedPermissionsDisabled", "supportsAllDrives": "true"},
        access_token,
    )


def _decode_file_text(content: bytes, charset: str | None) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    sample = content[:4096]
    # UTF-16 text has a NUL every other byte; plain text almost never has NULs.
    if len(sample) > 16 and sample.count(b"\x00") > len(sample) // 8:
        odd_nuls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
        even_nuls = sum(1 for i in range(0, len(sample), 2) if sample[i] == 0)
        encoding = "utf-16-le" if odd_nuls >= even_nuls else "utf-16-be"
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    try:
        return content.decode(charset or "utf-8")
    except (UnicodeDecodeError, LookupError):
        return content.decode("utf-8", errors="replace")


def fetch_file_text(access_token: str, file: dict) -> str:
    mime_type = file.get("mimeType", "")
    export_as = EXPORTABLE_MIME_TYPES.get(mime_type)
    if export_as is None and not (mime_type.startswith("text/") or mime_type in DOWNLOADABLE_MIME_TYPES):
        raise UnsupportedFileType(mime_type)
    url = f"{DRIVE_FILES_URL}/{file['id']}"
    params: dict[str, str] = {"supportsAllDrives": "true"}
    if export_as:
        url += "/export"
        params["mimeType"] = export_as
    else:
        params["alt"] = "media"
    try:
        response = httpx.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"}, timeout=60)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="drive_request_failed") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="drive_request_failed")
    return _decode_file_text(response.content, response.charset_encoding)


def list_pages(url: str, params: dict, access_token: str, key: str) -> list[dict]:
    items: list[dict] = []
    page_token = None
    while True:
        current = dict(params)
        if page_token:
            current["pageToken"] = page_token
        data = google_get(url, current, access_token)
        items.extend(data.get(key, []))
        page_token = data.get("nextPageToken")
        if not page_token:
            return items


def connection_for(organization_id: UUID, user: User, session: Session) -> DriveConnection:
    membership_for(organization_id, user, session)
    connection = session.scalar(
        select(DriveConnection).where(DriveConnection.organization_id == organization_id, DriveConnection.user_id == user.id)
    )
    if connection is None:
        raise HTTPException(status_code=409, detail="drive_not_connected")
    return connection


def workspace_context(workspace_id: UUID, user: User, session: Session) -> tuple[DriveWorkspace, DriveConnection]:
    workspace = session.get(DriveWorkspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="drive_workspace_not_found")
    connection = connection_for(workspace.organization_id, user, session)
    access = session.scalar(
        select(DriveWorkspaceConnection.id).where(
            DriveWorkspaceConnection.workspace_id == workspace.id,
            DriveWorkspaceConnection.connection_id == connection.id,
            DriveWorkspaceConnection.status == "active",
        )
    )
    if access is None or (workspace.kind == "my_drive" and workspace.owner_user_id != user.id):
        raise HTTPException(status_code=404, detail="drive_workspace_not_found")
    return workspace, connection


def workspace_params(workspace: DriveWorkspace) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "spaces": "drive",
    }
    if workspace.kind == "shared_drive":
        params.update({"corpora": "drive", "driveId": workspace.google_drive_id})
    else:
        params["corpora"] = "user"
    return params


def file_in_workspace(file: dict, workspace: DriveWorkspace) -> bool:
    return file.get("driveId") == workspace.google_drive_id if workspace.kind == "shared_drive" else not file.get("driveId")


def discover_workspaces(connection: DriveConnection, session: Session) -> list[DriveWorkspace]:
    token = ensure_access_token(connection, session)
    my_drive = session.scalar(
        select(DriveWorkspace).where(
            DriveWorkspace.organization_id == connection.organization_id,
            DriveWorkspace.kind == "my_drive",
            DriveWorkspace.owner_user_id == connection.user_id,
        )
    )
    if my_drive is None:
        my_drive = DriveWorkspace(
            organization_id=connection.organization_id,
            kind="my_drive",
            google_drive_id="root",
            name="My Drive",
            owner_user_id=connection.user_id,
        )
        session.add(my_drive)
        session.flush()
    association = session.scalar(
        select(DriveWorkspaceConnection).where(
            DriveWorkspaceConnection.workspace_id == my_drive.id,
            DriveWorkspaceConnection.connection_id == connection.id,
        )
    )
    if association is None:
        session.add(DriveWorkspaceConnection(workspace_id=my_drive.id, connection_id=connection.id))
    else:
        association.status = "active"
    existing_associations = session.scalars(
        select(DriveWorkspaceConnection).where(DriveWorkspaceConnection.connection_id == connection.id)
    ).all()
    for item in existing_associations:
        if item.workspace_id != my_drive.id:
            item.status = "stale"
    drives = list_pages(
        DRIVE_DRIVES_URL,
        {"pageSize": 100, "fields": "drives(id,name),nextPageToken", "useDomainAdminAccess": "false"},
        token,
        "drives",
    )
    workspaces = [my_drive]
    for drive in drives:
        workspace = session.scalar(
            select(DriveWorkspace).where(
                DriveWorkspace.organization_id == connection.organization_id,
                DriveWorkspace.kind == "shared_drive",
                DriveWorkspace.google_drive_id == drive["id"],
            )
        )
        if workspace is None:
            workspace = DriveWorkspace(
                organization_id=connection.organization_id,
                kind="shared_drive",
                google_drive_id=drive["id"],
                name=drive["name"],
            )
            session.add(workspace)
            session.flush()
        else:
            workspace.name = drive["name"]
            workspace.status = "active"
        association = session.scalar(
            select(DriveWorkspaceConnection).where(
                DriveWorkspaceConnection.workspace_id == workspace.id,
                DriveWorkspaceConnection.connection_id == connection.id,
            )
        )
        if association is None:
            session.add(DriveWorkspaceConnection(workspace_id=workspace.id, connection_id=connection.id))
        else:
            association.status = "active"
        workspaces.append(workspace)
    session.commit()
    return workspaces


@router.get("/drive/connect")
def connect_drive(organization_id: UUID, request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    membership_for(organization_id, user, session)
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    request.session["oauth_flow"] = {"state": state, "purpose": "drive", "organization_id": str(organization_id), "user_id": str(user.id)}
    params = {
        "client_id": settings.google_client_id.get_secret_value(),
        "redirect_uri": settings.google_drive_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_DRIVE_SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}")


@router.get("/drive/callback", response_model=None)
def drive_callback(request: Request, session: Session = Depends(get_session)):
    flow = request.session.pop("oauth_flow", None)
    if not flow or flow.get("purpose") != "drive" or request.query_params.get("state") != flow.get("state"):
        raise HTTPException(status_code=400, detail="invalid_oauth_state")
    if request.session.get("user_id") != flow.get("user_id"):
        raise HTTPException(status_code=403, detail="oauth_user_mismatch")
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="missing_authorization_code")
    token, profile = exchange_code(code, get_settings().google_drive_redirect_uri)
    user = session.get(User, UUID(flow["user_id"]))
    organization_id = UUID(flow["organization_id"])
    organization = session.get(Organization, organization_id)
    identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id)) if user else None
    if user is None or identity is None or profile["sub"] != identity.google_sub:
        raise HTTPException(status_code=403, detail="oauth_user_mismatch")
    if organization is None or (organization.account_type == "company" and profile.get("hd") != organization.google_domain):
        raise HTTPException(status_code=403, detail="workspace_domain_mismatch")
    granted_scopes = token.get("scope", "")
    if "https://www.googleapis.com/auth/drive.readonly" not in granted_scopes.split():
        raise HTTPException(status_code=400, detail="drive_scope_not_granted")
    connection = session.scalar(
        select(DriveConnection).where(DriveConnection.organization_id == organization_id, DriveConnection.user_id == user.id)
    )
    if connection is None and not token.get("refresh_token"):
        raise HTTPException(status_code=400, detail="google_refresh_token_missing")
    if connection is None:
        connection = DriveConnection(
            organization_id=organization_id,
            user_id=user.id,
            google_identity_id=identity.id,
            scopes=token.get("scope", GOOGLE_DRIVE_SCOPES),
        )
        session.add(connection)
    connection.scopes = token.get("scope", GOOGLE_DRIVE_SCOPES)
    connection.access_token = token.get("access_token")
    connection.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token.get("expires_in", 3600)))
    connection.status = "connected"
    if token.get("refresh_token"):
        connection.refresh_token = token["refresh_token"]
    session.commit()
    discover_workspaces(connection, session)
    return RedirectResponse(f"{get_settings().web_origin}/?drive=connected")


@router.get("/accounts/{organization_id}/drive/workspaces")
def list_workspaces(organization_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    connection = connection_for(organization_id, user, session)
    rows = session.execute(
        select(DriveWorkspace, DriveWorkspaceConnection)
        .join(DriveWorkspaceConnection, DriveWorkspaceConnection.workspace_id == DriveWorkspace.id)
        .where(
            DriveWorkspaceConnection.connection_id == connection.id,
            DriveWorkspaceConnection.status == "active",
            DriveWorkspace.status == "active",
        )
        .order_by(DriveWorkspace.kind, DriveWorkspace.name)
    ).all()
    return [
        {
            "id": str(workspace.id),
            "name": workspace.name,
            "kind": workspace.kind,
            "private": workspace.kind == "my_drive",
            "updated_at": association.updated_at,
        }
        for workspace, association in rows
        if workspace.kind != "my_drive" or workspace.owner_user_id == user.id
    ]


@router.post("/accounts/{organization_id}/drive/workspaces/refresh")
def refresh_workspaces(organization_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    connection = connection_for(organization_id, user, session)
    discover_workspaces(connection, session)
    return list_workspaces(organization_id, user, session)


def list_workspace_items(workspace: DriveWorkspace, connection: DriveConnection, session: Session, fields: str, q: str = "") -> list[dict]:
    params = workspace_params(workspace)
    params.update({"pageSize": 1000, "fields": fields})
    if q:
        params["q"] = q
    return list_pages(DRIVE_FILES_URL, params, ensure_access_token(connection, session), "files")


def selection_covers(file: dict, selected: set[str], parents_of: dict[str, list[str]]) -> bool:
    """True when the file or any ancestor folder was explicitly selected."""
    stack = [file["id"], *(file.get("parents") or [])]
    seen: set[str] = set()
    while stack:
        item_id = stack.pop()
        if item_id in selected:
            return True
        if item_id in seen:
            continue
        seen.add(item_id)
        stack.extend(parents_of.get(item_id, []))
    return False


@router.get("/drive/workspaces/{workspace_id}/tree")
def drive_tree(workspace_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workspace, connection = workspace_context(workspace_id, user, session)
    files = list_workspace_items(
        workspace,
        connection,
        session,
        "files(id,name,mimeType,parents,modifiedTime,driveId),nextPageToken",
        "trashed = false",
    )
    return {"files": files}


@router.get("/drive/workspaces/{workspace_id}/selection")
def get_selection(workspace_id: UUID, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workspace_context(workspace_id, user, session)
    selection = session.scalar(select(DriveSelection).where(DriveSelection.workspace_id == workspace_id, DriveSelection.user_id == user.id))
    return {
        "configured": bool(selection and selection.configured),
        "share_all": bool(selection and selection.share_all),
        "file_ids": selection.selected_file_ids if selection else [],
    }


@router.put("/drive/workspaces/{workspace_id}/selection")
def put_selection(workspace_id: UUID, body: SelectionIn, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workspace_context(workspace_id, user, session)
    selection = session.scalar(select(DriveSelection).where(DriveSelection.workspace_id == workspace_id, DriveSelection.user_id == user.id))
    if selection is None:
        selection = DriveSelection(workspace_id=workspace_id, user_id=user.id)
        session.add(selection)
    selection.share_all = body.share_all
    selection.selected_file_ids = [] if body.share_all else list(dict.fromkeys(body.file_ids))
    selection.configured = True
    session.commit()
    return {"configured": True, "share_all": selection.share_all, "file_ids": selection.selected_file_ids}


@router.get("/drive/workspaces/{workspace_id}/files")
def list_files(
    workspace_id: UUID,
    page_size: int = Query(default=25, ge=1, le=100),
    page_token: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    workspace, connection = workspace_context(workspace_id, user, session)
    params = workspace_params(workspace)
    params.update({
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,parents,driveId),nextPageToken",
        "orderBy": "modifiedTime desc",
        "q": "trashed = false",
    })
    if page_token:
        params["pageToken"] = page_token
    data = google_get(DRIVE_FILES_URL, params, ensure_access_token(connection, session))
    selection = session.scalar(select(DriveSelection).where(DriveSelection.workspace_id == workspace_id, DriveSelection.user_id == user.id))
    if not selection or not selection.configured:
        data["files"] = []
    elif not selection.share_all:
        selected = set(selection.selected_file_ids)
        folders = list_workspace_items(workspace, connection, session, "files(id,parents),nextPageToken", f"mimeType = '{FOLDER_MIME}' and trashed = false")
        parents_of = {folder["id"]: folder.get("parents") or [] for folder in folders}
        data["files"] = [file for file in data.get("files", []) if selection_covers(file, selected, parents_of)]
    return data


@router.get("/drive/workspaces/{workspace_id}/files/{file_id}/permissions")
def file_permissions(workspace_id: UUID, file_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    workspace, connection = workspace_context(workspace_id, user, session)
    token = ensure_access_token(connection, session)
    file = fetch_file_metadata(token, file_id)
    if not file_in_workspace(file, workspace):
        raise HTTPException(status_code=404, detail="drive_item_not_found")
    permissions = list_pages(
        f"{DRIVE_FILES_URL}/{file_id}/permissions",
        {
            "pageSize": 100,
            "supportsAllDrives": "true",
            "fields": "permissions(id,type,role,displayName,emailAddress,domain,allowFileDiscovery,expirationTime,permissionDetails),nextPageToken",
        },
        token,
        "permissions",
    )
    return {
        "file": {
            "id": file["id"],
            "name": file["name"],
            "shared": file.get("shared", False),
            "inherited_permissions_disabled": file.get("inheritedPermissionsDisabled", False),
        },
        "capabilities": file.get("capabilities", {}),
        "permissions": permissions,
    }
