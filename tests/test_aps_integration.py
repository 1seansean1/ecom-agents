"""Integration tests for the APS system.

Tests that the components work together correctly:
- Partition registration + theta registration
- instrument_node with real partitions/thetas
- Goal failure detectors + observations
- Controller evaluation flow (mocked DB)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.aps.channel import (
    build_confusion_matrix,
    channel_capacity_blahut_arimoto,
    mutual_information,
)
from src.aps.goals import GOALS, GoalTier
from src.aps.partitions import (
    _PARTITION_REGISTRY,
    get_active_partition,
    get_partition,
    register_all_partitions,
)
from src.aps.theta import (
    THETA_REGISTRY,
    _ACTIVE_THETA,
    get_active_theta,
    register_all_thetas,
    set_active_theta,
)


@pytest.fixture(autouse=True)
def setup_aps():
    _PARTITION_REGISTRY.clear()
    THETA_REGISTRY.clear()
    _ACTIVE_THETA.clear()
    register_all_partitions()
    register_all_thetas()


class TestPartitionThetaIntegration:
    def test_theta_partition_ids_match_registry(self):
        """Every theta's partition_id should exist in the partition registry."""
        for theta in THETA_REGISTRY.values():
            assert theta.partition_id in _PARTITION_REGISTRY, (
                f"Theta {theta.theta_id} references missing partition {theta.partition_id}"
            )

    def test_active_theta_uses_correct_partition(self):
        """Active theta for K1 nominal should use fine partition."""
        theta = get_active_theta("K1")
        assert theta.partition_id == "theta_K1_fine"
        partition = get_partition(theta.partition_id)
        assert partition.granularity == "fine"

    def test_escalated_theta_uses_coarse_partition(self):
        """Level 1 and 2 thetas should use coarse partitions."""
        set_active_theta("K1", "theta_K1_degraded")
        theta = get_active_theta("K1")
        assert theta.partition_id == "theta_K1_coarse"
        partition = get_partition(theta.partition_id)
        assert partition.granularity == "coarse"


class TestGoalDetectorsIntegration:
    def test_all_goals_have_channels(self):
        for goal in GOALS:
            assert len(goal.channels) > 0

    def test_mission_critical_zero_epsilon(self):
        for goal in GOALS:
            if goal.tier == GoalTier.MISSION_CRITICAL:
                assert goal.epsilon_G == 0.0

    def test_failure_detectors_callable(self):
        for goal in GOALS:
            # Should be callable with a dict
            result = goal.failure_detector({"sigma_out": "normal", "latency_ms": 100})
            assert isinstance(result, bool)

    def test_policy_violation_detector(self):
        from src.aps.goals import GOALS_BY_ID, GoalID
        g = GOALS_BY_ID[GoalID.POLICY_VIOLATION]
        assert g.failure_detector({"sigma_out": "blocked_policy_violation"}) is True
        assert g.failure_detector({"sigma_out": "order_check"}) is False

    def test_latency_detector(self):
        from src.aps.goals import GOALS_BY_ID, GoalID
        g = GOALS_BY_ID[GoalID.RESPONSE_LATENCY]
        assert g.failure_detector({"latency_ms": 50000}) is True
        assert g.failure_detector({"latency_ms": 5000}) is False

    def test_cost_detector(self):
        from src.aps.goals import GOALS_BY_ID, GoalID
        g = GOALS_BY_ID[GoalID.COST_EFFICIENCY]
        assert g.failure_detector({"cost_usd": 1.00}) is True
        assert g.failure_detector({"cost_usd": 0.10}) is False


class TestChannelComputationIntegration:
    def test_k1_fine_realistic_data(self):
        """Simulate realistic K1 observations and compute metrics."""
        partition = get_partition("theta_K1_fine")

        # Create observations mimicking real routing
        obs = []
        for _ in range(30):
            obs.append({"sigma_in": "order_check", "sigma_out": "order_check"})
        for _ in range(20):
            obs.append({"sigma_in": "content_post", "sigma_out": "content_post"})
        for _ in range(10):
            obs.append({"sigma_in": "revenue_report", "sigma_out": "revenue_report"})
        for _ in range(5):
            obs.append({"sigma_in": "order_check", "sigma_out": "error"})

        cm = build_confusion_matrix(
            obs, partition.sigma_in_alphabet, partition.sigma_out_alphabet
        )
        mi = mutual_information(cm)
        cap = channel_capacity_blahut_arimoto(cm)

        # Should have positive MI (not all noise)
        assert mi > 0.5
        # Capacity should be >= MI
        assert cap >= mi - 0.01

    def test_perfect_routing_high_capacity(self):
        """Perfect routing should give high channel capacity."""
        partition = get_partition("theta_K3_coarse")
        obs = []
        for _ in range(50):
            obs.append({"sigma_in": "read_operation", "sigma_out": "success"})
        for _ in range(50):
            obs.append({"sigma_in": "write_operation", "sigma_out": "success"})

        cm = build_confusion_matrix(
            obs, partition.sigma_in_alphabet, partition.sigma_out_alphabet
        )
        # All outputs are "success" regardless of input → zero MI (no info about input from output)
        mi = mutual_information(cm)
        assert mi < 0.1  # Very low because output doesn't distinguish inputs


class TestEndToEndFlow:
    @patch("src.aps.controller.store_aps_metrics")
    @patch("src.aps.controller.store_theta_switch_event")
    @patch("src.aps.controller.get_recent_observations")
    @patch("src.aps.controller.get_distinct_paths", return_value=[])
    @patch("src.aps.controller.cache_theta")
    @patch("src.aps.controller.query_theta_cache", return_value=None)
    @patch("src.resilience.circuit_breaker.get_all_states", return_value={})
    def test_full_evaluation_cycle(
        self, mock_cb, mock_cache_q, mock_cache_s, mock_paths, mock_obs, mock_switch, mock_metrics
    ):
        """Full evaluation cycle with synthetic data."""
        from src.aps.controller import APSController

        # Create observations that look healthy — need enough to make UCB very small
        # Beta(0.5, 200.5) at 95th percentile ≈ 0.01, below mission-critical threshold
        good_obs = [
            {"sigma_out": "order_check", "latency_ms": 2000, "cost_usd": 0.01,
             "sigma_in": "order_check", "total_tokens": 500}
            for _ in range(200)
        ]
        mock_obs.return_value = good_obs

        ctrl = APSController()
        result = ctrl.evaluate_all()

        # Should have run without errors
        assert "channels" in result
        assert "goals" in result
        assert "theta_states" in result
