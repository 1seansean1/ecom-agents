"""Financial health assessment from Stripe revenue data.

Queries Stripe for revenue, refunds, and balance to compute a FinancialHealth
snapshot.  The snapshot feeds the revenue-aware epsilon controller which decides
how much exploration the system can afford.

When revenue is low / cash is thin  -> epsilon_R ~ 0  (pure exploitation)
When revenue is growing / cash flush -> epsilon_R rises (exploration allowed)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FinancialHealth:
    """Snapshot of the company's financial position."""

    # Current Stripe balance (available + pending) in cents
    cash_balance_cents: int = 0

    # Revenue last 30 days in cents
    revenue_30d_cents: int = 0

    # Revenue last 7 days in cents (for trend calculation)
    revenue_7d_cents: int = 0

    # Revenue previous 30-day window (days 31-60 ago) in cents
    revenue_prev_30d_cents: int = 0

    # Refunds last 30 days in cents
    refunds_30d_cents: int = 0

    # Count of successful charges last 30 days
    charge_count_30d: int = 0

    # Operating cost estimate (LLM API spend last 30 days) in cents
    operating_cost_30d_cents: int = 0

    # Timestamp of this snapshot
    computed_at: float = field(default_factory=time.time)

    # --- Derived metrics (populated by compute_derived()) ---

    # Net revenue (revenue - refunds) last 30d in cents
    net_revenue_30d_cents: int = 0

    # Month-over-month revenue growth rate (-1.0 to +inf)
    revenue_growth_rate: float = 0.0

    # Monthly burn rate estimate in cents
    burn_rate_cents: int = 0

    # Runway in months (cash / burn_rate).  inf if burn_rate <= 0
    runway_months: float = float("inf")

    # Weekly run-rate annualized in cents
    annualized_revenue_cents: int = 0

    def compute_derived(self) -> None:
        """Fill in derived metrics from the raw fields."""
        self.net_revenue_30d_cents = self.revenue_30d_cents - self.refunds_30d_cents

        # Growth rate: (current - previous) / previous
        if self.revenue_prev_30d_cents > 0:
            self.revenue_growth_rate = (
                (self.revenue_30d_cents - self.revenue_prev_30d_cents)
                / self.revenue_prev_30d_cents
            )
        elif self.revenue_30d_cents > 0:
            self.revenue_growth_rate = 1.0  # went from 0 to something
        else:
            self.revenue_growth_rate = 0.0

        # Burn rate: we use LLM API costs as the primary operating cost
        self.burn_rate_cents = self.operating_cost_30d_cents

        # Runway: cash / monthly burn
        if self.burn_rate_cents > 0:
            self.runway_months = self.cash_balance_cents / self.burn_rate_cents
        else:
            self.runway_months = float("inf")

        # Annualized: 7-day revenue * 52
        self.annualized_revenue_cents = self.revenue_7d_cents * 52


# ---------------------------------------------------------------------------
# Stripe data fetcher
# ---------------------------------------------------------------------------

# Cache the latest health snapshot (refreshed by scheduled job)
_latest_health: FinancialHealth | None = None


def get_latest_health() -> FinancialHealth:
    """Return the most recent financial health snapshot, or a zero snapshot."""
    if _latest_health is not None:
        return _latest_health
    h = FinancialHealth()
    h.compute_derived()
    return h


def fetch_financial_health() -> FinancialHealth:
    """Query Stripe for current financial data and return a FinancialHealth.

    If Stripe is unavailable or no key is configured, returns a conservative
    zero-state snapshot (which maps to epsilon_R = 0).
    """
    global _latest_health

    api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not api_key:
        logger.warning("No STRIPE_SECRET_KEY — returning zero financial health")
        h = FinancialHealth()
        h.compute_derived()
        _latest_health = h
        return h

    try:
        import stripe

        client = stripe.StripeClient(api_key=api_key)
        now = int(time.time())

        # --- Balance ---
        balance = client.balance.retrieve()
        available = sum(b.get("amount", 0) for b in (balance.available or []))
        pending = sum(b.get("amount", 0) for b in (balance.pending or []))
        cash_balance = available + pending

        # --- Charges last 30 days ---
        since_30d = now - (30 * 86400)
        charges_30d = _paginate_charges(client, since_30d, now)
        revenue_30d = sum(c.amount for c in charges_30d if c.status == "succeeded")
        refunds_30d = sum(c.amount_refunded for c in charges_30d)
        charge_count = sum(1 for c in charges_30d if c.status == "succeeded")

        # --- Charges last 7 days (for weekly run-rate) ---
        since_7d = now - (7 * 86400)
        charges_7d = [c for c in charges_30d if (c.created or 0) >= since_7d]
        revenue_7d = sum(c.amount for c in charges_7d if c.status == "succeeded")

        # --- Previous 30d window (days 31-60) ---
        since_60d = now - (60 * 86400)
        charges_prev = _paginate_charges(client, since_60d, since_30d)
        revenue_prev_30d = sum(c.amount for c in charges_prev if c.status == "succeeded")

        # --- Operating costs (estimated from APS observation logs) ---
        operating_cost = _estimate_operating_costs()

        h = FinancialHealth(
            cash_balance_cents=cash_balance,
            revenue_30d_cents=revenue_30d,
            revenue_7d_cents=revenue_7d,
            revenue_prev_30d_cents=revenue_prev_30d,
            refunds_30d_cents=refunds_30d,
            charge_count_30d=charge_count,
            operating_cost_30d_cents=operating_cost,
        )
        h.compute_derived()
        _latest_health = h

        logger.info(
            "Financial health updated: cash=$%.2f, rev30d=$%.2f, growth=%.1f%%, runway=%.1f mo",
            cash_balance / 100,
            revenue_30d / 100,
            h.revenue_growth_rate * 100,
            h.runway_months,
        )
        return h

    except Exception:
        logger.warning("Failed to fetch financial health from Stripe", exc_info=True)
        h = FinancialHealth()
        h.compute_derived()
        _latest_health = h
        return h


def _paginate_charges(client: Any, since: int, until: int) -> list:
    """Fetch all charges in a time range, paginating if needed."""
    all_charges: list = []
    params: dict = {
        "created": {"gte": since, "lt": until},
        "limit": 100,
    }
    try:
        result = client.charges.list(params=params)
        all_charges.extend(result.data)
        # For a small business, 100 charges per 30 days is plenty.
        # If more, paginate:
        while result.has_more and len(all_charges) < 1000:
            params["starting_after"] = result.data[-1].id
            result = client.charges.list(params=params)
            all_charges.extend(result.data)
    except Exception:
        logger.warning("Charge pagination failed", exc_info=True)
    return all_charges


def _estimate_operating_costs() -> int:
    """Estimate monthly LLM operating costs from APS observation logs.

    Returns cost in cents.
    """
    try:
        from src.aps.store import get_recent_observations

        # Sum cost_usd from all channels over last 30 days
        total_cost_usd = 0.0
        for ch in ["K1", "K2", "K3", "K4", "K5", "K6", "K7"]:
            obs = get_recent_observations(ch, 30 * 86400)
            total_cost_usd += sum(o.get("cost_usd", 0) or 0 for o in obs)
        return int(total_cost_usd * 100)
    except Exception:
        return 0
