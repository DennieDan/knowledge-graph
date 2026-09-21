import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import get_current_user
from .config import get_settings
from .database import get_session
from .models import GoogleIdentity, Organization, OrganizationInvitation, OrganizationMembership, User

router = APIRouter(tags=["accounts"])


class AccountIn(BaseModel):
    account_type: str
    name: str | None = None


class InvitationIn(BaseModel):
    email: str


def identity_for(user: User, session: Session) -> GoogleIdentity:
    identity = session.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
    if identity is None:
        raise HTTPException(status_code=409, detail="google_identity_required")
    return identity


def membership_for(organization_id: UUID, user: User, session: Session) -> OrganizationMembership:
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    return membership


def account_json(organization: Organization, membership: OrganizationMembership, drive_linked: bool = False) -> dict:
    return {
        "id": str(organization.id),
        "name": organization.name,
        "account_type": organization.account_type,
        "google_domain": organization.google_domain,
        "role": membership.role,
        "drive_linked": drive_linked,
    }


@router.post("/accounts")
def create_account(
    body: AccountIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    identity = identity_for(user, session)
    if body.account_type not in {"personal", "company"}:
        raise HTTPException(status_code=422, detail="invalid_account_type")
    if body.account_type == "company":
        if not identity.hosted_domain:
            raise HTTPException(status_code=422, detail="workspace_account_required")
        existing_company = session.scalar(
            select(Organization).where(
                Organization.account_type == "company",
                Organization.google_domain == identity.hosted_domain,
            )
        )
        if existing_company is not None:
            raise HTTPException(status_code=409, detail="company_domain_taken")
    if body.account_type == "personal":
        existing = session.scalar(
            select(OrganizationMembership)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(OrganizationMembership.user_id == user.id, Organization.account_type == "personal")
        )
        if existing:
            raise HTTPException(status_code=409, detail="personal_account_exists")
    name = (body.name or "").strip()
    if not name:
        name = f"{user.display_name or user.email}'s workspace" if body.account_type == "personal" else identity.hosted_domain or "Company"
    organization = Organization(
        name=name,
        account_type=body.account_type,
        google_domain=identity.hosted_domain if body.account_type == "company" else None,
        created_by_user_id=user.id,
    )
    session.add(organization)
    session.flush()
    membership = OrganizationMembership(organization_id=organization.id, user_id=user.id, role="admin")
    session.add(membership)
    session.commit()
    request.session["organization_id"] = str(organization.id)
    return account_json(organization, membership)


@router.post("/accounts/{organization_id}/activate")
def activate_account(
    organization_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership_for(organization_id, user, session)
    request.session["organization_id"] = str(organization_id)
    return {"active_account_id": str(organization_id)}


@router.get("/accounts/{organization_id}/invitations")
def list_invitations(
    organization_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership = membership_for(organization_id, user, session)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    invitations = session.scalars(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == organization_id)
        .order_by(OrganizationInvitation.created_at.desc())
    ).all()
    return [
        {"id": str(item.id), "email": item.email, "status": item.status, "expires_at": item.expires_at}
        for item in invitations
    ]


@router.post("/accounts/{organization_id}/invitations")
def create_invitation(
    organization_id: UUID,
    body: InvitationIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership = membership_for(organization_id, user, session)
    organization = session.get(Organization, organization_id)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    if organization is None or organization.account_type != "company":
        raise HTTPException(status_code=422, detail="company_account_required")
    email = body.email.strip().lower()
    if not email.endswith(f"@{organization.google_domain}"):
        raise HTTPException(status_code=422, detail="invitation_domain_mismatch")
    if session.scalar(select(User.id).join(OrganizationMembership, OrganizationMembership.user_id == User.id).where(User.email == email, OrganizationMembership.organization_id == organization_id)):
        raise HTTPException(status_code=409, detail="already_a_member")
    pending = session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == email,
            OrganizationInvitation.status == "pending",
        )
    )
    if pending:
        raise HTTPException(status_code=409, detail="invitation_pending")
    token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email,
        invited_by_user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(invitation)
    session.commit()
    return {
        "id": str(invitation.id),
        "email": email,
        "status": invitation.status,
        "expires_at": invitation.expires_at,
        "invite_url": f"{get_settings().web_origin}/?invite={token}",
    }


@router.delete("/accounts/{organization_id}/invitations/{invitation_id}")
def revoke_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    membership = membership_for(organization_id, user, session)
    if membership.role != "admin":
        raise HTTPException(status_code=403, detail="admin_required")
    invitation = session.get(OrganizationInvitation, invitation_id)
    if invitation is None or invitation.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="invitation_not_found")
    invitation.status = "revoked"
    session.commit()
    return {"status": "revoked"}


@router.post("/invitations/{token}/accept")
def accept_invitation(
    token: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = session.scalar(select(OrganizationInvitation).where(OrganizationInvitation.token_hash == digest))
    if invitation is None or invitation.status != "pending":
        raise HTTPException(status_code=404, detail="invitation_not_found")
    if invitation.expires_at <= datetime.now(timezone.utc):
        invitation.status = "expired"
        session.commit()
        raise HTTPException(status_code=410, detail="invitation_expired")
    if user.email.lower() != invitation.email:
        raise HTTPException(status_code=403, detail="invitation_email_mismatch")
    organization = session.get(Organization, invitation.organization_id)
    identity = identity_for(user, session)
    if organization is None or identity.hosted_domain != organization.google_domain:
        raise HTTPException(status_code=403, detail="invitation_domain_mismatch")
    membership = OrganizationMembership(organization_id=organization.id, user_id=user.id, role="member")
    session.add(membership)
    invitation.status = "accepted"
    session.commit()
    request.session["organization_id"] = str(organization.id)
    return account_json(organization, membership)
