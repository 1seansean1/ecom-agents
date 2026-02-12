"""Tests for autonomy queue debug fixes.

Tests:
- get_completed_count / get_failed_count / _count_by_outcome
- list_recent_tasks
- retry_failed_task
- get_autonomy_status persistent counters
"""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("TESTING", "1")


_UNSET = object()


def _mock_pg_conn(rows=None, fetchone_val=_UNSET):
    """Helper to create a mock psycopg connection context manager."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    if fetchone_val is not _UNSET:
        mock_cursor.fetchone.return_value = fetchone_val
    if rows is not None:
        mock_cursor.fetchall.return_value = rows
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: mock_conn
    mock_conn.__exit__ = lambda *a: None
    return mock_conn


class TestCountByOutcome(unittest.TestCase):
    """Test persistent audit-log-based counting functions."""

    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_get_completed_count(self, mock_dsn, mock_connect):
        from src.holly.autonomy import get_completed_count

        mock_connect.return_value = _mock_pg_conn(fetchone_val=(12,))
        count = get_completed_count()
        self.assertEqual(count, 12)

    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_get_failed_count(self, mock_dsn, mock_connect):
        from src.holly.autonomy import get_failed_count

        mock_connect.return_value = _mock_pg_conn(fetchone_val=(3,))
        count = get_failed_count()
        self.assertEqual(count, 3)

    @patch("psycopg.connect", side_effect=Exception("DB down"))
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_count_returns_zero_on_exception(self, mock_dsn, mock_connect):
        from src.holly.autonomy import _count_by_outcome

        count = _count_by_outcome("completed")
        self.assertEqual(count, 0)

    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_count_returns_zero_on_empty_result(self, mock_dsn, mock_connect):
        from src.holly.autonomy import _count_by_outcome

        mock_connect.return_value = _mock_pg_conn(fetchone_val=None)
        count = _count_by_outcome("completed")
        self.assertEqual(count, 0)


class TestListRecentTasks(unittest.TestCase):
    """Test recently processed tasks query."""

    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_returns_recent_entries(self, mock_dsn, mock_connect):
        from src.holly.autonomy import list_recent_tasks

        now = datetime.now(timezone.utc)
        mock_connect.return_value = _mock_pg_conn(rows=[
            {
                "id": 1,
                "task_id": "abc12345",
                "task_type": "revenue_research",
                "objective": "Research MCP Builder",
                "priority": "normal",
                "outcome": "completed",
                "error_message": "",
                "started_at": now - timedelta(minutes=2),
                "finished_at": now - timedelta(minutes=1),
                "duration_sec": 60.0,
                "metadata": {},
                "retry_count": 0,
            }
        ])

        tasks = list_recent_tasks(minutes=5, limit=10)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "abc12345")
        # Verify datetimes were serialized to ISO strings
        self.assertIsInstance(tasks[0]["started_at"], str)
        self.assertIsInstance(tasks[0]["finished_at"], str)

    @patch("psycopg.connect", side_effect=Exception("DB down"))
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_returns_empty_on_exception(self, mock_dsn, mock_connect):
        from src.holly.autonomy import list_recent_tasks

        tasks = list_recent_tasks()
        self.assertEqual(tasks, [])


class TestRetryFailedTask(unittest.TestCase):
    """Test resubmission of exhausted_retries tasks."""

    @patch("src.holly.autonomy.submit_task", return_value="new12345")
    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_retry_resubmits_task(self, mock_dsn, mock_connect, mock_submit):
        from src.holly.autonomy import retry_failed_task

        mock_connect.return_value = _mock_pg_conn(fetchone_val={
            "task_id": "old12345",
            "objective": "REVENUE IDEA — AUTH ENGINE: Research...",
            "priority": "normal",
            "task_type": "revenue_research",
            "metadata": {},
        })

        result = retry_failed_task("old12345")
        self.assertTrue(result["resubmitted"])
        self.assertEqual(result["new_task_id"], "new12345")
        self.assertEqual(result["original_task_id"], "old12345")

        mock_submit.assert_called_once_with(
            objective="REVENUE IDEA — AUTH ENGINE: Research...",
            priority="normal",
            task_type="revenue_research",
            metadata={},
        )

    @patch("psycopg.connect")
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_retry_returns_error_when_not_found(self, mock_dsn, mock_connect):
        from src.holly.autonomy import retry_failed_task

        mock_connect.return_value = _mock_pg_conn(fetchone_val=None)
        result = retry_failed_task("nonexistent")
        self.assertIn("error", result)
        self.assertIn("nonexistent", result["error"])

    @patch("psycopg.connect", side_effect=Exception("DB down"))
    @patch("src.holly.autonomy._get_pg_dsn", return_value="postgresql://test/test")
    def test_retry_returns_error_on_exception(self, mock_dsn, mock_connect):
        from src.holly.autonomy import retry_failed_task

        result = retry_failed_task("abc12345")
        self.assertIn("error", result)


class TestGetAutonomyStatusPersistent(unittest.TestCase):
    """Test that get_autonomy_status uses persistent counts."""

    @patch("src.holly.autonomy.get_failed_count", return_value=2)
    @patch("src.holly.autonomy.get_completed_count", return_value=15)
    @patch("src.holly.autonomy.get_queue_depth", return_value=0)
    @patch("src.holly.autonomy._get_redis")
    @patch("src.holly.autonomy._loop", None)
    def test_status_includes_persistent_counts_without_loop(
        self, mock_redis, mock_depth, mock_completed, mock_failed
    ):
        from src.holly.autonomy import get_autonomy_status

        mock_r = MagicMock()
        mock_r.hgetall.return_value = {"status": "idle", "detail": "test"}
        mock_redis.return_value = mock_r

        status = get_autonomy_status()
        self.assertEqual(status["tasks_completed"], 15)
        self.assertEqual(status["failed_count"], 2)

    @patch("src.holly.autonomy.get_failed_count", return_value=1)
    @patch("src.holly.autonomy.get_completed_count", return_value=10)
    @patch("src.holly.autonomy.get_queue_depth", return_value=3)
    @patch("src.holly.autonomy._get_redis")
    def test_status_includes_persistent_counts_with_loop(
        self, mock_redis, mock_depth, mock_completed, mock_failed
    ):
        from src.holly import autonomy
        from src.holly.autonomy import get_autonomy_status

        mock_r = MagicMock()
        mock_r.hgetall.return_value = {"status": "running"}
        mock_redis.return_value = mock_r

        mock_loop = MagicMock()
        mock_loop.running = True
        mock_loop.paused = False
        mock_loop.consecutive_errors = 0
        mock_loop.idle_sweeps = 2
        mock_loop.monitor_interval = 300
        mock_loop._credit_exhausted = False
        mock_loop._thread = MagicMock()
        mock_loop._thread.is_alive.return_value = True

        original_loop = autonomy._loop
        try:
            autonomy._loop = mock_loop
            status = get_autonomy_status()
            self.assertEqual(status["tasks_completed"], 10)
            self.assertEqual(status["failed_count"], 1)
            self.assertEqual(status["queue_depth"], 3)
            self.assertTrue(status["running"])
        finally:
            autonomy._loop = original_loop


if __name__ == "__main__":
    unittest.main()
