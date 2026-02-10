"""Revenue-aware epsilon controller.

Maps financial health to an exploration rate (epsilon_R) that governs how
aggressively the system experiments vs. sticking with proven strategies.

    epsilon_R = 0.0   →  pure exploitation: cheapest models, proven tasks only
    epsilon_R = 0.35  →  significant exploration: premium models, novel campaigns

The controller modulates three things in the APS system:

1. **Goal epsilon_G values** — When broke, we raise tolerances (accept more
   failures to save money on cheaper models).  When flush, we tighten them
   (demand quality, can afford it).

2. **Cost budgets** — Per-invocation spend limits scale with revenue.

3. **Scheduler gate** — Exploratory scheduled tasks (weekly campaigns,
   experimental content) are gated by a minimum epsilon_R threshold.

Lifecycle:
    - `financial_health_job()` runs every 30 minutes, fetches Stripe data
    - `get_revenue_epsilon()` returns the current epsilon_R (cached)
    - APS controller calls `apply_revenue_modulation()` before each evaluation
    - Scheduler checks `is_exploration_allowed()` before exploratory tasks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.aps.financial_health import FinancialHealth, get_latest_health
from src.aps.goals import GOALS, Goal, GoalTier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Revenue phases
# ---------------------------------------------------------------------------


class RevenuePhase:
    """Named constants for the four operating phases."""

    SURVIVAL = "survival"       # runway < 3 months or zero revenue
    CONSERVATIVE = "conservative"  # runway 3-6 months or declining
    STEADY = "steady"           # runway 6-12 months, stable/growing
    GROWTH = "growth"           # runway > 12 months, growing


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class RevenueEpsilonConfig:
    """Tunable knobs for the revenue-epsilon mapping."""

    # Revenue thresholds (monthly, in cents)
    # Below this: survival mode regardless of runway
    min_viable_revenue_cents: int = 1_000  # $10/month minimum

    # Runway thresholds (months)
    survival_runway: float = 3.0
    conservative_runway: float = 6.0
    steady_runway: float = 12.0

    # Epsilon outputs per phase
    survival_epsilon: float = 0.0
    conservative_epsilon: float = 0.02
    steady_epsilon_base: float = 0.08
    steady_epsilon_max: float = 0.15
    growth_epsilon_base: float = 0.15
    growth_epsilon_max: float = 0.35

    # Goal epsilon_G scaling factors per phase
    # > 1.0 = more tolerant (save money), < 1.0 = less tolerant (demand quality)
    survival_goal_scale: float = 2.0     # 2x more tolerant when broke
    conservative_goal_scale: float = 1.5
    steady_goal_scale: float = 1.0       # baseline
    growth_goal_scale: float = 0.8       # 20% tighter when flush

    # Cost budget per invocation (USD) per phase
    survival_max_cost: float = 0.05
    conservative_max_cost: float = 0.15
    steady_max_cost: float = 0.50
    growth_max_cost: float = 1.00


_config = RevenueEpsilonConfig()

# Store the original (design-time) epsilon_G values so we can modulate them
_base_epsilons: dict[str, float] | None = None


def _snapshot_base_epsilons() -> None:
    """Capture the original goal epsilon_G values on first call."""
    global _base_epsilons
    if _base_epsilons is None:
        _base_epsilons = {g.goal_id.value: g.epsilon_G for g in GOALS}


# ---------------------------------------------------------------------------
# Core epsilon computation
# ---------------------------------------------------------------------------


def compute_revenue_phase(health: FinancialHealth) -> str:
    """Determine the current revenue phase from financial health."""
    # Zero or near-zero revenue: survival
    if health.revenue_30d_cents < _config.min_viable_revenue_cents:
        return RevenuePhase.SURVIVAL

    # Very short runway: survival
    if health.runway_months < _config.survival_runway:
        return RevenuePhase.SURVIVAL

    # Declining revenue or short runway: conservative
    if (
        health.revenue_growth_rate < -0.1
        or health.runway_months < _config.conservative_runway
    ):
        return RevenuePhase.CONSERVATIVE

    # Moderate runway, stable/growing: steady
    if health.runway_months < _config.steady_runway:
        return RevenuePhase.STEADY

    # Long runway, growing: growth
    return RevenuePhase.GROWTH


def compute_epsilon_r(health: FinancialHealth) -> float:
    """Compute the revenue-aware exploration epsilon.

    Returns a float in [0.0, 0.35] where:
        0.0   = pure exploitation (no exploration)
        0.35  = aggressive exploration
    """
    phase = compute_revenue_phase(health)

    if phase == RevenuePhase.SURVIVAL:
        return _config.survival_epsilon  # 0.0

    if phase == RevenuePhase.CONSERVATIVE:
        return _config.conservative_epsilon  # 0.02

    if phase == RevenuePhase.STEADY:
        # Scale between base and max based on growth rate
        growth_bonus = max(0.0, min(
            _config.steady_epsilon_max - _config.steady_epsilon_base,
            health.revenue_growth_rate * 0.5,
        ))
        return _config.steady_epsilon_base + growth_bonus

    # GROWTH phase
    growth_bonus = max(0.0, min(
        _config.growth_epsilon_max - _config.growth_epsilon_base,
        health.revenue_growth_rate * 1.0,
    ))
    return _config.growth_epsilon_base + growth_bonus


def get_revenue_epsilon() -> float:
    """Get the current revenue-aware epsilon from cached health data."""
    health = get_latest_health()
    return compute_epsilon_r(health)


def get_revenue_phase() -> str:
    """Get the current revenue phase name."""
    health = get_latest_health()
    return compute_revenue_phase(health)


# ---------------------------------------------------------------------------
# APS goal modulation
# ---------------------------------------------------------------------------


def apply_revenue_modulation() -> dict:
    """Adjust APS goal epsilon_G values based on current revenue phase.

    Called by the APS controller before each evaluation cycle.

    Returns a summary dict for logging/broadcast.
    """
    _snapshot_base_epsilons()

    health = get_latest_health()
    phase = compute_revenue_phase(health)
    epsilon_r = compute_epsilon_r(health)

    # Determine the goal scale factor for this phase
    scale = {
        RevenuePhase.SURVIVAL: _config.survival_goal_scale,
        RevenuePhase.CONSERVATIVE: _config.conservative_goal_scale,
        RevenuePhase.STEADY: _config.steady_goal_scale,
        RevenuePhase.GROWTH: _config.growth_goal_scale,
    }.get(phase, 1.0)

    adjustments = {}
    for goal in GOALS:
        if goal.tier == GoalTier.MISSION_CRITICAL:
            continue  # Never touch safety/margin goals

        base_eps = _base_epsilons[goal.goal_id.value]
        new_eps = min(base_eps * scale, 0.50)  # Cap at 50% tolerance
        if new_eps != goal.epsilon_G:
            adjustments[goal.goal_id.value] = {
                "base": base_eps,
                "previous": goal.epsilon_G,
                "new": round(new_eps, 4),
                "scale": scale,
            }
        goal.epsilon_G = new_eps

    summary = {
        "phase": phase,
        "epsilon_r": round(epsilon_r, 4),
        "goal_scale": scale,
        "adjustments": adjustments,
        "cash_usd": round(health.cash_balance_cents / 100, 2),
        "revenue_30d_usd": round(health.revenue_30d_cents / 100, 2),
        "runway_months": round(health.runway_months, 1),
        "growth_rate": round(health.revenue_growth_rate, 3),
    }

    if adjustments:
        logger.info(
            "Revenue modulation [%s]: epsilon_R=%.3f, scale=%.2f, %d goals adjusted",
            phase, epsilon_r, scale, len(adjustments),
        )
    else:
        logger.debug("Revenue modulation [%s]: epsilon_R=%.3f, no changes", phase, epsilon_r)

    return summary


# ---------------------------------------------------------------------------
# Scheduler gate
# ---------------------------------------------------------------------------


def is_exploration_allowed(min_epsilon: float = 0.05) -> bool:
    """Check if the current epsilon_R allows exploratory tasks.

    Exploratory tasks (novel campaigns, new product ideas, pricing experiments)
    should only run when epsilon_R >= min_epsilon.

    Args:
        min_epsilon: Minimum epsilon_R required.  Default 0.05 means we need
                     at least "conservative" phase with some growth.
    """
    return get_revenue_epsilon() >= min_epsilon


# ---------------------------------------------------------------------------
# Cost budget
# ---------------------------------------------------------------------------


def get_revenue_cost_budget() -> float:
    """Return the per-invocation cost budget (USD) for the current phase."""
    health = get_latest_health()
    phase = compute_revenue_phase(health)

    return {
        RevenuePhase.SURVIVAL: _config.survival_max_cost,
        RevenuePhase.CONSERVATIVE: _config.conservative_max_cost,
        RevenuePhase.STEADY: _config.steady_max_cost,
        RevenuePhase.GROWTH: _config.growth_max_cost,
    }.get(phase, _config.steady_max_cost)


# ---------------------------------------------------------------------------
# Model selection guidance
# ---------------------------------------------------------------------------


@dataclass
class ModelGuidance:
    """Recommendations for model selection based on revenue phase."""

    prefer_local: bool = True          # Prefer Ollama/local models
    allow_premium: bool = False        # Allow GPT-4o / Opus
    max_cost_per_call: float = 0.05    # Hard cap per LLM call
    phase: str = RevenuePhase.SURVIVAL


def get_model_guidance() -> ModelGuidance:
    """Return model selection guidance for the current revenue phase."""
    health = get_latest_health()
    phase = compute_revenue_phase(health)

    if phase == RevenuePhase.SURVIVAL:
        return ModelGuidance(
            prefer_local=True,
            allow_premium=False,
            max_cost_per_call=0.01,
            phase=phase,
        )
    if phase == RevenuePhase.CONSERVATIVE:
        return ModelGuidance(
            prefer_local=True,
            allow_premium=False,
            max_cost_per_call=0.05,
            phase=phase,
        )
    if phase == RevenuePhase.STEADY:
        return ModelGuidance(
            prefer_local=False,
            allow_premium=True,
            max_cost_per_call=0.10,
            phase=phase,
        )
    # GROWTH
    return ModelGuidance(
        prefer_local=False,
        allow_premium=True,
        max_cost_per_call=0.50,
        phase=phase,
    )
