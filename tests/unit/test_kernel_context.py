"""Tests for holly.kernel.context — KernelContext async context manager.

Task 15.4 — Implement per TLA+ state machine spec.

Covers:
    State-machine lifecycle        — all four paths (happy, gate-fail, async-cancel, exit-fail)
    State invariants               — state always in KernelState; always IDLE after block
    Gate evaluation                — pass/fail, ordering, first-fail-aborts
    Correlation ID                 — auto-generated UUID4 / explicit passthrough
    Re-entrancy prevention         — second enter raises KernelInvariantError
    __aexit__ never suppresses     — always returns False
    Exception identity             — original exception propagates unchanged
    Repr                           — contains state, corr_id, gate count
    Property-based                 — Hypothesis over random gate-fail positions

Test taxonomy
-------------
Structure    verify module exports KernelContext; Gate type is callable
Lifecycle    four state-machine paths end in IDLE; state transitions match TLA+ spec
Gates        ordered execution; first failure stops remaining gates
CorrId       UUID auto-gen; explicit passthrough; read-only
ReEntry      KernelInvariantError on second __aenter__ from non-IDLE state
Suppress     __aexit__ returns False in all paths
ExcId        exact exception object propagates (no wrapping)
Repr         string representation
Property     Hypothesis: any gate-fail position; always-IDLE postcondition
Invariants   Behavior Spec §1.1 INV-4 (pure), INV-5 (ACTIVE requires all gates passed)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import KernelError, KernelInvariantError
from holly.kernel.state_machine import KernelState

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _passing_gate(ctx: KernelContext) -> None:
    """A gate that always passes."""


def _failing_gate(exc: Exception) -> Callable:
    """Return a gate that always raises *exc*."""

    async def _gate(ctx: KernelContext) -> None:
        raise exc

    return _gate


async def _exit_fail_cleanup(ctx: KernelContext) -> None:
    """Raises to simulate exit-cleanup failure (used via monkeypatching)."""
    raise KernelError("simulated exit cleanup failure")


async def _enter_no_gates() -> KernelContext:
    """Enter a zero-gate KernelContext and return it for state inspection."""
    ctx = KernelContext()
    await ctx.__aenter__()
    return ctx


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestStructure:
    def test_kernel_context_importable(self) -> None:
        assert KernelContext is not None

    def test_default_state_is_idle(self) -> None:
        ctx = KernelContext()
        assert ctx.state == KernelState.IDLE

    def test_corr_id_is_valid_uuid4(self) -> None:
        ctx = KernelContext()
        parsed = uuid.UUID(ctx.corr_id, version=4)
        assert str(parsed) == ctx.corr_id

    def test_explicit_corr_id_is_stored(self) -> None:
        cid = "explicit-corr-id"
        ctx = KernelContext(corr_id=cid)
        assert ctx.corr_id == cid

    def test_corr_id_read_only(self) -> None:
        ctx = KernelContext()
        with pytest.raises(AttributeError):
            ctx.corr_id = "changed"  # type: ignore[misc]

    def test_state_read_only(self) -> None:
        ctx = KernelContext()
        with pytest.raises(AttributeError):
            ctx.state = KernelState.ACTIVE  # type: ignore[misc]

    def test_two_instances_have_different_corr_ids(self) -> None:
        assert KernelContext().corr_id != KernelContext().corr_id


# ---------------------------------------------------------------------------
# Lifecycle: happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_happy_path_state_transitions(self) -> None:
        """IDLE → ENTERING → ACTIVE → EXITING → IDLE."""
        ctx = KernelContext()
        assert ctx.state == KernelState.IDLE

        await ctx.__aenter__()
        assert ctx.state == KernelState.ACTIVE

        await ctx.__aexit__(None, None, None)
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_happy_path_async_with(self) -> None:
        """``async with`` happy-path block; state is IDLE after block."""
        ctx = KernelContext()
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_context_manager_yields_self(self) -> None:
        ctx = KernelContext()
        async with ctx as entered:
            assert entered is ctx

    @pytest.mark.asyncio
    async def test_multiple_crossings_after_idle(self) -> None:
        """A KernelContext in IDLE can be re-entered (sequential crossings)."""
        ctx = KernelContext()
        for _ in range(3):
            async with ctx:
                assert ctx.state == KernelState.ACTIVE
            assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_aexit_returns_false(self) -> None:
        """__aexit__ must return False (never suppress exceptions)."""
        ctx = KernelContext()
        await ctx.__aenter__()
        result = await ctx.__aexit__(None, None, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_aexit_with_exception_returns_false(self) -> None:
        """__aexit__ with exc_type must also return False."""
        ctx = KernelContext()
        await ctx.__aenter__()
        exc = KernelError("boom")
        result = await ctx.__aexit__(type(exc), exc, None)
        assert result is False


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


class TestGateEvaluation:
    @pytest.mark.asyncio
    async def test_zero_gates_happy_path(self) -> None:
        ctx = KernelContext(gates=[])
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_single_passing_gate(self) -> None:
        ctx = KernelContext(gates=[_passing_gate])
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_multiple_passing_gates(self) -> None:
        ctx = KernelContext(gates=[_passing_gate, _passing_gate, _passing_gate])
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_gate_receives_context(self) -> None:
        """Gate must receive the KernelContext as its argument."""
        received: list[KernelContext] = []

        async def spy_gate(ctx: KernelContext) -> None:
            received.append(ctx)

        ctx = KernelContext(gates=[spy_gate])
        async with ctx:
            pass
        assert received == [ctx]

    @pytest.mark.asyncio
    async def test_gate_failure_aborts_entry(self) -> None:
        """Gate failure: state is IDLE after __aenter__ raises."""
        sentinel = KernelError("gate-failed")
        ctx = KernelContext(gates=[_failing_gate(sentinel)])
        with pytest.raises(KernelError) as exc_info:
            async with ctx:
                pass  # should not be reached
        assert exc_info.value is sentinel
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_gate_failure_propagates_exact_exception(self) -> None:
        """The exact exception raised by the gate propagates to the caller."""
        sentinel = KernelError("exact-exc")
        ctx = KernelContext(gates=[_failing_gate(sentinel)])
        with pytest.raises(KernelError) as exc_info:
            await ctx.__aenter__()
        assert exc_info.value is sentinel

    @pytest.mark.asyncio
    async def test_second_gate_not_called_after_first_fails(self) -> None:
        """Failure aborts gate sequence; subsequent gates must not execute."""
        called: list[int] = []

        async def gate_0(ctx: KernelContext) -> None:
            called.append(0)
            raise KernelError("gate0")

        async def gate_1(ctx: KernelContext) -> None:
            called.append(1)

        ctx = KernelContext(gates=[gate_0, gate_1])
        with pytest.raises(KernelError):
            async with ctx:
                pass
        assert called == [0]  # gate_1 never called

    @pytest.mark.asyncio
    async def test_gates_executed_in_order(self) -> None:
        order: list[int] = []

        async def make_gate(n: int) -> None:
            async def _g(ctx: KernelContext) -> None:
                order.append(n)

            return _g  # type: ignore[return-value]

        g0, g1, g2 = await make_gate(0), await make_gate(1), await make_gate(2)
        ctx = KernelContext(gates=[g0, g1, g2])
        async with ctx:
            pass
        assert order == [0, 1, 2]


# ---------------------------------------------------------------------------
# Exception during active operation (ASYNC_CANCEL path)
# ---------------------------------------------------------------------------


class TestExceptionDuringOperation:
    @pytest.mark.asyncio
    async def test_exception_in_with_block_propagates(self) -> None:
        sentinel = KernelError("active-fail")
        ctx = KernelContext()
        with pytest.raises(KernelError) as exc_info:
            async with ctx:
                raise sentinel
        assert exc_info.value is sentinel

    @pytest.mark.asyncio
    async def test_exception_in_with_block_state_is_idle(self) -> None:
        """After exception in with-block, state returns to IDLE."""
        ctx = KernelContext()
        with pytest.raises(KernelError):
            async with ctx:
                raise KernelError("active-fail")
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self) -> None:
        """asyncio.CancelledError propagates unchanged."""
        ctx = KernelContext()
        with pytest.raises(asyncio.CancelledError):
            async with ctx:
                raise asyncio.CancelledError()

    @pytest.mark.asyncio
    async def test_cancelled_error_state_is_idle(self) -> None:
        ctx = KernelContext()
        with pytest.raises(asyncio.CancelledError):
            async with ctx:
                raise asyncio.CancelledError()
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_non_kernel_exception_propagates(self) -> None:
        """Non-KernelError exceptions propagate unchanged."""
        ctx = KernelContext()
        with pytest.raises(ValueError, match="oops"):
            async with ctx:
                raise ValueError("oops")

    @pytest.mark.asyncio
    async def test_non_kernel_exception_state_is_idle(self) -> None:
        ctx = KernelContext()
        with pytest.raises(ValueError):
            async with ctx:
                raise ValueError("oops")
        assert ctx.state == KernelState.IDLE


# ---------------------------------------------------------------------------
# Exit cleanup failure (EXIT_FAIL path)
# ---------------------------------------------------------------------------


class TestExitCleanupFailure:
    @pytest.mark.asyncio
    async def test_exit_cleanup_failure_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If _run_exit_cleanup raises, exception propagates and state is IDLE."""
        monkeypatch.setattr(KernelContext, "_run_exit_cleanup", _exit_fail_cleanup)
        ctx = KernelContext()
        with pytest.raises(KernelError, match="simulated exit cleanup failure"):
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_exit_cleanup_failure_not_suppressed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with no exception in the block, exit failure propagates."""
        monkeypatch.setattr(KernelContext, "_run_exit_cleanup", _exit_fail_cleanup)
        ctx = KernelContext()
        raised = False
        try:
            async with ctx:
                pass
        except KernelError:
            raised = True
        assert raised


# ---------------------------------------------------------------------------
# Re-entrancy prevention (INV — re-entrant entry)
# ---------------------------------------------------------------------------


class TestReEntrancyPrevention:
    @pytest.mark.asyncio
    async def test_enter_from_active_raises(self) -> None:
        """__aenter__ while ACTIVE (re-entrant entry) raises KernelInvariantError."""
        ctx = KernelContext()
        await ctx.__aenter__()
        assert ctx.state == KernelState.ACTIVE
        with pytest.raises(KernelInvariantError):
            await ctx.__aenter__()
        # State rolls back to IDLE (AENTER raises from ACTIVE,
        # which is not in VALID_TRANSITIONS — state_machine raises before
        # any state change, so validator stays ACTIVE; we just verify it
        # did not advance further)
        assert ctx.state == KernelState.ACTIVE
        # Clean up
        await ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_simultaneous_contexts_independent(self) -> None:
        """Two separate KernelContext instances are fully independent."""
        ctx_a = KernelContext()
        ctx_b = KernelContext()
        async with ctx_a:
            assert ctx_a.state == KernelState.ACTIVE
            assert ctx_b.state == KernelState.IDLE
            async with ctx_b:
                assert ctx_a.state == KernelState.ACTIVE
                assert ctx_b.state == KernelState.ACTIVE
            assert ctx_b.state == KernelState.IDLE
        assert ctx_a.state == KernelState.IDLE


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestRepr:
    def test_repr_contains_state(self) -> None:
        ctx = KernelContext()
        assert "IDLE" in repr(ctx)

    @pytest.mark.asyncio
    async def test_repr_changes_with_state(self) -> None:
        ctx = KernelContext()
        await ctx.__aenter__()
        assert "ACTIVE" in repr(ctx)
        await ctx.__aexit__(None, None, None)
        assert "IDLE" in repr(ctx)

    def test_repr_contains_corr_id(self) -> None:
        cid = "test-cid"
        ctx = KernelContext(corr_id=cid)
        assert cid in repr(ctx)

    def test_repr_contains_gate_count(self) -> None:
        ctx = KernelContext(gates=[_passing_gate, _passing_gate])
        assert "2" in repr(ctx)


# ---------------------------------------------------------------------------
# INV-5: ACTIVE requires all gates passed
# ---------------------------------------------------------------------------


class TestINV5ActiveRequiresGates:
    @pytest.mark.asyncio
    async def test_active_only_after_all_gates_pass(self) -> None:
        """INV-5: cannot reach ACTIVE without running all gates."""
        entered_states: list[KernelState] = []

        async def recording_gate(ctx: KernelContext) -> None:
            entered_states.append(ctx.state)

        ctx = KernelContext(gates=[recording_gate, recording_gate, recording_gate])
        async with ctx:
            # After all gates pass, state is ACTIVE
            assert ctx.state == KernelState.ACTIVE
        # All three gates ran while ENTERING (not ACTIVE)
        assert all(s == KernelState.ENTERING for s in entered_states)
        assert len(entered_states) == 3

    @pytest.mark.asyncio
    async def test_state_is_entering_during_gate_execution(self) -> None:
        """Gates run while state is ENTERING, not ACTIVE (INV-5)."""
        observed: list[KernelState] = []

        async def observe_gate(ctx: KernelContext) -> None:
            observed.append(ctx.state)

        async with KernelContext(gates=[observe_gate]):
            pass
        assert observed == [KernelState.ENTERING]


# ---------------------------------------------------------------------------
# FM-001-2: FAULTED never silently discarded
# ---------------------------------------------------------------------------


class TestFM0012FaultedNeverSilent:
    @pytest.mark.asyncio
    async def test_gate_failure_exception_propagates(self) -> None:
        """FM-001-2: gate failure must propagate; never silently FAULTED→IDLE."""
        ctx = KernelContext(gates=[_failing_gate(KernelError("gate-fail"))])
        raised = False
        try:
            async with ctx:
                pass
        except KernelError:
            raised = True
        assert raised
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_active_exception_propagates(self) -> None:
        """FM-001-2: exception in with-block always propagates."""
        ctx = KernelContext()
        raised = False
        exc = KernelError("active-exc")
        try:
            async with ctx:
                raise exc
        except KernelError as e:
            raised = e is exc
        assert raised


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------


class TestPropertyBased:
    @given(st.integers(min_value=0, max_value=8))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_gate_fail_at_any_position_state_is_idle(
        self, fail_at: int
    ) -> None:
        """Regardless of which gate position fails, state is always IDLE afterwards."""

        async def make_gate_at(pos: int) -> None:
            async def _gate(ctx: KernelContext) -> None:
                if pos == fail_at:
                    raise KernelError(f"fail at gate {pos}")

            return _gate  # type: ignore[return-value]

        n_gates = 8
        gates = [await make_gate_at(i) for i in range(n_gates)]
        ctx = KernelContext(gates=gates)

        try:
            async with ctx:
                pass
        except KernelError:
            pass
        # State must ALWAYS be IDLE regardless of which gate failed
        assert ctx.state == KernelState.IDLE

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_repeated_happy_path_always_ends_idle(self, n: int) -> None:
        """N sequential happy-path crossings always leave state in IDLE."""
        ctx = KernelContext()
        for _ in range(n):
            async with ctx:
                assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE
