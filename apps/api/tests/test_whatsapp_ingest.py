"""WhatsApp auto-ingest: transcripts become documents after import and webhook bursts."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_engine, get_session
from app.main import app
from app.models import Document, DocumentVersion, Organization, OrganizationMembership, User, WhatsappChat, WhatsappConnection, WhatsappMessage
from app.whatsapp import debounced_ingest, run_import


class _NoClose:
    """Context manager yielding the shared test session without closing it."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


def fake_settings(secret=None):
    return SimpleNamespace(
        waha_webhook_secret=(
            SimpleNamespace(get_secret_value=lambda: secret) if secret else None
        )
    )


class WhatsappIngestTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"wa-ingest-{uuid4()}@example.com")
        self.session.add(self.user)
        self.session.flush()
        self.organization = Organization(name="Ingest test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()
        self.session.add(OrganizationMembership(organization_id=self.organization.id, user_id=self.user.id, role="admin"))
        self.conn = WhatsappConnection(
            user_id=self.user.id, waha_session=f"u_{self.user.id.hex}", status="WORKING"
        )
        self.session.add(self.conn)
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

    def make_chat(self, **kwargs):
        chat = WhatsappChat(connection_id=self.conn.id, chat_jid="6591234567@c.us", **kwargs)
        self.session.add(chat)
        self.session.flush()
        return chat

    def document(self):
        return self.session.scalar(
            select(Document).where(
                Document.organization_id == self.organization.id,
                Document.source == "whatsapp",
                Document.external_id == "6591234567@c.us",
            )
        )

    def test_import_ingests_transcript_owned_by_importer(self):
        chat = self.make_chat(organization_id=self.organization.id)
        page = [
            {"id": "m1", "timestamp": 1700000000, "from": "6591234567@c.us", "body": "hello"},
        ]
        with (
            patch("app.whatsapp.Session", new=lambda *a, **k: _NoClose(self.session)),
            patch("app.whatsapp.waha_client.get_messages", return_value=page),
        ):
            run_import(self.conn.id, [chat.chat_jid])
        document = self.document()
        self.assertIsNotNone(document)
        self.assertEqual(self.user.id, document.owner_user_id)
        version = self.session.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document.id))
        self.assertIn("hello", version.content)

    def test_import_without_organization_skips_ingest(self):
        chat = self.make_chat()
        with (
            patch("app.whatsapp.Session", new=lambda *a, **k: _NoClose(self.session)),
            patch("app.whatsapp.waha_client.get_messages", return_value=[{"id": "m1", "timestamp": 1700000000, "body": "hi"}]),
        ):
            run_import(self.conn.id, [chat.chat_jid])
        self.assertIsNone(self.document())

    def test_webhook_marks_pending_and_debounced_ingest_revises_transcript(self):
        chat = self.make_chat(import_status="imported", organization_id=self.organization.id)
        self.session.add(WhatsappMessage(
            chat_id=chat.id, wa_message_id="m1",
            sent_at=datetime.fromtimestamp(1700000000, timezone.utc),
            body="first",
        ))
        self.session.flush()
        # The TestClient runs background tasks synchronously; silence the debounce
        # sleep and give the task a session that cannot see uncommitted test data.
        with (
            patch("app.whatsapp.get_settings", return_value=fake_settings(None)),
            patch("app.whatsapp.time.sleep"),
        ):
            resp = self.client.post(
                "/whatsapp/webhooks",
                json={
                    "event": "message",
                    "session": self.conn.waha_session,
                    "payload": {"id": "m2", "timestamp": 1700000100, "from": "6591234567@c.us", "body": "second"},
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(chat.pending_ingest)
        with (
            patch("app.whatsapp.Session", new=lambda *a, **k: _NoClose(self.session)),
            patch("app.whatsapp.time.sleep"),
        ):
            debounced_ingest(chat.id)
        self.session.refresh(chat)
        self.assertFalse(chat.pending_ingest)
        document = self.document()
        self.assertIsNotNone(document)
        version = self.session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        self.assertIn("second", version.content)

    def test_import_sets_organization_and_requires_membership(self):
        chat = self.make_chat(import_status="importing")
        resp = self.client.post(
            "/whatsapp/imports",
            json={"chat_ids": [chat.chat_jid], "organization_id": str(self.organization.id)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(chat.organization_id, self.organization.id)
        resp = self.client.post(
            "/whatsapp/imports",
            json={"chat_ids": [chat.chat_jid], "organization_id": str(uuid4())},
        )
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
