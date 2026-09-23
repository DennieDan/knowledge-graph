"""Generation pipeline: templates, citation validation, fingerprints, staleness."""
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import generators
from app.database import get_engine
from app.generation import mark_stale_for_document, run_generation
from app.ingest import SourceDocument, ingest_document
from app.models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    GenerationRun,
    Organization,
    Substack,
    SubstackContent,
    SubstackSource,
    User,
    WhatsappChat,
    WhatsappConnection,
    WhatsappMessage,
)
from app.segments import GeneratedContent, Segment
from app.sources import whatsapp_chat_document


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.user = User(email=f"gen-{uuid4()}@example.com")
        self.session.add(self.user)
        self.session.flush()
        self.organization = Organization(name="Generation test", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def make_substack(self, stack_type="files", content="seed content", source="google_drive"):
        external_id = f"ext-{uuid4()}"
        ingest_document(
            self.session,
            self.organization.id,
            SourceDocument(source=source, external_id=external_id, title="Evidence", content=content),
        )
        document = self.session.scalar(
            select(Document).where(Document.organization_id == self.organization.id, Document.external_id == external_id)
        )
        substack = Substack(organization_id=self.organization.id, stack_type=stack_type, name="SS")
        self.session.add(substack)
        self.session.flush()
        self.session.add(SubstackSource(substack_id=substack.id, document_id=document.id))
        self.session.flush()
        return substack, document

    def latest_chunks(self, document):
        version = self.session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.revision.desc())
            .limit(1)
        )
        return self.session.scalars(select(Chunk).where(Chunk.document_version_id == version.id)).all()

    def test_files_template_confirms_described_content(self):
        substack, document = self.make_substack()
        content = run_generation(self.session, substack)
        self.assertIsNotNone(content)
        self.assertEqual("confirmed", content.status)
        self.assertEqual("files.describe.v0", content.prompt_key)
        self.assertEqual("template", content.model)
        citations = self.session.scalars(
            select(ContentCitation).where(ContentCitation.content_id == content.id)
        ).all()
        self.assertTrue(citations)
        self.assertTrue(all(c.document_id == document.id for c in citations))
        valid_ids = {str(c.id) for c in self.latest_chunks(document)}
        self.assertTrue(all(str(c.chunk_id) in valid_ids for c in citations))

    def test_fingerprint_skips_unchanged_evidence(self):
        substack, _ = self.make_substack()
        first = run_generation(self.session, substack)
        second = run_generation(self.session, substack)
        self.assertEqual(first.id, second.id)
        self.assertEqual(1, second.revision)

    def test_validator_drops_citations_outside_evidence(self):
        from app.generation import _validate
        output = GeneratedContent(segments=[
            Segment(kind="token", value="x", citations=[str(uuid4()), "bogus"]),
        ])
        dropped = _validate(output, set())
        self.assertEqual(2, dropped)
        self.assertEqual([], output.segments[0].citations)

    def test_new_document_revision_stales_and_regenerates(self):
        substack, document = self.make_substack(content="first")
        first = run_generation(self.session, substack)
        ingest_document(
            self.session,
            self.organization.id,
            SourceDocument(source="google_drive", external_id=document.external_id, title="Evidence", content="second"),
        )
        staled = mark_stale_for_document(self.session, document.id)
        self.assertIn(substack.id, staled)
        self.assertEqual("stale", first.status)
        second = run_generation(self.session, substack)
        self.assertEqual(2, second.revision)
        self.assertEqual("confirmed", second.status)
        # Fresh content cites only the latest revision and is not flagged stale.
        self.assertEqual([], mark_stale_for_document(self.session, document.id))

    def test_conversations_template_builds_entries(self):
        conn = WhatsappConnection(user_id=self.user.id, waha_session=f"s-{uuid4()}")
        self.session.add(conn)
        self.session.flush()
        chat = WhatsappChat(connection_id=conn.id, chat_jid="chat@g.us", organization_id=self.organization.id)
        self.session.add(chat)
        self.session.flush()
        self.session.add(WhatsappMessage(
            chat_id=chat.id, wa_message_id="m1",
            sent_at=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
            sender_name="Ali", body="confirmed the order",
        ))
        self.session.flush()
        message = self.session.scalar(
            select(WhatsappMessage).where(WhatsappMessage.chat_id == chat.id)
        )
        ingest_document(
            self.session,
            self.organization.id,
            whatsapp_chat_document(chat, [message], self.user.id),
        )
        document = self.session.scalar(select(Document).order_by(Document.created_at.desc()).limit(1))
        substack = Substack(organization_id=self.organization.id, stack_type="conversations", name="chat")
        self.session.add(substack)
        self.session.flush()
        self.session.add(SubstackSource(substack_id=substack.id, document_id=document.id))
        self.session.flush()
        content = run_generation(self.session, substack)
        entries = content.content["entries"]
        self.assertEqual(1, len(entries))
        self.assertEqual("Ali", entries[0]["author"])
        self.assertIn("confirmed the order", entries[0]["message"])
        self.assertEqual("m1", entries[0]["locator"]["wa_message_id"])

    def test_stub_generator_proposes_content(self):
        substack, _ = self.make_substack(stack_type="items")
        content = run_generation(self.session, substack)
        self.assertEqual("proposed", content.status)
        self.assertEqual("generic.stub.v0", content.prompt_key)

    def test_generator_failure_is_recorded_not_raised(self):
        substack, _ = self.make_substack()
        original = generators.GENERATORS["files.describe.v0"]
        def boom(ctx):
            raise RuntimeError("generator exploded")
        generators.GENERATORS["files.describe.v0"] = (boom, True)
        try:
            self.assertIsNone(run_generation(self.session, substack))
        finally:
            generators.GENERATORS["files.describe.v0"] = original
        run = self.session.scalar(select(GenerationRun).where(GenerationRun.substack_id == substack.id))
        self.assertEqual("error", run.status)
        self.assertIn("generator exploded", run.error)


if __name__ == "__main__":
    unittest.main()
