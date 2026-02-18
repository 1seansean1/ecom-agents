"""K8 Predicate Registry — resolves and caches eval predicates.

Task 3a.10 — K8 eval gate support.

The registry is a process-global, thread-safe store of predicate
callables keyed by predicate identifier (e.g. ``"celestial_constraint_check"``).
Predicates are registered programmatically during application bootstrap
and are immutable once registered (no hot-swap to avoid mid-evaluation
predicate changes).

Design rationale
----------------
- Mirrors ``SchemaRegistry`` for consistency across the kernel layer.
- Deterministic: ``get()`` always returns the same callable for a given ID.
- Thread-safe: uses a lock around the mutable ``_predicates`` dict.
- Predicates are ``Callable[[Any], bool]`` — receive the output and
  return True (pass) or False (fail).  Exceptions during evaluation
  are caught by the K8 gate and raised as ``EvalError``.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

from holly.kernel.exceptions import (
    PredicateAlreadyRegisteredError,
    PredicateNotFoundError,
)


class PredicateRegistry:
    """Process-global K8 predicate registry.

    Class-level singleton — all access goes through class methods.
    """

    _lock: threading.Lock = threading.Lock()
    _predicates: ClassVar[dict[str, Callable[[Any], bool]]] = {}

    # -- mutators (bootstrap only) -----------------------------------------

    @classmethod
    def register(
        cls, predicate_id: str, predicate: Callable[[Any], bool]
    ) -> None:
        """Register a predicate callable for *predicate_id*.

        Parameters
        ----------
        predicate_id:
            Predicate identifier (e.g. ``"celestial_constraint_check"``).
        predicate:
            A callable that accepts one argument (output) and returns bool.

        Raises
        ------
        TypeError
            If *predicate* is not callable.
        PredicateAlreadyRegisteredError
            If *predicate_id* is already registered.
        """
        if not callable(predicate):
            msg = f"Expected callable, got {type(predicate).__name__}"
            raise TypeError(msg)
        with cls._lock:
            if predicate_id in cls._predicates:
                raise PredicateAlreadyRegisteredError(predicate_id)
            cls._predicates[predicate_id] = predicate

    @classmethod
    def clear(cls) -> None:
        """Remove all registered predicates.  Intended for testing only."""
        with cls._lock:
            cls._predicates.clear()

    # -- queries -----------------------------------------------------------

    @classmethod
    def get(cls, predicate_id: str) -> Callable[[Any], bool]:
        """Resolve *predicate_id* to its predicate callable.

        Returns the exact same callable on every call (idempotent).

        Raises
        ------
        PredicateNotFoundError
            If *predicate_id* has not been registered.
        """
        with cls._lock:
            try:
                return cls._predicates[predicate_id]
            except KeyError:
                raise PredicateNotFoundError(predicate_id) from None

    @classmethod
    def has(cls, predicate_id: str) -> bool:
        """Return True if *predicate_id* is registered."""
        with cls._lock:
            return predicate_id in cls._predicates

    @classmethod
    def registered_ids(cls) -> frozenset[str]:
        """Return all registered predicate IDs."""
        with cls._lock:
            return frozenset(cls._predicates)
