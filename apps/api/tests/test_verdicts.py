"""Golden v1 planted-conflict verdicts (#106) — CI shape checks.

verdicts.json is a scorer contract and a CI assert that every planted conflict
is named. It is not a substitute for two human labellers on questions.json.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

VERDICTS = Path(__file__).resolve().parent / "fixtures" / "verdicts.json"
REQUIRED_IDS = {f"C{i}" for i in range(1, 9)}
REQUIRED_FIELDS = (
    "id",
    "name",
    "description",
    "sources",
    "record",
    "answer_must_say",
    "answer_must_not_say",
    "checked_line",
)


class VerdictFixtureTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(VERDICTS.read_text())
        self.conflicts = self.data["planted_conflicts"]

    def test_exactly_eight_named_planted_conflicts(self):
        ids = [c["id"] for c in self.conflicts]
        self.assertEqual(len(ids), 8)
        self.assertEqual(set(ids), REQUIRED_IDS)
        self.assertEqual(len(set(c["name"] for c in self.conflicts)), 8)
        for conflict in self.conflicts:
            self.assertTrue(conflict["name"].strip())
            self.assertTrue(conflict["description"].strip())

    def test_unknown_conflict_keys_fail(self):
        known = set(REQUIRED_FIELDS) | {"_comment"}
        for conflict in self.conflicts:
            unknown = set(conflict) - known
            self.assertEqual(unknown, set(), f"{conflict['id']} has unknown keys: {unknown}")

    def test_each_card_has_must_say_and_sources(self):
        for conflict in self.conflicts:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, conflict, f"{conflict.get('id')} missing {field}")
            self.assertGreaterEqual(len(conflict["answer_must_say"]), 1)
            self.assertGreaterEqual(len(conflict["sources"]), 1)
            self.assertIsInstance(conflict["record"], dict)

    def test_live_cut_not_claimed(self):
        self.assertIs(self.data.get("live_cut"), False)


if __name__ == "__main__":
    unittest.main()
