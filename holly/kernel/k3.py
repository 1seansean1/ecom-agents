"""K3 Bounds Checking Gate — resource budget enforcement for KernelContext.

Task 16.5 — K3 bounds checking per TLA+.

K3 validates resource consumption within allocated budgets.  It prevents
any single boundary crossing from exhausting quotas and ensures per-tenant
resource isolation.

Resource model
--------------
Budgets are keyed by ``(tenant_id, resource_type)`` and stored in
``BudgetRegistry``.  Current usage is tracked by a ``UsageTracker``
implementation (in-memory by default; swap for Redis in production).

Usage
-----
>>> gate = k3_gate("tenant-a", "tokens", requested=500)
>>> ctx = KernelContext(gates=[gate])
>>> async with ctx:
...     pass  # only reaches here if 500 tokens are within budget

Traces to: Behavior Spec §1.4 K3, TLA+ spec §14.1, KernelContext §15.4.
SIL: 3
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from holly.kernel.budget_registry import BudgetRegistry
from holly.kernel.exceptions import (
    BoundsExceeded,
    UsageTrackingError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from holly.kernel.context import KernelContext


# ---------------------------------------------------------------------------
# UsageTracker protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class UsageTracker(Protocol):
    """Protocol for resource usage stores.

    Implementors track cumulative usage per (tenant, resource_type).
    If the store is unavailable, raise ``UsageTrackingError`` so K3 can
    apply fail-safe deny semantics.
    """

    def get_usage(self, tenant_id: str, resource_type: str) -> int:
        """Return current usage (``>= 0``).

        Raises
        ------
        holly.kernel.exceptions.UsageTrackingError
            If the store is unavailable.
        """
        ...

    def increment(self, tenant_id: str, resource_type: str, amount: int) -> None:
        """Atomically increment usage by *amount*.

        Raises
        ------
        holly.kernel.exceptions.UsageTrackingError
            If the store is unavailable.
        """
        ...


class InMemoryUsageTracker:
    """Thread-safe in-memory usage tracker.

    Suitable for unit tests and single-process deployments.  In
    production, replace with a Redis-backed implementation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._usage: dict[tuple[str, str], int] = {}

    def get_usage(self, tenant_id: str, resource_type: str) -> int:
        with self._lock:
            return self._usage.get((tenant_id, resource_type), 0)

    def increment(self, tenant_id: str, resource_type: str, amount: int) -> None:
        with self._lock:
            key = (tenant_id, resource_type)
            self._usage[key] = self._usage.get(key, 0) + amount

    def reset(self, tenant_id: str | None = None, resource_type: str | None = None) -> None:
        """Reset usage counters (for test isolation).

        If both *tenant_id* and *resource_type* are given, reset only that key.
        If only *tenant_id* is given, reset all resources for that tenant.
        If neither is given, reset all counters.
        """
        with self._lock:
            if tenant_id is not None and resource_type is not None:
                self._usage.pop((tenant_id, resource_type), None)
            elif tenant_id is not None:
                to_remove = [k for k in self._usage if k[0] == tenant_id]
                for k in to_remove:
                    del self._usage[k]
            else:
                self._usage.clear()


class FailUsageTracker:
    """Usage tracker that always raises ``UsageTrackingError``.

    Used in tests to verify K3 fail-safe deny semantics when the usage
    store is unavailable.
    """

    def get_usage(self, tenant_id: str, resource_type: str) -> int:
        raise UsageTrackingError("tracker unavailable (FailUsageTracker)")

    def increment(self, tenant_id: str, resource_type: str, amount: int) -> None:
        raise UsageTrackingError("tracker unavailable (FailUsageTracker)")


# Default singleton tracker — swap per-deployment
_DEFAULT_TRACKER: UsageTracker = InMemoryUsageTracker()


def get_default_tracker() -> InMemoryUsageTracker:
    """Return the process-level default ``InMemoryUsageTracker``."""
    return _DEFAULT_TRACKER  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Core check function
# ---------------------------------------------------------------------------


def k3_check_bounds(
    tenant_id: str,
    resource_type: str,
    requested: int,
    *,
    budget_registry: BudgetRegistry | None = None,
    usage_tracker: UsageTracker | None = None,
) -> None:
    """Validate that *requested* units of *resource_type* are within budget.

    Steps (in order):
    1. Validate *requested* is non-negative.
    2. Resolve budget limit from *budget_registry* (``BudgetNotFoundError`` on miss).
    3. Validate budget limit is non-negative (``InvalidBudgetError`` on failure).
    4. Fetch current usage from *usage_tracker* (``UsageTrackingError`` on failure).
    5. Validate current usage is non-negative (``UsageTrackingError`` on corruption).
    6. Check ``current + requested > budget`` → ``BoundsExceeded``.
    7. Atomically increment usage by *requested*.

    Parameters
    ----------
    tenant_id:
        Tenant identifier.
    resource_type:
        Resource type string (e.g. ``"tokens"``).
    requested:
        Amount being requested.  Must be ``>= 0``.
    budget_registry:
        Budget store.  Defaults to the class-level ``BudgetRegistry``.
    usage_tracker:
        Usage store.  Defaults to the process-level ``InMemoryUsageTracker``.

    Raises
    ------
    ValueError
        If *requested* is negative.
    holly.kernel.exceptions.BudgetNotFoundError
        No budget configured for (tenant, resource_type).
    holly.kernel.exceptions.InvalidBudgetError
        Budget limit is negative (config error).
    holly.kernel.exceptions.UsageTrackingError
        Usage tracker unavailable, or usage counter corrupted.
    holly.kernel.exceptions.BoundsExceeded
        current_usage + requested > budget_limit.
    """
    # Step 1: validate requested
    if requested < 0:
        raise ValueError(f"requested amount must be >= 0, got {requested}")

    # Step 2: resolve budget (registry defaults to class-level singleton)
    reg = budget_registry if budget_registry is not None else BudgetRegistry
    budget_limit = reg.get(tenant_id, resource_type)  # may raise BudgetNotFoundError

    # Step 3: validate budget limit (already enforced on register, but guard corruption)
    if budget_limit < 0:
        from holly.kernel.exceptions import InvalidBudgetError

        raise InvalidBudgetError(tenant_id, resource_type, limit=budget_limit)

    # Step 4: fetch current usage
    tracker = usage_tracker if usage_tracker is not None else _DEFAULT_TRACKER
    current = tracker.get_usage(tenant_id, resource_type)  # may raise UsageTrackingError

    # Step 5: validate current usage
    if current < 0:
        raise UsageTrackingError(
            f"usage counter for tenant={tenant_id!r} resource={resource_type!r} "
            f"is negative ({current}): data corruption"
        )

    # Step 6: bounds check
    remaining = budget_limit - current
    if current + requested > budget_limit:
        raise BoundsExceeded(
            tenant_id=tenant_id,
            resource_type=resource_type,
            budget=budget_limit,
            current=current,
            requested=requested,
            remaining=remaining,
        )

    # Step 7: atomically increment
    tracker.increment(tenant_id, resource_type, requested)


# ---------------------------------------------------------------------------
# Gate factory
# ---------------------------------------------------------------------------


def k3_gate(
    tenant_id: str,
    resource_type: str,
    requested: int,
    *,
    budget_registry: BudgetRegistry | None = None,
    usage_tracker: UsageTracker | None = None,
) -> Callable[[KernelContext], Awaitable[None]]:
    """Return a Gate that enforces K3 bounds for *tenant_id* and *resource_type*.

    The returned gate is an async callable conforming to the
    ``Gate = Callable[[KernelContext], Awaitable[None]]`` protocol.

    Parameters
    ----------
    tenant_id:
        Tenant identifier for budget lookup.
    resource_type:
        Resource type string (e.g. ``"tokens"``).
    requested:
        Amount being requested in this crossing.
    budget_registry:
        Budget store.  Defaults to class-level ``BudgetRegistry``.
    usage_tracker:
        Usage store.  Defaults to process-level ``InMemoryUsageTracker``.

    Returns
    -------
    Gate
        Async callable ``async def gate(ctx: KernelContext) -> None``.

    Examples
    --------
    >>> gate = k3_gate("tenant-a", "tokens", 500)
    >>> ctx = KernelContext(gates=[gate])
    >>> async with ctx:
    ...     pass
    """

    async def _k3_gate(ctx: KernelContext) -> None:
        k3_check_bounds(
            tenant_id,
            resource_type,
            requested,
            budget_registry=budget_registry,
            usage_tracker=usage_tracker,
        )

    return _k3_gate
