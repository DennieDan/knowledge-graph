"""Stacks API: filing, owner-only visibility, detail shape, confirm, backfill."""
import unittest
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.filing import ingest_and_file
from app.ingest import SourceDocument, ingest_document
from app.main import app
from app.models import (
    Document,
    Organization,
    OrganizationMembership,
    Substack,
    SubstackContent,
    SubstackSource,
    User,
)


class StacksApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Stacks test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add_all([
            OrganizationMembership(organization_id=self.organization.id, user_id=self.alice.id, role="admin"),
            OrganizationMembership(organization_id=self.organization.id, user_id=self.bob.id, role="member"),
        ])
        self.session.flush()
        self.current_user = self.alice

        def override_session():
            yield self.session

        app.dependency_overrides[get_current_user] = lambda: self.current_user
        app.dependency_overrides[get_session] = override_session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def ingest(self, source="google_drive", owner=None, title="PO2431.pdf", content="order contents"):
        external_id = f"ext-{uuid4()}"
        ingest_and_file(
            self.session,
            self.organization.id,
            SourceDocument(source=source, external_id=external_id, title=title, content=content, owner_user_id=owner),
        )
        self.session.commit()
        return external_id

    def list_substacks(self, user, **params):
        self.current_user = user
        return self.client.get(f"/accounts/{self.organization.id}/substacks", params=params).json()

    def test_filing_creates_files_substack_with_content(self):
        self.ingest(owner=self.alice.id)
        rows = self.list_substacks(self.alice)
        self.assertEqual(1, len(rows))
        self.assertEqual("files", rows[0]["type_id"])
        self.assertEqual("PO2431.pdf", rows[0]["name"])
        self.assertEqual("mine", rows[0]["scope"])
        detail = self.client.get(f"/substacks/{rows[0]['id']}").json()
        self.assertEqual("confirmed", detail["content_status"])
        self.assertEqual("PO2431.pdf", detail["sources"][0]["name"])
        self.assertIn("Google Drive", detail["sources"][0]["origin"])
        self.assertTrue(detail["content"]["segments"])

    def test_owner_only_substack_hidden_from_other_members(self):
        self.ingest(owner=self.alice.id)
        self.assertEqual([], self.list_substacks(self.bob))
        substack_id = self.list_substacks(self.alice)[0]["id"]
        self.current_user = self.bob
        self.assertEqual(404, self.client.get(f"/substacks/{substack_id}").status_code)

    def test_org_wide_document_visible_to_all_members(self):
        self.ingest(owner=None)
        self.assertEqual(1, len(self.list_substacks(self.bob)))
        stacks = self.client.get(f"/accounts/{self.organization.id}/stacks").json()
        by_type = {row["type"]: row["count"] for row in stacks}
        self.assertEqual(1, by_type["files"])
        self.assertEqual(0, by_type["clients"])

    def test_whatsapp_document_files_as_conversation(self):
        self.ingest(source="whatsapp", owner=self.alice.id, title="Group ABC", content="2026-01-02 10:30 Ali: hi")
        rows = self.list_substacks(self.alice, type="conversations")
        self.assertEqual(1, len(rows))
        self.assertEqual("conversations", rows[0]["type_id"])

    def test_analysis_can_be_started_and_listed(self):
        self.ingest(owner=self.alice.id)
        response = self.client.post(f"/accounts/{self.organization.id}/analysis")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json())
        listed = self.client.get(f"/accounts/{self.organization.id}/analysis")
        self.assertEqual(200, listed.status_code)
        self.assertTrue(any(run["scope"] == "mine" for run in listed.json()))

    def test_search_filters_by_name(self):
        self.ingest(owner=self.alice.id, title="PO2431.pdf")
        self.ingest(owner=self.alice.id, title="Rates.pdf")
        self.assertEqual(1, len(self.list_substacks(self.alice, q="PO2431")))

    def test_confirm_flips_proposed_content(self):
        self.ingest(owner=self.alice.id)
        substack_id = self.list_substacks(self.alice)[0]["id"]
        substack = self.session.get(Substack, UUID(substack_id))
        substack.status = "proposed"
        self.session.flush()
        resp = self.client.post(f"/substacks/{substack_id}/confirm")
        self.assertEqual(200, resp.status_code)
        self.assertEqual("confirmed", resp.json()["status"])

    def test_confirm_specific_pending_revision_supersedes_previous_content(self):
        self.ingest(owner=self.alice.id)
        substack_id = UUID(self.list_substacks(self.alice)[0]["id"])
        first = self.session.scalar(
            select(SubstackContent)
            .where(SubstackContent.substack_id == substack_id)
            .order_by(SubstackContent.revision.desc())
            .limit(1)
        )
        proposed = SubstackContent(
            substack_id=substack_id,
            revision=first.revision + 1,
            prompt_key="files.describe.v1",
            prompt_version="v1",
            model="fake",
            content={"segments": [], "entries": []},
            status="proposed",
            inputs_fingerprint="d" * 64,
        )
        self.session.add(proposed)
        self.session.commit()
        response = self.client.post(f"/substacks/{substack_id}/contents/{proposed.id}/confirm")
        self.assertEqual(200, response.status_code)
        self.assertEqual("confirmed", proposed.status)
        self.assertEqual("superseded", first.status)

    def test_file_all_backfills_unfiled_documents(self):
        external_id = f"ext-{uuid4()}"
        ingest_document(
            self.session,
            self.organization.id,
            SourceDocument(source="google_drive", external_id=external_id, title="Old.pdf", content="old"),
        )
        self.session.commit()
        resp = self.client.post(f"/accounts/{self.organization.id}/stacks/file-all")
        self.assertEqual(200, resp.status_code)
        self.assertEqual(1, resp.json()["filed"])
        self.assertEqual(1, len(self.list_substacks(self.alice)))

    def test_create_and_patch_manual_substack(self):
        created = self.client.post(
            f"/accounts/{self.organization.id}/substacks",
            json={"stack_type": "clients", "name": "Acme Engineering"},
        )
        self.assertEqual(200, created.status_code)
        substack_id = created.json()["id"]
        # Manually created substacks are org-visible.
        self.current_user = self.bob
        self.assertEqual(200, self.client.get(f"/substacks/{substack_id}").status_code)
        patched = self.client.patch(f"/substacks/{substack_id}", json={"summary": "Precision customer"})
        self.assertEqual("Precision customer", patched.json()["desc"])
        bad = self.client.post(
            f"/accounts/{self.organization.id}/substacks",
            json={"stack_type": "bogus", "name": "x"},
        )
        self.assertEqual(422, bad.status_code)


if __name__ == "__main__":
    unittest.main()
