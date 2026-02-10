"""APS scheduler job for periodic evaluation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def aps_evaluation_job() -> None:
    """Run the APS evaluation cycle. Called every 5 minutes by APScheduler."""
    try:
        from src.aps.controller import aps_controller
        result = aps_controller.evaluate_all()
        n_channels = len(result.get("channels", {}))
        n_switches = len(result.get("switches", []))
        logger.info(
            "APS evaluation complete: %d channels evaluated, %d switches triggered",
            n_channels, n_switches,
        )
    except Exception:
        logger.warning("APS evaluation job failed", exc_info=True)


def financial_health_job() -> None:
    """Fetch financial health from Stripe and update revenue epsilon. Every 30 min."""
    try:
        from src.aps.financial_health import fetch_financial_health
        from src.aps.revenue_epsilon import compute_epsilon_r, compute_revenue_phase

        health = fetch_financial_health()
        phase = compute_revenue_phase(health)
        epsilon_r = compute_epsilon_r(health)
        logger.info(
            "Financial health: phase=%s, epsilon_R=%.3f, cash=$%.2f, rev30d=$%.2f",
            phase,
            epsilon_r,
            health.cash_balance_cents / 100,
            health.revenue_30d_cents / 100,
        )
    except Exception:
        logger.warning("Financial health job failed", exc_info=True)


def efficacy_aggregation_job() -> None:
    """Aggregate APS observations into agent efficacy rows. Called every 30 minutes."""
    try:
        from src.aps.store import compute_agent_efficacy
        count = compute_agent_efficacy(days=30)
        logger.info("Efficacy aggregation complete: %d rows inserted", count)
    except Exception:
        logger.warning("Efficacy aggregation job failed", exc_info=True)
