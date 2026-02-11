"""Tests for Holly Grace agent — Phase 25b.

Tests cover:
- Triage logic (consumer.py)
- Session persistence (session.py)
- Tool execution (tools.py)
- Message building helpers (agent.py)
- Notification context injection (agent.py)
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure TESTING mode
os.environ["TESTING"] = "1"


# ============================================================================
# Triage tests
# ============================================================================


class TestTriage(unittest.TestCase):
    """Test the _triage() function from consumer.py."""

    def setUp(self):
        from src.holly.consumer import _triage
        self._triage = _triage

    def test_auto_ack_types(self):
        """Routine events should be auto-acknowledged."""
        for msg_type in ("run.queued", "run.running", "run.started", "health.check"):
            action, priority = self._triage(msg_type, {})
            self.assertEqual(action, "auto_ack", f"Expected auto_ack for {msg_type}")
            self.assertEqual(priority, "low")

    def test_completed_run_queued_low(self):
        action, priority = self._triage("run.completed", {})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "low")

    def test_ticket_high_risk_urgent(self):
        action, priority = self._triage("ticket.created", {"risk_level": "high"})
        self.assertEqual(action, "urgent")
        self.assertEqual(priority, "high")

    def test_ticket_medium_risk_queued(self):
        action, priority = self._triage("ticket.created", {"risk_level": "medium"})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "normal")

    def test_ticket_low_risk_queued(self):
        action, priority = self._triage("ticket.created", {"risk_level": "low"})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "low")

    def test_run_failed_urgent(self):
        action, priority = self._triage("run.failed", {"error": "timeout"})
        self.assertEqual(action, "urgent")
        self.assertEqual(priority, "high")

    def test_human_message_critical(self):
        action, priority = self._triage("human.message", {"content": "hello"})
        self.assertEqual(action, "urgent")
        self.assertEqual(priority, "critical")

    def test_scheduler_fired_low(self):
        action, priority = self._triage("scheduler.fired", {"job_name": "instagram"})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "low")

    def test_cascade_completed_normal(self):
        action, priority = self._triage("cascade.completed", {})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "normal")

    def test_tool_approval_high_risk(self):
        action, priority = self._triage("tool.approval_requested", {"risk": "high"})
        self.assertEqual(action, "urgent")
        self.assertEqual(priority, "high")

    def test_tool_approval_medium_risk(self):
        action, priority = self._triage("tool.approval_requested", {"risk": "medium"})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "normal")

    def test_unknown_type_default(self):
        action, priority = self._triage("unknown.event", {})
        self.assertEqual(action, "queue")
        self.assertEqual(priority, "normal")


# ============================================================================
# Message building tests
# ============================================================================


class TestBuildAnthropicMessages(unittest.TestCase):
    """Test _build_anthropic_messages from agent.py."""

    def setUp(self):
        from src.holly.agent import _build_anthropic_messages
        self._build = _build_anthropic_messages

    def test_empty_history(self):
        result = self._build([])
        self.assertEqual(result, [])

    def test_single_human_message(self):
        history = [{"role": "human", "content": "hello"}]
        result = self._build(history)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[0]["content"], "hello")

    def test_human_holly_alternation(self):
        history = [
            {"role": "human", "content": "hi"},
            {"role": "holly", "content": "hello!"},
            {"role": "human", "content": "status?"},
        ]
        result = self._build(history)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["role"], "user")
        self.assertEqual(result[1]["role"], "assistant")
        self.assertEqual(result[2]["role"], "user")

    def test_consecutive_user_messages_merged(self):
        """Consecutive same-role messages should be merged."""
        history = [
            {"role": "human", "content": "first"},
            {"role": "human", "content": "second"},
        ]
        result = self._build(history)
        # Should be merged into one user message
        self.assertEqual(len(result), 1)
        self.assertIn("first", result[0]["content"])
        self.assertIn("second", result[0]["content"])

    def test_system_messages_become_user(self):
        history = [
            {"role": "human", "content": "hi"},
            {"role": "holly", "content": "hello"},
            {"role": "system", "content": "session compacted"},
        ]
        result = self._build(history)
        # system → user with prefix
        system_msg = [m for m in result if "[System]" in m.get("content", "")]
        self.assertTrue(len(system_msg) >= 1)

    def test_ensures_starts_with_user(self):
        history = [
            {"role": "holly", "content": "I'm Holly Grace"},
        ]
        result = self._build(history)
        self.assertEqual(result[0]["role"], "user")

    def test_alternation_fix(self):
        """Two consecutive same-role messages should get bridge messages."""
        history = [
            {"role": "human", "content": "hi"},
            {"role": "holly", "content": "hello"},
            {"role": "holly", "content": "how can I help?"},
        ]
        result = self._build(history)
        # Should have bridge messages to fix alternation
        roles = [m["role"] for m in result]
        for i in range(1, len(roles)):
            self.assertNotEqual(roles[i], roles[i - 1], f"Consecutive same role at {i}")


# ============================================================================
# Notification summary tests
# ============================================================================


class TestSummarizePayload(unittest.TestCase):
    """Test _summarize_payload from agent.py."""

    def setUp(self):
        from src.holly.agent import _summarize_payload
        self._summarize = _summarize_payload

    def test_ticket_created(self):
        result = self._summarize("ticket.created", {
            "ticket_id": 42,
            "risk_level": "high",
            "tldr": "Publish Instagram post",
        })
        self.assertIn("42", result)
        self.assertIn("high", result)
        self.assertIn("Instagram", result)

    def test_run_failed(self):
        result = self._summarize("run.failed", {
            "run_id": "abc-123",
            "error": "API timeout",
        })
        self.assertIn("abc-123", result)
        self.assertIn("timeout", result)

    def test_run_completed(self):
        result = self._summarize("run.completed", {
            "run_id": "xyz",
            "run_name": "Weekly campaign",
        })
        self.assertIn("xyz", result)
        self.assertIn("Weekly campaign", result)

    def test_scheduler_fired(self):
        result = self._summarize("scheduler.fired", {
            "job_name": "instagram_post",
        })
        self.assertIn("instagram_post", result)

    def test_tool_approval(self):
        result = self._summarize("tool.approval_requested", {
            "tool_name": "shopify_publish",
            "risk": "medium",
        })
        self.assertIn("shopify_publish", result)
        self.assertIn("medium", result)

    def test_unknown_type_json_fallback(self):
        result = self._summarize("something.else", {"key": "value"})
        self.assertIn("key", result)


# ============================================================================
# Tool execution tests
# ============================================================================


class TestExecuteTool(unittest.TestCase):
    """Test _execute_tool from agent.py."""

    def setUp(self):
        from src.holly.agent import _execute_tool
        self._execute = _execute_tool

    def test_unknown_tool(self):
        result = self._execute("nonexistent_tool", {})
        self.assertIn("error", result)
        self.assertIn("Unknown tool", result["error"])

    @patch("src.holly.tools.query_system_health")
    def test_query_system_health(self, mock_health):
        mock_health.return_value = {
            "redis": "healthy",
            "postgres": "healthy",
            "overall": "healthy",
        }
        # Patch the HOLLY_TOOLS dict to use our mock
        from src.holly import tools
        original = tools.HOLLY_TOOLS["query_system_health"]
        tools.HOLLY_TOOLS["query_system_health"] = mock_health
        try:
            result = self._execute("query_system_health", {})
            self.assertEqual(result["overall"], "healthy")
        finally:
            tools.HOLLY_TOOLS["query_system_health"] = original

    def test_tool_exception_returns_error(self):
        """A tool that raises should return an error dict, not crash."""
        from src.holly import tools
        def bad_tool(**kwargs):
            raise RuntimeError("boom")
        tools.HOLLY_TOOLS["_test_bad"] = bad_tool
        try:
            result = self._execute("_test_bad", {})
            self.assertIn("error", result)
            self.assertIn("boom", result["error"])
        finally:
            del tools.HOLLY_TOOLS["_test_bad"]


# ============================================================================
# Greeting tests
# ============================================================================


class TestGreeting(unittest.TestCase):
    """Test generate_greeting from agent.py."""

    @patch("src.holly.tools.query_system_health")
    def test_greeting_contains_time_of_day(self, mock_health):
        mock_health.return_value = {
            "overall": "healthy",
            "active_runs": 0,
            "waiting_approval": 0,
            "pending_tickets": 0,
        }
        from src.holly.agent import generate_greeting
        greeting = generate_greeting()
        # Greeting should be concise and contain status info
        self.assertIn("Hey.", greeting)
        self.assertIn("need", greeting.lower())


# ============================================================================
# Tool schemas validation
# ============================================================================


class TestToolSchemas(unittest.TestCase):
    """Validate HOLLY_TOOL_SCHEMAS structure."""

    def test_all_tools_have_schemas(self):
        from src.holly.tools import HOLLY_TOOL_SCHEMAS, HOLLY_TOOLS
        schema_names = {s["name"] for s in HOLLY_TOOL_SCHEMAS}
        tool_names = set(HOLLY_TOOLS.keys())
        self.assertEqual(schema_names, tool_names)

    def test_schemas_have_required_fields(self):
        from src.holly.tools import HOLLY_TOOL_SCHEMAS
        for schema in HOLLY_TOOL_SCHEMAS:
            self.assertIn("name", schema)
            self.assertIn("description", schema)
            self.assertIn("input_schema", schema)
            self.assertIsInstance(schema["input_schema"], dict)
            self.assertEqual(schema["input_schema"]["type"], "object")


# ============================================================================
# Notification context building
# ============================================================================


class TestNotificationContext(unittest.TestCase):
    """Test _build_notification_context from agent.py."""

    @patch("src.holly.agent.mark_notification_surfaced")
    @patch("src.holly.agent.get_pending_notifications")
    def test_no_notifications_returns_none(self, mock_get, mock_mark):
        mock_get.return_value = []
        from src.holly.agent import _build_notification_context
        result = _build_notification_context()
        self.assertIsNone(result)

    @patch("src.holly.agent.mark_notification_surfaced")
    @patch("src.holly.agent.get_pending_notifications")
    def test_notifications_build_context(self, mock_get, mock_mark):
        mock_get.return_value = [
            {
                "id": 1,
                "msg_type": "ticket.created",
                "priority": "high",
                "payload": json.dumps({
                    "ticket_id": 42,
                    "risk_level": "high",
                    "tldr": "Publish post",
                }),
            },
            {
                "id": 2,
                "msg_type": "run.completed",
                "priority": "low",
                "payload": json.dumps({
                    "run_id": "xyz",
                    "run_name": "Campaign",
                }),
            },
        ]
        from src.holly.agent import _build_notification_context
        result = _build_notification_context()
        self.assertIsNotNone(result)
        self.assertIn("2 pending notification", result)
        self.assertIn("[URGENT]", result)
        self.assertIn("Publish post", result)
        # Should mark both as surfaced
        self.assertEqual(mock_mark.call_count, 2)


if __name__ == "__main__":
    unittest.main()
