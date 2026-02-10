"""Tests for APS regeneration protocols."""

from __future__ import annotations

import pytest

from src.aps.regeneration import (
    ConfirmProtocol,
    CrosscheckProtocol,
    FAILURE_SYMBOLS,
    ValidationResult,
    _validate_content_output,
    _validate_engagement_score,
    _validate_operations_result,
    _validate_revenue_numbers,
    _validate_tool_response,
    is_failure,
)


class TestFailureSymbols:
    def test_k1_failures(self):
        assert is_failure("error", "K1")
        assert is_failure("unknown", "K1")
        assert not is_failure("order_check", "K1")

    def test_k7_failures(self):
        assert is_failure("timeout", "K7")
        assert is_failure("auth_error", "K7")
        assert is_failure("rate_limited", "K7")
        assert not is_failure("success_data", "K7")

    def test_unknown_channel(self):
        assert not is_failure("error", "K99")


class TestValidators:
    def test_operations_valid(self):
        result = {"operations_result": {"status": "ok"}}
        vr = _validate_operations_result(result)
        assert vr.passed

    def test_operations_invalid_not_dict(self):
        result = {"operations_result": "string"}
        vr = _validate_operations_result(result)
        assert not vr.passed

    def test_operations_invalid_error(self):
        result = {"operations_result": {"error": "something"}}
        vr = _validate_operations_result(result)
        assert not vr.passed

    def test_revenue_valid(self):
        result = {"revenue_result": {"total": 100}}
        assert _validate_revenue_numbers(result).passed

    def test_revenue_invalid(self):
        result = {"revenue_result": "not a dict"}
        assert not _validate_revenue_numbers(result).passed

    def test_content_valid(self):
        result = {"sub_agent_results": {"content_writer": {"caption": "A great product for everyone!"}}}
        assert _validate_content_output(result).passed

    def test_content_too_short(self):
        result = {"sub_agent_results": {"content_writer": {"caption": "Hi"}}}
        assert not _validate_content_output(result).passed

    def test_engagement_valid(self):
        result = {"sub_agent_results": {"campaign_analyzer": {"expected_engagement_rate": "5.5%"}}}
        assert _validate_engagement_score(result).passed

    def test_engagement_invalid_range(self):
        result = {"sub_agent_results": {"campaign_analyzer": {"expected_engagement_rate": "150%"}}}
        assert not _validate_engagement_score(result).passed

    def test_engagement_not_numeric(self):
        result = {"sub_agent_results": {"campaign_analyzer": {"expected_engagement_rate": "high"}}}
        assert not _validate_engagement_score(result).passed

    def test_tool_valid(self):
        assert _validate_tool_response({"data": "ok"}).passed

    def test_tool_error(self):
        assert not _validate_tool_response({"error": "timeout"}).passed


class TestConfirmProtocol:
    def test_retry_with_new_result(self):
        protocol = ConfirmProtocol()

        call_count = 0
        def mock_node(state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": "failed"}
            return {"task_type": "order_check", "route_to": "operations"}

        # Simulate that first call failed
        original_result = {"error": "failed"}
        state = {"messages": []}

        new_result, new_sigma = protocol.execute(
            "K3", state, original_result, mock_node, None
        )
        # Retry happened
        assert call_count == 1  # execute calls node once
        assert new_sigma == "retry_completed"  # no partition → default

    def test_retry_failure_returns_original(self):
        protocol = ConfirmProtocol()

        def always_fail(state):
            raise RuntimeError("permanent failure")

        original = {"error": "initial"}
        new_result, sigma = protocol.execute(
            "K3", {"messages": []}, original, always_fail
        )
        assert sigma == "retry_failed"
        assert new_result is original


class TestCrosscheckProtocol:
    def test_passing_result(self):
        protocol = CrosscheckProtocol()
        result = {"operations_result": {"status": "ok"}}
        new_result, override = protocol.execute("K3", result)
        assert override is None
        assert "_crosscheck_failed" not in new_result

    def test_failing_result(self):
        protocol = CrosscheckProtocol()
        result = {"operations_result": {"error": "something broke"}}
        new_result, override = protocol.execute("K3", result)
        assert override == "crosscheck_failed"
        assert new_result["_crosscheck_failed"] is True

    def test_no_validator_for_channel(self):
        protocol = CrosscheckProtocol()
        result = {"data": "test"}
        new_result, override = protocol.execute("K1", result)
        assert override is None

    def test_k5_content_crosscheck(self):
        protocol = CrosscheckProtocol()
        # Too-short caption should fail
        result = {"sub_agent_results": {"content_writer": {"caption": "Hi"}}}
        _, override = protocol.execute("K5", result)
        assert override == "crosscheck_failed"
