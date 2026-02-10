"""Tests for the enhanced fallback chain system (Phase 18b).

Tests:
- Error classification for different provider error types
- Provider health tracking with exponential backoff
- Fallback audit log recording and querying
- invoke_with_fallback async flow
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.fallback import (
    ErrorClass,
    FallbackAuditLog,
    FallbackEvent,
    ProviderHealth,
    classify_error,
    get_fallback_audit_log,
    get_model_with_fallbacks,
    get_provider_health,
    invoke_with_fallback,
)
from src.llm.config import ModelID


class TestErrorClassification:
    """classify_error should map exceptions to the correct error class."""

    def test_rate_limit_429(self):
        err = Exception("Error 429: Too many requests")
        assert classify_error(err) == ErrorClass.RATE_LIMIT

    def test_rate_limit_too_many_requests(self):
        err = Exception("too many requests to the API")
        assert classify_error(err) == ErrorClass.RATE_LIMIT

    def test_rate_limit_class_name(self):
        class RateLimitError(Exception):
            pass
        err = RateLimitError("rate limited")
        assert classify_error(err) == ErrorClass.RATE_LIMIT

    def test_auth_failure_401(self):
        err = Exception("HTTP 401 Unauthorized")
        assert classify_error(err) == ErrorClass.AUTH_FAILURE

    def test_auth_failure_403(self):
        err = Exception("HTTP 403 Forbidden")
        assert classify_error(err) == ErrorClass.AUTH_FAILURE

    def test_auth_failure_invalid_key(self):
        err = Exception("invalid api key provided")
        assert classify_error(err) == ErrorClass.AUTH_FAILURE

    def test_auth_failure_class_name(self):
        class AuthenticationError(Exception):
            pass
        err = AuthenticationError("bad key")
        assert classify_error(err) == ErrorClass.AUTH_FAILURE

    def test_timeout(self):
        err = Exception("Request timed out after 30s")
        assert classify_error(err) == ErrorClass.TIMEOUT

    def test_timeout_class_name(self):
        class ConnectTimeout(Exception):
            pass
        err = ConnectTimeout("connection timeout")
        assert classify_error(err) == ErrorClass.TIMEOUT

    def test_server_error_500(self):
        err = Exception("HTTP 500 Internal Server Error")
        assert classify_error(err) == ErrorClass.SERVER_ERROR

    def test_server_error_502(self):
        err = Exception("502 Bad Gateway")
        assert classify_error(err) == ErrorClass.SERVER_ERROR

    def test_server_error_503(self):
        err = Exception("503 Service Unavailable")
        assert classify_error(err) == ErrorClass.SERVER_ERROR

    def test_server_error_class_name(self):
        class InternalServerError(Exception):
            pass
        err = InternalServerError("server down")
        assert classify_error(err) == ErrorClass.SERVER_ERROR

    def test_model_error_400(self):
        err = Exception("400 Bad Request: invalid parameters")
        assert classify_error(err) == ErrorClass.MODEL_ERROR

    def test_model_error_not_found(self):
        err = Exception("model gpt-5 not found")
        assert classify_error(err) == ErrorClass.MODEL_ERROR

    def test_unknown_error(self):
        err = Exception("something completely unexpected happened")
        assert classify_error(err) == ErrorClass.UNKNOWN


class TestProviderHealth:
    """ProviderHealth tracks failures and computes backoff."""

    def test_initial_state_available(self):
        health = ProviderHealth()
        assert health.is_available
        assert health.consecutive_failures == 0

    def test_failure_increments_count(self):
        health = ProviderHealth()
        health.record_failure(ErrorClass.SERVER_ERROR)
        assert health.consecutive_failures == 1

    def test_failure_sets_backoff(self):
        health = ProviderHealth()
        health.record_failure(ErrorClass.SERVER_ERROR)
        assert health.backoff_until > time.time()

    def test_consecutive_failures_increase_backoff(self):
        health = ProviderHealth()
        health.record_failure(ErrorClass.SERVER_ERROR)
        first_backoff = health.backoff_until

        health.record_failure(ErrorClass.SERVER_ERROR)
        second_backoff = health.backoff_until
        assert second_backoff > first_backoff

    def test_auth_failure_has_long_backoff(self):
        health = ProviderHealth()
        health.record_failure(ErrorClass.AUTH_FAILURE)
        # Auth failure should have at least 600s backoff
        assert health.backoff_until >= time.time() + 590

    def test_success_resets_state(self):
        health = ProviderHealth()
        health.record_failure(ErrorClass.SERVER_ERROR)
        health.record_failure(ErrorClass.SERVER_ERROR)
        assert health.consecutive_failures == 2

        health.record_success()
        assert health.consecutive_failures == 0
        assert health.is_available
        assert health.last_error_class is None

    def test_backoff_cap_at_300_for_non_auth(self):
        health = ProviderHealth()
        # Simulate many failures
        for _ in range(20):
            health.record_failure(ErrorClass.SERVER_ERROR)
        # Backoff should be capped at 300s
        assert health.backoff_until <= time.time() + 301


class TestFallbackAuditLog:
    """FallbackAuditLog records and queries fallback events."""

    def test_record_and_retrieve(self):
        log = FallbackAuditLog()
        event = FallbackEvent(
            timestamp=time.time(),
            primary_model="gpt4o",
            fallback_model="gpt4o_mini",
            error_class=ErrorClass.RATE_LIMIT,
            error_message="429 too many",
            success=True,
        )
        log.record(event)
        assert len(log.recent(hours=1)) == 1

    def test_recent_filters_old_events(self):
        log = FallbackAuditLog()
        old_event = FallbackEvent(
            timestamp=time.time() - 48 * 3600,  # 48 hours ago
            primary_model="gpt4o",
            fallback_model="gpt4o_mini",
            error_class=ErrorClass.RATE_LIMIT,
            error_message="old",
            success=True,
        )
        new_event = FallbackEvent(
            timestamp=time.time(),
            primary_model="gpt4o",
            fallback_model="gpt4o_mini",
            error_class=ErrorClass.SERVER_ERROR,
            error_message="new",
            success=True,
        )
        log.record(old_event)
        log.record(new_event)
        assert len(log.recent(hours=24)) == 1
        assert log.recent(hours=24)[0].error_message == "new"

    def test_cap_at_max_entries(self):
        log = FallbackAuditLog()
        for i in range(FallbackAuditLog.MAX_ENTRIES + 100):
            log.record(FallbackEvent(
                timestamp=time.time(),
                primary_model="m",
                fallback_model="f",
                error_class=ErrorClass.UNKNOWN,
                error_message=str(i),
                success=True,
            ))
        # Should be capped
        assert len(log._events) <= FallbackAuditLog.MAX_ENTRIES

    def test_summary_empty(self):
        log = FallbackAuditLog()
        summary = log.summary(hours=24)
        assert summary["total_fallbacks"] == 0
        assert summary["success_rate"] == 1.0

    def test_summary_with_events(self):
        log = FallbackAuditLog()
        for _ in range(3):
            log.record(FallbackEvent(
                timestamp=time.time(),
                primary_model="gpt4o",
                fallback_model="gpt4o_mini",
                error_class=ErrorClass.RATE_LIMIT,
                error_message="429",
                success=True,
            ))
        log.record(FallbackEvent(
            timestamp=time.time(),
            primary_model="gpt4o",
            fallback_model=None,
            error_class=ErrorClass.SERVER_ERROR,
            error_message="500",
            success=False,
        ))
        summary = log.summary(hours=1)
        assert summary["total_fallbacks"] == 4
        assert summary["success_rate"] == 0.75
        assert summary["by_error_class"]["rate_limit"] == 3
        assert summary["by_error_class"]["server_error"] == 1


class TestGetModelWithFallbacks:
    """get_model_with_fallbacks should wrap models with LangChain fallbacks."""

    def test_returns_primary_when_no_fallbacks(self):
        router = MagicMock()
        primary = MagicMock()
        router.get_model.return_value = primary

        with patch("src.llm.fallback.FALLBACK_CHAINS", {ModelID.OLLAMA_QWEN: []}):
            result = get_model_with_fallbacks(router, ModelID.OLLAMA_QWEN)
            assert result is primary

    def test_wraps_with_fallbacks_when_available(self):
        router = MagicMock()
        primary = MagicMock()
        fallback = MagicMock()
        wrapped = MagicMock()
        primary.with_fallbacks.return_value = wrapped
        router.get_model.side_effect = [primary, fallback]

        with patch("src.llm.fallback.FALLBACK_CHAINS", {ModelID.GPT4O: [ModelID.GPT4O_MINI]}):
            result = get_model_with_fallbacks(router, ModelID.GPT4O)
            assert result is wrapped
            primary.with_fallbacks.assert_called_once_with([fallback])


class TestInvokeWithFallback:
    """invoke_with_fallback should try models in order with error handling."""

    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        """When primary model works, no fallback needed."""
        router = MagicMock()
        model = AsyncMock()
        model.ainvoke.return_value = "response"
        router.get_model.return_value = model

        # Clear provider health state
        from src.llm import fallback as fb_module
        fb_module._provider_health.clear()

        result = await invoke_with_fallback(router, ModelID.GPT4O, ["hello"])
        assert result == "response"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        """When primary fails, should try fallback."""
        router = MagicMock()
        primary = AsyncMock()
        primary.ainvoke.side_effect = Exception("500 Server Error")
        fallback = AsyncMock()
        fallback.ainvoke.return_value = "fallback response"

        def get_model(mid):
            if mid == ModelID.GPT4O:
                return primary
            return fallback

        router.get_model.side_effect = get_model

        # Clear provider health state
        from src.llm import fallback as fb_module
        fb_module._provider_health.clear()

        result = await invoke_with_fallback(router, ModelID.GPT4O, ["hello"])
        assert result == "fallback response"

    @pytest.mark.asyncio
    async def test_all_fail_raises_last_error(self):
        """When all models fail, should raise the last error."""
        router = MagicMock()
        model = AsyncMock()
        model.ainvoke.side_effect = Exception("all down")
        router.get_model.return_value = model

        # Clear provider health state
        from src.llm import fallback as fb_module
        fb_module._provider_health.clear()

        with pytest.raises(Exception, match="all down"):
            await invoke_with_fallback(router, ModelID.GPT4O, ["hello"])

    @pytest.mark.asyncio
    async def test_fallback_records_audit_event(self):
        """Successful fallback should record an audit event."""
        router = MagicMock()
        primary = AsyncMock()
        primary.ainvoke.side_effect = Exception("429 rate limited")
        fallback = AsyncMock()
        fallback.ainvoke.return_value = "ok"

        def get_model(mid):
            if mid == ModelID.GPT4O:
                return primary
            return fallback

        router.get_model.side_effect = get_model

        # Clear state
        from src.llm import fallback as fb_module
        fb_module._provider_health.clear()
        fb_module._audit_log = FallbackAuditLog()

        await invoke_with_fallback(router, ModelID.GPT4O, ["hello"])

        log = get_fallback_audit_log()
        events = log.recent(hours=1)
        # Should have at least 1 failure event + 1 success event
        assert len(events) >= 1


class TestModuleSingletons:
    """Module-level singletons should be accessible."""

    def test_get_provider_health_creates_new(self):
        health = get_provider_health("test_provider_singleton")
        assert health.is_available
        assert health.consecutive_failures == 0

    def test_get_provider_health_returns_same(self):
        h1 = get_provider_health("test_provider_same")
        h2 = get_provider_health("test_provider_same")
        assert h1 is h2

    def test_get_fallback_audit_log_returns_singleton(self):
        log = get_fallback_audit_log()
        assert isinstance(log, FallbackAuditLog)
