import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import (
    DriveConnection,
    DriveWorkspace,
    DriveWorkspaceConnection,
    GoogleIdentity,
    Organization,
    OrganizationMembership,
    User,
)


class AccountDriveTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"owner-{uuid4()}@acme.example", display_name="Owner")
        self.session.add(self.user)
        self.session.flush()
        self.identity = GoogleIdentity(
            user_id=self.user.id,
            google_sub=f"sub-{uuid4()}",
            email=self.user.email,
            hosted_domain="acme.example",
        )
        self.session.add(self.identity)
        self.session.flush()

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_identity_login_does_not_request_drive_scope(self):
        response = self.client.get("/auth/google/login", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        scope = parse_qs(urlparse(response.headers["location"]).query)["scope"][0]
        self.assertEqual(scope, "openid email profile")
        self.assertNotIn("drive", scope)

    def test_company_creation_assigns_creator_as_admin(self):
        response = self.client.post("/accounts", json={"account_type": "company", "name": "Acme"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "admin")
        self.assertEqual(response.json()["google_domain"], "acme.example")
        membership = self.session.get(OrganizationMembership, uuid4())
        self.assertIsNone(membership)
        organization = self.session.get(Organization, response.json()["id"])
        self.assertEqual(organization.account_type, "company")

    def test_consumer_identity_cannot_create_company(self):
        self.identity.hosted_domain = None
        self.session.flush()
        response = self.client.post("/accounts", json={"account_type": "company", "name": "Acme"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "workspace_account_required")

    def test_invitation_requires_domain_and_exact_signed_in_email(self):
        account = self.client.post("/accounts", json={"account_type": "company", "name": "Acme"}).json()
        mismatch = self.client.post(f"/accounts/{account['id']}/invitations", json={"email": "person@other.example"})
        self.assertEqual(mismatch.status_code, 422)
        created = self.client.post(f"/accounts/{account['id']}/invitations", json={"email": "person@acme.example"})
        self.assertEqual(created.status_code, 200)
        token = created.json()["invite_url"].split("invite=", 1)[1]
        invited_user = User(email="person@acme.example")
        self.session.add(invited_user)
        self.session.flush()
        self.session.add(GoogleIdentity(user_id=invited_user.id, google_sub=f"sub-{uuid4()}", email=invited_user.email, hosted_domain="acme.example"))
        self.session.flush()
        app.dependency_overrides[get_current_user] = lambda: invited_user
        accepted = self.client.post(f"/invitations/{token}/accept")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["role"], "member")

    def test_duplicate_company_domain_rejected(self):
        self.session.add(Organization(name="Acme", account_type="company", google_domain="acme.example"))
        self.session.flush()
        response = self.client.post("/accounts", json={"account_type": "company", "name": "Outra"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "company_domain_taken")

    def test_workspace_user_auto_joins_existing_company_on_me(self):
        self.session.add(Organization(name="Acme", account_type="company", google_domain="acme.example"))
        self.session.flush()
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["accounts"]), 1)
        self.assertEqual(response.json()["accounts"][0]["role"], "member")
        self.assertEqual(response.json()["accounts"][0]["account_type"], "company")
        self.assertFalse(response.json()["needs_account"])

    def create_drive_context(self, kind="my_drive"):
        organization = Organization(
            name="Acme",
            account_type="company",
            google_domain="acme.example",
            created_by_user_id=self.user.id,
        )
        self.session.add(organization)
        self.session.flush()
        self.session.add(OrganizationMembership(organization_id=organization.id, user_id=self.user.id, role="admin"))
        connection = DriveConnection(
            organization_id=organization.id,
            user_id=self.user.id,
            google_identity_id=self.identity.id,
            scopes="drive.readonly",
            access_token="token",
            access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.session.add(connection)
        self.session.flush()
        workspace = DriveWorkspace(
            organization_id=organization.id,
            kind=kind,
            google_drive_id="root" if kind == "my_drive" else "shared-1",
            name="My Drive" if kind == "my_drive" else "Operations",
            owner_user_id=self.user.id if kind == "my_drive" else None,
        )
        self.session.add(workspace)
        self.session.flush()
        self.session.add(DriveWorkspaceConnection(workspace_id=workspace.id, connection_id=connection.id))
        self.session.flush()
        return organization, workspace

    def test_my_drive_tree_uses_user_corpus(self):
        _, workspace = self.create_drive_context()
        with patch("app.drive.list_pages", return_value=[]) as pages:
            response = self.client.get(f"/drive/workspaces/{workspace.id}/tree")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pages.call_args.args[1]["corpora"], "user")
        self.assertNotIn("driveId", pages.call_args.args[1])

    def test_shared_drive_permissions_are_read_only_and_workspace_checked(self):
        _, workspace = self.create_drive_context("shared_drive")
        metadata = {
            "id": "file-1",
            "name": "Plan",
            "driveId": "shared-1",
            "shared": True,
            "capabilities": {"canDownload": True, "canEdit": False},
        }
        permissions = [{"id": "p1", "type": "group", "role": "reader", "emailAddress": "ops@acme.example"}]
        with patch("app.drive.fetch_file_metadata", return_value=metadata), patch("app.drive.list_pages", return_value=permissions):
            response = self.client.get(f"/drive/workspaces/{workspace.id}/files/file-1/permissions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["permissions"][0]["type"], "group")
        self.assertTrue(response.json()["capabilities"]["canDownload"])


if __name__ == "__main__":
    unittest.main()
