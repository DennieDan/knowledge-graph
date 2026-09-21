"""Delete an organization (account) and all its related records.

Deletes cascade to memberships, invitations, Drive connections/workspaces/
selections, documents, versions, and chunks via ON DELETE CASCADE.
Users and their Google identities are kept so login flows can be re-tested.

Run from apps/api with the virtual environment active:

    python -m scripts.drop_organization --name "Studio North"
    python -m scripts.drop_organization --id UUID
    python -m scripts.drop_organization --domain dandinh.net

Pass --yes to skip the confirmation prompt.
"""
import argparse
import sys
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import (
    Document,
    DriveConnection,
    DriveWorkspace,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


def find_organization(session: Session, args) -> Organization | None:
    if args.id:
        return session.get(Organization, args.id)
    if args.domain:
        return session.scalar(
            select(Organization).where(
                Organization.account_type == "company",
                Organization.google_domain == args.domain,
            )
        )
    return session.scalar(select(Organization).where(Organization.name == args.name))


def summarize(session: Session, org_id: UUID) -> dict[str, int]:
    return {
        "memberships": session.scalar(select(func.count()).select_from(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)) or 0,
        "invitations": session.scalar(select(func.count()).select_from(OrganizationInvitation).where(OrganizationInvitation.organization_id == org_id)) or 0,
        "drive_connections": session.scalar(select(func.count()).select_from(DriveConnection).where(DriveConnection.organization_id == org_id)) or 0,
        "drive_workspaces": session.scalar(select(func.count()).select_from(DriveWorkspace).where(DriveWorkspace.organization_id == org_id)) or 0,
        "documents": session.scalar(select(func.count()).select_from(Document).where(Document.organization_id == org_id)) or 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--name")
    source.add_argument("--id", type=UUID)
    source.add_argument("--domain")
    parser.add_argument("--yes", action="store_true", help="delete without prompting")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        organization = find_organization(session, args)
        if organization is None:
            raise SystemExit("organization not found")

        counts = summarize(session, organization.id)
        print(f"Deleting organization: {organization.name} ({organization.id})")
        print(f"  type={organization.account_type} domain={organization.google_domain}")
        for label, count in counts.items():
            print(f"  {label}: {count}")
        print("Users and Google identities are NOT deleted.")

        if not args.yes:
            answer = input("Type the organization name to confirm deletion: ")
            if answer.strip() != organization.name:
                raise SystemExit("aborted")

        session.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": organization.id}
        )
        session.commit()
        print("deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
