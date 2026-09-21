import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session
from .models import DriveConnection, GoogleIdentity, Organization, OrganizationMembership, User, WhatsappConnection

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_IDENTITY_SCOPES = "openid email profile"
GOOGLE_DRIVE_SCOPES = f"{GOOGLE_IDENTITY_SCOPES} https://www.googleapis.com/auth/drive.readonly"

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


def exchange_code(code: str, redirect_uri: str) -> tuple[dict, dict]:
    settings = get_settings()
    with httpx.Client(timeout=10) as http:
        token_resp = http.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
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
    return token, profile_resp.json()


@router.get("/google/login")
def google_login(request: Request, invite: str | None = None):
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    request.session["oauth_flow"] = {"state": state, "purpose": "identity", "invite": invite}
    params = {
        "client_id": settings.google_client_id.get_secret_value(),
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_IDENTITY_SCOPES,
        "state": state,
    }
    return RedirectResponse(f"{GOOGLE_AUTHORIZATION_URL}?{urlencode(params)}")


@router.get("/google/callback", response_model=None)
def google_callback(request: Request, session: Session = Depends(get_session)):
    flow = request.session.pop("oauth_flow", None)
    if not flow or flow.get("purpose") != "identity" or request.query_params.get("state") != flow.get("state"):
        raise HTTPException(status_code=400, detail="invalid_oauth_state")
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="missing_authorization_code")
    token, profile = exchange_code(code, get_settings().google_redirect_uri)
    identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.google_sub == profile["sub"]))
    if identity is not None:
        user = session.get(User, identity.user_id)
    else:
        user = session.scalar(select(User).where(User.email == profile["email"].lower()))
        if user is None:
            user = User(email=profile["email"].lower())
            session.add(user)
            session.flush()
        identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        if identity is not None and identity.google_sub != profile["sub"]:
            raise HTTPException(status_code=409, detail="email_linked_to_different_google_identity")
        if identity is None:
            identity = GoogleIdentity(
                user_id=user.id,
                google_sub=profile["sub"],
                email=profile["email"].lower(),
                hosted_domain=profile.get("hd"),
            )
            session.add(identity)
    user.display_name = profile.get("name")
    user.avatar_url = profile.get("picture")
    identity.email = profile["email"].lower()
    identity.hosted_domain = profile.get("hd")
    session.commit()
    request.session["user_id"] = str(user.id)
    memberships = session.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)).all()
    target = get_settings().web_origin
    invite = flow.get("invite")
    if invite:
        target += f"/?invite={invite}"
    elif not memberships:
        target += "/?onboarding=account"
    else:
        active = request.session.get("organization_id")
        if not active or all(str(item.organization_id) != active for item in memberships):
            request.session["organization_id"] = str(memberships[0].organization_id)
    return RedirectResponse(target)


@router.get("/me")
def me(request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
    memberships = session.scalars(
        select(OrganizationMembership).where(OrganizationMembership.user_id == user.id).order_by(OrganizationMembership.created_at)
    ).all()
    # Domain auto-join: a Workspace user with no accounts is added as a member
    # of the company that owns their hosted domain, if one exists.
    if not memberships and identity is not None and identity.hosted_domain:
        company = session.scalar(
            select(Organization).where(
                Organization.account_type == "company",
                Organization.google_domain == identity.hosted_domain,
            )
        )
        if company is not None:
            membership = OrganizationMembership(
                organization_id=company.id, user_id=user.id, role="member"
            )
            session.add(membership)
            session.commit()
            memberships = [membership]
            request.session["organization_id"] = str(company.id)
    organizations = {
        organization.id: organization
        for organization in session.scalars(
            select(Organization).where(Organization.id.in_([item.organization_id for item in memberships]))
        ).all()
    } if memberships else {}
    active_id = request.session.get("organization_id")
    if active_id and all(str(item.organization_id) != active_id for item in memberships):
        active_id = None
    if not active_id and memberships:
        active_id = str(memberships[0].organization_id)
        request.session["organization_id"] = active_id
    connections = set(
        session.scalars(select(DriveConnection.organization_id).where(DriveConnection.user_id == user.id, DriveConnection.status == "connected")).all()
    )
    accounts = [
        {
            "id": str(item.organization_id),
            "name": organizations[item.organization_id].name,
            "account_type": organizations[item.organization_id].account_type,
            "google_domain": organizations[item.organization_id].google_domain,
            "role": item.role,
            "drive_linked": item.organization_id in connections,
        }
        for item in memberships
    ]
    whatsapp_linked = session.scalar(
        select(WhatsappConnection.id).where(WhatsappConnection.user_id == user.id, WhatsappConnection.status == "WORKING")
    ) is not None
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "hosted_domain": identity.hosted_domain if identity else None,
        "accounts": accounts,
        "active_account_id": active_id,
        "needs_account": not accounts,
        "drive_linked": any(item["id"] == active_id and item["drive_linked"] for item in accounts),
        "whatsapp_linked": whatsapp_linked,
    }


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}
