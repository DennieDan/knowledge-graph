"""Integration checks against a migrated DATABASE_URL; inserted rows are rolled back."""
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import get_engine, get_session
from app.main import app
from app.models import Chunk, Document, DocumentVersion, Organization, EMBEDDING_DIMENSIONS


class SettingsTests(unittest.TestCase):
    def settings(self, **overrides):
        values = {
            "database_url": "postgresql+psycopg://runtime",
            "google_client_id": "client",
            "google_client_secret": "secret",
            "session_secret": "session",
            **overrides,
        }
        return Settings(_env_file=None, **values)

    def test_runtime_url_uses_psycopg_driver(self):
        settings = self.settings(database_url="postgresql://runtime")
        self.assertEqual(settings.runtime_url(), "postgresql+psycopg://runtime")

    def test_migration_url_defaults_to_runtime_database(self):
        self.assertEqual(self.settings().migration_url(), "postgresql+psycopg://runtime")

    def test_migration_url_can_use_direct_database_connection(self):
        settings = self.settings(migration_database_url="postgresql://migration")
        self.assertEqual(settings.migration_url(), "postgresql+psycopg://migration")

    def test_session_cookie_defaults_are_local_development_safe(self):
        settings = self.settings()
        self.assertFalse(settings.session_https_only)
        self.assertEqual(settings.session_same_site, "lax")


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.organization = Organization(name="Database integration test")
        self.session.add(self.organization)
        self.session.flush()
        self.document = Document(organization_id=self.organization.id, title="Meeting notes", source="upload")
        self.session.add(self.document)
        self.session.flush()
        self.version = DocumentVersion(document_id=self.document.id, revision=1, content="Project meeting", content_hash=sha256(b"Project meeting").hexdigest())
        self.session.add(self.version)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_document_round_trip_through_api_session(self):
        self.session.commit()
        # A fresh session uses the same transaction so no test data is retained.
        with patch("app.database.get_engine", return_value=self.connection):
            dependency = get_session()
            session = next(dependency)
            try:
                document = session.get(Document, self.document.id)
                self.assertEqual(document.title, "Meeting notes")
                self.assertEqual(document.organization_id, self.organization.id)
            finally:
                dependency.close()

    def test_vector_ranking_and_version_reference(self):
        query = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
        other = [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)
        for position, vector in enumerate([query, other]):
            self.session.add(Chunk(document_version_id=self.version.id, position=position, text=f"Passage {position}", embedding=vector, embedding_model="synthetic-test-v1"))
        self.session.flush()
        chunks = self.session.scalars(select(Chunk).where(Chunk.document_version_id == self.version.id, Chunk.embedding_model == "synthetic-test-v1").order_by(Chunk.embedding.cosine_distance(query))).all()
        self.assertEqual([chunk.position for chunk in chunks], [0, 1])
        self.assertEqual(chunks[0].document_version_id, self.version.id)

    def test_duplicate_revision_rejected(self):
        self.session.add(DocumentVersion(document_id=self.document.id, revision=1, content="duplicate", content_hash=sha256(b"duplicate").hexdigest()))
        with self.assertRaises(IntegrityError):
            self.session.flush()

    def test_orphan_chunk_rejected(self):
        self.session.add(Chunk(document_version_id=uuid4(), position=0, text="orphan"))
        with self.assertRaises(IntegrityError):
            self.session.flush()

    def test_wrong_vector_dimensions_rejected(self):
        self.session.add(Chunk(document_version_id=self.version.id, position=0, text="bad vector", embedding=[1, 2, 3], embedding_model="synthetic-test-v1"))
        with self.assertRaises(StatementError):
            self.session.flush()


class ReadinessTests(unittest.TestCase):
    def test_ready_with_migrated_database(self):
        with TestClient(app) as client:
            response = client.get("/ready")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["database"], "ok")
            self.assertTrue(response.json()["pgvector"])

    def test_unavailable_database_keeps_liveness_and_hides_details(self):
        with patch("app.main.get_engine", side_effect=OperationalError("secret connection details", {}, Exception("private"))):
            with TestClient(app) as client:
                self.assertEqual(client.get("/health").json(), {"status": "ok"})
                response = client.get("/ready")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "not_ready"})

    def test_unmigrated_schema_is_not_ready(self):
        with get_engine().connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET LOCAL search_path TO pg_catalog"))
            with patch("app.main.get_engine", return_value=connection):
                with TestClient(app) as client:
                    self.assertEqual(client.get("/ready").status_code, 503)
            transaction.rollback()


if __name__ == "__main__":
    unittest.main()
