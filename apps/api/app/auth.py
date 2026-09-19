import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .models import GoogleAccount, User, WhatsappConnection

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = "openid email profile https://www.googleapis.com/auth/drive.readonly"

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    if user_id:
        try:
            user = session.get(User, UUID(user_id))
        except ValueError:
            user = None
        if user is not None:
            return user
    request.session.clear()
    raise HTTPException(status_code=401, detail="not_authenticated")


@router.get("/google/login")
def google_login(request: Request):
    settings = get_settings()
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    # access_type=offline + prompt=consent: Google only returns a refresh token
    # at consent time, so we force re-consent to guarantee we capture one.
    params = {
        "client_id": settings.google_client_id.get_secret_value(),
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}")


@router.get("/google/callback", response_model=None)
def google_callback(request: Request, session: Session = Depends(get_session)):
    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or request.query_params.get("state") != expected_state:
        raise HTTPException(status_code=400, detail="invalid_oauth_state")
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="missing_authorization_code")

    settings = get_settings()
    with httpx.Client(timeout=10) as http:
        token_resp = http.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.google_redirect_uri,
                "client_id": settings.google_client_id.get_secret_value(),
                "client_secret": settings.google_client_secret.get_secret_value(),
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="oauth_exchange_failed")
        token = token_resp.json()
        profile_resp = http.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="userinfo_failed")
        profile = profile_resp.json()

    account = session.scalar(select(GoogleAccount).where(GoogleAccount.google_sub == profile["sub"]))
    if account is not None:
        user = session.get(User, account.user_id)
    else:
        user = session.scalar(select(User).where(User.email == profile["email"]))
        if user is None:
            user = User(email=profile["email"])
            session.add(user)
            session.flush()
        account = GoogleAccount(user_id=user.id, google_sub=profile["sub"], scopes=GOOGLE_SCOPES)
        session.add(account)

    user.display_name = profile.get("name")
    user.avatar_url = profile.get("picture")
    account.scopes = token.get("scope", GOOGLE_SCOPES)
    account.access_token = token.get("access_token")
    if token.get("expires_in"):
        account.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
    if token.get("refresh_token"):
        account.refresh_token = token["refresh_token"]
    session.commit()

    request.session["user_id"] = str(user.id)
    # First-time link (or a user who never picked files) lands on the Drive
    # picker so they choose what to share; returning configured users go home.
    target = settings.web_origin
    if account.share_all is None:
        target += "/?drive=setup"
    return RedirectResponse(target)


@router.get("/me")
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    linked = session.scalar(select(GoogleAccount.id).where(GoogleAccount.user_id == user.id)) is not None
    whatsapp_linked = (
        session.scalar(
            select(WhatsappConnection.id).where(
                WhatsappConnection.user_id == user.id,
                WhatsappConnection.status == "WORKING",
            )
        )
        is not None
    )
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "drive_linked": linked,
        "whatsapp_linked": whatsapp_linked,
    }


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}
