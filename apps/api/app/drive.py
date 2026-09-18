from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import GOOGLE_TOKEN_URL, get_current_user
from .config import get_settings
from .database import get_session
from .models import GoogleAccount, User

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
# Cap tree/ancestor listings so a huge Drive can't stall the picker.
MAX_LIST_PAGES = 10

router = APIRouter(prefix="/drive", tags=["drive"])


def refresh_access_token(account: GoogleAccount, session: Session) -> None:
    settings = get_settings()
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": account.refresh_token,
            "client_id": settings.google_client_id.get_secret_value(),
            "client_secret": settings.google_client_secret.get_secret_value(),
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=409, detail="google_token_revoked_relink_required")
    token = resp.json()
    account.access_token = token["access_token"]
    if token.get("expires_in"):
        account.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
    if token.get("refresh_token"):
        account.refresh_token = token["refresh_token"]
    session.commit()


def get_drive_account(user: User, session: Session) -> GoogleAccount:
    account = session.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id))
    if account is None or not account.access_token:
        raise HTTPException(status_code=409, detail="google_account_not_linked")

    expires_soon = (
        account.access_token_expires_at is None
        or account.access_token_expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60)
    )
    if expires_soon:
        if not account.refresh_token:
            raise HTTPException(status_code=409, detail="google_token_expired_relink_required")
        refresh_access_token(account, session)
    return account


def drive_get(account: GoogleAccount, params: dict[str, str | int]) -> dict:
    try:
        resp = httpx.get(
            DRIVE_FILES_URL,
            params=params,
            headers={"Authorization": f"Bearer {account.access_token}"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="drive_request_failed") from exc
    if resp.status_code == 401:
        raise HTTPException(status_code=409, detail="google_token_revoked_relink_required")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="drive_request_failed")
    return resp.json()


def list_all_items(account: GoogleAccount, fields: str, q: str) -> list[dict]:
    items: list[dict] = []
    page_token: str | None = None
    for _ in range(MAX_LIST_PAGES):
        params: dict[str, str | int] = {
            "pageSize": 1000,
            "fields": fields,
            "q": q,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "corpora": "allDrives",
        }
        if page_token:
            params["pageToken"] = page_token
        data = drive_get(account, params)
        items.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return items


def shared_item_ids(account: GoogleAccount) -> set[str] | None:
    """Ids the user explicitly shared; None means unrestricted (share all / unconfigured)."""
    if account.share_all is False:
        return set(account.shared_file_ids or [])
    return None


@router.get("/files")
def list_files(
    page_size: int = Query(default=25, ge=1, le=100),
    page_token: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    account = get_drive_account(user, session)

    params: dict[str, str | int] = {
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,parents),nextPageToken",
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if page_token:
        params["pageToken"] = page_token
    data = drive_get(account, params)

    selected = shared_item_ids(account)
    if selected is not None:
        # Resolve ancestors via the folder map so a file inside a shared
        # folder counts as shared even when nested several levels deep.
        folders = list_all_items(
            account,
            fields="files(id,parents),nextPageToken",
            q=f"mimeType = '{FOLDER_MIME}' and trashed = false",
        )
        parents_of = {f["id"]: f.get("parents") or [] for f in folders}

        def is_shared(file: dict) -> bool:
            if file["id"] in selected:
                return True
            stack = list(file.get("parents") or [])
            seen: set[str] = set()
            while stack:
                pid = stack.pop()
                if pid in seen:
                    continue
                seen.add(pid)
                if pid in selected:
                    return True
                stack.extend(parents_of.get(pid, []))
            return False

        data["files"] = [f for f in data["files"] if is_shared(f)]

    return data


@router.get("/tree")
def drive_tree(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    account = get_drive_account(user, session)
    files = list_all_items(
        account,
        fields="files(id,name,mimeType,parents,modifiedTime),nextPageToken",
        q="trashed = false",
    )
    return {"files": files}


class SelectionIn(BaseModel):
    share_all: bool
    file_ids: list[str] = []


@router.get("/selection")
def get_selection(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    account = session.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id))
    if account is None:
        raise HTTPException(status_code=409, detail="google_account_not_linked")
    configured = account.share_all is not None
    return {
        "configured": configured,
        "share_all": account.share_all if configured else True,
        "file_ids": account.shared_file_ids or [],
    }


@router.put("/selection")
def put_selection(
    body: SelectionIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    account = session.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id))
    if account is None:
        raise HTTPException(status_code=409, detail="google_account_not_linked")
    account.share_all = body.share_all
    account.shared_file_ids = [] if body.share_all else body.file_ids
    session.commit()
    return {"configured": True, "share_all": account.share_all, "file_ids": account.shared_file_ids}
