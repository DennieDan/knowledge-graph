"""Queue simulation behind the analysis finish-time estimate."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.jobs import simulate_finish

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
DURATIONS = {"generate_substack": 60.0, "discover_document": 30.0}


def job(run_id, status="queued", kind="generate_substack", available_in=0, running_for=None):
    return SimpleNamespace(
        analysis_run_id=run_id,
        kind=kind,
        status=status,
        available_at=NOW + timedelta(seconds=available_in),
        locked_at=NOW - timedelta(seconds=running_for) if running_for is not None else None,
    )


class SimulateFinishTests(unittest.TestCase):
    def setUp(self):
        self.run = uuid4()

    def finish(self, pending, workers=1):
        return simulate_finish(NOW, pending, DURATIONS, workers, self.run)

    def test_single_worker_runs_jobs_back_to_back(self):
        self.assertEqual(NOW + timedelta(minutes=3), self.finish([job(self.run) for _ in range(3)]))

    def test_workers_share_the_queue(self):
        self.assertEqual(NOW + timedelta(minutes=2), self.finish([job(self.run) for _ in range(4)], workers=2))

    def test_running_job_counts_only_its_remaining_time(self):
        pending = [job(self.run, "running", running_for=45), job(self.run)]
        self.assertEqual(NOW + timedelta(seconds=75), self.finish(pending))

    def test_overdue_running_job_is_assumed_to_finish_now_not_in_the_past(self):
        pending = [job(self.run, "running", running_for=300), job(self.run)]
        self.assertEqual(NOW + timedelta(minutes=1), self.finish(pending))

    def test_retry_backoff_delays_the_job(self):
        self.assertEqual(NOW + timedelta(minutes=11), self.finish([job(self.run, available_in=600)]))

    def test_other_runs_ahead_in_the_queue_are_included(self):
        pending = [job(uuid4(), kind="discover_document"), job(uuid4()), job(self.run)]
        self.assertEqual(NOW + timedelta(seconds=150), self.finish(pending))

    def test_other_runs_behind_do_not_delay_this_run(self):
        self.assertEqual(NOW + timedelta(minutes=1), self.finish([job(self.run), job(uuid4())]))

    def test_no_duration_history_means_no_estimate(self):
        self.assertIsNone(simulate_finish(NOW, [job(self.run)], {}, 1, self.run))


if __name__ == "__main__":
    unittest.main()
