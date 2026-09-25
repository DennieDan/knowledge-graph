"""Golden harness (#106): seed agreement, label schema, fixture metrics."""
from __future__ import annotations

import unittest
from uuid import uuid4

from app.golden import fixture_golden_metrics, planted_conflict_ids, run_golden
from scripts.load_questions import load_fixture, validate_fixture
from scripts.seed_golden import assert_chat_drive_agreement


class SeedGoldenTests(unittest.TestCase):
    def test_chat_po_mentions_match_drive_except_c5(self):
        assert_chat_drive_agreement()


class LabelSchemaTests(unittest.TestCase):
    def test_fixture_validates_label_schema_and_conflict_ids(self):
        data = validate_fixture()
        self.assertEqual(len(data["synthetic"]), 50)
        self.assertEqual(sum(1 for q in data["synthetic"] if q["held_out"]), 10)
        covered = {q["conflict_id"] for q in data["synthetic"] if q["conflict_id"]}
        self.assertEqual(covered, set(planted_conflict_ids()))

    def test_unknown_conflict_id_rejected(self):
        data = load_fixture()
        data["synthetic"][0]["conflict_id"] = "C99"
        with self.assertRaises(ValueError) as ctx:
            validate_fixture(data)
        self.assertIn("unknown conflict_id", str(ctx.exception))


class GoldenMetricsTests(unittest.TestCase):
    def test_fixture_metrics_expose_stub_lines(self):
        metrics = fixture_golden_metrics()
        self.assertIs(metrics["live_cut"], False)
        self.assertEqual(metrics["conflicts"]["planted"], 8)
        for key in ("answers", "refusals", "conflicts", "provenance", "completeness"):
            self.assertIn(key, metrics)
            self.assertEqual(metrics[key]["source"], "fixture_stub")

    def test_run_golden_skipped_until_live_cut(self):
        # Stub does not touch the DB; pass a sentinel session.
        result = run_golden(session=None, organization_id=uuid4(), held_out=False)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "live_golden_cut_not_done")


if __name__ == "__main__":
    unittest.main()
