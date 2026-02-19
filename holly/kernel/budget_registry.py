"""K3 Budget Registry — per-tenant, per-resource budget limit store.

Task 16.5 — K3 bounds checking per TLA+.

Thread-safe class-level singleton following the same pattern as
``SchemaRegistry`` and ``PermissionRegistry``.

Traces to: Behavior Spec §1.4 K3, TLA+ spec §14.1.
"""

from __future__ import annotations

import threading
from typing import ClassVar


class BudgetRegistry:
    """Class-level registry mapping (tenant_id, resource_type) → budget limit.

    All methods are class methods; no instantiation is required.  A
    ``threading.Lock`` guards all mutation operations.

    Budget limits must be non-negative integers (``>= 0``).  A limit of
    ``0`` means any non-zero request is immediately rejected.

    Examples
    --------
    >>> BudgetRegistry.register("tenant-a", "tokens", 10_000)
    >>> BudgetRegistry.get("tenant-a", "tokens")
    10000
    """

    # Key: (tenant_id, resource_type)
    _registry: ClassVar[dict[tuple[str, str], int]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, tenant_id: str, resource_type: str, limit: int) -> None:
        """Register a budget limit for *(tenant_id, resource_type)*.

        Parameters
        ----------
        tenant_id:
            Tenant identifier string.
        resource_type:
            Resource type string (e.g. ``"tokens"``, ``"cpu_ms"``).
        limit:
            Maximum allowed cumulative usage.  Must be ``>= 0``.

        Raises
        ------
        holly.kernel.exceptions.InvalidBudgetError
            If *limit* is negative.
        ValueError
            If the budget is already registered (re-registration not permitted).
        """
        from holly.kernel.exceptions import InvalidBudgetError

        if limit < 0:
            raise InvalidBudgetError(tenant_id, resource_type, limit=limit)

        with cls._lock:
            key = (tenant_id, resource_type)
            if key in cls._registry:
                raise ValueError(
                    f"Budget for tenant={tenant_id!r} resource={resource_type!r} "
                    f"is already registered"
                )
            cls._registry[key] = limit

    @classmethod
    def clear(cls) -> None:
        """Remove all registered budgets (primarily for test isolation)."""
        with cls._lock:
            cls._registry.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, tenant_id: str, resource_type: str) -> int:
        """Return the budget limit for *(tenant_id, resource_type)*.

        Parameters
        ----------
        tenant_id:
            Tenant identifier.
        resource_type:
            Resource type to look up.

        Returns
        -------
        int
            The configured budget limit (``>= 0``).

        Raises
        ------
        holly.kernel.exceptions.BudgetNotFoundError
            If no budget is registered for the (tenant, resource_type) pair.
        """
        from holly.kernel.exceptions import BudgetNotFoundError

        with cls._lock:
            try:
                return cls._registry[(tenant_id, resource_type)]
            except KeyError:
                raise BudgetNotFoundError(tenant_id, resource_type) from None

    @classmethod
    def has_budget(cls, tenant_id: str, resource_type: str) -> bool:
        """Return ``True`` if a budget is registered for the pair."""
        with cls._lock:
            return (tenant_id, resource_type) in cls._registry

    @classmethod
    def registered_keys(cls) -> frozenset[tuple[str, str]]:
        """Return a snapshot of all registered (tenant_id, resource_type) keys."""
        with cls._lock:
            return frozenset(cls._registry)
