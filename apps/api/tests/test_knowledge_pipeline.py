import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.entity_resolution import identity_for_candidate, resolve_candidate
from app.extractions import (
    CandidateMention,
    ClientExtraction,
    ConversationExtraction,
    ConversationTopic,
    EvidenceValue,
)
from app.embedding_jobs import embed_document_version
from app.jobs import JobNotReady, create_run, enqueue_job
from app.knowledge_analysis import generate_substack, regenerate_records
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
    SubstackSource,
)
from app.retrieval import retrieve_chunks


class FakeLLM:
    def __init__(self, output):
        self.output = output

    def parse(self, **_kwargs):
        return LLMResult(parsed=self.output, request_id="fake-request", input_tokens=10, output_tokens=5)


class RecordingLLM(FakeLLM):
    def __init__(self, output):
        super().__init__(output)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return super().parse(**kwargs)


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
        jobs = self.session.scalars(select(KnowledgeJob).where(KnowledgeJob.analysis_run_id == run.id)).all()
        self.assertEqual(1, len(jobs))

    def test_ingest_run_embeds_without_discovery(self):
        document, version, chunk = self.make_document()
        chunk.embedding = None
        chunk.embedding_model = None
        self.session.flush()
        run = create_run(self.session, self.organization.id, None, "ingest", documents_total=1)
        with patch("app.embedding_jobs.embed_passages", return_value=[[1.0] + [0.0] * 383]):
            embed_document_version(self.session, version.id, run.id)
        kinds = self.session.scalars(select(KnowledgeJob.kind).where(KnowledgeJob.analysis_run_id == run.id)).all()
        self.assertEqual([], kinds)
        self.assertEqual("completed", run.status)

    def test_regenerate_records_waits_for_discovery_then_forces_generation(self):
        _, version, _ = self.make_document()
        wanted = Substack(organization_id=self.organization.id, stack_type="clients", name="Acme")
        other = Substack(organization_id=self.organization.id, stack_type="items", name="Bracket")
        self.session.add_all([wanted, other])
        self.session.flush()
        run = create_run(self.session, self.organization.id, None, "manual", documents_total=1)
        discover = enqueue_job(
            self.session, organization_id=self.organization.id, owner_user_id=None, kind="discover_document",
            payload={"document_version_id": str(version.id)}, dedupe_key=f"test:{uuid4()}", analysis_run_id=run.id,
        )
        barrier = enqueue_job(
            self.session, organization_id=self.organization.id, owner_user_id=None, kind="reconcile_scope",
            payload={"mode": "selected", "substack_ids": [str(wanted.id)]}, dedupe_key=f"test:{uuid4()}",
            analysis_run_id=run.id,
        )
        with self.assertRaises(JobNotReady):
            regenerate_records(self.session, barrier)
        discover.status = "succeeded"
        self.session.flush()
        self.assertEqual(1, regenerate_records(self.session, barrier))
        generated = self.session.scalars(select(KnowledgeJob).where(
            KnowledgeJob.analysis_run_id == run.id, KnowledgeJob.kind == "generate_substack",
        )).all()
        self.assertEqual([{"substack_id": str(wanted.id), "force": True}], [job.payload for job in generated])

    def test_conversation_summary_replaces_message_list_with_topics(self):
        document, version, chunk = self.make_document()
        document.source = "whatsapp"
        substack = Substack(organization_id=self.organization.id, stack_type="conversations", name="Meridian")
        self.session.add(substack)
        self.session.flush()
        self.session.add(SubstackSource(substack_id=substack.id, document_id=document.id))
        template = SubstackContent(
            substack_id=substack.id, revision=1, prompt_key="conversations.transcript.v0", prompt_version="v0",
            model="template", content={"segments": [], "entries": [{"message": "hi"}]}, status="confirmed",
            inputs_fingerprint="e" * 64,
        )
        self.session.add(template)
        self.session.flush()
        extraction = ConversationExtraction(topics=[
            ConversationTopic(
                title="Line 2 quantity raised to 60",
                kind="decision",
                summary=EvidenceValue(
                    value="Meridian raised line 2 of MER-PO-4123 to 60 pcs.", citations=[str(chunk.id)],
                ),
                date="2026-03-12",
            ),
            ConversationTopic(title="  ", summary=EvidenceValue(value="dropped", citations=[str(chunk.id)])),
        ])
        with patch("app.knowledge_analysis.get_llm_client", return_value=FakeLLM(extraction)):
            content = generate_substack(self.session, substack.id, None)
        self.assertEqual("conversations.summarize.v1", content.prompt_key)
        self.assertEqual("proposed", content.status)
        self.assertEqual("superseded", template.status)
        self.assertEqual("proposed", substack.status)
        segments = content.content["segments"]
        self.assertEqual(1, len(segments))
        self.assertEqual(("text", "Line 2 quantity raised to 60"), (segments[0]["kind"], segments[0]["name"]))
        self.assertEqual({"kind": "decision", "date": "2026-03-12"}, segments[0]["locator"])
        self.assertEqual([], content.content["entries"])

    def test_identity_requires_stable_type_specific_identifiers(self):
        client = CandidateMention(
            entity_type="clients", name="Acme", identifiers={"registration_number": "2019-12345-K"}
        )
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
        self.session.add(Chunk(
            document_version_id=hidden_version.id,
            position=0,
            text="hidden",
            embedding=[1.0] + [0.0] * 383,
            embedding_model="intfloat/multilingual-e5-small",
        ))
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
            report=[
                EvidenceValue(
                    value="Acme Engineering is identified by UEN 201912345K.",
                    citations=[str(chunk.id)],
                    confidence="high",
                ),
                EvidenceValue(
                    value="The available evidence does not state commercial terms.",
                    citations=[str(chunk.id)],
                    confidence="high",
                ),
            ],
            name=EvidenceValue(value="Acme Engineering", citations=[str(chunk.id)], confidence="high"),
            registration_number=EvidenceValue(value="201912345K", citations=[str(chunk.id)], confidence="high"),
        )
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383), patch(
            "app.knowledge_analysis.get_llm_client", return_value=FakeLLM(extraction)
        ):
            content = generate_substack(self.session, substack.id, None)
        self.assertEqual("confirmed", content.status)
        self.assertEqual("clients.extract.v3", content.prompt_key)
        self.assertEqual("v3", content.prompt_version)
        self.assertEqual("confirmed", substack.status)
        self.assertEqual("clean", substack.review_state)
        self.assertEqual(["text", "text"], [segment["kind"] for segment in content.content["segments"]])
        self.assertIn("Acme Engineering is identified", content.content["segments"][0]["value"])
        citations = self.session.scalars(select(ContentCitation).where(ContentCitation.content_id == content.id)).all()
        self.assertTrue(citations)

    def test_described_record_uses_description_and_named_file_as_evidence(self):
        named, _, named_chunk = self.make_document()
        named.title = "Acme PO 4471.pdf"
        named_chunk.embedding = [0.0, 1.0] + [0.0] * 382
        other, _, other_chunk = self.make_document()
        other.title = "PO"
        self.session.flush()
        substack = Substack(
            organization_id=self.organization.id,
            stack_type="clients",
            name="Acme",
            summary="The client on acme po 4471, 500 brackets",
            created_by="user",
            status="proposed",
            review_state="pending",
        )
        self.session.add(substack)
        self.session.flush()
        extraction = ClientExtraction(
            report=[
                EvidenceValue(value="Acme Engineering is identified by UEN 201912345K.", citations=[str(named_chunk.id)]),
                EvidenceValue(value="No commercial terms are stated.", citations=[str(named_chunk.id)]),
            ],
            name=EvidenceValue(value="Acme Engineering", citations=[str(named_chunk.id)]),
        )
        llm = RecordingLLM(extraction)
        settings = get_settings().model_copy(update={"retrieval_max_chunks": 1})
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383), patch(
            "app.knowledge_analysis.get_llm_client", return_value=llm
        ), patch("app.knowledge_analysis.get_settings", return_value=settings), patch(
            "app.retrieval.get_settings", return_value=settings
        ):
            content = generate_substack(self.session, substack.id, None, force=True)
        self.assertEqual("proposed", content.status)
        evidence = llm.calls[0]["evidence"]
        self.assertTrue(evidence.startswith("<user_request>\nThe client on acme po 4471"))
        # The named file survives the retrieval cap even though it ranks below the other document.
        self.assertIn(str(named_chunk.id), evidence)
        self.assertNotIn(str(other_chunk.id), evidence)
        self.assertIn("<user_request>", llm.calls[0]["prompt"])
        sources = self.session.scalars(select(SubstackSource.document_id).where(SubstackSource.substack_id == substack.id)).all()
        self.assertEqual([named.id], list(sources))

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
            report=[
                EvidenceValue(value="Acme Engineering is identified by UEN 201912345K.", citations=[str(chunk.id)]),
                EvidenceValue(
                    value="The customer record is supported by the current master document.",
                    citations=[str(chunk.id)],
                ),
            ],
            name=EvidenceValue(value="Acme Engineering", citations=[str(chunk.id)]),
            registration_number=EvidenceValue(value="201912345K", citations=[str(chunk.id)]),
        )
        with patch("app.retrieval.embed_query", return_value=[1.0] + [0.0] * 383), patch(
            "app.knowledge_analysis.get_llm_client", return_value=FakeLLM(extraction)
        ):
            content = generate_substack(self.session, substack.id, None)
        self.assertEqual("proposed", content.status)
        original = self.session.scalar(
            select(SubstackContent).where(SubstackContent.substack_id == substack.id, SubstackContent.revision == 1)
        )
        self.assertEqual("confirmed", original.status)
        self.assertEqual("pending_update", substack.review_state)


if __name__ == "__main__":
    unittest.main()
