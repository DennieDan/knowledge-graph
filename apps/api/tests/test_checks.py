"""Checks + findings: invented corpus only."""
from hashlib import sha256
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks import (
    entity_mentioned_often_but_has_no_record,
    record_not_updated_since_threshold,
    run_all_checks,
    source_changed,
    sources_disagree,
)
from app.database import get_engine
from app.findings import DAILY_OPEN_CAP, create_finding, dismiss_finding, open_count_today
from app.models import (
    Chunk,
    ContentCitation,
    Document,
    DocumentVersion,
    EntityMention,
    Finding,
    Organization,
    Substack,
    SubstackContent,
    User,
)


def _hash(text: str) -> str:
    return sha256(text.encode()).hexdigest()


class ChecksTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name="Checks corp")
        self.session.add(self.org)
        self.session.flush()
        self.user = User(email=f"checks-{uuid4().hex[:8]}@example.com")
        self.session.add(self.user)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def _doc(self, title: str, revisions: list[str]) -> Document:
        doc = Document(organization_id=self.org.id, title=title, source="upload", external_id=str(uuid4()))
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

    def test_source_changed_on_superseded_citation(self):
        doc = self._doc("PO-1", ["rev1 qty 40", "rev2 qty 60"])
        versions = self.session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.revision)
        ).all()
        old_chunk = self.session.scalars(
            select(Chunk).where(Chunk.document_version_id == versions[0].id)
        ).one()
        substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="PO-1",
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
            content={"lines": []},
            status="confirmed",
            inputs_fingerprint=_hash("x"),
        )
        self.session.add(content)
        self.session.flush()
        self.session.add(
            ContentCitation(
                content_id=content.id,
                segment_index=0,
                chunk_id=old_chunk.id,
                document_id=doc.id,
            )
        )
        self.session.flush()
        drafts = source_changed(self.session, self.org.id)
        self.assertTrue(any(d.check_key == "source_changed" for d in drafts))

    def test_record_not_updated_threshold(self):
        substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="Stale Order",
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
            content={},
            status="confirmed",
            inputs_fingerprint=_hash("stale"),
        )
        self.session.add(content)
        self.session.flush()
        content.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        self.session.flush()
        drafts = record_not_updated_since_threshold(self.session, self.org.id)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].threshold_value, "14")

    def test_entity_mentioned_often(self):
        docs = [self._doc(f"Doc {i}", [f"mentions Acme {i}"]) for i in range(3)]
        for doc in docs:
            version = self.session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
            ).one()
            self.session.add(
                EntityMention(
                    organization_id=self.org.id,
                    document_id=doc.id,
                    document_version_id=version.id,
                    entity_type="clients",
                    candidate_key=_hash(f"acme-{doc.id}")[:64],
                    data={"name": "Acme Trading"},
                    cited_chunk_ids=[],
                    prompt_key="discovery",
                    prompt_version="v1",
                    model="test",
                )
            )
        self.session.flush()
        drafts = entity_mentioned_often_but_has_no_record(self.session, self.org.id)
        self.assertTrue(any("Acme Trading" in d.summary_sentence for d in drafts))

    def test_sources_disagree_from_stored_conflicts(self):
        substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="Conflicted PO",
            status="proposed",
        )
        self.session.add(substack)
        self.session.flush()
        self.session.add(
            SubstackContent(
                substack_id=substack.id,
                revision=1,
                prompt_key="sales_orders",
                prompt_version="v1",
                model="test",
                content={
                    "conflicts": [
                        {"values": [40, 60], "explanation": "two quotes", "citations": ["chunk-a", "chunk-b"]}
                    ]
                },
                status="proposed",
                inputs_fingerprint=_hash("c"),
            )
        )
        self.session.flush()
        drafts = sources_disagree(self.session, self.org.id)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].check_key, "sources_disagree")

    def test_dedupe_and_daily_cap(self):
        subject = uuid4()
        first = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=subject,
            summary_sentence="first",
            fingerprint="same",
        )
        second = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=subject,
            summary_sentence="first",
            fingerprint="same",
        )
        self.assertEqual(first.id, second.id)
        for i in range(DAILY_OPEN_CAP + 5):
            create_finding(
                self.session,
                organization_id=self.org.id,
                check_key="record_not_updated_since_threshold",
                subject_kind="substack",
                subject_id=uuid4(),
                summary_sentence=f"noise {i}",
                fingerprint=f"noise-{i}",
            )
        self.assertEqual(open_count_today(self.session, self.org.id), DAILY_OPEN_CAP)

    def test_dismiss_records_who(self):
        finding = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="dismiss me",
            fingerprint="dismiss",
        )
        dismiss_finding(self.session, finding, user_id=self.user.id, reason="not_a_change")
        self.session.flush()
        loaded = self.session.get(Finding, finding.id)
        self.assertEqual(loaded.decision, "dismissed")
        self.assertEqual(loaded.decided_by_user_id, self.user.id)
        self.assertEqual(loaded.dismissal_reason, "not_a_change")

    def test_referenced_entity_missing(self):
        substack = Substack(
            organization_id=self.org.id,
            stack_type="sales-orders",
            name="PO with ghost ref",
            status="proposed",
        )
        self.session.add(substack)
        self.session.flush()
        self.session.add(
            SubstackContent(
                substack_id=substack.id,
                revision=1,
                prompt_key="sales_orders",
                prompt_version="v1",
                model="test",
                content={
                    "extraction": {
                        "references": [
                            {"entity_type": "clients", "name": "Ghost Client Ltd", "identifier": None}
                        ]
                    }
                },
                status="proposed",
                inputs_fingerprint=_hash("ref"),
            )
        )
        self.session.flush()
        from app.checks import referenced_record_not_found
        drafts = referenced_record_not_found(self.session, self.org.id)
        self.assertTrue(any("Ghost Client Ltd" in d.summary_sentence for d in drafts))

    def test_owner_only_finding_visibility_filter(self):
        private = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="private",
            owner_user_id=self.user.id,
            fingerprint="private-vis",
        )
        shared = create_finding(
            self.session,
            organization_id=self.org.id,
            check_key="source_changed",
            subject_kind="substack",
            subject_id=uuid4(),
            summary_sentence="shared",
            owner_user_id=None,
            fingerprint="shared-vis",
        )
        self.session.flush()
        from sqlalchemy import or_, select
        visible = self.session.scalars(
            select(Finding).where(
                Finding.organization_id == self.org.id,
                Finding.decision.is_(None),
                or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == self.user.id),
            )
        ).all()
        ids = {f.id for f in visible}
        self.assertIn(private.id, ids)
        self.assertIn(shared.id, ids)
        other = User(email=f"other-{uuid4().hex[:8]}@example.com")
        self.session.add(other)
        self.session.flush()
        visible_other = self.session.scalars(
            select(Finding).where(
                Finding.organization_id == self.org.id,
                Finding.decision.is_(None),
                or_(Finding.owner_user_id.is_(None), Finding.owner_user_id == other.id),
            )
        ).all()
        other_ids = {f.id for f in visible_other}
        self.assertNotIn(private.id, other_ids)
        self.assertIn(shared.id, other_ids)

    def test_run_all_checks_commits(self):
        self._doc("empty", ["nothing"])
        created = run_all_checks(self.session, self.org.id)
        self.assertIsInstance(created, list)


if __name__ == "__main__":
    unittest.main()
