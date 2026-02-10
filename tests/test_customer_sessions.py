"""Tests for customer session management — Phase 21b.

Tests:
- Session creation and lifecycle (active, idle, expired, closed)
- Message management and rate limiting
- Identity linking
- Memory compaction
- PII sanitization for LLM dispatch
- Session cleanup
"""

from __future__ import annotations

import time

import pytest

from src.sessions.manager import (
    SessionManager,
    _COMPACTION_KEEP_RECENT,
    _IDLE_THRESHOLD_SECONDS,
    _MAX_MESSAGES_PER_SESSION,
    _RATE_LIMIT_MESSAGES_PER_HOUR,
)
from src.sessions.models import (
    CustomerSession,
    SessionStatus,
    create_session,
)
from src.sessions.sanitizer import (
    sanitize_messages_for_llm,
    sanitize_session_context,
    sanitize_text_for_llm,
)


# ── Session Model ─────────────────────────────────────────────────────────


class TestSessionModel:
    """Session model creation and properties."""

    def test_create_session(self):
        session = create_session(customer_ref="test-cust")
        assert session.session_id != ""
        assert session.customer_ref == "test-cust"
        assert session.status == SessionStatus.ACTIVE
        assert session.is_active

    def test_create_session_auto_ref(self):
        session = create_session()
        assert session.customer_ref.startswith("cust_")

    def test_session_not_expired(self):
        session = create_session(ttl_seconds=3600)
        assert not session.is_expired
        assert session.is_active

    def test_session_expired(self):
        session = create_session(ttl_seconds=0)
        # TTL of 0 means immediately expired
        time.sleep(0.01)
        assert session.is_expired
        assert not session.is_active

    def test_message_count(self):
        session = create_session()
        assert session.message_count == 0


# ── Session Manager ───────────────────────────────────────────────────────


class TestSessionManager:
    """SessionManager CRUD operations."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_create_session(self, manager):
        session = manager.create(customer_ref="test")
        assert session.session_id in manager._sessions
        assert manager.active_count == 1

    def test_get_session(self, manager):
        session = manager.create()
        retrieved = manager.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_nonexistent_returns_none(self, manager):
        assert manager.get("nonexistent-id") is None

    def test_get_expired_returns_none(self, manager):
        session = manager.create(ttl_seconds=0)
        time.sleep(0.01)
        assert manager.get(session.session_id) is None

    def test_add_message(self, manager):
        session = manager.create()
        result = manager.add_message(session.session_id, "customer", "Hello!")
        assert result is True
        assert session.message_count == 1
        assert session.messages[0].content == "Hello!"
        assert session.messages[0].role == "customer"

    def test_add_message_to_nonexistent(self, manager):
        result = manager.add_message("nonexistent", "customer", "Hello")
        assert result is False

    def test_close_session(self, manager):
        session = manager.create()
        result = manager.close(session.session_id)
        assert result is True
        assert session.status == SessionStatus.CLOSED

    def test_close_nonexistent(self, manager):
        assert manager.close("nonexistent") is False


# ── Identity Linking ──────────────────────────────────────────────────────


class TestIdentityLinking:
    """Identity linking and verification."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_link_email(self, manager):
        session = manager.create()
        result = manager.link_identity(
            session.session_id, "email", "john@example.com", verified=True
        )
        assert result is True
        assert len(session.identities) == 1
        assert session.identities[0].identity_type == "email"
        assert session.identities[0].verified is True

    def test_link_phone(self, manager):
        session = manager.create()
        result = manager.link_identity(
            session.session_id, "phone", "+15551234567"
        )
        assert result is True
        assert session.identities[0].identity_value == "+15551234567"

    def test_link_shopify_id(self, manager):
        session = manager.create()
        result = manager.link_identity(
            session.session_id, "shopify_customer_id", "12345"
        )
        assert result is True

    def test_duplicate_identity_updates(self, manager):
        session = manager.create()
        manager.link_identity(session.session_id, "email", "john@example.com", verified=False)
        manager.link_identity(session.session_id, "email", "john@example.com", verified=True)
        # Should update, not duplicate
        assert len(session.identities) == 1
        assert session.identities[0].verified is True

    def test_link_to_nonexistent_session(self, manager):
        result = manager.link_identity("nonexistent", "email", "test@test.com")
        assert result is False


# ── Idle Detection ────────────────────────────────────────────────────────


class TestIdleDetection:
    """Session becomes idle after inactivity."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_becomes_idle_after_threshold(self, manager):
        session = manager.create()
        # Simulate old activity
        session.last_activity = time.time() - _IDLE_THRESHOLD_SECONDS - 1
        retrieved = manager.get(session.session_id)
        assert retrieved is not None
        assert retrieved.status == SessionStatus.IDLE

    def test_reactivates_on_message(self, manager):
        session = manager.create()
        session.last_activity = time.time() - _IDLE_THRESHOLD_SECONDS - 1
        # Force idle detection
        manager.get(session.session_id)
        assert session.status == SessionStatus.IDLE

        # New message should reactivate
        manager.add_message(session.session_id, "customer", "I'm back!")
        assert session.status == SessionStatus.ACTIVE


# ── Rate Limiting ─────────────────────────────────────────────────────────


class TestRateLimiting:
    """Per-session message rate limiting."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_allows_under_limit(self, manager):
        session = manager.create()
        for i in range(10):
            assert manager.add_message(session.session_id, "customer", f"msg {i}")

    def test_blocks_over_limit(self, manager):
        session = manager.create()
        # Fill up to the rate limit
        for i in range(_RATE_LIMIT_MESSAGES_PER_HOUR):
            manager.add_message(session.session_id, "customer", f"msg {i}")

        # Next should be rate limited
        result = manager.add_message(session.session_id, "customer", "one too many")
        assert result is False


# ── Memory Compaction ─────────────────────────────────────────────────────


class TestMemoryCompaction:
    """Memory compaction prevents context explosion."""

    @pytest.fixture
    def manager(self):
        mgr = SessionManager()
        # Override rate limit for compaction tests
        mgr._rate_counts = {}
        return mgr

    def test_compaction_triggers_at_max(self, manager):
        session = manager.create()
        # Disable rate limiting for this test
        original_check = manager._check_rate_limit
        manager._check_rate_limit = lambda sid: True

        # Fill to max
        for i in range(_MAX_MESSAGES_PER_SESSION + 1):
            manager.add_message(session.session_id, "customer", f"msg {i}")

        # Should have compacted
        assert session.message_count <= _COMPACTION_KEEP_RECENT + 2  # +1 for compaction marker, +1 for new msg

        manager._check_rate_limit = original_check

    def test_compaction_keeps_recent(self, manager):
        session = manager.create()
        manager._check_rate_limit = lambda sid: True

        for i in range(_MAX_MESSAGES_PER_SESSION + 1):
            manager.add_message(session.session_id, "customer", f"msg {i}")

        # Last message should still be present
        assert session.messages[-1].content == f"msg {_MAX_MESSAGES_PER_SESSION}"

        manager._check_rate_limit = lambda sid: True

    def test_compaction_adds_marker(self, manager):
        session = manager.create()
        manager._check_rate_limit = lambda sid: True

        for i in range(_MAX_MESSAGES_PER_SESSION + 1):
            manager.add_message(session.session_id, "customer", f"msg {i}")

        # First message should be compaction marker
        assert "compacted" in session.messages[0].content.lower()
        assert session.messages[0].role == "system"

        manager._check_rate_limit = lambda sid: True


# ── Context Retrieval ─────────────────────────────────────────────────────


class TestContextRetrieval:
    """Getting context for LLM dispatch."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_get_context_returns_recent(self, manager):
        session = manager.create()
        for i in range(5):
            manager.add_message(session.session_id, "customer", f"msg {i}")

        context = manager.get_context(session.session_id, max_messages=3)
        assert len(context) == 3
        # Should be the most recent 3
        assert context[0].content == "msg 2"
        assert context[2].content == "msg 4"

    def test_get_context_nonexistent(self, manager):
        assert manager.get_context("nonexistent") == []


# ── Session Cleanup ───────────────────────────────────────────────────────


class TestSessionCleanup:
    """Expired session cleanup."""

    @pytest.fixture
    def manager(self):
        return SessionManager()

    def test_cleanup_removes_expired(self, manager):
        s1 = manager.create(ttl_seconds=0)
        s2 = manager.create(ttl_seconds=3600)
        time.sleep(0.01)

        removed = manager.cleanup_expired()
        assert removed == 1
        assert manager.get(s1.session_id) is None
        assert manager.get(s2.session_id) is not None

    def test_cleanup_removes_closed(self, manager):
        session = manager.create()
        manager.close(session.session_id)

        removed = manager.cleanup_expired()
        assert removed == 1


# ── PII Sanitization ─────────────────────────────────────────────────────


class TestPiiSanitization:
    """PII sanitization for LLM dispatch."""

    def test_redacts_email(self):
        result = sanitize_text_for_llm("Contact john@example.com")
        assert "john@example.com" not in result
        assert "[EMAIL]" in result

    def test_redacts_phone(self):
        result = sanitize_text_for_llm("Call 555-123-4567")
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_redacts_ssn(self):
        result = sanitize_text_for_llm("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_redacts_address(self):
        result = sanitize_text_for_llm("Ship to 123 Main Street")
        assert "123 Main Street" not in result
        assert "[ADDRESS]" in result

    def test_preserves_normal_text(self):
        result = sanitize_text_for_llm("Order status: shipped via UPS")
        assert result == "Order status: shipped via UPS"

    def test_sanitize_messages(self):
        from src.sessions.models import SessionMessage

        messages = [
            SessionMessage(role="customer", content="My email is john@example.com"),
            SessionMessage(role="agent", content="Found your order at 123 Main Street"),
        ]
        sanitized = sanitize_messages_for_llm(messages)
        assert len(sanitized) == 2
        assert "john@example.com" not in sanitized[0]["content"]
        assert "123 Main Street" not in sanitized[1]["content"]

    def test_sanitize_session_context(self):
        session = create_session(customer_ref="cust_abc")
        session.messages.append(
            __import__("src.sessions.models", fromlist=["SessionMessage"]).SessionMessage(
                role="customer",
                content="My email is jane@test.com, call 555-999-8888",
            )
        )
        session.identities.append(
            __import__("src.sessions.models", fromlist=["CustomerIdentity"]).CustomerIdentity(
                identity_type="email",
                identity_value="jane@test.com",
            )
        )

        context = sanitize_session_context(session)
        # customer_ref is preserved (non-PII)
        assert context["customer_ref"] == "cust_abc"
        # Messages are sanitized
        assert "jane@test.com" not in str(context["messages"])
        assert "555-999-8888" not in str(context["messages"])
        # Identities are NOT included (raw PII)
        assert "identities" not in context
