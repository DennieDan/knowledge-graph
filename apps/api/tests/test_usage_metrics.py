"""Usage metrics against the migrated test database; all changes are rolled back."""
import unittest
from datetime import date
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database import get_engine
from scripts.usage_metrics import collect, cost


class UsageMetricsTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def test_cost_uses_per_million_prices(self):
        self.assertAlmostEqual(cost(1_000_000, 1_000_000, 0.25, 2.0), 2.25)
        self.assertEqual(cost(None, None, 0.25, 2.0), 0)

    def test_spend_totals_include_new_rows(self):
        before = collect(self.connection, 28)["spend"]
        org_id = uuid4()
        self.connection.execute(
            text("INSERT INTO organizations (id, name) VALUES (:id, 'Metrics test')"), {"id": org_id}
        )
        self.connection.execute(
            text(
                "INSERT INTO spend (id, organization_id, day, input_tokens, output_tokens) "
                "VALUES (:id, :org, :day, 1000000, 500000)"
            ),
            {"id": uuid4(), "org": org_id, "day": date.today()},
        )
        after = collect(self.connection, 28)
        self.assertEqual(after["spend"]["input_tokens"] - before["input_tokens"], 1_000_000)
        self.assertAlmostEqual(after["spend"]["usd_total"] - before["usd_total"], 1.25, places=3)
        for section in ("generations", "chat", "analysis_runs", "corpus", "scorer"):
            self.assertIn(section, after)

    def test_collect_runs_in_a_read_only_transaction(self):
        self.connection.execute(text("SET TRANSACTION READ ONLY"))
        self.assertIn("corpus", collect(self.connection, 7))
        with self.assertRaises(DBAPIError):
            self.connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'x')"), {"id": uuid4()})
