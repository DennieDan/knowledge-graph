"""The readiness check against the migrated test database; all changes are rolled back."""
import unittest
from contextlib import redirect_stdout
from io import StringIO

from sqlalchemy import text

from app.database import get_engine
from scripts.check_database import Report, check_runtime


class CheckDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def run_check(self, require_migrated=False) -> Report:
        report = Report()
        with redirect_stdout(StringIO()):
            check_runtime(self.connection, report, require_migrated)
        return report

    def test_migrated_local_database_passes(self):
        report = self.run_check(require_migrated=True)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.warnings, [])

    def test_pending_migrations_warn_or_fail(self):
        self.connection.execute(text("UPDATE alembic_version SET version_num = '0001'"))
        self.assertIn("migrations pending", self.run_check().warnings[0])
        self.assertIn("migrations pending", self.run_check(require_migrated=True).failures[0])

    def test_tables_granted_to_data_api_roles_warn(self):
        self.connection.execute(text("CREATE ROLE anon NOLOGIN"))
        self.connection.execute(text("GRANT SELECT ON public.documents TO anon"))
        warnings = self.run_check().warnings
        self.assertEqual(len(warnings), 1)
        self.assertIn("anon:documents", warnings[0])


if __name__ == "__main__":
    unittest.main()
