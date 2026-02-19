"""Task 18.4 — K8 full gate factory unit tests.

Acceptance criteria (Behavior Spec §1.9 + Goal Hierarchy S2.0-2.4):
1. All five Celestial predicates evaluated in strict L0→L4 order.
2. First predicate failure halts sweep immediately (fail-fast).
3. Any predicate missing from registry → PredicateNotFoundError (fail-safe).
4. Any predicate raising an exception → EvalError (fail-safe).
5. k8_gate returns a Gate coroutine function accepting KernelContext.
6. Successful sweep leaves KernelContext in IDLE state.
7. Failed sweep (EvalGateFailure) leaves KernelContext in IDLE/FAULTED state.
8. Custom predicate_ids override is respected.
9. CELESTIAL_PREDICATE_IDS contains exactly five entries in L0→L4 order.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    EvalError,
    EvalGateFailure,
    PredicateNotFoundError,
)
from holly.kernel.k8 import (
    CELESTIAL_PREDICATE_IDS,
    k8_gate,
)
from holly.kernel.predicate_registry import PredicateRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_OUTPUT: dict[str, Any] = {"goal": "execute_task", "payload": {"steps": 3}}


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    """Reset PredicateRegistry before and after each test."""
    PredicateRegistry.clear()
    yield
    PredicateRegistry.clear()


def _register_all_pass() -> None:
    """Register all 5 Celestial predicates as always-True."""
    for pid in CELESTIAL_PREDICATE_IDS:
        PredicateRegistry.register(pid, lambda o: True)


def _register_all_pass_tracking() -> dict[str, int]:
    """Register all 5 predicates; return call-count dict."""
    counts: dict[str, int] = {pid: 0 for pid in CELESTIAL_PREDICATE_IDS}

    for pid in CELESTIAL_PREDICATE_IDS:

        def _make_pred(p: str) -> Callable[[Any], bool]:
            def _pred(o: Any) -> bool:
                counts[p] += 1
                return True

            return _pred

        PredicateRegistry.register(pid, _make_pred(pid))

    return counts


def _register_fail_at(failing_pid: str) -> dict[str, int]:
    """Register predicates: all pass except *failing_pid* which returns False."""
    counts: dict[str, int] = {pid: 0 for pid in CELESTIAL_PREDICATE_IDS}

    for pid in CELESTIAL_PREDICATE_IDS:

        def _make_pred(p: str, fail: bool) -> Callable[[Any], bool]:
            def _pred(o: Any) -> bool:
                counts[p] += 1
                return not fail

            return _pred

        PredicateRegistry.register(pid, _make_pred(pid, pid == failing_pid))

    return counts


# ---------------------------------------------------------------------------
# TestK8GateFactory — AC5, AC8
# ---------------------------------------------------------------------------


class TestK8GateFactory:
    """k8_gate() factory: returns a Gate; validates inputs."""

    def test_k8_gate_returns_callable(self) -> None:
        _register_all_pass()
        gate = k8_gate(output=_OUTPUT)
        assert callable(gate)

    def test_k8_gate_is_coroutine_function(self) -> None:
        _register_all_pass()
        gate = k8_gate(output=_OUTPUT)
        assert inspect.iscoroutinefunction(gate)

    def test_k8_gate_accepts_ctx_parameter(self) -> None:
        _register_all_pass()
        gate = k8_gate(output=_OUTPUT)
        sig = inspect.signature(gate)
        assert "ctx" in sig.parameters

    def test_empty_predicate_ids_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            k8_gate(output=_OUTPUT, predicate_ids=())

    def test_custom_predicate_ids_single(self) -> None:
        PredicateRegistry.register("custom:pred", lambda o: True)
        gate = k8_gate(output=_OUTPUT, predicate_ids=("custom:pred",))
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))


# ---------------------------------------------------------------------------
# TestK8AllPredicatesPass — AC1, AC6
# ---------------------------------------------------------------------------


class TestK8AllPredicatesPass:
    """All predicates pass → gate passes, context returns to IDLE."""

    def test_all_five_celestial_pass(self) -> None:
        _register_all_pass()
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))

    def test_all_five_called_when_all_pass(self) -> None:
        counts = _register_all_pass_tracking()
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        for pid in CELESTIAL_PREDICATE_IDS:
            assert counts[pid] == 1, f"predicate {pid!r} was not called"

    def test_single_custom_predicate_pass(self) -> None:
        PredicateRegistry.register("p1", lambda o: True)
        gate = k8_gate(output=_OUTPUT, predicate_ids=("p1",))
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))

    def test_two_custom_predicates_both_pass(self) -> None:
        PredicateRegistry.register("p1", lambda o: True)
        PredicateRegistry.register("p2", lambda o: True)
        gate = k8_gate(output=_OUTPUT, predicate_ids=("p1", "p2"))
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))

    def test_all_pass_via_async_with(self) -> None:
        _register_all_pass()

        async def _run() -> None:
            gate = k8_gate(output=_OUTPUT)
            async with KernelContext(gates=[gate]):
                pass

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# TestK8FailFast — AC2
# ---------------------------------------------------------------------------


class TestK8FailFast:
    """First predicate failure halts sweep; subsequent predicates not called."""

    def _check_fail_at_level(self, level_idx: int) -> None:
        failing_pid = CELESTIAL_PREDICATE_IDS[level_idx]
        counts = _register_fail_at(failing_pid)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(EvalGateFailure) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert exc_info.value.predicate_id == failing_pid
        # Predicates before the failing one must have been called
        for i in range(level_idx):
            pid = CELESTIAL_PREDICATE_IDS[i]
            assert counts[pid] == 1, f"{pid!r} (before failure) was not called"
        # Predicates at or after the failing one: failing one called once
        assert counts[failing_pid] == 1
        # Predicates after the failing one must NOT have been called (fail-fast)
        for i in range(level_idx + 1, len(CELESTIAL_PREDICATE_IDS)):
            pid = CELESTIAL_PREDICATE_IDS[i]
            assert counts[pid] == 0, f"{pid!r} (after failure) was incorrectly called"

    def test_l0_fail_stops_at_l0(self) -> None:
        self._check_fail_at_level(0)

    def test_l1_fail_stops_at_l1(self) -> None:
        self._check_fail_at_level(1)

    def test_l2_fail_stops_at_l2(self) -> None:
        self._check_fail_at_level(2)

    def test_l3_fail_stops_at_l3(self) -> None:
        self._check_fail_at_level(3)

    def test_l4_fail_stops_at_l4(self) -> None:
        self._check_fail_at_level(4)

    def test_fail_fast_raises_eval_gate_failure(self) -> None:
        _register_fail_at(CELESTIAL_PREDICATE_IDS[0])
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(EvalGateFailure):
            asyncio.run(ctx.__aenter__())

    def test_fail_gate_failure_contains_predicate_id(self) -> None:
        l2_pid = CELESTIAL_PREDICATE_IDS[2]
        _register_fail_at(l2_pid)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(EvalGateFailure) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert exc_info.value.predicate_id == l2_pid


# ---------------------------------------------------------------------------
# TestK8OrderEnforcement — AC1 (strict L0→L4)
# ---------------------------------------------------------------------------


class TestK8OrderEnforcement:
    """Predicates evaluated in strict left-to-right index order."""

    def test_predicates_evaluated_in_declared_order(self) -> None:
        """Record evaluation order and assert it matches CELESTIAL_PREDICATE_IDS."""
        order: list[str] = []

        for pid in CELESTIAL_PREDICATE_IDS:

            def _make_pred(p: str) -> Callable[[Any], bool]:
                def _pred(o: Any) -> bool:
                    order.append(p)
                    return True

                return _pred

            PredicateRegistry.register(pid, _make_pred(pid))

        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        assert order == list(CELESTIAL_PREDICATE_IDS)

    def test_custom_order_respected(self) -> None:
        """Custom predicate_ids are evaluated in the given order."""
        order: list[str] = []

        for p in ("alpha", "beta", "gamma"):

            def _mk(name: str) -> Any:
                def _tr(o: Any) -> bool:
                    order.append(name)
                    return True

                return _tr

            PredicateRegistry.register(p, _mk(p))

        gate = k8_gate(output=_OUTPUT, predicate_ids=("alpha", "beta", "gamma"))
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        assert order == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# TestK8FailSafe — AC3, AC4
# ---------------------------------------------------------------------------


class TestK8FailSafe:
    """Missing predicates and raising predicates are fail-safe (deny)."""

    def test_missing_l0_raises_predicate_not_found(self) -> None:
        # Register L1-L4 but NOT L0
        for pid in CELESTIAL_PREDICATE_IDS[1:]:
            PredicateRegistry.register(pid, lambda o: True)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(PredicateNotFoundError) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert exc_info.value.predicate_id == CELESTIAL_PREDICATE_IDS[0]

    def test_missing_predicate_halts_sweep(self) -> None:
        # Register only L0; L1 missing
        PredicateRegistry.register(CELESTIAL_PREDICATE_IDS[0], lambda o: True)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(PredicateNotFoundError):
            asyncio.run(ctx.__aenter__())

    def test_raising_predicate_wraps_as_eval_error(self) -> None:
        _register_all_pass()
        PredicateRegistry.clear()
        for pid in CELESTIAL_PREDICATE_IDS:
            if pid == CELESTIAL_PREDICATE_IDS[2]:

                def _raise(o: Any) -> bool:
                    raise RuntimeError("db offline")

                PredicateRegistry.register(pid, _raise)
            else:
                PredicateRegistry.register(pid, lambda o: True)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(EvalError) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert CELESTIAL_PREDICATE_IDS[2] == exc_info.value.predicate_id

    def test_fail_safe_no_output_returned_on_failure(self) -> None:
        """When K8 fails, control must not proceed past __aenter__."""
        _register_fail_at(CELESTIAL_PREDICATE_IDS[0])
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        reached_body = False
        try:
            asyncio.run(ctx.__aenter__())
            reached_body = True
        except EvalGateFailure:
            pass
        assert not reached_body


# ---------------------------------------------------------------------------
# TestK8ContextIntegration — AC6, AC7
# ---------------------------------------------------------------------------


class TestK8ContextIntegration:
    """Gate integrates correctly with KernelContext lifecycle."""

    def test_all_pass_context_idle_after(self) -> None:
        from holly.kernel.state_machine import KernelState

        _register_all_pass()
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        assert ctx.state == KernelState.IDLE

    def test_failure_context_idle_after(self) -> None:
        from holly.kernel.state_machine import KernelState

        _register_fail_at(CELESTIAL_PREDICATE_IDS[0])
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(EvalGateFailure):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE

    def test_missing_predicate_context_idle_after(self) -> None:
        from holly.kernel.state_machine import KernelState

        # Only register L0; L1 will be missing
        PredicateRegistry.register(CELESTIAL_PREDICATE_IDS[0], lambda o: True)
        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(PredicateNotFoundError):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE

    def test_k8_composed_with_k5(self) -> None:
        """k8_gate composes correctly alongside k5_gate."""
        from holly.kernel.k5 import InMemoryIdempotencyStore, k5_gate

        _register_all_pass()
        store = InMemoryIdempotencyStore()
        gate_k5 = k5_gate(payload={"op": "eval"}, store=store)
        gate_k8 = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate_k5, gate_k8])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))


# ---------------------------------------------------------------------------
# TestK8CelestialPredicateIds — AC9
# ---------------------------------------------------------------------------


class TestK8CelestialPredicateIds:
    """CELESTIAL_PREDICATE_IDS constant: five entries, L0→L4 ordered."""

    def test_exactly_five_predicate_ids(self) -> None:
        assert len(CELESTIAL_PREDICATE_IDS) == 5

    def test_l0_authorization_boundary_first(self) -> None:
        assert "L0" in CELESTIAL_PREDICATE_IDS[0]
        assert "authorization" in CELESTIAL_PREDICATE_IDS[0]

    def test_l1_system_integrity_second(self) -> None:
        assert "L1" in CELESTIAL_PREDICATE_IDS[1]
        assert "integrity" in CELESTIAL_PREDICATE_IDS[1]

    def test_l2_privacy_boundary_third(self) -> None:
        assert "L2" in CELESTIAL_PREDICATE_IDS[2]
        assert "privacy" in CELESTIAL_PREDICATE_IDS[2]

    def test_l3_failure_recovery_fourth(self) -> None:
        assert "L3" in CELESTIAL_PREDICATE_IDS[3]
        assert "recovery" in CELESTIAL_PREDICATE_IDS[3]

    def test_l4_agent_autonomy_fifth(self) -> None:
        assert "L4" in CELESTIAL_PREDICATE_IDS[4]
        assert "autonomy" in CELESTIAL_PREDICATE_IDS[4]

    def test_is_tuple(self) -> None:
        assert isinstance(CELESTIAL_PREDICATE_IDS, tuple)

    def test_all_entries_are_strings(self) -> None:
        assert all(isinstance(pid, str) for pid in CELESTIAL_PREDICATE_IDS)

    def test_all_entries_are_unique(self) -> None:
        assert len(set(CELESTIAL_PREDICATE_IDS)) == len(CELESTIAL_PREDICATE_IDS)


# ---------------------------------------------------------------------------
# TestK8PropertyBased — determinism + fail-fast
# ---------------------------------------------------------------------------


class TestK8PropertyBased:
    """Property-based tests for K8 invariants."""

    @given(
        failing_index=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=5, deadline=None)
    def test_fail_fast_at_any_level(self, failing_index: int) -> None:
        """Regardless of which level fails, predicates after it are not called."""
        PredicateRegistry.clear()
        failing_pid = CELESTIAL_PREDICATE_IDS[failing_index]
        counts: dict[str, int] = {pid: 0 for pid in CELESTIAL_PREDICATE_IDS}

        for pid in CELESTIAL_PREDICATE_IDS:

            def _mk(p: str, fail: bool) -> Callable[[Any], bool]:
                def _pred(o: Any) -> bool:
                    counts[p] += 1
                    return not fail

                return _pred

            PredicateRegistry.register(pid, _mk(pid, pid == failing_pid))

        gate = k8_gate(output=_OUTPUT)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(EvalGateFailure):
            asyncio.run(ctx.__aenter__())

        # Predicates after the failing level must have call count 0
        for i in range(failing_index + 1, len(CELESTIAL_PREDICATE_IDS)):
            pid = CELESTIAL_PREDICATE_IDS[i]
            assert counts[pid] == 0

    @given(
        output=st.one_of(
            st.dictionaries(st.text(max_size=10), st.integers()),
            st.text(max_size=50),
            st.integers(),
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_determinism_same_output_same_result(self, output: Any) -> None:
        """Deterministic: same output → same pass/fail outcome."""
        PredicateRegistry.clear()
        _register_all_pass()
        gate1 = k8_gate(output=output)
        gate2 = k8_gate(output=output)
        ctx1 = KernelContext(gates=[gate1])
        ctx2 = KernelContext(gates=[gate2])
        # Both must produce the same result (both pass since all predicates pass)
        asyncio.run(ctx1.__aenter__())
        asyncio.run(ctx1.__aexit__(None, None, None))
        asyncio.run(ctx2.__aenter__())
        asyncio.run(ctx2.__aexit__(None, None, None))
