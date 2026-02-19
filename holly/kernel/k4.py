"""K4 — Trace injection gate (Task 16.6).

Injects correlation ID and tenant ID into every boundary crossing,
enabling distributed tracing and tenant isolation auditing.

Traces to:
    Behavior Spec §1.5 K4  docs/Component_Behavior_Specs_SIL3.md
    TLA+ spec              docs/tla/KernelInvariants.tla  (Task 14.1)
    FMEA-K004              docs/FMEA_Kernel_Invariants.md

SIL: 3  (docs/SIL_Classification_Matrix.md)

Public surface
--------------
* ``k4_inject_trace`` — standalone trace-ID resolution (pure, no side effects).
* ``k4_gate``          — Gate-compatible factory for ``KernelContext``.

State machine (Behavior Spec §1.5 K4):

    INIT → EXTRACT_TENANT
    EXTRACT_TENANT → TENANT_FOUND | TENANT_MISSING
    TENANT_FOUND → RESOLVE_CORRELATION
    RESOLVE_CORRELATION → CORRELATION_PROVIDED | CORRELATION_GENERATED
    CORRELATION_PROVIDED / CORRELATION_GENERATED → INJECTING → INJECTED → IDLE
    TENANT_MISSING → FAULTED  (raises TenantContextError)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from holly.kernel.exceptions import TenantContextError

if TYPE_CHECKING:
    from holly.kernel.context import KernelContext

# ---------------------------------------------------------------------------
# Gate type alias (mirrors context.Gate — repeated to avoid circular import)
# ---------------------------------------------------------------------------

Gate = Callable[["KernelContext"], Awaitable[None]]


# ---------------------------------------------------------------------------
# Standalone function
# ---------------------------------------------------------------------------


def k4_inject_trace(
    claims: dict[str, Any] | None,
    *,
    provided_correlation_id: str | None = None,
    context_corr_id: str | None = None,
) -> tuple[str, str]:
    """Validate claims and resolve trace IDs without mutating any context.

    Steps
    -----
    1. Validate ``claims`` is not None; extract ``tenant_id``.
    2. Resolve correlation ID:

       * If ``provided_correlation_id`` is given, validate its UUID format
         and use it.
       * Otherwise use ``context_corr_id`` if given, else generate a new
         UUID4 string.

    3. Return ``(correlation_id, tenant_id)``.

    The caller (typically ``k4_gate``) is responsible for injecting the
    returned IDs into the ``KernelContext`` via ``ctx._set_trace()``.

    Parameters
    ----------
    claims:
        Pre-decoded JWT claims dict.  Must contain ``'tenant_id'``.
    provided_correlation_id:
        Caller-supplied correlation ID override.  Must be a valid UUID4
        string if provided; raises ``ValueError`` otherwise.
    context_corr_id:
        The auto-generated ``corr_id`` from ``KernelContext.__init__``.
        Used as the correlation ID when ``provided_correlation_id`` is
        ``None``.  If both are ``None``, a fresh UUID4 is generated.

    Returns
    -------
    tuple[str, str]
        ``(correlation_id, tenant_id)`` — both non-empty strings.

    Raises
    ------
    TenantContextError
        If ``claims`` is ``None`` or lacks a non-empty ``tenant_id`` claim.
    ValueError
        If ``provided_correlation_id`` is not a valid UUID format.
    """
    # ── Step 1: Extract tenant_id ─────────────────────────────────────────
    if claims is None:
        raise TenantContextError("JWT claims are None; cannot extract tenant_id")

    tenant_id: str | None = claims.get("tenant_id")  # type: ignore[assignment]
    if not tenant_id:
        raise TenantContextError(
            "JWT missing tenant_id claim; every boundary crossing requires tenant context"
        )

    # ── Step 2: Resolve correlation ID ───────────────────────────────────
    if provided_correlation_id is not None:
        # Validate UUID format before accepting
        try:
            uuid.UUID(provided_correlation_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"Invalid correlation ID format: {provided_correlation_id!r}; "
                "must be a valid UUID string"
            ) from exc
        correlation_id: str = provided_correlation_id
    elif context_corr_id is not None:
        # Use the auto-generated UUID from KernelContext.__init__
        correlation_id = context_corr_id
    else:
        # Fallback: generate a fresh UUID (standalone usage without a context)
        correlation_id = str(uuid.uuid4())

    return correlation_id, tenant_id


# ---------------------------------------------------------------------------
# Gate factory
# ---------------------------------------------------------------------------


def k4_gate(
    claims: dict[str, Any] | None,
    *,
    provided_correlation_id: str | None = None,
) -> Gate:
    """Return a Gate that injects correlation and tenant IDs into context.

    The returned gate runs during ``KernelContext.__aenter__`` (context is
    in ENTERING state).  On success, ``ctx.tenant_id``, ``ctx.corr_id``,
    and ``ctx.trace_started_at`` are all populated before the context
    transitions to ACTIVE.

    On failure (missing tenant_id or invalid correlation_id), the gate
    raises and the context advances ENTERING → FAULTED → IDLE
    (TLA+ EventuallyIdle).

    Parameters
    ----------
    claims:
        Pre-decoded JWT claims dict.
    provided_correlation_id:
        Optional caller-supplied correlation ID override (validated UUID).

    Returns
    -------
    Gate
        Async callable ``gate(ctx: KernelContext) -> None``.
    """

    async def _k4_gate(ctx: KernelContext) -> None:
        corr_id, tenant_id = k4_inject_trace(
            claims,
            provided_correlation_id=provided_correlation_id,
            context_corr_id=ctx.corr_id,
        )
        ctx._set_trace(tenant_id, corr_id, time.monotonic())

    return _k4_gate
