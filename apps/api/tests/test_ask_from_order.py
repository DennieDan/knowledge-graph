"""Ask-from-order: scoped chat with substack_id / record_id (#94)."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_current_user
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
from app.record_retrieval import get_visible_record, source_document_ids
from sqlalchemy import select


class ScriptedLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, *, prompt, evidence, schema, effort=None):
        self.calls.append({"prompt": prompt, "evidence": evidence, "schema": schema, "effort": effort})
        output = self.outputs.pop(0) if self.outputs else Answer(answered=False, sentences=[])
        return LLMResult(parsed=output, request_id="fake-request", input_tokens=10, output_tokens=5)


def answer_step(text, citations):
    return AgentStep(
        tool="answer",
        answer=Answer(answered=True, sentences=[AnswerSentence(text=text, citations=citations)]),
    )


class AskFromOrderTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example", display_name="Alice Tan")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Ask scope test", account_type="personal")
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
        identity_key=None,
        owner=None,
        status="confirmed",
        confirmed_by=None,
        segments=None,
        document=None,
    ):
        substack = Substack(
            organization_id=self.organization.id,
            stack_type="sales-orders",
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
            revision=1,
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

    def ask(self, text, llm, *, substack_id=None, record_id=None):
        thread_id = self.client.post(
            f"/accounts/{self.organization.id}/chat/threads", json={}
        ).json()["id"]
        body = {"text": text}
        if substack_id is not None:
            body["substack_id"] = str(substack_id)
        if record_id is not None:
            body["record_id"] = str(record_id)
        with patch("app.chat_agent.get_llm_client", return_value=llm):
            return self.client.post(
                f"/accounts/{self.organization.id}/chat/threads/{thread_id}/messages",
                json=body,
            )

    def test_scoped_ask_seeds_record_and_sources(self):
        version = self.document("PO HH-2231.pdf", "Purchase order HH-2231: 50 brackets at $12 each.")
        substack, _ = self.record(
            "PO HH-2231",
            identity_key="HH-2231",
            confirmed_by=self.alice,
            segments=[{"kind": "field", "name": "unit_price", "value": "$12"}],
            document=version,
        )
        # Answer from the seeded record without searching — scope already loaded it.
        llm = ScriptedLLM([answer_step("This order is priced at $12 per unit.", [str(substack.id)])])

        response = self.ask("what is the unit price?", llm, substack_id=substack.id)
        body = response.json()

        self.assertEqual(201, response.status_code)
        self.assertTrue(body["answered"])
        self.assertTrue(body["checked"])
        self.assertEqual("scope_record", body["steps"][0]["tool"])
        self.assertEqual(str(substack.id), body["steps"][0]["record_id"])
        self.assertIn(f'record_id="{substack.id}"', llm.calls[0]["evidence"])
        self.assertIn("<scope record_id=", llm.calls[0]["evidence"])
        self.assertIn("HH-2231", llm.calls[0]["evidence"])
        self.assertEqual([version.document_id], source_document_ids(self.session, substack.id))

    def test_record_id_alias_scopes_the_same_way(self):
        substack, _ = self.record(
            "PO HH-2231",
            identity_key="HH-2231",
            confirmed_by=self.alice,
            segments=[{"kind": "field", "name": "qty", "value": "50"}],
        )
        llm = ScriptedLLM([answer_step("Quantity is 50.", [str(substack.id)])])

        body = self.ask("how many?", llm, record_id=substack.id).json()

        self.assertTrue(body["answered"])
        self.assertEqual("scope_record", body["steps"][0]["tool"])

    def test_hidden_owner_only_scope_is_not_found(self):
        substack, _ = self.record("Private PO", identity_key="PO-PRIVATE", owner=self.alice.id)
        self.current_user = self.bob
        llm = ScriptedLLM([answer_step("should not run", [])])

        response = self.ask("what is on this order?", llm, substack_id=substack.id)

        self.assertEqual(404, response.status_code)
        self.assertEqual("scope_not_found", response.json()["detail"])
        self.assertEqual([], llm.calls)
        self.assertIsNone(get_visible_record(self.session, self.organization.id, self.bob.id, substack.id))

    def test_feedback_stores_optional_reason(self):
        substack, _ = self.record(
            "PO HH-2231",
            identity_key="HH-2231",
            confirmed_by=self.alice,
            segments=[{"kind": "field", "name": "qty", "value": "50"}],
        )
        llm = ScriptedLLM([answer_step("Quantity is 50.", [str(substack.id)])])
        message = self.ask("how many?", llm, substack_id=substack.id).json()

        url = f"/accounts/{self.organization.id}/chat/messages/{message['id']}/feedback"
        body = self.client.post(url, json={"rating": "down", "reason": "Wrong answer"}).json()

        self.assertEqual("down", body["feedback"])
        self.assertEqual("Wrong answer", body["feedback_reason"])


if __name__ == "__main__":
    unittest.main()
