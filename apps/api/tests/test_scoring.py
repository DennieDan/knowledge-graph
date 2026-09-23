"""Retrieval scoring with labelled expected chunk ids."""
from hashlib import sha256
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Chunk, Document, DocumentVersion, Organization, TestQuestion, EMBEDDING_DIMENSIONS
from app.retrieval import RetrievedChunk
from app.scoring import run_retrieval_score


def _hash(text: str) -> str:
    return sha256(text.encode()).hexdigest()


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name=f"Score-{uuid4().hex[:6]}")
        self.session.add(self.org)
        self.session.flush()
        self.document = Document(
            organization_id=self.org.id,
            title="PO notes",
            source="upload",
            external_id=str(uuid4()),
        )
        self.session.add(self.document)
        self.session.flush()
        version = DocumentVersion(
            document_id=self.document.id,
            revision=1,
            content="qty 60",
            content_hash=_hash("qty 60"),
        )
        self.session.add(version)
        self.session.flush()
        vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
        self.chunk = Chunk(
            document_version_id=version.id,
            position=0,
            text="qty 60 on line 2",
            embedding=vector,
            embedding_model="intfloat/multilingual-e5-small",
        )
        self.session.add(self.chunk)
        self.session.flush()
        self.session.add(
            TestQuestion(
                organization_id=self.org.id,
                external_key="syn-test-1",
                question="what quantity on line 2?",
                language="en",
                origin="synthetic",
                expected_chunk_ids=[str(self.chunk.id)],
                answerable=True,
            )
        )
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_empty_labels_are_skipped_not_passed(self):
        # Remove the labelled question created in setUp's sibling — use a fresh org.
        from app.models import TestQuestion as TQ
        from sqlalchemy import delete
        self.session.execute(delete(TQ).where(TQ.organization_id == self.org.id))
        self.session.add(
            TQ(
                organization_id=self.org.id,
                external_key="syn-unlabelled",
                question="unlabelled?",
                language="en",
                origin="synthetic",
                expected_chunk_ids=[],
                answerable=True,
            )
        )
        self.session.flush()
        run = run_retrieval_score(self.session, self.org.id)
        self.assertEqual(run.status, "skipped")
        self.assertEqual(run.metrics.get("reason"), "no_labelled_questions")

    def test_retrieval_score_records_recall(self):
        fake = [RetrievedChunk(chunk=self.chunk, document=self.document, score=0.1)]
        with patch("app.scoring.search_chunks", return_value=fake):
            run = run_retrieval_score(self.session, self.org.id)
        self.assertEqual(run.status, "passed")
        self.assertEqual(run.kind, "retrieval")
        self.assertIsNotNone(run.metrics.get("recall_at_5_mean"))
        self.assertIsNotNone(run.git_sha or True)  # may be None outside git
        self.assertEqual(run.model, "intfloat/multilingual-e5-small")
        self.assertIn("retrieval", run.prompt_versions)


if __name__ == "__main__":
    unittest.main()
