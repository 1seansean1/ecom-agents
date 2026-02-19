"""KernelContext — async context manager for boundary crossings.

Tasks 15.4 & 16.6 — Implement per TLA+ state machine spec; K4 trace slots.

Traces to:
    TLA+ spec  docs/tla/KernelInvariants.tla  (Task 14.1)
    Formal validator  holly/kernel/state_machine.py  (Task 14.5)
    Behavior Spec §1.1  KernelContext state machine
    FMEA-K001  docs/FMEA_Kernel_Invariants.md

SIL: 3  (docs/SIL_Classification_Matrix.md)

Every boundary crossing in Holly is wrapped in a ``KernelContext`` instance.
The context is the unit of atomicity for kernel invariant enforcement.

State machine (mirrors KernelInvariants.tla exactly):

    IDLE --> ENTERING  : __aenter__ called
    ENTERING --> ACTIVE  : all gates pass
    ENTERING --> FAULTED  : any gate raises
    ACTIVE --> EXITING  : operation completes
    ACTIVE --> FAULTED  : exception during operation
    EXITING --> IDLE  : exit cleanup succeeds
    EXITING --> FAULTED  : exit cleanup raises

    FAULTED --> IDLE  : exception consumed (within __aenter__ or __aexit__)

After every ``async with KernelContext(...):`` block, the validator is
always back in IDLE — regardless of which path was taken — while the
exception still propagates to the caller.  This satisfies the TLA+
liveness property ``EventuallyIdle: []<>(kstate = IDLE)``.

Gate protocol
-------------
A gate is an async callable::

    async def gate(ctx: KernelContext) -> None: ...

Gates MUST return without raising to indicate PASS, and raise
``KernelError`` (or any exception) to indicate FAIL.
K1-K8 gates are wired in Tasks 16-18.

Design constraints (Behavior Spec §1.1):
    INV-4  Guard evaluation is pure and deterministic.
    INV-5  ACTIVE requires all gates to have passed.
    FM-001-2  FAULTED is never silently discarded; exception always propagates.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from holly.kernel.state_machine import (
    KernelEvent,
    KernelState,
    KernelStateMachineValidator,
)

if TYPE_CHECKING:
    from types import TracebackType

# ---------------------------------------------------------------------------
# Gate type alias
# ---------------------------------------------------------------------------

#: A gate is an async callable that receives the active context.
#: It returns None on PASS and raises on FAIL.
Gate = Callable[["KernelContext"], Awaitable[None]]


# ---------------------------------------------------------------------------
# KernelContext
# ---------------------------------------------------------------------------


class KernelContext:
    """Async context manager that enforces kernel invariants at boundary crossings.

    Usage::

        async with KernelContext(gates=[k1_validate_gate, k8_eval_gate]) as ctx:
            result = await cross_boundary(payload)

    Parameters
    ----------
    gates:
        Sequence of async gate callables executed during ``__aenter__``.
        Executed in order; first failure aborts entry (Behavior Spec §1.1 INV-5).
        Default: empty — the bare lifecycle is exercised with no gates
        (used by Tasks 14.5 and 15.4; K1-K8 wired in Tasks 16-18).
    corr_id:
        Correlation ID for this boundary crossing.  Auto-generated (UUID4)
        if not supplied (Behavior Spec §1.1 K4 / INV-6).

    Invariants
    ----------
    * ``self.state`` is always a member of ``KernelState``.
    * After every ``async with`` block, ``self.state`` is IDLE.
    * An exception in ``__aenter__`` means ``__aexit__`` is NOT invoked
      by Python; the context internally advances FAULTED→IDLE before
      re-raising to satisfy the liveness property.
    """

    __slots__ = ("_corr_id", "_gates", "_tenant_id", "_trace_started_at", "_validator")

    def __init__(
        self,
        *,
        gates: Sequence[Gate] = (),
        corr_id: str | None = None,
    ) -> None:
        self._gates: tuple[Gate, ...] = tuple(gates)
        self._corr_id: str = corr_id if corr_id is not None else str(uuid.uuid4())
        self._tenant_id: str | None = None
        self._trace_started_at: float | None = None
        self._validator: KernelStateMachineValidator = KernelStateMachineValidator()

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> KernelState:
        """Current KernelContext state (read-only)."""
        return self._validator.state

    @property
    def corr_id(self) -> str:
        """Correlation ID for this boundary crossing (read-only)."""
        return self._corr_id

    @property
    def tenant_id(self) -> str | None:
        """Tenant ID injected by K4 gate (``None`` before injection).

        Read-only after K4 sets it; no subsequent operation may change it
        (Behavior Spec §1.5 K4 invariant 3).
        """
        return self._tenant_id

    @property
    def trace_started_at(self) -> float | None:
        """Monotonic timestamp (``time.monotonic()``) when K4 injected trace.

        ``None`` before K4 gate runs.
        """
        return self._trace_started_at

    # ------------------------------------------------------------------
    # Internal trace-injection interface (K4 only)
    # ------------------------------------------------------------------

    def _set_trace(self, tenant_id: str, corr_id: str, started_at: float) -> None:
        """Inject K4 trace metadata.  Called exclusively by ``k4_inject_trace``.

        Parameters
        ----------
        tenant_id:
            Tenant identifier extracted from JWT claims.
        corr_id:
            Resolved correlation UUID string (validated by K4).
        started_at:
            ``time.monotonic()`` timestamp captured at injection time.
        """
        self._tenant_id = tenant_id
        self._corr_id = corr_id
        self._trace_started_at = started_at

    # ------------------------------------------------------------------
    # Async context manager protocol
    # ------------------------------------------------------------------

    async def __aenter__(self) -> KernelContext:
        """Advance IDLE → ENTERING, run gates, then ENTERING → ACTIVE.

        If any gate raises, the context advances ENTERING → FAULTED →
        IDLE and re-raises the exception.  (Python does NOT invoke
        ``__aexit__`` when ``__aenter__`` raises, so the FAULTED→IDLE
        transition is driven internally here.)

        Returns
        -------
        KernelContext
            Self, to support ``async with KernelContext(...) as ctx:``.

        Raises
        ------
        KernelInvariantError
            If the context is not in IDLE when entered (re-entrancy guard).
        KernelError
            If any gate fails.
        """
        # IDLE → ENTERING (raises KernelInvariantError on re-entry)
        self._validator.advance(KernelEvent.AENTER)

        try:
            for gate in self._gates:
                await gate(self)
            # All gates passed: ENTERING → ACTIVE
            self._validator.advance(KernelEvent.ALL_GATES_PASS)
        except BaseException:
            # Gate failure: ENTERING → FAULTED → IDLE
            # (must close the FAULTED state here because __aexit__ will not fire)
            self._validator.advance(KernelEvent.GATE_FAIL)
            self._validator.advance(KernelEvent.EXC_CONSUMED)
            raise

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Advance from ACTIVE through exit states back to IDLE.

        Called only when ``__aenter__`` succeeded (context is ACTIVE).

        Exception during the with-block
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        ACTIVE → FAULTED (ASYNC_CANCEL event) → IDLE (EXC_CONSUMED).
        Returns False so the exception propagates to the caller.

        Normal exit
        ~~~~~~~~~~~
        ACTIVE → EXITING (OP_COMPLETE), then ``_run_exit_cleanup()``.
        On cleanup success: EXITING → IDLE (EXIT_OK).
        On cleanup failure: EXITING → FAULTED (EXIT_FAIL) → IDLE
        (EXC_CONSUMED), exception re-raised.

        Returns
        -------
        bool
            Always False (never suppress exceptions).

        Raises
        ------
        KernelError
            If exit cleanup raises.  Original ``exc_val`` is lost in
            favour of the cleanup exception per Python exception chaining.
        """
        if exc_type is not None:
            # Exception during the with-block (including CancelledError).
            # ACTIVE → FAULTED → IDLE
            self._validator.advance(KernelEvent.ASYNC_CANCEL)
            self._validator.advance(KernelEvent.EXC_CONSUMED)
            return False  # propagate exception

        # Normal exit path: ACTIVE → EXITING
        self._validator.advance(KernelEvent.OP_COMPLETE)

        try:
            await self._run_exit_cleanup()
            # Cleanup succeeded: EXITING → IDLE
            self._validator.advance(KernelEvent.EXIT_OK)
        except BaseException:
            # Cleanup failed: EXITING → FAULTED → IDLE
            self._validator.advance(KernelEvent.EXIT_FAIL)
            self._validator.advance(KernelEvent.EXC_CONSUMED)
            raise

        return False  # never suppress

    # ------------------------------------------------------------------
    # Exit cleanup (stub; wired in Tasks 17-18)
    # ------------------------------------------------------------------

    async def _run_exit_cleanup(self) -> None:
        """Run exit-phase cleanup: WAL write, trace injection, metrics flush.

        Stub implementation for Task 15.4.  K6 (WAL) is wired in Task 17;
        K4 (trace) and metrics are wired in Tasks 16-18.

        Raises
        ------
        KernelError
            Subclass on any cleanup failure (drives EXITING → FAULTED).
        """

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"KernelContext("
            f"state={self._validator.state.value!r}, "
            f"corr_id={self._corr_id!r}, "
            f"tenant_id={self._tenant_id!r}, "
            f"gates={len(self._gates)})"
        )
