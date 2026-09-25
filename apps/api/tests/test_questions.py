"""The question set (#34): fixture invariants and an idempotent load into test_questions."""
import unittest
from collections import Counter
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Organization, TestQuestion
from scripts.load_questions import load_fixture, upsert_rows, validate_fixture


class QuestionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.data = validate_fixture(load_fixture())
        self.synthetic = self.data["synthetic"]
        self.shapes = self.data["from_interview_shapes"]

    def test_fifty_synthetic_with_the_required_mix(self):
        self.assertEqual(len(self.synthetic), 50)
        self.assertEqual(Counter(q["origin"] for q in self.synthetic), {"synthetic": 50})
        shapes = Counter(q["shape"] for q in self.synthetic)
        self.assertEqual(set(shapes), {"single_value", "change_over_time", "status_list", "relation", "not_in_sources"})
        self.assertTrue(all(count >= 8 for count in shapes.values()), shapes)
        self.assertEqual(sum(1 for q in self.synthetic if q["answerable"] is False), 10)
        self.assertGreaterEqual(sum(1 for q in self.synthetic if q["language"] in ("ms", "zh")), 5)
        self.assertTrue(all(q["language"] in ("en", "ms", "zh") for q in self.synthetic))

    def test_invented_interview_shapes_never_pose_as_real_interviews(self):
        # Transcripts were not available. The shapes are invented, so they must not
        # carry origin=from_interview or #19 would report a fictional "real" group.
        self.assertEqual(Counter(q["origin"] for q in self.shapes), {"invented_shape": len(self.shapes)})
        self.assertTrue(all(q["answerable"] is None for q in self.shapes))
        self.assertTrue(all(not q["expected_chunk_ids"] and not q["expected_substack_ids"] for q in self.shapes))

    def test_expected_answers_are_ids_not_free_text(self):
        for q in self.synthetic:
            self.assertIsInstance(q["expected_chunk_ids"], list)
            self.assertIsInstance(q["expected_substack_ids"], list)

    def test_dual_label_fields_present(self):
        for q in self.synthetic:
            self.assertIn("label_a", q)
            self.assertIn("label_b", q)
            self.assertIn("agreed", q)
            self.assertEqual(q["label_a"]["status"], "outstanding")
            self.assertEqual(q["label_b"]["status"], "outstanding")
        self.assertEqual(sum(1 for q in self.synthetic if q["held_out"]), 10)


class QuestionLoadTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name=f"Questions-{uuid4().hex[:6]}")
        self.session.add(self.org)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_load_is_idempotent_and_keeps_groups_apart(self):
        synthetic, interview = upsert_rows(self.session, self.org.id, replace=False)
        self.assertEqual((synthetic, interview), (50, 0))
        rows = self.session.scalars(select(TestQuestion).where(TestQuestion.organization_id == self.org.id)).all()
        self.assertEqual(len(rows), 65)
        self.assertEqual(Counter(r.origin for r in rows), {"synthetic": 50, "invented_shape": 15})
        upsert_rows(self.session, self.org.id, replace=False)
        again = self.session.scalars(select(TestQuestion).where(TestQuestion.organization_id == self.org.id)).all()
        self.assertEqual(len(again), 65)
        self.assertTrue(all(r.meta.get("fixture_id") == r.external_key for r in again))
        labelled = [r for r in again if r.origin == "synthetic"]
        self.assertTrue(all(r.meta.get("label_a", {}).get("status") == "outstanding" for r in labelled))


if __name__ == "__main__":
    unittest.main()
