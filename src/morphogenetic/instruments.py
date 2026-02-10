"""Instrumentation suite: developmental snapshot computation.

Computes all observables from morphogenetic_agency_v5.md:
- AI-proxy (structural complexity)
- CLC (cognitive light cone / goal reach)
- eta (informational efficiency = capacity / work)
- CP(l) profile (causal power per channel/scale)
- P_feasible count (recoverable partitions)
- Attractor count (goals satisfied)
- Spec gap (mean failure beyond tolerance)
- Competency distribution (count per type)
- APS tier usage (cascade tier counts)
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DevelopmentalSnapshot:
    """A point-in-time measurement of the system's developmental state."""

    snapshot_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Assembly Theory proxy
    ai_proxy: float = 0.0           # structural complexity (modules * depth + caches)

    # Cognitive Light Cone
    clc_horizon: int = 0            # max feasible goal horizon T (seconds)
    clc_dimensions: int = 0         # max observation map dimensions

    # Informational efficiency
    eta_mean: float = 0.0           # mean eta_usd across active channels

    # Causal Emergence 2.0 profile
    cp_profile: dict[str, float] = field(default_factory=dict)  # channel -> capacity

    # Feasible partitions
    p_feasible_count: int = 0       # partitions with enough observations

    # Attractor count (goals in basin)
    attractor_count: int = 0        # goals with p_fail <= epsilon_G

    # Spec gap
    spec_gap_mean: float = 0.0      # mean(max(0, p_fail - epsilon_G))

    # Competency distribution
    competency_dist: dict[str, int] = field(default_factory=dict)

    # Cascade tier usage
    tier_usage: dict[str, int] = field(default_factory=dict)

    # Assembly reuse
    total_reuse: int = 0            # sum of all competency reuse counts

    def to_dict(self) -> dict:
        d = asdict(self)
        d["snapshot_at"] = str(self.snapshot_at)
        return d


def compute_developmental_snapshot(
    goals: list | None = None,
    metrics: dict[str, dict] | None = None,
) -> DevelopmentalSnapshot:
    """Compute a full developmental snapshot from current system state.

    Gathers data from APS metrics, assembly cache, and goal specs
    to produce all observables from the morphogenetic framework.
    """
    snapshot = DevelopmentalSnapshot()

    # Load goals if not provided
    if goals is None:
        from src.morphogenetic.goals import get_default_goal_specs
        goals = get_default_goal_specs()

    # Load metrics if not provided
    if metrics is None:
        metrics = _load_current_metrics()

    # 1. Compute AI-proxy (structural complexity)
    snapshot.ai_proxy = _compute_ai_proxy()

    # 2. Compute CLC (cognitive light cone)
    snapshot.clc_horizon, snapshot.clc_dimensions = _compute_clc(goals, metrics)

    # 3. Compute eta (informational efficiency)
    snapshot.eta_mean = _compute_eta_mean(metrics)

    # 4. Compute CP(l) profile (causal power per channel)
    snapshot.cp_profile = _compute_cp_profile(metrics)

    # 5. Count feasible partitions
    snapshot.p_feasible_count = _count_feasible_partitions(metrics)

    # 6. Count attractors (satisfied goals)
    snapshot.attractor_count = _count_attractors(goals, metrics)

    # 7. Compute spec gap
    snapshot.spec_gap_mean = _compute_spec_gap(goals, metrics)

    # 8. Competency distribution
    snapshot.competency_dist = _get_competency_distribution()

    # 9. Tier usage
    snapshot.tier_usage = _get_tier_usage()

    # 10. Total reuse count
    snapshot.total_reuse = _get_total_reuse()

    return snapshot


# ---------------------------------------------------------------------------
# Private computation helpers
# ---------------------------------------------------------------------------


def _load_current_metrics() -> dict[str, dict]:
    """Load current APS metrics for all channels."""
    try:
        from src.aps.store import get_latest_metrics
        rows = get_latest_metrics()
        return {r["channel_id"]: r for r in rows}
    except Exception:
        logger.warning("Failed to load APS metrics", exc_info=True)
        return {}


def _compute_ai_proxy() -> float:
    """Assembly index proxy: structural complexity of the agent system.

    AI-proxy = num_active_thetas * compositional_depth + num_cached_competencies
    """
    try:
        from src.aps.theta import get_all_theta_states
        theta_states = get_all_theta_states()
        num_thetas = len(theta_states)

        # Compositional depth: count unique levels across thetas
        levels = set()
        for state in theta_states.values():
            if isinstance(state, dict):
                levels.add(state.get("level", 0))

        depth = len(levels) if levels else 1

        # Add cached competencies
        from src.morphogenetic.assembly import get_all_competencies
        num_competencies = len(get_all_competencies())

        return float(num_thetas * depth + num_competencies)

    except Exception:
        logger.debug("AI-proxy computation fell back to default", exc_info=True)
        return 0.0


def _compute_clc(goals: list, metrics: dict) -> tuple[int, int]:
    """Cognitive Light Cone: max(T, dim(m_G)) across satisfied goals.

    CLC captures the spatiotemporal reach of the agent's goal satisfaction.
    """
    max_horizon = 0
    max_dims = 0

    for goal in goals:
        # Check if goal is satisfied
        goal_satisfied = True
        for ch in goal.observation_map:
            ch_metrics = metrics.get(ch, {})
            p_fail = ch_metrics.get("p_fail", 1.0)
            if p_fail > goal.epsilon_g:
                goal_satisfied = False
                break

        if goal_satisfied:
            max_horizon = max(max_horizon, goal.horizon_t)
            max_dims = max(max_dims, len(goal.observation_map))

    return max_horizon, max_dims


def _compute_eta_mean(metrics: dict) -> float:
    """Mean informational efficiency eta = C(P) / W across active channels."""
    eta_values = []
    for ch_metrics in metrics.values():
        eta = ch_metrics.get("eta_usd")
        if eta is not None and eta > 0:
            eta_values.append(eta)

    if not eta_values:
        return 0.0
    return sum(eta_values) / len(eta_values)


def _compute_cp_profile(metrics: dict) -> dict[str, float]:
    """Causal power profile: channel capacity per scale/channel.

    This is the CE 2.0 approximation — we use Shannon channel capacity
    (already computed by APS) as a proxy for causal contribution.
    """
    profile = {}
    for ch_id, ch_metrics in metrics.items():
        capacity = ch_metrics.get("capacity")
        if capacity is not None:
            profile[ch_id] = round(capacity, 4)
    return profile


def _count_feasible_partitions(metrics: dict) -> int:
    """Count partitions with enough observations to be considered feasible.

    A partition is (T, epsilon)-recoverable if it has >= 20 observations.
    """
    count = 0
    for ch_metrics in metrics.values():
        n_obs = ch_metrics.get("n_observations", 0)
        if n_obs >= 20:
            count += 1
    return count


def _count_attractors(goals: list, metrics: dict) -> int:
    """Count goals that are currently satisfied (agent is in basin)."""
    count = 0
    for goal in goals:
        if not goal.is_formalized():
            continue
        satisfied = True
        for ch in goal.observation_map:
            ch_metrics = metrics.get(ch, {})
            p_fail = ch_metrics.get("p_fail", 1.0)
            if p_fail > goal.epsilon_g:
                satisfied = False
                break
        if satisfied:
            count += 1
    return count


def _compute_spec_gap(goals: list, metrics: dict) -> float:
    """Mean specification gap across failing goals.

    Spec gap = mean(max(0, p_fail - epsilon_G)) for goals that are failing.
    Positive values indicate the system is outside the goal basin.
    """
    gaps = []
    for goal in goals:
        if not goal.is_formalized():
            continue
        for ch in goal.observation_map:
            ch_metrics = metrics.get(ch, {})
            p_fail = ch_metrics.get("p_fail", 0.0)
            gap = max(0.0, p_fail - goal.epsilon_g)
            if gap > 0:
                gaps.append(gap)

    if not gaps:
        return 0.0
    return sum(gaps) / len(gaps)


def _get_competency_distribution() -> dict[str, int]:
    """Get count of cached competencies per type."""
    try:
        from src.morphogenetic.assembly import get_competency_distribution
        return get_competency_distribution()
    except Exception:
        return {}


def _get_tier_usage() -> dict[str, int]:
    """Get count of cascade events per tier."""
    try:
        from src.aps.store import get_tier_usage_counts
        counts = get_tier_usage_counts()
        return {str(k): v for k, v in counts.items()}
    except Exception:
        return {}


def _get_total_reuse() -> int:
    """Get total reuse count across all cached competencies."""
    try:
        from src.aps.store import _get_conn
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(reuse_count), 0) FROM assembly_cache"
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0
