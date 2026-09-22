import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.entity_resolution import identity_for_candidate, resolve_candidate
from app.extractions import CandidateMention, ClientExtraction, EvidenceValue
from app.jobs import create_run, enqueue_job
from app.knowledge_analysis import generate_substack
from app.llm import LLMResult
from app.models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    KnowledgeJob,
    Organization,
    Substack,
    SubstackContent,
)
from app.retrieval import retrieve_chunks


class FakeLLM:
    def __init__(self, output):
        self.output = output

    def parse(self, **_kwargs):
        return LLMResult(parsed=self.output, request_id="fake-request", input_tokens=10, output_tokens=5)


class KnowledgePipelineTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.organization = Organization(name=f"Pipeline {uuid4()}", account_type="personal")
        self.session.add(self.organization)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def make_document(self, owner_user_id=None):
        document = Document(
            organization_id=self.organization.id,
            source="google_drive",
            external_id=str(uuid4()),
            title="Customer master",
            owner_user_id=owner_user_id,
        )
        self.session.add(document)
        self.session.flush()
        version = DocumentVersion(
            document_id=document.id,
            revision=1,
            content_hash="a" * 64,
            content="Acme Engineering UEN 201912345K",
        )
        self.session.add(version)
        self.session.flush()
        chunk = Chunk(
            document_version_id=version.id,
            position=0,
            text=version.content,
            embedding=[1.0] + [0.0] * 383,
            embedding_model="intfloat/multilingual-e5-small",
        )
        self.session.add(chunk)
        self.session.flush()
        return document, version, chunk

    def test_job_enqueue_is_idempotent(self):
        run = create_run(self.session, self.organization.id, None, "manual")
        first = enqueue_job(
            self.session,
            organization_id=self.organization.id,
            owner_user_id=None,
            kind="reconcile_scope",
            payload={},
            dedupe_key=f"test:{uuid4()}",
            analysis_run_id=run.id,
        )
        second = enqueue_job(
            self.session,
            organization_id=self.organization.id,
            owner_user_id=None,
            kind="reconcile_scope",
            payload={},
            dedupe_key=first.dedupe_key,
            analysis_run_id=run.id,
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(1, len(self.session.scalars(select(KnowledgeJob).where(KnowledgeJob.analysis_run_id == run.id)).all()))

    def test_identity_requires_stable_type_specific_identifiers(self):
        client = CandidateMention(entity_type="clients", name="Acme", identifiers={"registration_number": "2019-12345-K"})
        unnamed = CandidateMention(entity_type="clients", name="Acme")
        order = CandidateMention(entity_type="sales-orders", name="PO 42", identifiers={"order_number": "42"})
        self.assertEqual(("registration:201912345K", "registration_number"), identity_for_candidate(client))
        self.assertEqual((None, None), identity_for_candidate(unnamed))
        self.assertEqual((None, None), identity_for_candidate(order))

    def test_exact_identity_resolution_reuses_same_scope_substack(self):
        document, version, chunk = self.make_document()
        candidate = CandidateMention(
            entity_type="clients",
            name="Acme Engineering",
            identifiers={"registration_number": "201912345K"},
            citations=[str(chunk.id)],
        )
        _, first, created = resolve_candidate(
            self.session,
            document=document,
            version=version,
            candidate=candidate,
            prompt_key="discovery.core_entities.v1",
            prompt_version="v1",
            model="fake",
            analysis_run_id=None,
        )
        self.assertTrue(created)
        second_document, second_version, second_chunk = self.make_document()
        candidate.citations = [str(second_chunk.id)]
        _, second, created = resolve_candidate(
            self.session,
            document=second_document,
            version=second_version,
            candidate=candidate,
            prompt_key="discovery.core_entities.v1",
            prompt_version="v1",
            model="fake",
            analysis_run_id=None,
        )
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)

    def test_retrieval_is_organization_and_visibility_scoped(self):
        visible, _, visible_chunk = self.make_document()
        other_org = Organization(name=f"Other {uuid4()}", account_type="personal")
        self.session.add(other_org)
        self.session.flush()
        hidden = Document(organization_id=other_org.id, source="upload", external_id=str(uuid4()), title="Hidden")
        self.session.add(hidden)
        self.session.flush()
        hidden_version = DocumentVersion(document_id=hidden.id, revision=1, content_hash="b" * 64, content="hidden")
        self.session.add(hidden_version)
        self.session.flush()
        self.session.add(Chunk(document_version_id=hidden_version.id, position=0, text="hidden", embedding=[1.0] + [0.0] * 383, embedding_model="intfloat/multilingual-e5-small"))
        self.session.flush()
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383):
            result = retrieve_chunks(self.session, self.organization.id, None, "Acme")
        self.assertIn(visible_chunk.id, {item.chunk.id for item in result})
        self.assertTrue(all(item.document.organization_id == self.organization.id for item in result))
        self.assertEqual(visible.id, result[0].document.id)

    def test_generation_auto_confirms_new_stable_client_with_valid_citations(self):
        document, version, chunk = self.make_document()
        candidate = CandidateMention(
            entity_type="clients",
            name="Acme Engineering",
            identifiers={"registration_number": "201912345K"},
            citations=[str(chunk.id)],
        )
        _, substack, _ = resolve_candidate(
            self.session,
            document=document,
            version=version,
            candidate=candidate,
            prompt_key="discovery.core_entities.v1",
            prompt_version="v1",
            model="fake",
            analysis_run_id=None,
        )
        extraction = ClientExtraction(
            name=EvidenceValue(value="Acme Engineering", citations=[str(chunk.id)], confidence="high"),
            registration_number=EvidenceValue(value="201912345K", citations=[str(chunk.id)], confidence="high"),
        )
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383), patch(
            "app.knowledge_analysis.get_llm_client", return_value=FakeLLM(extraction)
        ):
            content = generate_substack(self.session, substack.id, None)
        self.assertEqual("confirmed", content.status)
        self.assertEqual("confirmed", substack.status)
        self.assertEqual("clean", substack.review_state)
        citations = self.session.scalars(select(ContentCitation).where(ContentCitation.content_id == content.id)).all()
        self.assertTrue(citations)

    def test_existing_confirmed_content_remains_live_when_update_is_generated(self):
        document, version, chunk = self.make_document()
        substack = Substack(
            organization_id=self.organization.id,
            stack_type="clients",
            name="Acme",
            status="confirmed",
            identity_key="registration:201912345K",
            identity_kind="registration_number",
        )
        self.session.add(substack)
        self.session.flush()
        self.session.add(SubstackContent(
            substack_id=substack.id,
            revision=1,
            prompt_key="clients.extract.v1",
            prompt_version="v1",
            model="fake",
            content={"segments": [], "entries": []},
            status="confirmed",
            inputs_fingerprint="c" * 64,
        ))
        self.session.flush()
        extraction = ClientExtraction(
            name=EvidenceValue(value="Acme Engineering", citations=[str(chunk.id)]),
            registration_number=EvidenceValue(value="201912345K", citations=[str(chunk.id)]),
        )
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383), patch(
            "app.knowledge_analysis.get_llm_client", return_value=FakeLLM(extraction)
        ):
            content = generate_substack(self.session, substack.id, None)
        self.assertEqual("proposed", content.status)
        self.assertEqual("confirmed", self.session.scalar(select(SubstackContent).where(SubstackContent.substack_id == substack.id, SubstackContent.revision == 1)).status)
        self.assertEqual("pending_update", substack.review_state)


if __name__ == "__main__":
    unittest.main()
