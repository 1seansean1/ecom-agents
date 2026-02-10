"""Goal specifications for the APS controller.

Two tiers:
- Tier 1: Mission-critical (hard floors, epsilon_G = 0.0)
- Tier 2: Operational (epsilon-triggered switching)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class GoalTier(str, Enum):
    MISSION_CRITICAL = "mission_critical"
    OPERATIONAL = "operational"


class GoalID(str, Enum):
    # Tier 1
    POLICY_VIOLATION = "policy_violation"
    NEGATIVE_MARGIN = "negative_margin"
    # Tier 2
    ROUTING_ACCURACY = "routing_accuracy"
    TASK_COMPLETION = "task_completion"
    TOOL_RELIABILITY = "tool_reliability"
    CAMPAIGN_QUALITY = "campaign_quality"
    RESPONSE_LATENCY = "response_latency"
    COST_EFFICIENCY = "cost_efficiency"


@dataclass
class Goal:
    """A goal with a failure detector, tolerance, and channel scope."""

    goal_id: GoalID
    tier: GoalTier
    epsilon_G: float                     # failure tolerance (0.0 for mission-critical)
    window_seconds: float                # observation window
    channels: list[str]                  # which channels this goal applies to
    failure_detector: Callable[[dict], bool] = field(default=lambda obs: False)
    description: str = ""


# ---------------------------------------------------------------------------
# Failure Detectors
# ---------------------------------------------------------------------------

def _detect_policy_violation(obs: dict) -> bool:
    """Tier 1: Policy violation detected in sigma_out."""
    return obs.get("sigma_out", "").startswith("blocked_policy")


def _detect_negative_margin(obs: dict) -> bool:
    """Tier 1: Negative margin detected."""
    return obs.get("sigma_out", "").startswith("blocked_margin")


def _detect_routing_failure(obs: dict) -> bool:
    """Tier 2: Orchestrator routing failed (error_handler or retry)."""
    sigma_out = obs.get("sigma_out", "")
    return sigma_out in ("error", "unknown")


def _detect_task_failure(obs: dict) -> bool:
    """Tier 2: Agent task produced error/malformed/failure output."""
    sigma_out = obs.get("sigma_out", "")
    return sigma_out in ("error", "malformed", "failure", "crosscheck_failed")


def _detect_tool_failure(obs: dict) -> bool:
    """Tier 2: Tool call failed."""
    sigma_out = obs.get("sigma_out", "")
    return sigma_out in ("http_error", "timeout", "auth_error", "rate_limited", "failure")


def _detect_campaign_failure(obs: dict) -> bool:
    """Tier 2: Campaign sub-agent produced unusable output."""
    sigma_out = obs.get("sigma_out", "")
    return sigma_out in ("unusable", "analysis_failed", "error", "fail")


def _detect_latency_failure(obs: dict) -> bool:
    """Tier 2: Response latency exceeded 30s."""
    latency = obs.get("latency_ms", 0) or 0
    return latency > 30_000


def _detect_cost_failure(obs: dict) -> bool:
    """Tier 2: Single invocation cost exceeded $0.50."""
    cost = obs.get("cost_usd", 0) or 0
    return cost > 0.50


# ---------------------------------------------------------------------------
# Goal Registry
# ---------------------------------------------------------------------------

ALL_CHANNELS = ["K1", "K2", "K3", "K4", "K5", "K6", "K7"]

GOALS: list[Goal] = [
    # Tier 1: Mission-Critical
    Goal(
        goal_id=GoalID.POLICY_VIOLATION,
        tier=GoalTier.MISSION_CRITICAL,
        epsilon_G=0.0,
        window_seconds=86400,  # 24h
        channels=ALL_CHANNELS,
        failure_detector=_detect_policy_violation,
        description="No policy violations (Shopify ToS, Instagram, Stripe, ad platforms)",
    ),
    Goal(
        goal_id=GoalID.NEGATIVE_MARGIN,
        tier=GoalTier.MISSION_CRITICAL,
        epsilon_G=0.0,
        window_seconds=86400,
        channels=["K3", "K4"],
        failure_detector=_detect_negative_margin,
        description="No negative-margin orders",
    ),
    # Tier 2: Operational
    Goal(
        goal_id=GoalID.ROUTING_ACCURACY,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.10,
        window_seconds=3600,
        channels=["K1"],
        failure_detector=_detect_routing_failure,
        description="Orchestrator routes correctly >= 90% of the time",
    ),
    Goal(
        goal_id=GoalID.TASK_COMPLETION,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.05,
        window_seconds=7200,
        channels=["K2", "K3", "K4"],
        failure_detector=_detect_task_failure,
        description="Agent tasks complete successfully >= 95% of the time",
    ),
    Goal(
        goal_id=GoalID.TOOL_RELIABILITY,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.15,
        window_seconds=1800,
        channels=["K7"],
        failure_detector=_detect_tool_failure,
        description="Tool calls succeed >= 85% of the time",
    ),
    Goal(
        goal_id=GoalID.CAMPAIGN_QUALITY,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.10,
        window_seconds=86400,
        channels=["K5", "K6"],
        failure_detector=_detect_campaign_failure,
        description="Campaign outputs are usable >= 90% of the time",
    ),
    Goal(
        goal_id=GoalID.RESPONSE_LATENCY,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.05,
        window_seconds=3600,
        channels=["K1", "K2", "K3", "K4"],
        failure_detector=_detect_latency_failure,
        description="Responses complete within 30s >= 95% of the time",
    ),
    Goal(
        goal_id=GoalID.COST_EFFICIENCY,
        tier=GoalTier.OPERATIONAL,
        epsilon_G=0.10,
        window_seconds=3600,
        channels=["K2", "K4", "K6"],
        failure_detector=_detect_cost_failure,
        description="Invocations cost <= $0.50 each >= 90% of the time",
    ),
]

# Quick lookups
GOALS_BY_ID: dict[GoalID, Goal] = {g.goal_id: g for g in GOALS}
MISSION_CRITICAL_GOALS = [g for g in GOALS if g.tier == GoalTier.MISSION_CRITICAL]
OPERATIONAL_GOALS = [g for g in GOALS if g.tier == GoalTier.OPERATIONAL]
