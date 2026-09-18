"""Ingestion tests: chunking is pure, document writes roll back."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chunking import chunk_text
from app.database import get_engine
from app.drive import UnsupportedFileType, fetch_file_text
from app.ingest import SourceDocument, content_hash, ingest_document
from app.models import Chunk, Document, DocumentVersion, Organization, User, WhatsappChat, WhatsappConnection, WhatsappMessage
from app.sources import whatsapp_chat_document


class ChunkingTests(unittest.TestCase):
    def test_paragraphs_are_packed_without_exceeding_the_budget(self):
        text = "\n\n".join(["alpha " * 20, "beta " * 20, "gamma " * 60])
        chunks = chunk_text(text, max_chars=200, overlap=20)
        self.assertTrue(all(len(chunk) <= 200 for chunk in chunks))
        self.assertGreater(len(chunks), 1)

    def test_unbroken_text_is_split_with_overlap(self):
        text = "".join(chr(0x4E00 + index) for index in range(250))
        chunks = chunk_text(text, max_chars=100, overlap=20)
        self.assertEqual([100, 100, 90], [len(chunk) for chunk in chunks])
        self.assertEqual(chunks[0][-20:], chunks[1][:20])

    def test_blank_input_produces_no_chunks(self):
        self.assertEqual([], chunk_text("   \n\n  "))

    def test_overlap_must_be_smaller_than_the_budget(self):
        with self.assertRaises(ValueError):
            chunk_text("text", max_chars=10, overlap=10)


class WhatsappNormalizerTests(unittest.TestCase):
    def message(self, **kwargs):
        defaults = dict(
            sent_at=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
            from_me=False,
            sender_name="Ali",
            sender_jid="6591234567@c.us",
            msg_type="chat",
            body="hello",
            has_media=False,
        )
        return WhatsappMessage(**{**defaults, **kwargs})

    def test_transcript_is_chronological_and_labels_speakers(self):
        chat = WhatsappChat(chat_jid="123@g.us", name="Team")
        later = self.message(sent_at=datetime(2026, 1, 2, 11, 0, tzinfo=timezone.utc), from_me=True, body="hi")
        document = whatsapp_chat_document(chat, [later, self.message()])
        self.assertEqual(
            "2026-01-02 10:30 Ali: hello\n2026-01-02 11:00 Me: hi",
            document.content,
        )
        self.assertEqual("123@g.us", document.external_id)
        self.assertEqual("Team", document.title)

    def test_media_without_text_becomes_a_placeholder(self):
        chat = WhatsappChat(chat_jid="123@c.us", name=None)
        document = whatsapp_chat_document(chat, [self.message(body=None, has_media=True, msg_type="image")])
        self.assertTrue(document.content.endswith("Ali: [image]"))
        self.assertEqual("123@c.us", document.title)


class DriveFetchTests(unittest.TestCase):
    def test_google_docs_are_exported_as_text(self):
        with patch("app.drive.httpx.get", return_value=httpx.Response(200, text="body")) as get:
            text = fetch_file_text("token", {"id": "f1", "mimeType": "application/vnd.google-apps.document"})
        self.assertEqual("body", text)
        self.assertTrue(get.call_args.args[0].endswith("/f1/export"))
        self.assertEqual("text/plain", get.call_args.kwargs["params"]["mimeType"])

    def test_plain_files_are_downloaded_with_alt_media(self):
        with patch("app.drive.httpx.get", return_value=httpx.Response(200, text="body")) as get:
            fetch_file_text("token", {"id": "f1", "mimeType": "text/markdown"})
        self.assertEqual("media", get.call_args.kwargs["params"]["alt"])

    def test_binary_files_are_rejected(self):
        with self.assertRaises(UnsupportedFileType):
            fetch_file_text("token", {"id": "f1", "mimeType": "application/pdf"})


class IngestDocumentTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.organization = Organization(name=f"org-{uuid4()}")
        self.session.add(self.organization)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def document(self, content: str, title: str = "Notes") -> SourceDocument:
        return SourceDocument(
            source="google_drive",
            external_id="file-1",
            title=title,
            content=content,
            source_uri="https://drive.example/file-1",
        )

    def test_first_ingest_creates_a_document_version_and_chunks(self):
        version = ingest_document(self.session, self.organization.id, self.document("alpha\n\nbeta"))
        self.assertEqual(1, version.revision)
        self.assertEqual(content_hash("alpha\n\nbeta"), version.content_hash)
        chunks = self.session.scalars(
            select(Chunk).where(Chunk.document_version_id == version.id).order_by(Chunk.position)
        ).all()
        self.assertEqual([0], [chunk.position for chunk in chunks])
        self.assertIsNone(chunks[0].embedding)
        self.assertIsNone(chunks[0].embedding_model)

    def test_unchanged_content_does_not_create_a_revision(self):
        ingest_document(self.session, self.organization.id, self.document("alpha"))
        self.assertIsNone(ingest_document(self.session, self.organization.id, self.document("alpha")))
        self.assertEqual(
            1,
            len(self.session.scalars(select(DocumentVersion)).all()),
        )

    def test_changed_content_adds_a_revision_and_keeps_the_old_chunks(self):
        first = ingest_document(self.session, self.organization.id, self.document("alpha"))
        second = ingest_document(self.session, self.organization.id, self.document("beta", title="Renamed"))
        self.assertEqual(2, second.revision)
        self.assertEqual(first.document_id, second.document_id)
        self.assertEqual(
            1,
            len(self.session.scalars(select(Chunk).where(Chunk.document_version_id == first.id)).all()),
        )
        document = self.session.get(Document, second.document_id)
        self.assertEqual("Renamed", document.title)

    def test_empty_content_is_skipped(self):
        self.assertIsNone(ingest_document(self.session, self.organization.id, self.document("  \n ")))
        self.assertEqual([], self.session.scalars(select(Document)).all())

    def test_whatsapp_chat_round_trips_into_chunks(self):
        user = User(email=f"ingest-{uuid4()}@example.com")
        self.session.add(user)
        self.session.flush()
        connection = WhatsappConnection(user_id=user.id, waha_session=f"u_{user.id.hex}")
        self.session.add(connection)
        self.session.flush()
        chat = WhatsappChat(connection_id=connection.id, chat_jid="123@c.us", name="Ali")
        self.session.add(chat)
        self.session.flush()
        message = WhatsappMessage(
            chat_id=chat.id,
            wa_message_id="m1",
            sent_at=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
            body="selamat pagi",
        )
        self.session.add(message)
        self.session.flush()

        version = ingest_document(self.session, self.organization.id, whatsapp_chat_document(chat, [message]))
        chunk = self.session.scalar(select(Chunk).where(Chunk.document_version_id == version.id))
        self.assertIn("selamat pagi", chunk.text)


if __name__ == "__main__":
    unittest.main()
