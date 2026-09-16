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


@router.get("/files")
def list_files(
    page_size: int = Query(default=25, ge=1, le=100),
    page_token: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
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

    params: dict[str, str | int] = {
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink),nextPageToken",
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    if page_token:
        params["pageToken"] = page_token

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
