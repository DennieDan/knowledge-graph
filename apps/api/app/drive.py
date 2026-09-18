from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import GOOGLE_TOKEN_URL, get_current_user
from .config import get_settings
from .database import get_session
from .models import GoogleAccount, User

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
# Editor files come out of files.export; everything else is downloaded verbatim,
# so binary formats (PDF, images) are rejected rather than indexed as mojibake.
EXPORTABLE_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
DOWNLOADABLE_MIME_TYPES = {"application/json", "application/xml"}

router = APIRouter(prefix="/drive", tags=["drive"])


def _drive_get(url: str, params: dict, access_token: str, timeout: int = 15) -> httpx.Response:
    try:
        resp = httpx.get(url, params=params, headers={"Authorization": f"Bearer {access_token}"}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="drive_request_failed") from exc
    if resp.status_code == 401:
        raise HTTPException(status_code=409, detail="google_token_revoked_relink_required")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail="drive_request_failed")
    return resp


class UnsupportedFileType(Exception):
    """The file has no text representation Drive can hand back."""


def ensure_access_token(account: GoogleAccount, session: Session) -> str:
    """Return a usable access token, refreshing it when it is about to expire."""
    if not account.access_token:
        raise HTTPException(status_code=409, detail="google_account_not_linked")
    expires_soon = (
        account.access_token_expires_at is None
        or account.access_token_expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60)
    )
    if expires_soon:
        if not account.refresh_token:
            raise HTTPException(status_code=409, detail="google_token_expired_relink_required")
        refresh_access_token(account, session)
    return account.access_token


def fetch_file_metadata(access_token: str, file_id: str) -> dict:
    return _drive_get(
        f"{DRIVE_FILES_URL}/{file_id}",
        {"fields": "id,name,mimeType,modifiedTime,webViewLink", "supportsAllDrives": "true"},
        access_token,
    ).json()


def fetch_file_text(access_token: str, file: dict) -> str:
    """Download a Drive file as text, exporting Google editor files first."""
    mime_type = file.get("mimeType", "")
    export_as = EXPORTABLE_MIME_TYPES.get(mime_type)
    if export_as is None and not (mime_type.startswith("text/") or mime_type in DOWNLOADABLE_MIME_TYPES):
        raise UnsupportedFileType(mime_type)

    url = f"{DRIVE_FILES_URL}/{file['id']}"
    params: dict[str, str] = {"supportsAllDrives": "true"}
    if export_as:
        url = f"{url}/export"
        params["mimeType"] = export_as
    else:
        params["alt"] = "media"

    return _drive_get(url, params, access_token, timeout=60).text


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


@router.get("/files")
def list_files(
    page_size: int = Query(default=25, ge=1, le=100),
    page_token: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    account = session.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id))
    if account is None:
        raise HTTPException(status_code=409, detail="google_account_not_linked")
    access_token = ensure_access_token(account, session)

    params: dict[str, str | int] = {
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink),nextPageToken",
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if page_token:
        params["pageToken"] = page_token

    return _drive_get(DRIVE_FILES_URL, params, access_token).json()
