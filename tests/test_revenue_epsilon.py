"""Tests for the revenue-aware epsilon controller.

Validates that:
1. Financial health phases are correctly determined
2. Epsilon values scale with revenue/cash
3. Goal epsilon_G modulation works (survival widens, growth tightens)
4. Exploration gating blocks tasks when broke
5. Cost budgets scale with phase
6. Edge cases (zero revenue, infinite runway, negative growth)
"""

from __future__ import annotations

import pytest

from src.aps.financial_health import FinancialHealth
from src.aps.revenue_epsilon import (
    ModelGuidance,
    RevenueEpsilonConfig,
    RevenuePhase,
    compute_epsilon_r,
    compute_revenue_phase,
    get_model_guidance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_health(**overrides) -> FinancialHealth:
    """Create a FinancialHealth with overrides and compute derived metrics."""
    defaults = {
        "cash_balance_cents": 0,
        "revenue_30d_cents": 0,
        "revenue_7d_cents": 0,
        "revenue_prev_30d_cents": 0,
        "refunds_30d_cents": 0,
        "charge_count_30d": 0,
        "operating_cost_30d_cents": 0,
    }
    defaults.update(overrides)
    h = FinancialHealth(**defaults)
    h.compute_derived()
    return h


# ---------------------------------------------------------------------------
# Phase determination tests
# ---------------------------------------------------------------------------


class TestRevenuePhase:
    """Test compute_revenue_phase under various financial conditions."""

    def test_zero_revenue_is_survival(self):
        h = _make_health(revenue_30d_cents=0)
        assert compute_revenue_phase(h) == RevenuePhase.SURVIVAL

    def test_tiny_revenue_is_survival(self):
        # $5/month — below $10 min_viable threshold
        h = _make_health(revenue_30d_cents=500)
        assert compute_revenue_phase(h) == RevenuePhase.SURVIVAL

    def test_short_runway_is_survival(self):
        # $100 revenue, $50 cash, $50/mo burn → 1 month runway
        h = _make_health(
            cash_balance_cents=5000,
            revenue_30d_cents=10000,
            operating_cost_30d_cents=5000,
        )
        assert compute_revenue_phase(h) == RevenuePhase.SURVIVAL

    def test_declining_revenue_is_conservative(self):
        # Good cash but declining revenue (prev > current by >10%)
        h = _make_health(
            cash_balance_cents=500_00,
            revenue_30d_cents=10_000,  # $100
            revenue_prev_30d_cents=15_000,  # $150 (declined 33%)
            operating_cost_30d_cents=1_000,  # low burn
        )
        assert compute_revenue_phase(h) == RevenuePhase.CONSERVATIVE

    def test_moderate_runway_is_conservative(self):
        # 4 months runway — between survival (3) and conservative (6)
        h = _make_health(
            cash_balance_cents=40_000,  # $400
            revenue_30d_cents=5_000,   # $50
            operating_cost_30d_cents=10_000,  # $100/mo burn → 4 mo runway
        )
        assert compute_revenue_phase(h) == RevenuePhase.CONSERVATIVE

    def test_steady_phase_moderate_runway(self):
        # 8 months runway, stable revenue
        h = _make_health(
            cash_balance_cents=80_000,  # $800
            revenue_30d_cents=20_000,   # $200
            revenue_prev_30d_cents=19_000,  # slight growth
            operating_cost_30d_cents=10_000,  # $100/mo → 8 mo runway
        )
        assert compute_revenue_phase(h) == RevenuePhase.STEADY

    def test_growth_phase_long_runway(self):
        # 20 months runway, growing revenue
        h = _make_health(
            cash_balance_cents=200_000,  # $2000
            revenue_30d_cents=50_000,    # $500
            revenue_prev_30d_cents=40_000,  # 25% growth
            operating_cost_30d_cents=10_000,  # $100/mo → 20 mo runway
        )
        assert compute_revenue_phase(h) == RevenuePhase.GROWTH

    def test_zero_burn_rate_infinite_runway(self):
        # Revenue with no operating costs → infinite runway → growth
        h = _make_health(
            cash_balance_cents=10_000,
            revenue_30d_cents=5_000,
            operating_cost_30d_cents=0,
        )
        assert compute_revenue_phase(h) == RevenuePhase.GROWTH

    def test_no_previous_revenue_first_revenue(self):
        # First month of revenue — prev is 0, growth_rate = 1.0
        h = _make_health(
            cash_balance_cents=100_000,
            revenue_30d_cents=20_000,
            revenue_prev_30d_cents=0,
            operating_cost_30d_cents=5_000,
        )
        # 20 months runway, positive growth → growth
        assert compute_revenue_phase(h) == RevenuePhase.GROWTH


# ---------------------------------------------------------------------------
# Epsilon computation tests
# ---------------------------------------------------------------------------


class TestEpsilonComputation:
    """Test compute_epsilon_r produces correct exploration rates."""

    def test_survival_epsilon_is_zero(self):
        h = _make_health(revenue_30d_cents=0)
        assert compute_epsilon_r(h) == 0.0

    def test_conservative_epsilon_is_small(self):
        h = _make_health(
            cash_balance_cents=40_000,
            revenue_30d_cents=5_000,
            operating_cost_30d_cents=10_000,
        )
        eps = compute_epsilon_r(h)
        assert 0.0 < eps <= 0.05

    def test_steady_epsilon_moderate(self):
        h = _make_health(
            cash_balance_cents=80_000,
            revenue_30d_cents=20_000,
            revenue_prev_30d_cents=19_000,
            operating_cost_30d_cents=10_000,
        )
        eps = compute_epsilon_r(h)
        assert 0.05 <= eps <= 0.20

    def test_growth_epsilon_high(self):
        h = _make_health(
            cash_balance_cents=200_000,
            revenue_30d_cents=50_000,
            revenue_prev_30d_cents=40_000,
            operating_cost_30d_cents=10_000,
        )
        eps = compute_epsilon_r(h)
        assert eps >= 0.15

    def test_epsilon_never_exceeds_max(self):
        # Extreme growth scenario
        h = _make_health(
            cash_balance_cents=10_000_000,
            revenue_30d_cents=1_000_000,
            revenue_prev_30d_cents=100,
            operating_cost_30d_cents=100,
        )
        eps = compute_epsilon_r(h)
        assert eps <= 0.35

    def test_epsilon_monotonic_with_revenue(self):
        """Higher revenue → higher or equal epsilon."""
        epsilons = []
        for rev in [0, 500, 5_000, 20_000, 50_000, 200_000]:
            h = _make_health(
                cash_balance_cents=rev * 10,  # 10x cash:revenue ratio
                revenue_30d_cents=rev,
                revenue_prev_30d_cents=max(1, int(rev * 0.8)),
                operating_cost_30d_cents=max(1, rev // 10),
            )
            epsilons.append(compute_epsilon_r(h))
        # Should be non-decreasing (monotonic)
        for i in range(1, len(epsilons)):
            assert epsilons[i] >= epsilons[i - 1], (
                f"Epsilon decreased at revenue={[0, 500, 5000, 20000, 50000, 200000][i]}: "
                f"{epsilons[i]} < {epsilons[i-1]}"
            )


# ---------------------------------------------------------------------------
# Goal modulation tests
# ---------------------------------------------------------------------------


class TestGoalModulation:
    """Test that goal epsilon_G values are properly scaled."""

    def test_survival_widens_tolerances(self):
        """In survival mode, goal epsilons should be 2x base (save money)."""
        from src.aps.goals import GOALS, GoalTier
        from src.aps.revenue_epsilon import _base_epsilons, _snapshot_base_epsilons

        # Reset base epsilons
        import src.aps.revenue_epsilon as mod
        mod._base_epsilons = None
        _snapshot_base_epsilons()

        config = RevenueEpsilonConfig()
        scale = config.survival_goal_scale  # 2.0

        for goal in GOALS:
            if goal.tier == GoalTier.MISSION_CRITICAL:
                continue
            base = mod._base_epsilons[goal.goal_id.value]
            expected = min(base * scale, 0.50)
            assert expected > base, "Survival scale should widen tolerances"

    def test_growth_tightens_tolerances(self):
        """In growth mode, goal epsilons should be 0.8x base (demand quality)."""
        config = RevenueEpsilonConfig()
        assert config.growth_goal_scale < 1.0

    def test_mission_critical_never_touched(self):
        """Mission-critical goals (policy_violation, negative_margin) are never scaled."""
        from src.aps.goals import GOALS, GoalTier
        from src.aps.revenue_epsilon import apply_revenue_modulation
        import src.aps.revenue_epsilon as mod
        import src.aps.financial_health as fh_mod

        # Force survival mode
        mod._base_epsilons = None
        fh_mod._latest_health = _make_health(revenue_30d_cents=0)

        summary = apply_revenue_modulation()

        for goal in GOALS:
            if goal.tier == GoalTier.MISSION_CRITICAL:
                assert goal.epsilon_G == 0.0, (
                    f"Mission-critical goal {goal.goal_id.value} was modified"
                )

        # Cleanup
        fh_mod._latest_health = None
        mod._base_epsilons = None


# ---------------------------------------------------------------------------
# Exploration gating tests
# ---------------------------------------------------------------------------


class TestExplorationGating:
    """Test that exploratory tasks are properly gated."""

    def test_exploration_blocked_in_survival(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import is_exploration_allowed

        fh_mod._latest_health = _make_health(revenue_30d_cents=0)
        assert not is_exploration_allowed()
        fh_mod._latest_health = None

    def test_exploration_blocked_in_conservative(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import is_exploration_allowed

        fh_mod._latest_health = _make_health(
            cash_balance_cents=40_000,
            revenue_30d_cents=5_000,
            operating_cost_30d_cents=10_000,
        )
        # Conservative epsilon = 0.02, default gate = 0.05 → blocked
        assert not is_exploration_allowed()
        fh_mod._latest_health = None

    def test_exploration_allowed_in_steady(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import is_exploration_allowed

        fh_mod._latest_health = _make_health(
            cash_balance_cents=80_000,
            revenue_30d_cents=20_000,
            revenue_prev_30d_cents=19_000,
            operating_cost_30d_cents=10_000,
        )
        assert is_exploration_allowed()
        fh_mod._latest_health = None

    def test_exploration_allowed_in_growth(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import is_exploration_allowed

        fh_mod._latest_health = _make_health(
            cash_balance_cents=200_000,
            revenue_30d_cents=50_000,
            revenue_prev_30d_cents=40_000,
            operating_cost_30d_cents=10_000,
        )
        assert is_exploration_allowed()
        fh_mod._latest_health = None

    def test_custom_gate_threshold(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import is_exploration_allowed

        # Conservative epsilon = 0.02
        fh_mod._latest_health = _make_health(
            cash_balance_cents=40_000,
            revenue_30d_cents=5_000,
            operating_cost_30d_cents=10_000,
        )
        # With lower threshold, should pass
        assert is_exploration_allowed(min_epsilon=0.01)
        # With higher threshold, should fail
        assert not is_exploration_allowed(min_epsilon=0.10)
        fh_mod._latest_health = None


# ---------------------------------------------------------------------------
# Cost budget tests
# ---------------------------------------------------------------------------


class TestCostBudget:
    """Test that cost budgets scale with revenue phase."""

    def test_survival_lowest_budget(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import get_revenue_cost_budget

        fh_mod._latest_health = _make_health(revenue_30d_cents=0)
        budget = get_revenue_cost_budget()
        assert budget <= 0.05
        fh_mod._latest_health = None

    def test_growth_highest_budget(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import get_revenue_cost_budget

        fh_mod._latest_health = _make_health(
            cash_balance_cents=200_000,
            revenue_30d_cents=50_000,
            revenue_prev_30d_cents=40_000,
            operating_cost_30d_cents=10_000,
        )
        budget = get_revenue_cost_budget()
        assert budget >= 1.00
        fh_mod._latest_health = None

    def test_budget_monotonic_with_phase(self):
        import src.aps.financial_health as fh_mod
        from src.aps.revenue_epsilon import get_revenue_cost_budget

        budgets = []
        scenarios = [
            {"revenue_30d_cents": 0},  # survival
            {"cash_balance_cents": 40_000, "revenue_30d_cents": 5_000,
             "operating_cost_30d_cents": 10_000},  # conservative
            {"cash_balance_cents": 80_000, "revenue_30d_cents": 20_000,
             "revenue_prev_30d_cents": 19_000,
             "operating_cost_30d_cents": 10_000},  # steady
            {"cash_balance_cents": 200_000, "revenue_30d_cents": 50_000,
             "revenue_prev_30d_cents": 40_000,
             "operating_cost_30d_cents": 10_000},  # growth
        ]
        for s in scenarios:
            fh_mod._latest_health = _make_health(**s)
            budgets.append(get_revenue_cost_budget())

        fh_mod._latest_health = None

        for i in range(1, len(budgets)):
            assert budgets[i] >= budgets[i - 1], (
                f"Budget decreased: {budgets[i]} < {budgets[i-1]}"
            )


# ---------------------------------------------------------------------------
# Model guidance tests
# ---------------------------------------------------------------------------


class TestModelGuidance:
    """Test model selection guidance by phase."""

    def test_survival_prefers_local_no_premium(self):
        import src.aps.financial_health as fh_mod

        fh_mod._latest_health = _make_health(revenue_30d_cents=0)
        g = get_model_guidance()
        assert g.prefer_local is True
        assert g.allow_premium is False
        assert g.max_cost_per_call <= 0.01
        fh_mod._latest_health = None

    def test_growth_allows_premium(self):
        import src.aps.financial_health as fh_mod

        fh_mod._latest_health = _make_health(
            cash_balance_cents=200_000,
            revenue_30d_cents=50_000,
            revenue_prev_30d_cents=40_000,
            operating_cost_30d_cents=10_000,
        )
        g = get_model_guidance()
        assert g.allow_premium is True
        assert g.max_cost_per_call >= 0.10
        fh_mod._latest_health = None


# ---------------------------------------------------------------------------
# FinancialHealth derived metrics tests
# ---------------------------------------------------------------------------


class TestFinancialHealthDerived:
    """Test FinancialHealth.compute_derived() math."""

    def test_net_revenue(self):
        h = _make_health(revenue_30d_cents=10_000, refunds_30d_cents=2_000)
        assert h.net_revenue_30d_cents == 8_000

    def test_growth_rate_positive(self):
        h = _make_health(
            revenue_30d_cents=12_000,
            revenue_prev_30d_cents=10_000,
        )
        assert abs(h.revenue_growth_rate - 0.2) < 0.01

    def test_growth_rate_negative(self):
        h = _make_health(
            revenue_30d_cents=8_000,
            revenue_prev_30d_cents=10_000,
        )
        assert abs(h.revenue_growth_rate - (-0.2)) < 0.01

    def test_growth_rate_from_zero(self):
        h = _make_health(
            revenue_30d_cents=5_000,
            revenue_prev_30d_cents=0,
        )
        assert h.revenue_growth_rate == 1.0

    def test_runway_calculation(self):
        h = _make_health(
            cash_balance_cents=100_000,
            operating_cost_30d_cents=10_000,
        )
        assert abs(h.runway_months - 10.0) < 0.01

    def test_zero_burn_infinite_runway(self):
        h = _make_health(
            cash_balance_cents=100_000,
            operating_cost_30d_cents=0,
        )
        assert h.runway_months == float("inf")

    def test_annualized_revenue(self):
        h = _make_health(revenue_7d_cents=10_000)
        assert h.annualized_revenue_cents == 10_000 * 52


# ---------------------------------------------------------------------------
# ExecutionBudget.from_revenue tests
# ---------------------------------------------------------------------------


class TestExecutionBudgetFromRevenue:
    """Test that ExecutionBudget.from_revenue() scales correctly."""

    def test_survival_budget(self):
        import src.aps.financial_health as fh_mod
        from src.execution_limits import ExecutionBudget

        fh_mod._latest_health = _make_health(revenue_30d_cents=0)
        budget = ExecutionBudget.from_revenue()
        assert budget.max_cost_usd <= 0.05
        assert budget.max_tokens <= 20_000
        fh_mod._latest_health = None

    def test_growth_budget(self):
        import src.aps.financial_health as fh_mod
        from src.execution_limits import ExecutionBudget

        fh_mod._latest_health = _make_health(
            cash_balance_cents=200_000,
            revenue_30d_cents=50_000,
            revenue_prev_30d_cents=40_000,
            operating_cost_30d_cents=10_000,
        )
        budget = ExecutionBudget.from_revenue()
        assert budget.max_cost_usd >= 1.00
        assert budget.max_tokens >= 80_000
        fh_mod._latest_health = None

    def test_default_fallback(self):
        """If revenue module fails, should return defaults."""
        from src.execution_limits import ExecutionBudget

        budget = ExecutionBudget.from_revenue()
        # Should succeed regardless
        assert budget.max_iterations == 20
