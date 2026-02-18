"""K8 — Eval Gate.

Task 3a.10 — Minimal K8 eval gate checking one behavioral predicate.

Runs a behavioral predicate on an operation's output before allowing
it to proceed.  Halts execution if the output violates the predicate.

The gate implements the K8 state machine from Behavior Spec §1.9:

    READY → LOADING_PREDICATE → PREDICATE_LOADED → EVALUATING → PASS
                                                               → FAIL → HALTED
                              → PREDICATE_NOT_FOUND → HALTED
                                                   EVAL_ERROR → HALTED

Usage (standalone)::

    from holly.kernel.k8 import k8_evaluate
    k8_evaluate(output, "celestial_constraint_check")

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
- Timeout enforcement is left to the caller / KernelContext for
  this minimal implementation (full timeout wiring in Task 18.9).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from holly.kernel.exceptions import (
    EvalError,
    EvalGateFailure,
    PredicateNotFoundError,
)
from holly.kernel.predicate_registry import PredicateRegistry

# ── Constants ────────────────────────────────────────────

DEFAULT_EVAL_TIMEOUT: int = 5  # seconds (spec §1.9)


# ── Helpers ──────────────────────────────────────────────


def _output_hash(output: Any) -> str:
    """SHA-256 of the JSON-serialised output (for audit, not PII)."""
    try:
        raw = json.dumps(output, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = repr(output)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── K8 Gate ──────────────────────────────────────────────


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
