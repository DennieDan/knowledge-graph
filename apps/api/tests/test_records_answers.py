"""Records-first answering: ranking, visibility, and the checked line."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.chat import SOURCE_NOTE, UNCHECKED_NOTE
from app.chat_agent import AgentStep, Answer, AnswerSentence
from app.database import get_engine, get_session
from app.embedding_jobs import embed_document_version
from app.ingest import SourceDocument, ingest_document
from app.llm import LLMResult
from app.main import app
from app.models import (
    Chunk,
    ContentCitation,
    Organization,
    OrganizationMembership,
    Substack,
    SubstackContent,
    SubstackSource,
    User,
)
from app.record_retrieval import search_records


class ScriptedLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, *, prompt, evidence, schema):
        self.calls.append({"prompt": prompt, "evidence": evidence, "schema": schema})
        output = self.outputs.pop(0) if self.outputs else Answer(answered=False, sentences=[])
        return LLMResult(parsed=output, request_id="fake-request", input_tokens=10, output_tokens=5)


def records_step(query):
    return AgentStep(tool="search_records", query=query)


def answer_step(text, citations):
    return AgentStep(
        tool="answer",
        answer=Answer(answered=True, sentences=[AnswerSentence(text=text, citations=citations)]),
    )


class RecordsFirstTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example", display_name="Alice Tan")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Records test", account_type="personal")
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

    def document(self, title, content, owner=None):
        version = ingest_document(
            self.session,
            self.organization.id,
            SourceDocument(
                source="google_drive",
                external_id=f"ext-{uuid4()}",
                title=title,
                content=content,
                owner_user_id=owner,
            ),
        )
        embed_document_version(self.session, version.id, None)
        self.session.flush()
        return version

    def chunk_id(self, version):
        return self.session.scalars(
            select(Chunk.id).where(Chunk.document_version_id == version.id).order_by(Chunk.position)
        ).first()

    def record(
        self,
        name,
        *,
        stack_type="sales-orders",
        identity_key=None,
        owner=None,
        status="confirmed",
        confirmed_by=None,
        segments=None,
        document=None,
        revision=1,
    ):
        substack = Substack(
            organization_id=self.organization.id,
            stack_type=stack_type,
            name=name,
            identity_key=identity_key,
            identity_kind="name" if identity_key else None,
            owner_user_id=owner,
            status="confirmed" if status == "confirmed" else "proposed",
        )
        self.session.add(substack)
        self.session.flush()
        content = SubstackContent(
            substack_id=substack.id,
            revision=revision,
            prompt_key="orders.read.v0",
            prompt_version="v0",
            model="fake",
            content={"segments": segments or [], "entries": []},
            status=status,
            inputs_fingerprint="a" * 64,
            confirmed_by_user_id=confirmed_by.id if confirmed_by else None,
        )
        if status == "confirmed":
            content.confirmed_at = datetime(2026, 3, 14, tzinfo=timezone.utc)
        self.session.add(content)
        self.session.flush()
        if document is not None:
            self.session.add(
                SubstackSource(
                    substack_id=substack.id,
                    document_id=document.document_id,
                    role="evidence",
                )
            )
            self.session.add(
                ContentCitation(
                    content_id=content.id,
                    segment_index=0,
                    chunk_id=self.chunk_id(document),
                    document_id=document.document_id,
                )
            )
            self.session.flush()
        return substack, content

    def ask(self, text, llm, user=None):
        self.current_user = user or self.alice
        thread_id = self.client.post(f"/accounts/{self.organization.id}/chat/threads", json={}).json()["id"]
        with patch("app.chat_agent.get_llm_client", return_value=llm):
            return self.client.post(
                f"/accounts/{self.organization.id}/chat/threads/{thread_id}/messages",
                json={"text": text},
            ).json()

    def test_finds_a_record_by_identifier_and_ranks_confirmed_first(self):
        self.record("Sales order PO2431 revision A", identity_key="PO2431-A", status="proposed")
        confirmed, _ = self.record("Sales order PO2431 revision B", identity_key="PO2431-B")

        found = search_records(self.session, self.organization.id, self.alice.id, "PO2431 quantity", 5)

        self.assertEqual([confirmed.id], [record.substack.id for record in found[:1]])
        self.assertEqual(2, len(found))
        self.assertTrue(found[0].confirmed)
        self.assertFalse(found[1].confirmed)

    def test_finds_a_record_through_the_passages_its_content_cites(self):
        version = self.document("Order sheet.pdf", "Two hundred stainless steel brackets for the west site.")
        substack, _ = self.record("Unrelated name", document=version)

        found = search_records(self.session, self.organization.id, self.alice.id, "stainless steel brackets", 5)

        self.assertIn(substack.id, [record.substack.id for record in found])

    def test_hides_another_persons_owner_only_record(self):
        self.record("Alice private order", identity_key="PO9000", owner=self.alice.id)

        mine = search_records(self.session, self.organization.id, self.alice.id, "PO9000", 5)
        theirs = search_records(self.session, self.organization.id, self.bob.id, "PO9000", 5)

        self.assertEqual(1, len(mine))
        self.assertEqual([], theirs)

    def test_answer_from_a_person_confirmed_record_is_checked(self):
        version = self.document("PO2431.pdf", "Purchase order 2431: 120 stainless steel brackets.")
        substack, _ = self.record(
            "PO2431",
            identity_key="PO2431",
            confirmed_by=self.alice,
            segments=[{"kind": "field", "name": "quantity", "value": "120 brackets"}],
            document=version,
        )
        llm = ScriptedLLM([
            records_step("PO2431 quantity"),
            answer_step("PO2431 is for 120 brackets.", [str(substack.id)]),
        ])

        body = self.ask("how many brackets are on PO2431?", llm)

        self.assertTrue(body["answered"])
        self.assertTrue(body["checked"])
        self.assertEqual("Confirmed by Alice Tan on 2026-03-14", body["checked_note"])
        citation = body["citations"][0]
        self.assertEqual(str(substack.id), citation["record_id"])
        self.assertEqual("person", citation["checked"])
        self.assertEqual([str(version.document_id)], citation["source_ids"])
        # The record was offered to the model as data, with its checked state.
        self.assertIn('checked="person"', llm.calls[1]["evidence"])
        self.assertIn("120 brackets", llm.calls[1]["evidence"])

    def test_answer_from_an_auto_confirmed_record_is_not_checked(self):
        substack, _ = self.record(
            "PO2431",
            identity_key="PO2431",
            segments=[{"kind": "field", "name": "quantity", "value": "120 brackets"}],
        )
        llm = ScriptedLLM([
            records_step("PO2431 quantity"),
            answer_step("PO2431 is for 120 brackets, not yet confirmed.", [str(substack.id)]),
        ])

        body = self.ask("how many brackets are on PO2431?", llm)

        self.assertTrue(body["answered"])
        self.assertFalse(body["checked"])
        self.assertEqual(UNCHECKED_NOTE, body["checked_note"])
        self.assertEqual("system", body["citations"][0]["checked"])

    def test_answer_from_passages_alone_says_it_is_unconfirmed(self):
        version = self.document("Notes.txt", "Two hundred brackets were promised for the west site.")
        llm = ScriptedLLM([
            AgentStep(tool="search_sources", query="brackets west site"),
            answer_step("Two hundred brackets were promised.", [str(self.chunk_id(version))]),
        ])

        body = self.ask("how many brackets for the west site?", llm)

        self.assertTrue(body["answered"])
        self.assertFalse(body["checked"])
        self.assertEqual(SOURCE_NOTE, body["checked_note"])

    def test_confirming_content_records_who_and_when(self):
        substack, content = self.record("PO2431", identity_key="PO2431", status="proposed")

        response = self.client.post(f"/substacks/{substack.id}/contents/{content.id}/confirm")

        self.assertEqual(200, response.status_code)
        self.assertEqual("confirmed", content.status)
        self.assertEqual(self.alice.id, content.confirmed_by_user_id)
        self.assertIsNotNone(content.confirmed_at)
        detail = self.client.get(f"/substacks/{substack.id}").json()
        self.assertEqual("Alice Tan", detail["content"]["confirmed_by"])


if __name__ == "__main__":
    unittest.main()
