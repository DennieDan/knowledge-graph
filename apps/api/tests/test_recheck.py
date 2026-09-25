"""Nightly re-check: invented source drift only."""
from hashlib import sha256
import unittest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    Finding,
    KnowledgeJob,
    Organization,
    Schedule,
    Substack,
    SubstackContent,
    User,
)
from app.recheck import recheck_mismatch, run_recheck, source_drift
from app.scheduler import ensure_default_schedules, tick


def _hash(text: str) -> str:
    return sha256(text.encode()).hexdigest()


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name=f"Recheck-{uuid4().hex[:6]}")
        self.session.add(self.org)
        self.session.flush()
        self.user = User(email=f"recheck-{uuid4().hex[:8]}@example.com")
        self.session.add(self.user)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _doc(self, title: str, revisions: list[str], *, source: str = "upload") -> Document:
        doc = Document(
            organization_id=self.org.id,
            title=title,
            source=source,
            external_id=str(uuid4()),
        )
        self.session.add(doc)
        self.session.flush()
        for index, text in enumerate(revisions, start=1):
            version = DocumentVersion(
                document_id=doc.id,
                revision=index,
                content=text,
                content_hash=_hash(text),
            )
            self.session.add(version)
            self.session.flush()
            self.session.add(Chunk(document_version_id=version.id, position=0, text=text))
        self.session.flush()
        return doc

    def _confirmed_citing(self, doc: Document, revision: int, *, segments: list[dict]) -> Substack:
        version = self.session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.revision == revision,
            )
        ).one()
        chunk = self.session.scalars(
            select(Chunk).where(Chunk.document_version_id == version.id)
        ).one()
        substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="PO-SN-1001",
            status="confirmed",
        )
        self.session.add(substack)
        self.session.flush()
        content = SubstackContent(
            substack_id=substack.id,
            revision=1,
            prompt_key="sales_orders",
            prompt_version="v1",
            model="test",
            content={"segments": segments},
            status="confirmed",
            inputs_fingerprint=_hash("confirmed"),
        )
        self.session.add(content)
        self.session.flush()
        self.session.add(
            ContentCitation(
                content_id=content.id,
                segment_index=0,
                chunk_id=chunk.id,
                document_id=doc.id,
            )
        )
        self.session.flush()
        return substack

    def test_source_drift_when_latest_hash_differs(self):
        doc = self._doc(
            "SN-1001 drawing",
            ["Rev B qty 40 material SS316", "Rev C qty 40 material Ti-6Al-4V"],
            source="google_drive",
        )
        self._confirmed_citing(
            doc,
            revision=1,
            segments=[{"kind": "field", "name": "revision", "value": "Rev B"}],
        )
        drafts = source_drift(self.session, self.org.id)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].check_key, "source_drift")
        self.assertIn("Drawing changed after confirmation", drafts[0].summary_sentence)

    def test_no_drift_when_hash_unchanged(self):
        doc = self._doc("Stable PO", ["qty 12 due 2026-10-01"])
        self._confirmed_citing(
            doc,
            revision=1,
            segments=[{"kind": "field", "name": "quantity", "value": "12"}],
        )
        self.assertEqual(source_drift(self.session, self.org.id), [])
        self.assertEqual(recheck_mismatch(self.session, self.org.id), [])

    def test_recheck_mismatch_when_confirmed_value_gone(self):
        doc = self._doc(
            "WA change note",
            [
                "Confirm qty 40 for bracket SN-1001 Rev B",
                "Updated: qty 55 for bracket SN-1001 Rev C — ignore prior qty",
            ],
            source="whatsapp",
        )
        self._confirmed_citing(
            doc,
            revision=1,
            segments=[
                {"kind": "field", "name": "quantity", "value": "qty 40"},
                {"kind": "text", "value": "ignore me"},
            ],
        )
        drafts = recheck_mismatch(self.session, self.org.id)
        self.assertTrue(any(d.check_key == "recheck_mismatch" for d in drafts))
        mismatch = next(d for d in drafts if d.check_key == "recheck_mismatch")
        self.assertEqual(mismatch.threshold_value, "quantity")
        self.assertIn("qty 40", mismatch.observed_value or "")

    def test_run_recheck_opens_findings_idempotently(self):
        doc = self._doc(
            "Drawing DWG-9",
            ["material AL6061 rev1", "material SS304 rev2 — supersedes AL6061"],
        )
        self._confirmed_citing(
            doc,
            revision=1,
            segments=[{"kind": "field", "name": "material", "value": "AL6061"}],
        )
        first = run_recheck(self.session, self.org.id)
        self.assertGreaterEqual(len(first), 1)
        keys = {f.check_key for f in first}
        self.assertTrue(keys & {"source_drift", "recheck_mismatch"})
        open_before = self.session.scalars(
            select(Finding).where(
                Finding.organization_id == self.org.id,
                Finding.decision.is_(None),
            )
        ).all()
        second = run_recheck(self.session, self.org.id)
        # Same open fingerprints must not duplicate open findings.
        self.assertEqual(len(second), len(open_before))
        open_after = self.session.scalars(
            select(Finding).where(
                Finding.organization_id == self.org.id,
                Finding.decision.is_(None),
            )
        ).all()
        self.assertEqual(len(open_after), len(open_before))

    def test_scheduler_enqueues_run_recheck(self):
        ensure_default_schedules(self.session, self.org.id)
        for schedule in self.session.scalars(select(Schedule)).all():
            schedule.next_run_at = None
        self.session.flush()
        result = tick(self.session)
        self.assertGreaterEqual(result["jobs_enqueued"], 3)
        kinds = {
            job.kind
            for job in self.session.scalars(
                select(KnowledgeJob).where(KnowledgeJob.organization_id == self.org.id)
            )
        }
        self.assertIn("run_recheck", kinds)
        self.assertIn("run_checks", kinds)


if __name__ == "__main__":
    unittest.main()
