"""Tests for APS Controller: UCB, escalation, context fingerprinting."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.aps.controller import (
    APSController,
    DE_ESCALATION_COOLDOWN,
    ESCALATION_COOLDOWN,
    MIN_OBSERVATIONS,
    _beta_ppf,
    _regularized_incomplete_beta,
    compute_p_fail_ucb,
    get_context_fingerprint,
)
from src.aps.goals import GOALS, GoalID, GoalTier
from src.aps.partitions import register_all_partitions, _PARTITION_REGISTRY
from src.aps.theta import (
    THETA_REGISTRY,
    _ACTIVE_THETA,
    get_active_theta,
    register_all_thetas,
)


@pytest.fixture(autouse=True)
def setup_aps():
    """Register all partitions and thetas before each test."""
    _PARTITION_REGISTRY.clear()
    THETA_REGISTRY.clear()
    _ACTIVE_THETA.clear()
    register_all_partitions()
    register_all_thetas()


class TestRegularizedIncompleteBeta:
    def test_boundary_zero(self):
        assert _regularized_incomplete_beta(0, 1, 1) == 0.0

    def test_boundary_one(self):
        assert _regularized_incomplete_beta(1, 1, 1) == 1.0

    def test_uniform_at_half(self):
        """I_{0.5}(1, 1) = 0.5 for uniform Beta."""
        val = _regularized_incomplete_beta(0.5, 1, 1)
        assert abs(val - 0.5) < 0.01

    def test_symmetric(self):
        """I_x(a, b) = 1 - I_{1-x}(b, a)."""
        val1 = _regularized_incomplete_beta(0.3, 2, 5)
        val2 = 1 - _regularized_incomplete_beta(0.7, 5, 2)
        assert abs(val1 - val2) < 0.001

    def test_jeffreys_prior(self):
        """Sanity: I_{0.5}(0.5, 0.5) should be 0.5 (symmetric Jeffreys)."""
        val = _regularized_incomplete_beta(0.5, 0.5, 0.5)
        assert abs(val - 0.5) < 0.01


class TestBetaPPF:
    def test_median_uniform(self):
        """PPF(0.5, 1, 1) = 0.5 for uniform."""
        val = _beta_ppf(0.5, 1, 1)
        assert abs(val - 0.5) < 0.01

    def test_high_quantile(self):
        """PPF(0.95) should be > PPF(0.5)."""
        p50 = _beta_ppf(0.5, 2, 8)
        p95 = _beta_ppf(0.95, 2, 8)
        assert p95 > p50

    def test_inverse_matches_cdf(self):
        """PPF should be the inverse of the CDF."""
        q = 0.8
        a, b = 3, 7
        x = _beta_ppf(q, a, b)
        cdf_at_x = _regularized_incomplete_beta(x, a, b)
        assert abs(cdf_at_x - q) < 0.001


class TestComputePFailUCB:
    def test_zero_observations(self):
        assert compute_p_fail_ucb(0, 0) == 1.0

    def test_all_failures(self):
        ucb = compute_p_fail_ucb(100, 100)
        assert ucb > 0.9

    def test_no_failures(self):
        ucb = compute_p_fail_ucb(0, 100)
        # Should be positive but small (upper bound on near-zero rate)
        assert 0 < ucb < 0.1

    def test_ucb_higher_than_point_estimate(self):
        """UCB should be >= point estimate."""
        failures, total = 5, 50
        point = failures / total
        ucb = compute_p_fail_ucb(failures, total, confidence=0.95)
        assert ucb >= point

    def test_small_sample_high_uncertainty(self):
        """With small samples, UCB should be wide."""
        ucb_small = compute_p_fail_ucb(1, 5)
        ucb_large = compute_p_fail_ucb(20, 100)
        # Same rate (20%), but small sample UCB should be larger
        assert ucb_small > ucb_large


class TestContextFingerprint:
    @patch("src.aps.controller.get_recent_observations", return_value=[])
    @patch("src.resilience.circuit_breaker.get_all_states", return_value={})
    def test_returns_hex_hash(self, mock_states, mock_obs):
        fp = get_context_fingerprint("K1")
        assert len(fp) == 32  # MD5 hex digest
        assert all(c in "0123456789abcdef" for c in fp)

    @patch("src.aps.controller.get_recent_observations", return_value=[])
    @patch("src.resilience.circuit_breaker.get_all_states", return_value={})
    def test_same_context_same_hash(self, mock_states, mock_obs):
        fp1 = get_context_fingerprint("K1")
        fp2 = get_context_fingerprint("K1")
        assert fp1 == fp2


class TestAPSControllerEscalation:
    def _make_obs(self, n_ok: int, n_fail: int, channel_id: str = "K1") -> list[dict]:
        """Create synthetic observation dicts."""
        obs = []
        for _ in range(n_ok):
            obs.append({"sigma_out": "order_check", "latency_ms": 1000, "cost_usd": 0.01})
        for _ in range(n_fail):
            obs.append({"sigma_out": "error", "latency_ms": 1000, "cost_usd": 0.01})
        return obs

    @patch("src.aps.controller.store_aps_metrics")
    @patch("src.aps.controller.store_theta_switch_event")
    @patch("src.aps.controller.get_recent_observations")
    def test_no_escalation_below_threshold(self, mock_obs, mock_switch, mock_metrics):
        """No switch when p_fail < epsilon_G."""
        mock_obs.return_value = self._make_obs(95, 2)  # ~2% failure
        ctrl = APSController()

        # Routing accuracy goal: epsilon_G = 0.10
        result = ctrl.evaluate_all()
        # Should not have escalated K1 (2% < 10%)
        assert get_active_theta("K1").level == 0

    @patch("src.aps.controller.store_aps_metrics")
    @patch("src.aps.controller.store_theta_switch_event")
    @patch("src.aps.controller.get_recent_observations")
    @patch("src.aps.controller.get_distinct_paths", return_value=[])
    @patch("src.aps.controller.cache_theta")
    @patch("src.aps.controller.query_theta_cache", return_value=None)
    @patch("src.resilience.circuit_breaker.get_all_states", return_value={})
    def test_escalation_above_threshold(
        self, mock_cb, mock_cache_q, mock_cache_s, mock_paths, mock_obs, mock_switch, mock_metrics
    ):
        """Switches happen when p_fail > epsilon_G."""
        mock_obs.return_value = self._make_obs(70, 30)  # 30% failure >> 10%
        ctrl = APSController()

        result = ctrl.evaluate_all()
        # Should have produced switch events (escalation or de-escalation)
        assert len(result["switches"]) > 0
        # store_theta_switch_event should have been called
        assert mock_switch.called
        # At least one escalation should have happened
        escalations = [s for s in result["switches"] if s["direction"] == "escalated"]
        assert len(escalations) > 0

    @patch("src.aps.controller.store_aps_metrics")
    @patch("src.aps.controller.store_theta_switch_event")
    @patch("src.aps.controller.get_recent_observations")
    @patch("src.aps.controller.get_distinct_paths", return_value=[])
    def test_cooldown_prevents_rapid_escalation(
        self, mock_paths, mock_obs, mock_switch, mock_metrics
    ):
        """Escalation cooldown prevents switches within 60s."""
        mock_obs.return_value = self._make_obs(70, 30)
        ctrl = APSController()
        ctrl._last_escalation["K1"] = time.time()  # Just escalated

        result = ctrl.evaluate_all()
        # Should not escalate due to cooldown
        theta = get_active_theta("K1")
        assert theta.level == 0

    def test_min_observations_guard(self):
        """No action with fewer than MIN_OBSERVATIONS."""
        ctrl = APSController()
        from src.aps.goals import GOALS
        goal = GOALS[2]  # routing_accuracy

        result = ctrl._evaluate_escalation(
            "K1", goal, 0.5, MIN_OBSERVATIONS - 1, time.time()
        )
        assert result is None


class TestAPSControllerTheta:
    def test_all_channels_start_nominal(self):
        for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
            theta = get_active_theta(ch)
            assert theta.level == 0

    def test_21_thetas_registered(self):
        assert len(THETA_REGISTRY) == 21

    def test_theta_levels(self):
        for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
            for level in (0, 1, 2):
                from src.aps.theta import get_theta_by_channel_and_level
                t = get_theta_by_channel_and_level(ch, level)
                assert t is not None
                assert t.level == level
                assert t.channel_id == ch
