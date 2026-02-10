"""Execution limits and budget enforcement for graph invocations.

Prevents runaway costs and infinite loops by enforcing:
- Max iterations (20)
- Max execution time (120s)
- Max cost per invocation ($1.00)
- Max tokens per invocation (50,000)
- Loop detection (3 consecutive identical outputs)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExecutionBudget:
    """Budget limits for a single graph invocation."""

    max_iterations: int = 20
    max_time_seconds: float = 120.0
    max_cost_usd: float = 1.00
    max_tokens: int = 50_000

    @classmethod
    def from_revenue(cls) -> "ExecutionBudget":
        """Create a budget scaled to the current revenue phase.

        Survival  -> $0.05 cap, 20k tokens
        Conservative -> $0.15 cap, 30k tokens
        Steady    -> $0.50 cap, 50k tokens (default)
        Growth    -> $1.00 cap, 80k tokens
        """
        try:
            from src.aps.revenue_epsilon import get_revenue_cost_budget, get_revenue_phase, RevenuePhase

            cost = get_revenue_cost_budget()
            phase = get_revenue_phase()
            tokens = {
                RevenuePhase.SURVIVAL: 20_000,
                RevenuePhase.CONSERVATIVE: 30_000,
                RevenuePhase.STEADY: 50_000,
                RevenuePhase.GROWTH: 80_000,
            }.get(phase, 50_000)

            return cls(max_cost_usd=cost, max_tokens=tokens)
        except Exception:
            return cls()  # defaults


class BudgetExhaustedError(Exception):
    """Raised when an execution budget limit is hit."""

    def __init__(self, reason: str, budget_report: dict):
        self.reason = reason
        self.budget_report = budget_report
        super().__init__(f"Budget exhausted: {reason}")


@dataclass
class BudgetTracker:
    """Tracks resource usage during a graph invocation."""

    budget: ExecutionBudget = field(default_factory=ExecutionBudget)
    iterations: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    start_time: float = field(default_factory=time.time)

    def record(
        self,
        cost_usd: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """Record resource usage for one node execution."""
        self.iterations += 1
        self.total_cost_usd += cost_usd
        self.total_tokens += tokens

    def check(self) -> dict | None:
        """Check if any budget limit is exceeded.

        Returns None if within budget, or a dict with the violation details.
        """
        elapsed = time.time() - self.start_time

        if self.iterations >= self.budget.max_iterations:
            return self._violation(
                f"Max iterations ({self.budget.max_iterations}) exceeded",
                elapsed,
            )
        if elapsed >= self.budget.max_time_seconds:
            return self._violation(
                f"Max time ({self.budget.max_time_seconds}s) exceeded",
                elapsed,
            )
        if self.total_cost_usd >= self.budget.max_cost_usd:
            return self._violation(
                f"Max cost (${self.budget.max_cost_usd:.2f}) exceeded",
                elapsed,
            )
        if self.total_tokens >= self.budget.max_tokens:
            return self._violation(
                f"Max tokens ({self.budget.max_tokens}) exceeded",
                elapsed,
            )
        return None

    def get_report(self) -> dict:
        """Get a summary report of resource usage."""
        elapsed = time.time() - self.start_time
        return {
            "iterations": self.iterations,
            "max_iterations": self.budget.max_iterations,
            "elapsed_seconds": round(elapsed, 1),
            "max_time_seconds": self.budget.max_time_seconds,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "max_cost_usd": self.budget.max_cost_usd,
            "total_tokens": self.total_tokens,
            "max_tokens": self.budget.max_tokens,
        }

    def _violation(self, reason: str, elapsed: float) -> dict:
        report = self.get_report()
        report["violation"] = reason
        logger.warning("Budget violation: %s | %s", reason, report)
        return report


class LoopDetector:
    """Detects infinite loops in graph execution.

    Tracks the last N node outputs and flags loops when:
    - 3 consecutive identical outputs are detected
    - The same node is visited more than 5 times
    """

    def __init__(self, window_size: int = 5):
        self._recent_outputs: deque[str] = deque(maxlen=window_size)
        self._node_visits: dict[str, int] = {}
        self._max_node_visits = 5
        self._consecutive_threshold = 3

    def record(self, node_name: str, output_summary: str) -> str | None:
        """Record a node execution. Returns a loop description if detected, else None."""
        # Track node visits
        self._node_visits[node_name] = self._node_visits.get(node_name, 0) + 1
        if self._node_visits[node_name] > self._max_node_visits:
            reason = f"Node '{node_name}' visited {self._node_visits[node_name]} times (max {self._max_node_visits})"
            logger.warning("Loop detected: %s", reason)
            return reason

        # Track consecutive identical outputs
        self._recent_outputs.append(output_summary)
        if len(self._recent_outputs) >= self._consecutive_threshold:
            recent = list(self._recent_outputs)[-self._consecutive_threshold:]
            if len(set(recent)) == 1:
                reason = f"{self._consecutive_threshold} consecutive identical outputs from '{node_name}'"
                logger.warning("Loop detected: %s", reason)
                return reason

        return None
