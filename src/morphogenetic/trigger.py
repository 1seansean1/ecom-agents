"""Epsilon-trigger mechanism: failure-driven cascade activation.

When UCB_{1-delta}(p_fail) > epsilon_G, the system enters structured
morphogenetic search (APS cascade) ordered by substrate modification cost.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from src.morphogenetic.goals import GoalSpec

logger = logging.getLogger(__name__)

_MIN_OBSERVATIONS_DEFAULT = 20
_DELTA_DEFAULT = 0.05


def _get_trigger_config() -> dict:
    """Load trigger parameters from DB cascade_config."""
    try:
        from src.aps.store import get_cascade_config
        return get_cascade_config()
    except Exception:
        return {"min_observations": _MIN_OBSERVATIONS_DEFAULT, "delta": _DELTA_DEFAULT}


@dataclass
class TriggerResult:
    """Result of checking an epsilon-trigger."""

    triggered: bool
    goal_id: str = ""
    channel_id: str = ""
    p_fail: float = 0.0
    p_fail_ucb: float = 0.0
    epsilon_g: float = 0.0
    margin: float = 0.0          # ucb - epsilon_g (positive = triggered)
    n_observations: int = 0
    recommended_tier: int = 0    # which tier to try first
    reason: str = ""


def hoeffding_ucb(p_fail: float, n: int, delta: float = 0.05) -> float:
    """Compute Hoeffding upper confidence bound on failure probability.

    UCB = p_hat + sqrt(ln(1/delta) / (2n))

    This gives a (1-delta) confidence upper bound on the true failure rate.
    """
    if n <= 0:
        return 1.0
    return p_fail + math.sqrt(math.log(1.0 / delta) / (2.0 * n))


def check_epsilon_trigger(
    goal: GoalSpec,
    p_fail: float,
    n_observations: int,
    channel_id: str = "",
    delta: float | None = None,
) -> TriggerResult:
    """Check if UCB(p_fail) > epsilon_G for a goal.

    This is the core morphogenetic trigger: when empirical goal failure
    exceeds tolerance with statistical confidence, enter exploration.

    Args:
        goal: The goal specification to check.
        p_fail: Empirical failure probability from observations.
        n_observations: Number of observations in the evaluation window.
        channel_id: Which channel this observation is for.
        delta: Confidence parameter (None = read from DB config).

    Returns:
        TriggerResult with triggered flag and diagnostic info.
    """
    cfg = _get_trigger_config()
    min_obs = cfg.get("min_observations", _MIN_OBSERVATIONS_DEFAULT)
    if delta is None:
        delta = cfg.get("delta", _DELTA_DEFAULT)

    if n_observations < min_obs:
        return TriggerResult(
            triggered=False,
            goal_id=goal.goal_id,
            channel_id=channel_id,
            p_fail=p_fail,
            n_observations=n_observations,
            reason="insufficient_observations",
        )

    ucb = hoeffding_ucb(p_fail, n_observations, delta)
    triggered = ucb > goal.epsilon_g
    margin = ucb - goal.epsilon_g

    # Recommend starting tier based on margin severity and goal hint
    recommended_tier = _recommend_tier(goal, p_fail, ucb, margin)

    return TriggerResult(
        triggered=triggered,
        goal_id=goal.goal_id,
        channel_id=channel_id,
        p_fail=p_fail,
        p_fail_ucb=ucb,
        epsilon_g=goal.epsilon_g,
        margin=margin,
        n_observations=n_observations,
        recommended_tier=recommended_tier,
        reason="epsilon_exceeded" if triggered else "within_tolerance",
    )


def _recommend_tier(
    goal: GoalSpec, p_fail: float, ucb: float, margin: float
) -> int:
    """Recommend which cascade tier to start at.

    Normally starts at Tier 0 (cheapest first). But if margin is very large
    or the goal hints at a higher tier, skip ahead.
    """
    # If goal has a primary tier hint, use it as minimum
    min_tier = goal.primary_tier

    # If margin is massive (> 3x epsilon), consider starting higher
    if goal.epsilon_g > 0 and margin > 3 * goal.epsilon_g:
        min_tier = max(min_tier, 1)
    if goal.epsilon_g > 0 and margin > 5 * goal.epsilon_g:
        min_tier = max(min_tier, 2)

    return min(min_tier, 3)  # Cap at Tier 3


def check_all_triggers(
    goals: list[GoalSpec],
    metrics: dict[str, dict],
) -> list[TriggerResult]:
    """Check epsilon-triggers for all goals against current metrics.

    Args:
        goals: List of goal specifications.
        metrics: Dict of channel_id -> {p_fail, n_observations, ...}

    Returns:
        List of TriggerResults (only triggered ones).
    """
    triggered = []
    for goal in goals:
        if not goal.is_formalized():
            continue

        for channel_id in goal.observation_map:
            ch_metrics = metrics.get(channel_id, {})
            p_fail = ch_metrics.get("p_fail", 0.0)
            n_obs = ch_metrics.get("n_observations", 0)

            result = check_epsilon_trigger(goal, p_fail, n_obs, channel_id)
            if result.triggered:
                triggered.append(result)
                logger.info(
                    "Epsilon-trigger fired: goal=%s channel=%s p_fail=%.3f ucb=%.3f > eps=%.3f",
                    goal.goal_id, channel_id, p_fail, result.p_fail_ucb, goal.epsilon_g,
                )

    return triggered
