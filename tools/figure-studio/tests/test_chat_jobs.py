from __future__ import annotations

from pathlib import Path
import sys
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from studio.chat_jobs import ChatJobError, ChatJobManager


class ChatJobTests(unittest.TestCase):
    def test_job_lifecycle_and_idempotent_cancel(self) -> None:
        manager = ChatJobManager()
        job = manager.create("session-one")
        self.assertEqual(manager.active("session-one"), job)
        manager.update(job, "in_progress", "Calling the figure agent")
        self.assertTrue(manager.cancel("session-one", job.job_id).cancel_event.is_set())
        self.assertEqual(manager.cancel("session-one", job.job_id).status, "cancelling")
        manager.finish(job, "cancelled", "Revision cancelled")
        self.assertIsNone(manager.active("session-one"))
        self.assertEqual(manager.get("session-one", job.job_id).status, "cancelled")

    def test_only_one_job_runs_per_session(self) -> None:
        manager = ChatJobManager()
        first = manager.create("session-one")
        with self.assertRaisesRegex(ChatJobError, "already running"):
            manager.create("session-one")
        manager.finish(first, "completed", "Revision completed")
        second = manager.create("session-one")
        self.assertNotEqual(first.job_id, second.job_id)

    def test_job_ids_are_scoped_to_the_session(self) -> None:
        manager = ChatJobManager()
        job = manager.create("session-one")
        with self.assertRaisesRegex(ChatJobError, "unavailable"):
            manager.get("session-two", job.job_id)


if __name__ == "__main__":
    unittest.main()
