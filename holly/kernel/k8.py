"""K8 — Eval Gate.

Task 3a.10 — Minimal K8 eval gate checking one behavioral predicate.
Task 18.4  — Full K8 gate factory: ordered Celestial L0-L4 predicate sweep.

Runs behavioral predicates on an operation's output before allowing
it to proceed.  Halts execution if the output violates any predicate.

State machine (Behavior Spec §1.9)
-----------------------------------
    READY → LOADING_PREDICATE → PREDICATE_LOADED → EVALUATING → PASS
                                                               → FAIL → HALTED
                              → PREDICATE_NOT_FOUND → HALTED
                                                   EVAL_ERROR → HALTED

For the full K8 gate (``k8_gate``), all five Celestial predicates are
evaluated in ascending L0→L4 order; the first failure halts the sweep
immediately (fail-fast / left-to-right ordering).

Usage (standalone — single predicate)::

    from holly.kernel.k8 import k8_evaluate
    k8_evaluate(output, "celestial_constraint_check")

Usage (gate factory — full Celestial sweep)::

    from holly.kernel.k8 import k8_gate
    gate = k8_gate(output=my_output)
    ctx = KernelContext(gates=[gate])
    async with ctx:
        ...

Usage (via decorator)::

    @eval_gated(predicate="celestial_constraint_check")
    def my_boundary_func(payload: dict) -> ...:
        ...  # output is evaluated after this returns

Design constraints
------------------
- Predicate is resolved **once** per call via PredicateRegistry.
- Output is hashed (SHA-256) for audit; original output is NOT
  stored in exceptions to avoid PII leakage (same as K1 pattern).
- Predicates must be deterministic within the same version
  (invariant 3 from Behavior Spec §1.9).
- Celestial predicates are evaluated in strict L0→L4 order; the
  first failure raises immediately (fail-fast).
- Timeout enforcement is left to the caller / KernelContext for
  this implementation (full timeout wiring in Task 18.9).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from holly.kernel.exceptions import (
    EvalError,
    EvalGateFailure,
    PredicateNotFoundError,
)
from holly.kernel.predicate_registry import PredicateRegistry

if TYPE_CHECKING:
    from holly.kernel.context import KernelContext

# ── Type alias ───────────────────────────────────────────

Gate = Callable[["KernelContext"], Awaitable[None]]

# ── Constants ────────────────────────────────────────────

DEFAULT_EVAL_TIMEOUT: int = 5  # seconds (spec §1.9)

# Ordered Celestial predicate IDs (Goal Hierarchy S2.0-2.4, L0->L4).
# Each must be registered in PredicateRegistry before the gate runs.
CELESTIAL_PREDICATE_IDS: tuple[str, ...] = (
    "celestial:L0:authorization_boundary",
    "celestial:L1:system_integrity",
    "celestial:L2:privacy_boundary",
    "celestial:L3:failure_recovery",
    "celestial:L4:agent_autonomy_limit",
)


# ── Helpers ──────────────────────────────────────────────


def _output_hash(output: Any) -> str:
    """SHA-256 of the JSON-serialised output (for audit, not PII)."""
    try:
        raw = json.dumps(output, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = repr(output)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── K8 single-predicate evaluator ────────────────────────


def k8_evaluate(
    output: Any,
    predicate_id: str,
) -> bool:
    """Evaluate *output* against the predicate identified by *predicate_id*.

    Returns ``True`` if the predicate passes (output satisfies the
    behavioral constraint).

    Raises
    ------
    PredicateNotFoundError
        If *predicate_id* is not in the PredicateRegistry.
    EvalError
        If the predicate callable raises an unhandled exception.
    EvalGateFailure
        If the predicate returns ``False`` — the output violates
        the behavioral constraint and must be blocked.
    """
    # ── LOADING_PREDICATE → PREDICATE_LOADED | PREDICATE_NOT_FOUND ─
    predicate = PredicateRegistry.get(predicate_id)  # raises PredicateNotFoundError

    # ── EVALUATING → PASS | FAIL | EVAL_ERROR ──────────────────────
    try:
        result = predicate(output)
    except PredicateNotFoundError:
        # Re-raise registry errors as-is (shouldn't happen here, but
        # defensive — don't wrap kernel errors in EvalError).
        raise
    except Exception as exc:
        raise EvalError(
            predicate_id,
            f"Predicate evaluation failed: {exc}",
        ) from exc

    if not result:
        raise EvalGateFailure(
            predicate_id,
            output_hash=_output_hash(output),
            reason="Output violated eval gate",
        )

    return True


# ── K8 full-sweep gate factory ───────────────────────────


def k8_gate(
    *,
    output: Any,
    predicate_ids: tuple[str, ...] = CELESTIAL_PREDICATE_IDS,
) -> Gate:
    """Return a Gate coroutine-function that runs Celestial predicates in order.

    The gate evaluates each predicate in *predicate_ids* (default: all five
    Celestial levels L0-L4) against *output* in strict ascending order.  The
    first predicate failure halts the sweep immediately (fail-fast).

    Parameters
    ----------
    output:
        The operation output to evaluate.  Must be JSON-serialisable for
        audit hash computation; non-serialisable values are repr()-hashed.
    predicate_ids:
        Ordered sequence of predicate IDs to evaluate.  Defaults to
        ``CELESTIAL_PREDICATE_IDS`` (L0→L4).  Must be non-empty.

    Returns
    -------
    Gate
        An ``async def _k8_gate(ctx: KernelContext) -> None`` coroutine
        function compatible with ``KernelContext(gates=[...])``.

    Raises (when the returned gate is invoked)
    ------------------------------------------
    ValueError
        If *predicate_ids* is empty.
    PredicateNotFoundError
        If any predicate ID is not registered.
    EvalError
        If any predicate callable raises an unhandled exception.
    EvalGateFailure
        If any predicate returns ``False`` (fail-fast; stops at first failure).
    """
    if not predicate_ids:
        msg = "k8_gate requires at least one predicate_id"
        raise ValueError(msg)

    async def _k8_gate(ctx: KernelContext) -> None:
        """K8 Celestial sweep gate: evaluate predicates L0→L4 in order."""
        for pid in predicate_ids:
            k8_evaluate(output, pid)  # raises on first failure; halts sweep

    return _k8_gate
