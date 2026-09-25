"""Create, list or switch off assistant connector keys from the command line.

The app's settings do the same through /accounts/{id}/connector-keys; this is
for local development and demos. Run from apps/api with the virtual environment
active:

    python -m scripts.connector_key create --email owner@example.com --name "Claude Desktop"
    python -m scripts.connector_key list --email owner@example.com
    python -m scripts.connector_key revoke --id UUID

Pass --account-id when the person belongs to more than one account. A new key
is printed once and never stored.
"""
import argparse
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connector_keys import create_key, role_may_connect
from app.database import get_engine
from app.models import ConnectorKey, OrganizationMembership, User


def membership(session: Session, email: str, account_id: UUID | None) -> OrganizationMembership:
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        sys.exit(f"No user with email {email}.")
    memberships = session.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)).all()
    if account_id is not None:
        memberships = [item for item in memberships if item.organization_id == account_id]
    if len(memberships) != 1:
        sys.exit(f"{email} belongs to {len(memberships)} matching accounts; pass --account-id.")
    return memberships[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("create", "list", "revoke"))
    parser.add_argument("--email")
    parser.add_argument("--account-id", type=UUID)
    parser.add_argument("--name", default="Assistant")
    parser.add_argument("--id", type=UUID, help="key id, for revoke")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        if args.action == "revoke":
            row = session.get(ConnectorKey, args.id) if args.id else None
            if row is None:
                sys.exit("No key with that --id.")
            row.revoked_at = row.revoked_at or datetime.now(timezone.utc)
            session.commit()
            print(f"Switched off {row.name} ({row.prefix}…).")
            return
        if not args.email:
            sys.exit("--email is required.")
        member = membership(session, args.email, args.account_id)
        if args.action == "list":
            for row in session.scalars(
                select(ConnectorKey)
                .where(ConnectorKey.organization_id == member.organization_id, ConnectorKey.user_id == member.user_id)
                .order_by(ConnectorKey.created_at)
            ):
                state = "off" if row.revoked_at else "on"
                print(f"{row.id}  {row.prefix}…  {state:3}  {row.name}  last used {row.last_used_at or 'never'}")
            return
        if not role_may_connect(member.role):
            sys.exit(f"The {member.role} role cannot connect assistants yet.")
        row, key = create_key(session, organization_id=member.organization_id, user_id=member.user_id, name=args.name)
        session.commit()
        print(f"Created {row.name} ({row.id}). The key is shown once:\n{key}")


if __name__ == "__main__":
    main()
