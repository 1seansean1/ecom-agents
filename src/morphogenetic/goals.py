"""Goal Specification Framework — G^0/G^1/G^2 formalism from morphogenetic_agency_v5.

Goals are treated as attractor basins at causally relevant scales.
Each GoalSpec is a measurable G^1 tuple: (F_G, epsilon_G, T, m_G).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formalization levels (G^0 → G^1 → G^2)
# ---------------------------------------------------------------------------

LEVEL_G0 = "g0_preference"    # Informal intent, no testable predicate
LEVEL_G1 = "g1_spec"          # Measurable goal tuple
LEVEL_G2 = "g2_implementation"  # Realized policy satisfying G^1


@dataclass
class GoalSpec:
    """A measurable goal specification G^1 = (F_G, epsilon_G, T, m_G).

    F_G:     failure predicate (what counts as failure)
    epsilon_G: tolerated failure probability
    T:       evaluation horizon in seconds
    m_G:     observation map (which channels/variables to track)
    """

    goal_id: str
    display_name: str

    # G^1 formalism
    failure_predicate: str           # e.g., "p_fail", "latency_exceed", "cost_exceed"
    epsilon_g: float                 # tolerated failure probability [0, 1]
    horizon_t: int                   # evaluation window in seconds
    observation_map: list[str]       # channel_ids to observe

    # G^0 → G^1 tracking
    formalization_level: str = LEVEL_G1
    g0_description: str = ""         # informal preference (if still at G^0)

    # Cascade tier hint (which tier is most likely needed to fix failures)
    primary_tier: int = 0            # 0=param, 1=goal, 2=boundary, 3=scale

    # Compound goal priority (lower = relax first under pressure)
    priority: int = 5                # 1-10, higher = more important

    def is_formalized(self) -> bool:
        """Whether this goal has a testable failure predicate."""
        return self.formalization_level != LEVEL_G0

    def spec_gap(self, p_fail: float) -> float:
        """Specification gap: how far the implementation is from the spec.

        Positive = failing, negative = satisfying with margin.
        """
        return p_fail - self.epsilon_g

    def is_satisfied(self, p_fail: float) -> bool:
        """Whether the goal is currently satisfied (in basin)."""
        return p_fail <= self.epsilon_g


# ---------------------------------------------------------------------------
# Default goal specs (extending existing APS goals with full formalism)
# ---------------------------------------------------------------------------

def get_default_goal_specs() -> list[GoalSpec]:
    """Return goal specs from DB (seeds hardcoded defaults on first call)."""
    try:
        from src.aps.store import get_goals, seed_default_goals
        db_goals = get_goals()
        if not db_goals:
            # First run: seed from hardcoded defaults
            defaults = _hardcoded_goal_specs()
            seed_default_goals([_goal_to_dict(g) for g in defaults])
            return defaults
        return [_dict_to_goal(g) for g in db_goals]
    except Exception:
        logger.debug("DB unavailable, using hardcoded goals", exc_info=True)
        return _hardcoded_goal_specs()


def _goal_to_dict(g: GoalSpec) -> dict:
    """Convert GoalSpec to dict for DB storage."""
    return {
        "goal_id": g.goal_id, "display_name": g.display_name,
        "failure_predicate": g.failure_predicate, "epsilon_g": g.epsilon_g,
        "horizon_t": g.horizon_t, "observation_map": g.observation_map,
        "formalization_level": g.formalization_level,
        "g0_description": g.g0_description, "primary_tier": g.primary_tier,
        "priority": g.priority,
    }


def _dict_to_goal(d: dict) -> GoalSpec:
    """Convert DB dict to GoalSpec."""
    return GoalSpec(
        goal_id=d["goal_id"], display_name=d["display_name"],
        failure_predicate=d["failure_predicate"], epsilon_g=d["epsilon_g"],
        horizon_t=d["horizon_t"], observation_map=d["observation_map"],
        formalization_level=d.get("formalization_level", LEVEL_G1),
        g0_description=d.get("g0_description", ""),
        primary_tier=d.get("primary_tier", 0), priority=d.get("priority", 5),
    )


def _hardcoded_goal_specs() -> list[GoalSpec]:
    """The original hardcoded goal specs (used for seeding and fallback)."""
    return [
        # Tier 1 — Mission-critical (epsilon_G = 0.0)
        GoalSpec(
            goal_id="policy_violation",
            display_name="Zero Policy Violations",
            failure_predicate="p_fail",
            epsilon_g=0.0,
            horizon_t=86400,  # 24h
            observation_map=["K1", "K2", "K3", "K4", "K5", "K6", "K7"],
            formalization_level=LEVEL_G2,
            g0_description="No policy violations across all channels",
            primary_tier=0,
            priority=10,
        ),
        GoalSpec(
            goal_id="negative_margin",
            display_name="No Negative Margins",
            failure_predicate="p_fail",
            epsilon_g=0.0,
            horizon_t=86400,
            observation_map=["K3", "K4"],
            formalization_level=LEVEL_G2,
            g0_description="No orders with negative profit margin",
            primary_tier=1,
            priority=9,
        ),
        # Tier 2 — Operational
        GoalSpec(
            goal_id="routing_accuracy",
            display_name="Routing Accuracy",
            failure_predicate="p_fail",
            epsilon_g=0.10,
            horizon_t=3600,  # 1h
            observation_map=["K1"],
            formalization_level=LEVEL_G2,
            g0_description="Orchestrator routes tasks to correct agent",
            primary_tier=0,
            priority=8,
        ),
        GoalSpec(
            goal_id="task_completion",
            display_name="Task Completion Rate",
            failure_predicate="p_fail",
            epsilon_g=0.05,
            horizon_t=7200,  # 2h
            observation_map=["K2", "K3", "K4"],
            formalization_level=LEVEL_G2,
            g0_description="Agents complete assigned tasks successfully",
            primary_tier=0,
            priority=7,
        ),
        GoalSpec(
            goal_id="tool_reliability",
            display_name="Tool Reliability",
            failure_predicate="p_fail",
            epsilon_g=0.15,
            horizon_t=1800,  # 30m
            observation_map=["K7"],
            formalization_level=LEVEL_G2,
            g0_description="External tool calls succeed reliably",
            primary_tier=2,
            priority=6,
        ),
        GoalSpec(
            goal_id="campaign_quality",
            display_name="Campaign Quality",
            failure_predicate="p_fail",
            epsilon_g=0.10,
            horizon_t=86400,
            observation_map=["K5", "K6"],
            formalization_level=LEVEL_G2,
            g0_description="Campaign content meets quality standards",
            primary_tier=1,
            priority=5,
        ),
        GoalSpec(
            goal_id="response_latency",
            display_name="Response Latency",
            failure_predicate="latency_exceed",
            epsilon_g=0.05,
            horizon_t=3600,
            observation_map=["K1", "K2", "K3", "K4"],
            formalization_level=LEVEL_G2,
            g0_description="Agents respond within acceptable latency",
            primary_tier=0,
            priority=4,
        ),
        GoalSpec(
            goal_id="cost_efficiency",
            display_name="Cost Efficiency",
            failure_predicate="cost_exceed",
            epsilon_g=0.10,
            horizon_t=3600,
            observation_map=["K2", "K4", "K6"],
            formalization_level=LEVEL_G2,
            g0_description="Per-task cost stays within budget",
            primary_tier=0,
            priority=3,
        ),
    ]


def compute_formalization_gap(goals: list[GoalSpec]) -> float:
    """Fraction of active goals still at G^0 (no testable predicate).

    Decreases over development as G^0 preferences are formalized into G^1 specs.
    """
    if not goals:
        return 0.0
    g0_count = sum(1 for g in goals if g.formalization_level == LEVEL_G0)
    return g0_count / len(goals)
