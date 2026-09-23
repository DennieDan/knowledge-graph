"""Search API: ranking, org isolation, owner-only visibility, latest revision."""
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.embedding_jobs import embed_document_version
from app.filing import ingest_and_file
from app.ingest import SourceDocument
from app.main import app
from app.models import Organization, OrganizationMembership, User


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Search test", account_type="personal")
        self.other_organization = Organization(name="Other co", account_type="personal")
        self.session.add_all([self.organization, self.other_organization])
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

    def ingest(self, title, content, organization_id=None, owner=None, external_id=None):
        version = ingest_and_file(
            self.session,
            organization_id or self.organization.id,
            SourceDocument(
                source="google_drive",
                external_id=external_id or f"ext-{uuid4()}",
                title=title,
                content=content,
                owner_user_id=owner,
            ),
        )
        # The worker embeds asynchronously; search only sees embedded chunks.
        embed_document_version(self.session, version.id, None)

    def search(self, query, user=None, organization_id=None, **params):
        self.current_user = user or self.alice
        response = self.client.get(
            f"/accounts/{organization_id or self.organization.id}/search",
            params={"q": query, **params},
        )
        return response

    def test_ranks_the_closest_passage_first(self):
        self.ingest("PO2431.pdf", "Purchase order 2431: 120 stainless steel brackets, due 14 March.")
        self.ingest("Menu.txt", "Lunch menu for the staff canteen: rice, noodles, soup.")

        body = self.search("how many brackets were ordered?").json()

        self.assertEqual("PO2431.pdf", body["results"][0]["title"])
        self.assertEqual("Google Drive", body["results"][0]["source_label"])
        self.assertIn("brackets", body["results"][0]["snippet"])
        self.assertIsNotNone(body["results"][0]["substack"])
        self.assertGreater(body["results"][0]["similarity"], body["results"][-1]["similarity"])

    def test_answers_a_question_asked_in_another_language(self):
        self.ingest("PO2431.pdf", "Purchase order 2431: 120 stainless steel brackets, due 14 March.")
        self.ingest("Menu.txt", "Lunch menu for the staff canteen: rice, noodles, soup.")

        body = self.search("berapa banyak pendakap keluli dipesan?").json()

        self.assertEqual("PO2431.pdf", body["results"][0]["title"])

    def test_hides_another_organizations_documents(self):
        self.ingest("Rival PO.pdf", "Purchase order 9999: 40 brackets.", organization_id=self.other_organization.id)

        body = self.search("brackets").json()

        self.assertEqual([], body["results"])

    def test_refuses_an_organization_the_asker_is_not_in(self):
        response = self.search("brackets", organization_id=self.other_organization.id)

        self.assertEqual(404, response.status_code)

    def test_hides_another_members_private_document(self):
        self.ingest("Alice only.pdf", "Purchase order 2431: 120 brackets.", owner=self.alice.id)

        self.assertEqual("Alice only.pdf", self.search("brackets").json()["results"][0]["title"])
        self.assertEqual([], self.search("brackets", user=self.bob).json()["results"])

    def test_searches_only_the_latest_revision(self):
        external_id = f"ext-{uuid4()}"
        self.ingest("PO2431.pdf", "Purchase order 2431: 120 brackets.", external_id=external_id)
        self.ingest("PO2431.pdf", "Purchase order 2431: 240 brackets.", external_id=external_id)

        snippets = [result["snippet"] for result in self.search("how many brackets?").json()["results"]]

        self.assertTrue(any("240" in snippet for snippet in snippets))
        self.assertFalse(any("120" in snippet for snippet in snippets))

    def test_limits_the_number_of_hits(self):
        for index in range(3):
            self.ingest(f"PO{index}.pdf", f"Purchase order {index}: brackets.")

        self.assertEqual(2, len(self.search("brackets", limit=2).json()["results"]))
        self.assertEqual(422, self.search("brackets", limit=0).status_code)
        self.assertEqual(422, self.client.get(f"/accounts/{self.organization.id}/search").status_code)


if __name__ == "__main__":
    unittest.main()
