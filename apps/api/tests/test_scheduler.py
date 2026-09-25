"""Scheduler tick enqueues due jobs."""
import unittest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import KnowledgeJob, Organization, Schedule
from app.jobs import claim_job, enqueue_job, park_budget_exhausted
from app.spend import add_tokens, budget_exhausted
from app.scheduler import ensure_default_schedules, tick


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.connection = get_engine().connect()
        self.transaction = self.connection.begin()
        self.session = Session(self.connection, join_transaction_mode="create_savepoint")
        self.org = Organization(name=f"Sched-{uuid4().hex[:6]}")
        self.session.add(self.org)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def test_tick_enqueues_run_checks(self):
        ensure_default_schedules(self.session, self.org.id)
        for schedule in self.session.scalars(select(Schedule)).all():
            schedule.next_run_at = None
        self.session.flush()
        result = tick(self.session)
        self.assertGreaterEqual(result["jobs_enqueued"], 2)
        kinds = {
            job.kind
            for job in self.session.scalars(
                select(KnowledgeJob).where(KnowledgeJob.organization_id == self.org.id)
            )
        }
        self.assertIn("run_checks", kinds)
        self.assertIn("score_questions", kinds)

    def test_budget_parks_generation_until_tomorrow(self):
        self.org.daily_token_budget = 100
        self.session.flush()
        self.assertFalse(budget_exhausted(self.session, self.org.id))
        add_tokens(self.session, self.org.id, input_tokens=80, output_tokens=30)
        self.assertTrue(budget_exhausted(self.session, self.org.id))
        job = enqueue_job(
            self.session,
            organization_id=self.org.id,
            owner_user_id=None,
            kind="generate_substack",
            payload={"substack_id": str(uuid4())},
            dedupe_key=f"budget-test:{uuid4()}",
        )
        self.session.flush()
        park_budget_exhausted(self.session, job.id)
        self.session.refresh(job)
        self.assertEqual(job.status, "budget_exhausted")
        claimed = claim_job(self.session, "test-worker")
        self.assertTrue(claimed is None or claimed.id != job.id, "a parked job must not be claimed today")
        self.assertEqual(job.status, "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
