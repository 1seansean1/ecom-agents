"""Morphogenetic scheduler jobs: periodic trigger checks + developmental snapshots.

Runs every 15 minutes to:
1. Check epsilon-triggers across all goals
2. Execute cascade for any triggered goals
3. Compute and store a developmental snapshot
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def morphogenetic_evaluation_job() -> None:
    """Run the full morphogenetic evaluation cycle.

    Called every 15 minutes by APScheduler. This is the heartbeat of the
    morphogenetic system — it checks whether any goals are failing beyond
    tolerance and triggers the cascade if so.
    """
    try:
        from src.aps.store import get_latest_metrics
        from src.morphogenetic.assembly import get_all_competencies
        from src.morphogenetic.cascade import get_cascade
        from src.morphogenetic.goals import get_default_goal_specs
        from src.morphogenetic.instruments import compute_developmental_snapshot
        from src.morphogenetic.trigger import check_all_triggers

        # 1. Load current state
        goals = get_default_goal_specs()
        metrics_rows = get_latest_metrics()
        metrics = {r["channel_id"]: r for r in metrics_rows}

        # 2. Check epsilon-triggers
        triggers = check_all_triggers(goals, metrics)
        n_triggered = len(triggers)

        if n_triggered > 0:
            logger.info(
                "Morphogenetic: %d goal(s) triggered, executing cascade...",
                n_triggered,
            )

        # 3. Execute cascade for each triggered goal
        cascade = get_cascade()
        goal_map = {g.goal_id: g for g in goals}
        cascade_results = []

        for trigger in triggers:
            goal = goal_map.get(trigger.goal_id)
            if goal is None:
                continue

            result = cascade.execute(trigger, goal, metrics)
            cascade_results.append(result)

            logger.info(
                "Cascade %s: goal=%s channel=%s tier=%s outcome=%s",
                result.cascade_id,
                trigger.goal_id,
                trigger.channel_id,
                result.tier_succeeded,
                result.outcome,
            )

        # 4. Compute and store developmental snapshot
        snapshot = compute_developmental_snapshot(goals, metrics)

        from src.aps.store import store_developmental_snapshot

        store_developmental_snapshot(snapshot.to_dict())

        # 5. Log summary
        n_competencies = len(get_all_competencies())
        logger.info(
            "Morphogenetic snapshot: AI=%.1f CLC=(%d,%d) eta=%.4f "
            "attractors=%d/%d spec_gap=%.4f competencies=%d triggers=%d",
            snapshot.ai_proxy,
            snapshot.clc_horizon,
            snapshot.clc_dimensions,
            snapshot.eta_mean,
            snapshot.attractor_count,
            len(goals),
            snapshot.spec_gap_mean,
            n_competencies,
            n_triggered,
        )

    except Exception:
        logger.warning("Morphogenetic evaluation job failed", exc_info=True)
