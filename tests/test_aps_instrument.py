"""Tests for APS instrumentation wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.aps.instrument import (
    TokenAccumulator,
    compute_actual_cost,
    estimate_cost,
    get_token_accumulator,
    instrument_node,
)
from src.aps.partitions import _PARTITION_REGISTRY, register_all_partitions
from src.aps.theta import THETA_REGISTRY, _ACTIVE_THETA, register_all_thetas
from src.llm.config import MODEL_REGISTRY, ModelID


@pytest.fixture(autouse=True)
def setup_aps():
    _PARTITION_REGISTRY.clear()
    THETA_REGISTRY.clear()
    _ACTIVE_THETA.clear()
    register_all_partitions()
    register_all_thetas()


class TestTokenAccumulator:
    def test_reset_clears(self):
        acc = TokenAccumulator()
        acc.accumulate({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        acc.reset()
        assert acc.get() is None

    def test_accumulate_adds(self):
        acc = TokenAccumulator()
        acc.reset()
        acc.accumulate({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        acc.accumulate({"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300})
        result = acc.get()
        assert result["prompt_tokens"] == 300
        assert result["completion_tokens"] == 150
        assert result["total_tokens"] == 450

    def test_get_returns_none_when_empty(self):
        acc = TokenAccumulator()
        acc.reset()
        assert acc.get() is None

    def test_global_singleton(self):
        acc1 = get_token_accumulator()
        acc2 = get_token_accumulator()
        assert acc1 is acc2


class TestCostComputation:
    def test_gpt4o_cost(self):
        """GPT-4o: $2.50/M input, $10.00/M output."""
        tokens = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = compute_actual_cost(ModelID.GPT4O, tokens)
        # (1000/1M)*2.50 + (500/1M)*10.00 = 0.0025 + 0.005 = 0.0075
        assert abs(cost - 0.0075) < 0.0001

    def test_gpt4o_mini_cost(self):
        """GPT-4o-mini: $0.15/M input, $0.60/M output."""
        tokens = {"prompt_tokens": 10000, "completion_tokens": 5000}
        cost = compute_actual_cost(ModelID.GPT4O_MINI, tokens)
        # (10000/1M)*0.15 + (5000/1M)*0.60 = 0.0015 + 0.003 = 0.0045
        assert abs(cost - 0.0045) < 0.0001

    def test_unknown_model_returns_zero(self):
        cost = compute_actual_cost("totally_unknown_model", {"prompt_tokens": 1000})
        assert cost == 0.0

    def test_none_tokens(self):
        tokens = {"prompt_tokens": None, "completion_tokens": None}
        cost = compute_actual_cost(ModelID.GPT4O, tokens)
        assert cost == 0.0

    def test_estimate_returns_nonzero(self):
        cost = estimate_cost(ModelID.GPT4O, {}, {})
        assert cost > 0


class TestInstrumentNode:
    @patch("src.aps.instrument.log_observation")
    @patch("src.aps.instrument.broadcaster", create=True)
    def test_wraps_function(self, mock_broadcaster, mock_log):
        """The wrapper calls the original function and returns its result."""
        mock_broadcaster.broadcast = MagicMock()

        def fake_node(state):
            return {"task_type": "order_check", "route_to": "operations"}

        wrapped = instrument_node("K1", ModelID.OLLAMA_QWEN, fake_node)

        from langchain_core.messages import HumanMessage
        state = {
            "messages": [HumanMessage(content="Check orders")],
            "trigger_payload": {},
        }
        result = wrapped(state)

        assert result["task_type"] == "order_check"
        assert result["route_to"] == "operations"
        assert "_aps_path_id" in result

    @patch("src.aps.instrument.log_observation")
    @patch("src.aps.instrument.broadcaster", create=True)
    def test_logs_observation(self, mock_broadcaster, mock_log):
        """The wrapper logs an observation after execution."""
        mock_broadcaster.broadcast = MagicMock()

        def fake_node(state):
            return {"task_type": "order_check", "route_to": "operations"}

        wrapped = instrument_node("K1", ModelID.OLLAMA_QWEN, fake_node)

        from langchain_core.messages import HumanMessage
        state = {
            "messages": [HumanMessage(content="Check orders")],
            "trigger_payload": {},
        }
        wrapped(state)

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["channel_id"] == "K1"
        assert call_kwargs["sigma_in"] in ("order_check",)
        assert call_kwargs["sigma_out"] in ("order_check", "unknown")

    @patch("src.aps.instrument.log_observation")
    @patch("src.aps.instrument.broadcaster", create=True)
    def test_propagates_path_id(self, mock_broadcaster, mock_log):
        """path_id builds incrementally from parent."""
        mock_broadcaster.broadcast = MagicMock()

        def fake_node(state):
            return {"task_type": "order_check"}

        wrapped = instrument_node("K3", ModelID.GPT4O_MINI, fake_node)

        from langchain_core.messages import HumanMessage
        state = {
            "messages": [HumanMessage(content="Check orders")],
            "_aps_path_id": "K1",
            "task_type": "order_check",
            "trigger_payload": {},
        }
        result = wrapped(state)
        assert result["_aps_path_id"] == "K1>K3"

    @patch("src.aps.instrument.log_observation")
    @patch("src.aps.instrument.broadcaster", create=True)
    def test_node_failure_still_returns(self, mock_broadcaster, mock_log):
        """If the node raises, the exception propagates (we don't swallow it)."""
        mock_broadcaster.broadcast = MagicMock()

        def failing_node(state):
            raise ValueError("boom")

        wrapped = instrument_node("K1", ModelID.OLLAMA_QWEN, failing_node)

        from langchain_core.messages import HumanMessage
        state = {"messages": [HumanMessage(content="test")], "trigger_payload": {}}

        with pytest.raises(ValueError, match="boom"):
            wrapped(state)
