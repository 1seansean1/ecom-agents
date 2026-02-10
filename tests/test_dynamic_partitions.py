"""Tests for dynamic partitions — auto-generated APS for dynamic agents."""

from __future__ import annotations

import pytest

from src.aps.dynamic_partitions import (
    ensure_dynamic_agent_registered,
    generate_partitions_for_agent,
    generate_thetas_for_agent,
    register_dynamic_agent,
)
from src.aps.partitions import (
    PartitionScheme,
    _PARTITION_REGISTRY,
    get_partition,
    register_all_partitions,
    set_active_partition,
)
from src.aps.theta import (
    ProtocolLevel,
    THETA_REGISTRY,
    _ACTIVE_THETA,
    get_active_theta,
    register_all_thetas,
)


@pytest.fixture(autouse=True)
def clean_registries():
    """Reset partition and theta registries before each test."""
    # Save originals
    orig_partitions = dict(_PARTITION_REGISTRY)
    orig_active = {}
    orig_thetas = dict(THETA_REGISTRY)
    orig_active_theta = dict(_ACTIVE_THETA)

    # Clear
    _PARTITION_REGISTRY.clear()
    _ACTIVE_THETA.clear()
    THETA_REGISTRY.clear()

    # Register built-in partitions and thetas so they don't interfere
    register_all_partitions()
    register_all_thetas()

    yield

    # Restore
    _PARTITION_REGISTRY.clear()
    _PARTITION_REGISTRY.update(orig_partitions)
    _ACTIVE_THETA.clear()
    _ACTIVE_THETA.update(orig_active_theta)
    THETA_REGISTRY.clear()
    THETA_REGISTRY.update(orig_thetas)


# ---------------------------------------------------------------------------
# Tests: generate_partitions_for_agent
# ---------------------------------------------------------------------------


class TestGeneratePartitions:
    def test_generates_fine_and_coarse(self):
        fine, coarse = generate_partitions_for_agent("my_agent", "K8")

        assert fine.partition_id == "theta_K8_fine"
        assert fine.channel_id == "K8"
        assert fine.granularity == "fine"
        assert len(fine.sigma_in_alphabet) > 0
        assert len(fine.sigma_out_alphabet) > 0

        assert coarse.partition_id == "theta_K8_coarse"
        assert coarse.channel_id == "K8"
        assert coarse.granularity == "coarse"
        assert "task" in coarse.sigma_in_alphabet
        assert "success" in coarse.sigma_out_alphabet
        assert "failure" in coarse.sigma_out_alphabet

    def test_fine_classify_input_with_task_type(self):
        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_input({"task_type": "order_check"})
        assert result == "order_check"

    def test_fine_classify_input_simple_message(self):
        from langchain_core.messages import HumanMessage

        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_input({"messages": [HumanMessage(content="short")]})
        assert result == "simple_input"

    def test_fine_classify_input_complex_message(self):
        from langchain_core.messages import HumanMessage

        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_input({"messages": [HumanMessage(content="x" * 600)]})
        assert result == "complex_input"

    def test_fine_classify_input_trigger(self):
        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_input({"trigger_payload": {"task": "do something"}})
        assert result == "triggered"

    def test_fine_classify_output_error(self):
        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_output({"error": "something broke"})
        assert result == "error"

    def test_fine_classify_output_structured(self):
        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_output({
            "agent_results": {
                "my_agent": {"caption": "hello", "hashtags": ["#test"], "call_to_action": "buy"}
            }
        })
        assert result == "completed_structured"

    def test_fine_classify_output_raw(self):
        fine, _ = generate_partitions_for_agent("my_agent", "K8")
        result = fine.classify_output({
            "agent_results": {"my_agent": {"raw_content": "just text"}}
        })
        assert result == "completed_raw"

    def test_coarse_classify_input_always_task(self):
        _, coarse = generate_partitions_for_agent("my_agent", "K8")
        assert coarse.classify_input({}) == "task"
        assert coarse.classify_input({"anything": "here"}) == "task"

    def test_coarse_classify_output_success(self):
        _, coarse = generate_partitions_for_agent("my_agent", "K8")
        result = coarse.classify_output({"agent_results": {"my_agent": {"status": "completed"}}})
        assert result == "success"

    def test_coarse_classify_output_failure(self):
        _, coarse = generate_partitions_for_agent("my_agent", "K8")
        result = coarse.classify_output({"error": "boom"})
        assert result == "failure"


# ---------------------------------------------------------------------------
# Tests: generate_thetas_for_agent
# ---------------------------------------------------------------------------


class TestGenerateThetas:
    def test_generates_three_levels(self):
        thetas = generate_thetas_for_agent("my_agent", "K8")
        assert len(thetas) == 3

        nominal = thetas[0]
        assert nominal.theta_id == "theta_K8_nominal"
        assert nominal.level == 0
        assert nominal.partition_id == "theta_K8_fine"
        assert nominal.protocol_level == ProtocolLevel.PASSIVE

        degraded = thetas[1]
        assert degraded.theta_id == "theta_K8_degraded"
        assert degraded.level == 1
        assert degraded.partition_id == "theta_K8_coarse"
        assert degraded.protocol_level == ProtocolLevel.CONFIRM

        critical = thetas[2]
        assert critical.theta_id == "theta_K8_critical"
        assert critical.level == 2
        assert critical.partition_id == "theta_K8_coarse"
        assert critical.protocol_level == ProtocolLevel.CROSSCHECK

    def test_all_reference_correct_channel(self):
        thetas = generate_thetas_for_agent("my_agent", "K10")
        for t in thetas:
            assert t.channel_id == "K10"

    def test_no_model_overrides(self):
        thetas = generate_thetas_for_agent("my_agent", "K8")
        for t in thetas:
            assert t.model_override is None


# ---------------------------------------------------------------------------
# Tests: register_dynamic_agent
# ---------------------------------------------------------------------------


class TestRegisterDynamicAgent:
    def test_registers_everything(self):
        channel = register_dynamic_agent("new_agent", "K8")
        assert channel == "K8"

        # Partitions registered
        fine = get_partition("theta_K8_fine")
        assert fine.channel_id == "K8"
        coarse = get_partition("theta_K8_coarse")
        assert coarse.channel_id == "K8"

        # Thetas registered
        assert "theta_K8_nominal" in THETA_REGISTRY
        assert "theta_K8_degraded" in THETA_REGISTRY
        assert "theta_K8_critical" in THETA_REGISTRY

        # Active theta set to nominal
        active = get_active_theta("K8")
        assert active.theta_id == "theta_K8_nominal"

    def test_ensure_idempotent(self):
        register_dynamic_agent("agent_a", "K11")

        # Should not raise
        ensure_dynamic_agent_registered("agent_a", "K11")

        # Partition still exists
        fine = get_partition("theta_K11_fine")
        assert fine.channel_id == "K11"

    def test_ensure_registers_if_missing(self):
        # K12 hasn't been registered
        with pytest.raises(KeyError):
            get_partition("theta_K12_fine")

        ensure_dynamic_agent_registered("agent_b", "K12")

        # Now it exists
        fine = get_partition("theta_K12_fine")
        assert fine.channel_id == "K12"
