"""Tests for multi-channel notification system — Phase 20a.

Tests:
- Channel protocol compliance
- ChannelDock registration, routing, dispatch
- Circuit breaker behavior
- Event sanitization
- Event bridge (EventBroadcaster -> ChannelDock)
- Slack and Email channel formatting
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.channels.protocol import (
    Channel,
    ChannelConfig,
    ChannelDock,
    ChannelStatus,
    NotificationMessage,
    SendResult,
)
from src.channels.sanitizer import (
    _sanitize_string,
    sanitize_event,
    sanitize_notification,
)


# ── Test Channel Implementation ───────────────────────────────────────────


class MockChannel:
    """Mock channel for testing the dock and dispatch."""

    def __init__(self, channel_id: str = "mock-1", configured: bool = True):
        self._channel_id = channel_id
        self._configured = configured
        self.sent: list[Any] = []
        self.should_fail = False

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def channel_type(self) -> str:
        return "mock"

    @property
    def is_configured(self) -> bool:
        return self._configured

    @property
    def capabilities(self) -> set[str]:
        return {"text"}

    def format_message(self, message: NotificationMessage) -> dict:
        return {"title": message.title, "body": message.body}

    def send(self, formatted: Any) -> SendResult:
        if self.should_fail:
            return SendResult(success=False, channel_id=self._channel_id, error="mock failure")
        self.sent.append(formatted)
        return SendResult(success=True, channel_id=self._channel_id)


# ── Channel Protocol ─────────────────────────────────────────────────────


class TestChannelProtocol:
    """Verify MockChannel satisfies Channel protocol."""

    def test_mock_is_channel(self):
        assert isinstance(MockChannel(), Channel)

    def test_protocol_properties(self):
        ch = MockChannel("test-ch")
        assert ch.channel_id == "test-ch"
        assert ch.channel_type == "mock"
        assert ch.is_configured is True
        assert "text" in ch.capabilities


# ── ChannelDock ───────────────────────────────────────────────────────────


class TestChannelDock:
    """ChannelDock registration, routing, and dispatch."""

    @pytest.fixture(autouse=True)
    def reset_dock(self):
        ChannelDock.reset()
        yield
        ChannelDock.reset()

    def test_register_channel(self):
        dock = ChannelDock()
        ch = MockChannel("ch-1")
        dock.register(ch)
        assert "ch-1" in dock.channels
        assert dock.channels["ch-1"].status == ChannelStatus.ACTIVE

    def test_register_unconfigured_channel(self):
        dock = ChannelDock()
        ch = MockChannel("ch-2", configured=False)
        dock.register(ch)
        assert dock.channels["ch-2"].status == ChannelStatus.DISABLED

    def test_unregister_channel(self):
        dock = ChannelDock()
        ch = MockChannel("ch-3")
        dock.register(ch)
        dock.unregister("ch-3")
        assert "ch-3" not in dock.channels

    def test_active_channels(self):
        dock = ChannelDock()
        dock.register(MockChannel("active"))
        dock.register(MockChannel("disabled", configured=False))
        assert "active" in dock.active_channels
        assert "disabled" not in dock.active_channels

    def test_dispatch_to_all_channels(self):
        dock = ChannelDock()
        ch1 = MockChannel("ch-a")
        ch2 = MockChannel("ch-b")
        dock.register(ch1)
        dock.register(ch2)

        msg = NotificationMessage(title="Test", body="Hello")
        results = dock.dispatch(msg)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert len(ch1.sent) == 1
        assert len(ch2.sent) == 1

    def test_dispatch_to_specific_channel(self):
        dock = ChannelDock()
        ch1 = MockChannel("ch-a")
        ch2 = MockChannel("ch-b")
        dock.register(ch1)
        dock.register(ch2)

        msg = NotificationMessage(title="Test", body="Hello")
        results = dock.dispatch(msg, channel_ids=["ch-a"])

        assert len(results) == 1
        assert len(ch1.sent) == 1
        assert len(ch2.sent) == 0

    def test_dispatch_skips_disabled(self):
        dock = ChannelDock()
        ch = MockChannel("disabled", configured=False)
        dock.register(ch)

        msg = NotificationMessage(title="Test", body="Hello")
        results = dock.dispatch(msg)

        assert len(results) == 0

    def test_allow_events_filter(self):
        dock = ChannelDock()
        ch = MockChannel("filtered")
        dock.register(ch, allow_events={"webhook_received", "agent_error"})

        msg = NotificationMessage(title="Test", body="Hello", event_type="webhook_received")
        results = dock.dispatch(msg)
        assert len(results) == 1

        msg2 = NotificationMessage(title="Test", body="Hello", event_type="node_entered")
        results2 = dock.dispatch(msg2)
        assert len(results2) == 0

    def test_deny_events_filter(self):
        dock = ChannelDock()
        ch = MockChannel("denied")
        dock.register(ch, deny_events={"node_entered"})

        msg = NotificationMessage(title="Test", body="Hello", event_type="node_entered")
        results = dock.dispatch(msg)
        assert len(results) == 0

        msg2 = NotificationMessage(title="Test", body="Hello", event_type="webhook_received")
        results2 = dock.dispatch(msg2)
        assert len(results2) == 1

    def test_deny_overrides_allow(self):
        dock = ChannelDock()
        ch = MockChannel("both")
        dock.register(ch, allow_events={"webhook_received"}, deny_events={"webhook_received"})

        msg = NotificationMessage(title="Test", body="Hello", event_type="webhook_received")
        results = dock.dispatch(msg)
        assert len(results) == 0

    def test_status(self):
        dock = ChannelDock()
        dock.register(MockChannel("ch-1"))
        status = dock.status()
        assert status["total_channels"] == 1
        assert status["active"] == 1
        assert "ch-1" in status["channels"]


# ── Circuit Breaker ───────────────────────────────────────────────────────


class TestCircuitBreaker:
    """Circuit breaker isolates failing channels."""

    @pytest.fixture(autouse=True)
    def reset_dock(self):
        ChannelDock.reset()
        yield
        ChannelDock.reset()

    def test_failures_trigger_circuit_open(self):
        dock = ChannelDock()
        ch = MockChannel("failing")
        ch.should_fail = True
        dock.register(ch)

        msg = NotificationMessage(title="Test", body="Hello")

        # Send enough to trigger circuit breaker (default max_failures=5)
        for _ in range(5):
            dock.dispatch(msg)

        config = dock.get_channel("failing")
        assert config.status == ChannelStatus.DEGRADED
        assert config.failure_count >= 5

    def test_circuit_open_blocks_dispatch(self):
        dock = ChannelDock()
        ch = MockChannel("failing")
        ch.should_fail = True
        dock.register(ch)

        msg = NotificationMessage(title="Test", body="Hello")

        # Trigger circuit breaker
        for _ in range(5):
            dock.dispatch(msg)

        # Now dispatch should be blocked
        ch.should_fail = False  # Even if channel recovers
        results = dock.dispatch(msg)
        assert len(results) == 0  # Circuit is open

    def test_circuit_resets_after_timeout(self):
        dock = ChannelDock()
        ch = MockChannel("recovering")
        ch.should_fail = True
        dock.register(ch)

        msg = NotificationMessage(title="Test", body="Hello")

        # Trigger circuit breaker
        for _ in range(5):
            dock.dispatch(msg)

        # Simulate timeout passing
        config = dock.get_channel("recovering")
        config.circuit_open_until = time.time() - 1  # Expired

        ch.should_fail = False
        results = dock.dispatch(msg)
        assert len(results) == 1
        assert results[0].success is True

    def test_success_resets_failure_count(self):
        dock = ChannelDock()
        ch = MockChannel("flaky")
        ch.should_fail = True
        dock.register(ch)

        msg = NotificationMessage(title="Test", body="Hello")

        # Accumulate some failures (not enough to trip breaker)
        for _ in range(3):
            dock.dispatch(msg)

        config = dock.get_channel("flaky")
        assert config.failure_count == 3

        # Now succeed
        ch.should_fail = False
        dock.dispatch(msg)

        assert config.failure_count == 0


# ── Event Sanitization ────────────────────────────────────────────────────


class TestEventSanitization:
    """Event data is sanitized before channel dispatch."""

    def test_redacts_email(self):
        result = _sanitize_string("Contact john@example.com for info")
        assert "john@example.com" not in result
        assert "[email]" in result

    def test_redacts_phone(self):
        result = _sanitize_string("Call 555-123-4567 now")
        assert "555-123-4567" not in result
        assert "[phone]" in result

    def test_redacts_ssn(self):
        result = _sanitize_string("SSN is 123-45-6789")
        assert "123-45-6789" not in result
        assert "[ssn]" in result

    def test_redacts_db_url(self):
        result = _sanitize_string("DB at postgresql://user:pass@host/db")
        assert "postgresql://" not in result
        assert "[redacted]" in result

    def test_redacts_stripe_key(self):
        result = _sanitize_string("Key is sk_test_abc123")
        assert "sk_test_abc123" not in result

    def test_preserves_normal_text(self):
        result = _sanitize_string("Order #12345 shipped via UPS")
        assert result == "Order #12345 shipped via UPS"

    def test_sanitize_event_dict(self):
        event = {
            "type": "order",
            "email": "john@example.com",
            "nested": {"url": "postgresql://secret@host/db"},
        }
        result = sanitize_event(event)
        assert "john@example.com" not in str(result)
        assert "postgresql://" not in str(result)

    def test_sanitize_notification_caps_length(self):
        msg = NotificationMessage(
            title="Test",
            body="A" * 1000,
            severity="info",
        )
        result = sanitize_notification(msg)
        assert len(result.body) <= 503  # 500 + "..."

    def test_sanitize_notification_redacts_body(self):
        msg = NotificationMessage(
            title="Alert",
            body="Contact admin@corp.com or call 555-123-4567",
            severity="warning",
        )
        result = sanitize_notification(msg)
        assert "admin@corp.com" not in result.body
        assert "555-123-4567" not in result.body


# ── Slack Channel ─────────────────────────────────────────────────────────


class TestSlackChannel:
    """Slack channel formatting and configuration."""

    def test_not_configured_without_url(self):
        from src.channels.slack import SlackChannel

        ch = SlackChannel(webhook_url="")
        assert ch.is_configured is False

    def test_configured_with_url(self):
        from src.channels.slack import SlackChannel

        ch = SlackChannel(webhook_url="https://hooks.slack.com/test")
        assert ch.is_configured is True

    def test_format_message(self):
        from src.channels.slack import SlackChannel

        ch = SlackChannel(webhook_url="https://hooks.slack.com/test")
        msg = NotificationMessage(title="Alert", body="Something happened", severity="warning")
        formatted = ch.format_message(msg)

        assert "attachments" in formatted
        assert formatted["attachments"][0]["color"] == "#ff9900"  # warning color

    def test_send_without_url_fails(self):
        from src.channels.slack import SlackChannel

        ch = SlackChannel(webhook_url="")
        result = ch.send({})
        assert result.success is False
        assert "not configured" in result.error

    def test_channel_properties(self):
        from src.channels.slack import SlackChannel

        ch = SlackChannel(channel_id="my-slack")
        assert ch.channel_id == "my-slack"
        assert ch.channel_type == "slack"
        assert "text" in ch.capabilities
        assert "rich" in ch.capabilities


# ── Email Channel ─────────────────────────────────────────────────────────


class TestEmailChannel:
    """Email channel formatting and configuration."""

    def test_not_configured_without_host(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(smtp_host="", smtp_user="user", recipients=["a@b.com"])
        assert ch.is_configured is False

    def test_not_configured_without_recipients(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(smtp_host="smtp.test.com", smtp_user="user", recipients=[])
        assert ch.is_configured is False

    def test_configured_with_all(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            recipients=["admin@test.com"],
        )
        assert ch.is_configured is True

    def test_format_message(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(
            smtp_host="smtp.test.com",
            smtp_user="user@test.com",
            smtp_from="noreply@test.com",
            recipients=["admin@test.com"],
        )
        msg = NotificationMessage(title="Alert", body="Something happened", severity="error")
        formatted = ch.format_message(msg)

        assert formatted["Subject"] == "[ERROR] Alert"
        assert formatted["From"] == "noreply@test.com"
        assert formatted["To"] == "admin@test.com"

    def test_send_without_config_fails(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(smtp_host="", recipients=[])
        result = ch.send(MagicMock())
        assert result.success is False
        assert "not configured" in result.error

    def test_channel_properties(self):
        from src.channels.email import EmailChannel

        ch = EmailChannel(channel_id="my-email")
        assert ch.channel_id == "my-email"
        assert ch.channel_type == "email"


# ── Event Bridge ──────────────────────────────────────────────────────────


class TestEventBridge:
    """Event bridge converts internal events to notifications."""

    def test_event_to_notification(self):
        from src.channels.bridge import _event_to_notification

        event = {"type": "webhook_received", "provider": "shopify", "event_type": "orders/create"}
        notification = _event_to_notification(event)
        assert notification is not None
        assert notification.severity == "info"
        assert "shopify" in notification.title

    def test_non_notifiable_event_returns_none(self):
        from src.channels.bridge import _event_to_notification

        event = {"type": "node_entered", "node": "orchestrator"}
        notification = _event_to_notification(event)
        assert notification is None

    def test_critical_severity_for_escalation(self):
        from src.channels.bridge import _event_to_notification

        event = {"type": "cascade_tier_escalation", "from_tier": 2, "to_tier": 3}
        notification = _event_to_notification(event)
        assert notification is not None
        assert notification.severity == "critical"

    def test_error_severity_for_agent_error(self):
        from src.channels.bridge import _event_to_notification

        event = {"type": "agent_error", "agent": "sales", "error": "timeout"}
        notification = _event_to_notification(event)
        assert notification is not None
        assert notification.severity == "error"

    def test_approval_required_is_warning(self):
        from src.channels.bridge import _event_to_notification

        event = {"type": "approval_required", "action": "refund", "ttl": 300}
        notification = _event_to_notification(event)
        assert notification is not None
        assert notification.severity == "warning"
        assert "refund" in notification.title
