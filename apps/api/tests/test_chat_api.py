"""Chat API: the agent loop, citation validation, thread privacy, feedback."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.chat import NO_ANSWER_TEXT
from app.chat_agent import AgentStep, Answer, AnswerSentence, StandaloneQuestion
from app.config import get_settings
from app.database import get_engine, get_session
from app.embedding_jobs import embed_document_version
from app.filing import ingest_and_file
from app.ingest import SourceDocument
from app.llm import LLMResult
from app.main import app
from app.models import Chunk, ChatMessage, Organization, OrganizationMembership, User


class ScriptedLLM:
    """Replays a fixed list of parsed outputs and records what it was asked."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, *, prompt, evidence, schema):
        self.calls.append({"prompt": prompt, "evidence": evidence, "schema": schema})
        output = self.outputs.pop(0) if self.outputs else Answer(answered=False, sentences=[])
        return LLMResult(parsed=output, request_id="fake-request", input_tokens=10, output_tokens=5)


def search_step(query):
    return AgentStep(tool="search_sources", query=query)


def answer_step(text, citations):
    return AgentStep(tool="answer", answer=Answer(
        answered=True,
        sentences=[AnswerSentence(text=text, citations=citations)],
    ))


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")

        self.alice = User(email=f"alice-{uuid4()}@acme.example")
        self.bob = User(email=f"bob-{uuid4()}@acme.example")
        self.session.add_all([self.alice, self.bob])
        self.session.flush()
        self.organization = Organization(name="Chat test", account_type="personal")
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

    def ingest(self, title, content, organization_id=None, owner=None):
        version = ingest_and_file(
            self.session,
            organization_id or self.organization.id,
            SourceDocument(
                source="google_drive",
                external_id=f"ext-{uuid4()}",
                title=title,
                content=content,
                owner_user_id=owner,
            ),
        )
        # The worker embeds asynchronously; the agent only sees embedded chunks.
        embed_document_version(self.session, version.id, None)
        return version

    def chunk_id(self, version):
        return str(self.session.scalars(
            select(Chunk.id).where(Chunk.document_version_id == version.id).order_by(Chunk.position)
        ).first())

    def thread(self, user=None, organization_id=None):
        self.current_user = user or self.alice
        return self.client.post(
            f"/accounts/{organization_id or self.organization.id}/chat/threads",
            json={},
        )

    def ask(self, thread_id, text, llm, user=None, organization_id=None):
        self.current_user = user or self.alice
        with patch("app.chat_agent.get_llm_client", return_value=llm):
            return self.client.post(
                f"/accounts/{organization_id or self.organization.id}/chat/threads/{thread_id}/messages",
                json={"text": text},
            )

    def test_searches_then_answers_with_citations(self):
        version = self.ingest("PO2431.pdf", "Purchase order 2431: 120 stainless steel brackets, due 14 March.")
        chunk_id = self.chunk_id(version)
        llm = ScriptedLLM([
            search_step("purchase order 2431 brackets quantity"),
            answer_step("PO2431 orders 120 stainless steel brackets.", [chunk_id]),
        ])
        thread_id = self.thread().json()["id"]

        body = self.ask(thread_id, "how many brackets are on PO2431?", llm).json()

        self.assertTrue(body["answered"])
        self.assertIn("120", body["text"])
        self.assertEqual([chunk_id], [citation["chunk_id"] for citation in body["citations"]])
        self.assertEqual("PO2431.pdf", body["citations"][0]["title"])
        self.assertEqual(["search_sources", "answer"], [step["tool"] for step in body["steps"]])
        # The evidence the model saw is data, not instructions.
        self.assertIn("<evidence", llm.calls[1]["evidence"])

    def test_refuses_to_answer_without_evidence(self):
        self.ingest("Menu.txt", "Lunch menu for the staff canteen.")
        invented = str(uuid4())
        llm = ScriptedLLM([
            search_step("brackets"),
            answer_step("PO2431 orders 120 brackets.", [invented]),
        ])
        thread_id = self.thread().json()["id"]

        body = self.ask(thread_id, "how many brackets are on PO2431?", llm).json()

        self.assertFalse(body["answered"])
        self.assertEqual(NO_ANSWER_TEXT, body["text"])
        self.assertEqual([], body["citations"])

    def test_rewrites_a_follow_up_before_retrieving(self):
        version = self.ingest("PO2431.pdf", "Purchase order 2431: 120 brackets, due 14 March.")
        chunk_id = self.chunk_id(version)
        thread_id = self.thread().json()["id"]
        self.ask(thread_id, "how many brackets are on PO2431?", ScriptedLLM([
            search_step("PO2431 brackets"),
            answer_step("PO2431 orders 120 brackets.", [chunk_id]),
        ]))

        follow_up = ScriptedLLM([
            StandaloneQuestion(question="When is PO2431 due?"),
            search_step("PO2431 due date"),
            answer_step("PO2431 is due 14 March.", [chunk_id]),
        ])
        body = self.ask(thread_id, "and when is it due?", follow_up).json()

        self.assertIn("14 March", body["text"])
        self.assertIn("<conversation>", follow_up.calls[0]["evidence"])
        stored = self.session.scalars(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id, ChatMessage.role == "user")
        ).all()
        self.assertEqual("When is PO2431 due?", stored[-1].resolved_question)

    def test_cannot_reach_another_organizations_sources(self):
        self.ingest("Rival PO.pdf", "Purchase order 9999: 40 brackets.", organization_id=self.other_organization.id)
        llm = ScriptedLLM([search_step("brackets"), answer_step("40 brackets.", [])])
        thread_id = self.thread().json()["id"]

        body = self.ask(thread_id, "how many brackets?", llm).json()

        self.assertFalse(body["answered"])
        self.assertEqual(0, llm.calls[1]["evidence"].count("<evidence chunk_id"))

    def test_refuses_an_organization_the_asker_is_not_in(self):
        self.assertEqual(404, self.thread(organization_id=self.other_organization.id).status_code)

    def test_keeps_threads_private_to_their_owner(self):
        thread_id = self.thread().json()["id"]

        self.current_user = self.bob
        response = self.client.get(f"/accounts/{self.organization.id}/chat/threads/{thread_id}")

        self.assertEqual(404, response.status_code)
        self.assertEqual([], self.client.get(f"/accounts/{self.organization.id}/chat/threads").json()["threads"])

    def test_refetch_keeps_question_before_answer_on_timestamp_ties(self):
        thread_id = self.thread().json()["id"]
        at = datetime.now(timezone.utc)
        # A turn commits both rows together, so their created_at ties; the
        # assistant row here sorts first on id, like a random-UUID tie-break.
        question = ChatMessage(
            id=UUID("ffffffff-ffff-4fff-bfff-ffffffffffff"),
            thread_id=UUID(thread_id),
            role="user",
            text="when is PO2431 due?",
            created_at=at,
        )
        answer = ChatMessage(
            id=UUID("00000000-0000-4000-8000-000000000000"),
            thread_id=UUID(thread_id),
            role="assistant",
            text="PO2431 is due 14 March.",
            answered=True,
            created_at=at,
        )
        self.session.add_all([answer, question])
        self.session.flush()

        messages = self.client.get(
            f"/accounts/{self.organization.id}/chat/threads/{thread_id}"
        ).json()["messages"]

        self.assertEqual(["user", "assistant"], [message["role"] for message in messages])

    def test_records_feedback_on_an_answer(self):
        version = self.ingest("PO2431.pdf", "Purchase order 2431: 120 brackets.")
        chunk_id = self.chunk_id(version)
        thread_id = self.thread().json()["id"]
        message = self.ask(thread_id, "how many brackets?", ScriptedLLM([
            search_step("brackets"),
            answer_step("120 brackets.", [chunk_id]),
        ])).json()

        url = f"/accounts/{self.organization.id}/chat/messages/{message['id']}/feedback"
        self.assertEqual("down", self.client.post(url, json={"rating": "down"}).json()["feedback"])
        self.assertEqual(422, self.client.post(url, json={"rating": "sideways"}).status_code)

    def test_stops_searching_at_the_step_limit(self):
        self.ingest("PO2431.pdf", "Purchase order 2431: 120 brackets.")
        steps = get_settings().chat_max_steps
        llm = ScriptedLLM([search_step(f"query {index}") for index in range(steps)])
        thread_id = self.thread().json()["id"]

        body = self.ask(thread_id, "how many brackets?", llm).json()

        # One call per step, plus the forced final answer.
        self.assertEqual(steps + 1, len(llm.calls))
        self.assertTrue(body["steps"][-1]["forced"])
        self.assertFalse(body["answered"])


if __name__ == "__main__":
    unittest.main()
