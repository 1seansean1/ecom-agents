"""APS Controller: adaptive escalation/de-escalation with UCB and theta caching.

Runs every 5 minutes via APScheduler. For each (goal, channel) pair:
1. Query recent observations
2. Compute p_fail (and UCB for Tier 1 goals)
3. Build confusion matrix → mutual information → channel capacity
4. Compute eta variants (bits/$, bits/token, bits/second)
5. Evaluate escalation/de-escalation decision (with cache check)
6. Store metrics and broadcast events
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from src.aps.channel import (
    build_confusion_matrix,
    channel_capacity_blahut_arimoto,
    compute_eta_variants,
    mutual_information,
)
from src.aps.goals import GOALS, Goal, GoalTier
from src.aps.partitions import get_partition
from src.aps.store import (
    cache_theta,
    get_distinct_paths,
    get_observations_by_path_and_channel,
    get_recent_observations,
    query_theta_cache,
    store_aps_metrics,
    store_theta_switch_event,
)
from src.aps.theta import (
    THETA_REGISTRY,
    get_active_theta,
    get_all_theta_states,
    get_theta_by_channel_and_level,
    set_active_theta,
)

logger = logging.getLogger(__name__)

MIN_OBSERVATIONS = 20
ESCALATION_COOLDOWN = 60.0    # seconds
DE_ESCALATION_COOLDOWN = 300.0


# ---------------------------------------------------------------------------
# UCB confidence bounds (v3: Beta-Binomial posterior)
# ---------------------------------------------------------------------------


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """Approximate I_x(a, b) using continued fraction (Lentz method).

    Good enough for our a, b in [0.5, 50] range.
    """
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    # Use the symmetry relation if needed for convergence
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _regularized_incomplete_beta(1 - x, b, a)

    # Compute log(B(a,b)) via lgamma
    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    prefix = math.exp(a * math.log(x) + b * math.log(1 - x) - log_beta) / a

    # Continued fraction
    result = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    result = d

    for m in range(1, 200):
        # Even step
        numerator = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        result *= d * c

        # Odd step
        numerator = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        result *= delta

        if abs(delta - 1.0) < 1e-10:
            break

    return prefix * result


def _beta_ppf(q: float, a: float, b: float) -> float:
    """Inverse regularized incomplete beta via bisection. Pure Python."""
    lo, hi = 0.0, 1.0
    for _ in range(64):  # ~1e-19 precision
        mid = (lo + hi) / 2
        if _regularized_incomplete_beta(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def compute_p_fail_ucb(failures: int, total: int, confidence: float = 0.95) -> float:
    """Beta-Binomial upper confidence bound with Jeffreys prior.

    Uses Beta(failures + 0.5, successes + 0.5) posterior.
    Returns the confidence-th quantile.
    """
    if total == 0:
        return 1.0
    alpha = failures + 0.5
    beta_param = (total - failures) + 0.5
    return _beta_ppf(confidence, alpha, beta_param)


# ---------------------------------------------------------------------------
# Context fingerprinting (v3: theta caching)
# ---------------------------------------------------------------------------


def get_context_fingerprint(channel_id: str) -> str:
    """Hash of current operational context for theta caching."""
    try:
        from src.resilience.circuit_breaker import get_all_states
        breaker_states = sorted(get_all_states().items())
    except Exception:
        breaker_states = []

    hour = datetime.now(timezone.utc).hour
    if 6 <= hour < 12:
        time_bucket = "morning"
    elif 12 <= hour < 18:
        time_bucket = "afternoon"
    else:
        time_bucket = "night"

    # Simple error regime from recent observations
    obs = get_recent_observations(channel_id, 3600)
    if obs:
        errors = sum(1 for o in obs if o.get("sigma_out", "") in (
            "error", "failure", "malformed", "http_error", "timeout"
        ))
        error_rate = errors / len(obs)
        if error_rate > 0.15:
            error_regime = "high"
        elif error_rate > 0.05:
            error_regime = "medium"
        else:
            error_regime = "low"
    else:
        error_regime = "low"

    fingerprint_str = f"{breaker_states}|{time_bucket}|{error_regime}"
    return hashlib.md5(fingerprint_str.encode()).hexdigest()


# ---------------------------------------------------------------------------
# APS Controller
# ---------------------------------------------------------------------------


class APSController:
    """Adaptive Partition Selection controller.

    Monitors goal-failure rates and adaptively escalates/de-escalates
    theta configurations across all 7 channels.
    """

    def __init__(self):
        self._last_escalation: dict[str, float] = {}   # channel_id -> timestamp
        self._last_deescalation: dict[str, float] = {}  # channel_id -> timestamp

    def evaluate_all(self) -> dict[str, Any]:
        """Run the full APS evaluation cycle.

        Called every 5 minutes by APScheduler.
        Returns summary dict for API/WebSocket broadcast.
        """
        # Apply revenue-aware epsilon modulation before evaluation
        revenue_summary: dict[str, Any] = {}
        try:
            from src.aps.revenue_epsilon import apply_revenue_modulation
            revenue_summary = apply_revenue_modulation()
        except Exception:
            logger.debug("Revenue modulation skipped", exc_info=True)

        now = time.time()
        channel_metrics: dict[str, dict] = {}
        goal_statuses: dict[str, dict] = {}
        switches: list[dict] = []

        all_channels = {"K1", "K2", "K3", "K4", "K5", "K6", "K7"}

        for goal in GOALS:
            goal_failures = 0
            goal_total = 0

            for channel_id in goal.channels:
                if channel_id not in all_channels:
                    continue

                # Get observations
                obs = get_recent_observations(channel_id, goal.window_seconds)
                if not obs:
                    continue

                # Compute p_fail
                failures = sum(1 for o in obs if goal.failure_detector(o))
                total = len(obs)
                p_fail = failures / total if total > 0 else 0.0

                goal_failures += failures
                goal_total += total

                # UCB for mission-critical goals
                p_fail_ucb = None
                if goal.tier == GoalTier.MISSION_CRITICAL:
                    p_fail_ucb = compute_p_fail_ucb(failures, total)

                # Compute info-theoretic metrics if we have enough data
                if channel_id not in channel_metrics:
                    channel_metrics[channel_id] = self._compute_channel_metrics(
                        channel_id, obs, p_fail, p_fail_ucb
                    )

                # Evaluate escalation/de-escalation
                effective_p = p_fail_ucb if p_fail_ucb is not None else p_fail
                switch = self._evaluate_escalation(
                    channel_id, goal, effective_p, total, now
                )
                if switch:
                    switches.append(switch)

            # Aggregate goal status
            goal_p = goal_failures / goal_total if goal_total > 0 else 0.0
            goal_statuses[goal.goal_id.value] = {
                "p_fail": round(goal_p, 4),
                "epsilon_G": goal.epsilon_G,
                "violated": goal_p > goal.epsilon_G if goal.epsilon_G > 0 else goal_failures > 0,
                "tier": goal.tier.value,
            }

        # Compute realized bottlenecks (v3)
        bottlenecks = self._compute_realized_bottlenecks()

        # Broadcast evaluation event
        try:
            from src.events import broadcaster
            broadcaster.broadcast({
                "type": "aps_evaluation",
                "channels": channel_metrics,
                "goals": goal_statuses,
                "switches": switches,
                "realized_bottlenecks": bottlenecks,
                "revenue": revenue_summary,
            })
        except Exception:
            pass

        return {
            "channels": channel_metrics,
            "goals": goal_statuses,
            "switches": switches,
            "realized_bottlenecks": bottlenecks,
            "theta_states": get_all_theta_states(),
            "revenue": revenue_summary,
        }

    def _compute_channel_metrics(
        self,
        channel_id: str,
        obs: list[dict],
        p_fail: float,
        p_fail_ucb: float | None,
    ) -> dict[str, Any]:
        """Compute all info-theoretic metrics for a channel."""
        try:
            theta = get_active_theta(channel_id)
            partition = get_partition(theta.partition_id)

            cm = build_confusion_matrix(
                obs, partition.sigma_in_alphabet, partition.sigma_out_alphabet
            )
            mi = mutual_information(cm)
            cap = channel_capacity_blahut_arimoto(cm)

            total_cost = sum(o.get("cost_usd", 0) or 0 for o in obs)
            total_tokens = sum(o.get("total_tokens", 0) or 0 for o in obs)
            total_time = sum((o.get("latency_ms", 0) or 0) / 1000 for o in obs)

            eta = compute_eta_variants(cap, total_cost, total_tokens, total_time)

            # Store metrics
            store_aps_metrics(
                channel_id=channel_id,
                theta_id=theta.theta_id,
                p_fail=p_fail,
                p_fail_ucb=p_fail_ucb,
                mutual_info=mi,
                capacity=cap,
                eta_usd=eta["eta_usd"],
                eta_token=eta["eta_token"],
                eta_time=eta["eta_time"],
                n_observations=len(obs),
                total_cost_usd=total_cost,
                total_tokens=total_tokens,
                total_time_s=total_time,
                confusion_matrix=cm.counts.tolist() if cm.counts is not None else None,
                window_seconds=max(
                    g.window_seconds for g in GOALS if channel_id in g.channels
                ),
            )

            return {
                "p_fail": round(p_fail, 4),
                "p_fail_ucb": round(p_fail_ucb, 4) if p_fail_ucb is not None else None,
                "mutual_information_bits": round(mi, 4),
                "channel_capacity_bits": round(cap, 4),
                "eta_usd": round(eta["eta_usd"], 2) if eta["eta_usd"] != float("inf") else "inf",
                "eta_token": round(eta["eta_token"], 6) if eta["eta_token"] != float("inf") else "inf",
                "eta_time": round(eta["eta_time"], 4) if eta["eta_time"] != float("inf") else "inf",
                "n_observations": len(obs),
                "total_tokens": total_tokens,
                "active_theta": theta.theta_id,
                "level": theta.level,
            }
        except Exception:
            logger.warning("Failed to compute metrics for %s", channel_id, exc_info=True)
            return {"p_fail": round(p_fail, 4), "error": "metrics_computation_failed"}

    def _evaluate_escalation(
        self,
        channel_id: str,
        goal: Goal,
        effective_p: float,
        n_obs: int,
        now: float,
    ) -> dict | None:
        """Three-level escalation logic with hysteresis and cache check."""
        if n_obs < MIN_OBSERVATIONS:
            return None

        try:
            theta = get_active_theta(channel_id)
        except Exception:
            return None

        current_level = theta.level
        eps = goal.epsilon_G
        if eps == 0.0:
            eps = 0.01  # Practical epsilon for mission-critical goals

        # Check escalation
        if effective_p > 2 * eps and current_level < 2:
            if now - self._last_escalation.get(channel_id, 0) < ESCALATION_COOLDOWN:
                return None
            # Try cache first
            target_level = 2
            cached = self._try_cached_theta(channel_id, target_level)
            if cached:
                return self._apply_switch(channel_id, theta, cached, goal, effective_p, "cache_hit")
            target = get_theta_by_channel_and_level(channel_id, 2)
            if target:
                return self._apply_switch(channel_id, theta, target, goal, effective_p, "escalated")

        elif effective_p > eps and current_level < 1:
            if now - self._last_escalation.get(channel_id, 0) < ESCALATION_COOLDOWN:
                return None
            cached = self._try_cached_theta(channel_id, 1)
            if cached:
                return self._apply_switch(channel_id, theta, cached, goal, effective_p, "cache_hit")
            target = get_theta_by_channel_and_level(channel_id, 1)
            if target:
                return self._apply_switch(channel_id, theta, target, goal, effective_p, "escalated")

        # Check de-escalation
        elif effective_p < eps * 0.5 and current_level > 0:
            if now - self._last_deescalation.get(channel_id, 0) < DE_ESCALATION_COOLDOWN:
                return None
            target_level = current_level - 1
            target = get_theta_by_channel_and_level(channel_id, target_level)
            if target:
                # Cache the successful configuration before de-escalating
                self._cache_successful_theta(channel_id, theta, effective_p)
                return self._apply_switch(
                    channel_id, theta, target, goal, effective_p, "de-escalated"
                )

        return None

    def _apply_switch(
        self,
        channel_id: str,
        from_theta: Any,
        to_theta: Any,
        goal: Goal,
        effective_p: float,
        direction: str,
    ) -> dict:
        """Apply a theta switch and record it."""
        set_active_theta(channel_id, to_theta.theta_id)

        now = time.time()
        if direction in ("escalated", "cache_hit"):
            self._last_escalation[channel_id] = now
        else:
            self._last_deescalation[channel_id] = now

        model_changed = from_theta.model_override != to_theta.model_override
        protocol_changed = from_theta.protocol_level != to_theta.protocol_level

        store_theta_switch_event(
            channel_id=channel_id,
            from_theta=from_theta.theta_id,
            to_theta=to_theta.theta_id,
            direction=direction,
            from_level=from_theta.level,
            to_level=to_theta.level,
            model_changed=model_changed,
            protocol_changed=protocol_changed,
            trigger_p_fail=effective_p,
            trigger_epsilon=goal.epsilon_G,
            goal_id=goal.goal_id.value,
        )

        # Broadcast switch event
        try:
            from src.events import broadcaster
            broadcaster.broadcast({
                "type": "aps_theta_switch",
                "channel_id": channel_id,
                "from_theta": from_theta.theta_id,
                "to_theta": to_theta.theta_id,
                "direction": direction,
                "from_level": from_theta.level,
                "to_level": to_theta.level,
                "model_changed": model_changed,
                "protocol_changed": protocol_changed,
                "trigger_p_fail": round(effective_p, 4),
                "trigger_epsilon": goal.epsilon_G,
                "goal_id": goal.goal_id.value,
            })
        except Exception:
            pass

        logger.info(
            "APS switch %s: %s -> %s (%s, p_fail=%.3f, goal=%s)",
            channel_id, from_theta.theta_id, to_theta.theta_id,
            direction, effective_p, goal.goal_id.value,
        )

        return {
            "channel_id": channel_id,
            "from_theta": from_theta.theta_id,
            "to_theta": to_theta.theta_id,
            "direction": direction,
            "from_level": from_theta.level,
            "to_level": to_theta.level,
            "trigger_p_fail": round(effective_p, 4),
            "goal_id": goal.goal_id.value,
        }

    def _try_cached_theta(self, channel_id: str, target_level: int) -> Any | None:
        """Try to find a cached theta for the current context."""
        try:
            ctx = get_context_fingerprint(channel_id)
            cached = query_theta_cache(channel_id, ctx)
            if cached:
                theta = THETA_REGISTRY.get(cached["theta_id"])
                if theta and theta.level >= target_level:
                    logger.info("APS cache hit for %s: %s", channel_id, theta.theta_id)
                    return theta
        except Exception:
            pass
        return None

    def _cache_successful_theta(
        self, channel_id: str, theta: Any, p_fail: float
    ) -> None:
        """Cache a theta that successfully stabilized the channel."""
        try:
            ctx = get_context_fingerprint(channel_id)
            cache_theta(channel_id, theta.theta_id, ctx, p_fail)
            logger.info("APS cached %s for %s (p_fail=%.3f)", theta.theta_id, channel_id, p_fail)
        except Exception:
            pass

    def _compute_realized_bottlenecks(self) -> list[dict]:
        """Compute chain capacity on actually realized paths (v3)."""
        results = []
        try:
            # Use a 1-hour window for bottleneck analysis
            paths = get_distinct_paths(3600)
            for path_id in paths:
                channels = path_id.split(">")
                per_channel: dict[str, float] = {}
                for ch in channels:
                    try:
                        obs = get_observations_by_path_and_channel(path_id, ch, 3600)
                        if len(obs) < 5:  # Need some minimum data
                            continue
                        partition = get_partition(get_active_theta(ch).partition_id)
                        cm = build_confusion_matrix(
                            obs, partition.sigma_in_alphabet, partition.sigma_out_alphabet
                        )
                        cap = channel_capacity_blahut_arimoto(cm)
                        per_channel[ch] = cap
                    except Exception:
                        continue
                if per_channel:
                    bottleneck = min(per_channel, key=per_channel.get)
                    results.append({
                        "path_id": path_id,
                        "chain_capacity": round(min(per_channel.values()), 4),
                        "bottleneck": bottleneck,
                        "per_channel": {k: round(v, 4) for k, v in per_channel.items()},
                    })
        except Exception:
            logger.debug("Failed to compute realized bottlenecks", exc_info=True)
        return results


# Singleton
aps_controller = APSController()
