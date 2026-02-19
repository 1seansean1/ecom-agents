"""Task 18.9 — K7-K8 Failure Isolation integration tests.

Verifies Behavior Spec §1.8-§1.9: K7 (HITL) and K8 (eval) gates block
independently.  No cascade failures; each gate raises only its own exception
types; exception class hierarchies are mutually exclusive.

Acceptance criteria (Task_Manifest.md §18.9):
1. K7 failures raise K7-specific exceptions, never K8 exceptions.
2. K8 failures raise K8-specific exceptions, never K7 exceptions.
3. When K7 fails in a K7→K8 gate chain, K8 is never invoked (fail-fast).
4. When K7 passes and K8 fails, the raised exception is K8-type only.
5. Both gates passing → context reaches ACTIVE → exits to IDLE.
6. K7 and K8 exception classes are structurally non-subclassing.
7. All K7 and K8 exceptions derive from KernelError.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    ApprovalChannelError,
    ApprovalTimeout,
    ConfidenceError,
    EvalError,
    EvalGateFailure,
    KernelError,
    OperationRejected,
    PredicateNotFoundError,
)
from holly.kernel.k7 import (
    FailConfidenceEvaluator,
    FixedConfidenceEvaluator,
    FixedThresholdConfig,
    HumanDecision,
    InMemoryApprovalChannel,
    k7_gate,
)
from holly.kernel.k8 import k8_gate
from holly.kernel.predicate_registry import PredicateRegistry
from holly.kernel.state_machine import KernelState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HIGH_SCORE: float = 0.95   # above threshold → K7 passes transparently
_LOW_SCORE: float = 0.50    # below threshold → K7 routes to human review
_THRESHOLD: float = 0.85

_OUTPUT: dict[str, Any] = {"data": "sentinel", "task": "18.9"}

# Exception class groups for isinstance checks
_K7_EXCEPTIONS = (ConfidenceError, ApprovalTimeout, OperationRejected, ApprovalChannelError)
_K8_EXCEPTIONS = (EvalGateFailure, EvalError, PredicateNotFoundError)


# ---------------------------------------------------------------------------
# Module-level predicate for eval_error tests (cannot use lambda that raises)
# ---------------------------------------------------------------------------


def _always_error(output: object) -> bool:
    """Predicate that always raises RuntimeError — used for EvalError tests."""
    raise RuntimeError("predicate exploded: test:18_9")


# ---------------------------------------------------------------------------
# Helpers: custom approval channel
# ---------------------------------------------------------------------------


class _AlwaysRejectChannel(InMemoryApprovalChannel):
    """Approval channel that immediately rejects every request.

    Allows testing OperationRejected without knowing the UUID of the
    ApprovalRequest that will be generated at gate-run time.
    """

    def wait_for_decision(self, request_id: str, *, timeout: float) -> HumanDecision:
        """Return an immediate rejection for any request_id."""
        return HumanDecision(
            request_id=request_id,
            action="reject",
            reviewer_id="test-auto-reject",
            reason="test: always reject",
        )


# ---------------------------------------------------------------------------
# Helpers: spy gate
# ---------------------------------------------------------------------------


class _SpyGate:
    """Gate that records its call count and always passes."""

    def __init__(self) -> None:
        self.call_count: int = 0

    async def __call__(self, ctx: KernelContext) -> None:
        self.call_count += 1


# ---------------------------------------------------------------------------
# Helpers: K7 gate factories
# ---------------------------------------------------------------------------


def _make_k7_pass() -> Any:
    """K7 gate configured to pass (high-confidence, no human review required)."""
    channel = InMemoryApprovalChannel()
    return k7_gate(
        operation_type="test_op",
        payload={"test": True},
        evaluator=FixedConfidenceEvaluator(_HIGH_SCORE),
        threshold_config=FixedThresholdConfig(_THRESHOLD),
        approval_channel=channel,
        timeout_seconds=5.0,
    )


def _make_k7_confidence_error() -> Any:
    """K7 gate where the confidence evaluator itself raises (→ ConfidenceError)."""
    channel = InMemoryApprovalChannel()
    return k7_gate(
        operation_type="test_op",
        payload={"test": True},
        evaluator=FailConfidenceEvaluator("injected evaluator failure"),
        threshold_config=FixedThresholdConfig(_THRESHOLD),
        approval_channel=channel,
        timeout_seconds=5.0,
    )


def _make_k7_timeout() -> Any:
    """K7 gate that times out awaiting human approval (→ ApprovalTimeout)."""
    channel = InMemoryApprovalChannel()
    channel.set_timeout_all()
    return k7_gate(
        operation_type="test_op",
        payload={"test": True},
        evaluator=FixedConfidenceEvaluator(_LOW_SCORE),
        threshold_config=FixedThresholdConfig(_THRESHOLD),
        approval_channel=channel,
        timeout_seconds=0.01,  # recorded in exception only; set_timeout_all raises immediately
    )


def _make_k7_channel_error() -> Any:
    """K7 gate where emit() raises (→ ApprovalChannelError)."""
    channel = InMemoryApprovalChannel()
    channel.set_fail_emit()
    return k7_gate(
        operation_type="test_op",
        payload={"test": True},
        evaluator=FixedConfidenceEvaluator(_LOW_SCORE),
        threshold_config=FixedThresholdConfig(_THRESHOLD),
        approval_channel=channel,
        timeout_seconds=5.0,
    )


def _make_k7_rejected() -> Any:
    """K7 gate where the human reviewer rejects the operation (→ OperationRejected)."""
    channel = _AlwaysRejectChannel()
    return k7_gate(
        operation_type="test_op",
        payload={"test": True},
        evaluator=FixedConfidenceEvaluator(_LOW_SCORE),
        threshold_config=FixedThresholdConfig(_THRESHOLD),
        approval_channel=channel,
        timeout_seconds=5.0,
    )


# ---------------------------------------------------------------------------
# Helpers: K8 gate factories (unique predicate IDs to avoid re-registration)
# ---------------------------------------------------------------------------


def _make_k8_pass() -> Any:
    """K8 gate configured to pass (predicate returns True)."""
    pid = f"test:18_9:pass:{uuid.uuid4().hex}"
    PredicateRegistry.register(pid, lambda o: True)
    return k8_gate(output=_OUTPUT, predicate_ids=(pid,))


def _make_k8_fail() -> Any:
    """K8 gate that raises EvalGateFailure (predicate returns False)."""
    pid = f"test:18_9:fail:{uuid.uuid4().hex}"
    PredicateRegistry.register(pid, lambda o: False)
    return k8_gate(output=_OUTPUT, predicate_ids=(pid,))


def _make_k8_not_found() -> Any:
    """K8 gate that raises PredicateNotFoundError (predicate not in registry)."""
    pid = f"test:18_9:unregistered:{uuid.uuid4().hex}"
    # Deliberately NOT registered
    return k8_gate(output=_OUTPUT, predicate_ids=(pid,))


def _make_k8_eval_error() -> Any:
    """K8 gate that raises EvalError (predicate raises RuntimeError)."""
    pid = f"test:18_9:error:{uuid.uuid4().hex}"
    PredicateRegistry.register(pid, _always_error)
    return k8_gate(output=_OUTPUT, predicate_ids=(pid,))


# ---------------------------------------------------------------------------
# Helpers: test runner
# ---------------------------------------------------------------------------


async def _run_gates_raising(*gates: Any) -> tuple[KernelContext, BaseException]:
    """Run a KernelContext with *gates*; return (ctx, exc) where exc is the exception raised.

    Asserts that an exception IS raised — callers testing failure paths rely on this.
    """
    ctx = KernelContext(gates=list(gates))
    exc: BaseException | None = None
    try:
        async with ctx:
            pass
    except BaseException as e:
        exc = e
    assert exc is not None, "Expected an exception but KernelContext raised nothing"
    return ctx, exc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_predicate_registry() -> Any:
    """Reset PredicateRegistry before/after every test to prevent cross-test bleed."""
    PredicateRegistry.clear()
    yield
    PredicateRegistry.clear()


# ---------------------------------------------------------------------------
# TestK7FailsIndependently  (6 tests)
# ---------------------------------------------------------------------------


class TestK7FailsIndependently:
    """K7 gates fail with K7-specific exceptions only; K8 types are never raised."""

    async def test_confidence_error_is_k7_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_confidence_error())
        assert isinstance(exc, ConfidenceError)

    async def test_confidence_error_not_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_confidence_error())
        assert not isinstance(exc, _K8_EXCEPTIONS)

    async def test_approval_timeout_is_k7_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_timeout())
        assert isinstance(exc, ApprovalTimeout)

    async def test_approval_timeout_not_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_timeout())
        assert not isinstance(exc, _K8_EXCEPTIONS)

    async def test_channel_error_is_k7_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_channel_error())
        assert isinstance(exc, ApprovalChannelError)

    async def test_channel_error_not_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_channel_error())
        assert not isinstance(exc, _K8_EXCEPTIONS)


# ---------------------------------------------------------------------------
# TestK8FailsIndependently  (5 tests)
# ---------------------------------------------------------------------------


class TestK8FailsIndependently:
    """K8 gates fail with K8-specific exceptions only; K7 types are never raised."""

    async def test_eval_gate_failure_is_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k8_fail())
        assert isinstance(exc, EvalGateFailure)

    async def test_eval_gate_failure_not_k7_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k8_fail())
        assert not isinstance(exc, _K7_EXCEPTIONS)

    async def test_predicate_not_found_is_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k8_not_found())
        assert isinstance(exc, PredicateNotFoundError)

    async def test_predicate_not_found_not_k7_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k8_not_found())
        assert not isinstance(exc, _K7_EXCEPTIONS)

    async def test_eval_error_is_k8_type(self) -> None:
        _, exc = await _run_gates_raising(_make_k8_eval_error())
        assert isinstance(exc, EvalError)


# ---------------------------------------------------------------------------
# TestK7FailK8NotCalled  (4 tests)
# ---------------------------------------------------------------------------


class TestK7FailK8NotCalled:
    """When K7 fails in a [K7, K8] chain, K8 gate is never invoked (fail-fast)."""

    async def test_confidence_error_blocks_k8(self) -> None:
        spy = _SpyGate()
        await _run_gates_raising(_make_k7_confidence_error(), spy)
        assert spy.call_count == 0

    async def test_timeout_blocks_k8(self) -> None:
        spy = _SpyGate()
        await _run_gates_raising(_make_k7_timeout(), spy)
        assert spy.call_count == 0

    async def test_channel_error_blocks_k8(self) -> None:
        spy = _SpyGate()
        await _run_gates_raising(_make_k7_channel_error(), spy)
        assert spy.call_count == 0

    async def test_k7_exception_propagates_not_swapped_for_k8(self) -> None:
        """Even when K8 is configured, the propagated exception is the K7 type."""
        _, exc = await _run_gates_raising(_make_k7_confidence_error(), _make_k8_fail())
        assert isinstance(exc, ConfidenceError)
        assert not isinstance(exc, _K8_EXCEPTIONS)


# ---------------------------------------------------------------------------
# TestK7PassK8Fail  (4 tests)
# ---------------------------------------------------------------------------


class TestK7PassK8Fail:
    """K7 passes → K8 runs → K8 fails; exception must be K8-type only."""

    async def test_k7_pass_k8_eval_failure_is_k8(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_pass(), _make_k8_fail())
        assert isinstance(exc, EvalGateFailure)

    async def test_k7_pass_k8_eval_failure_not_k7(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_pass(), _make_k8_fail())
        assert not isinstance(exc, _K7_EXCEPTIONS)

    async def test_k7_pass_k8_predicate_not_found(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_pass(), _make_k8_not_found())
        assert isinstance(exc, PredicateNotFoundError)

    async def test_k7_pass_k8_eval_error(self) -> None:
        _, exc = await _run_gates_raising(_make_k7_pass(), _make_k8_eval_error())
        assert isinstance(exc, EvalError)


# ---------------------------------------------------------------------------
# TestBothGatesPass  (3 tests)
# ---------------------------------------------------------------------------


class TestBothGatesPass:
    """K7 and K8 both pass → context reaches ACTIVE → exits cleanly to IDLE."""

    async def test_both_pass_reaches_active(self) -> None:
        ctx = KernelContext(gates=[_make_k7_pass(), _make_k8_pass()])
        async with ctx:
            assert ctx.state == KernelState.ACTIVE

    async def test_both_pass_exits_to_idle(self) -> None:
        ctx = KernelContext(gates=[_make_k7_pass(), _make_k8_pass()])
        async with ctx:
            pass
        assert ctx.state == KernelState.IDLE

    async def test_two_independent_contexts_no_state_bleed(self) -> None:
        """Two separate KernelContext instances share no state (INV-5 isolation)."""
        ctx_a = KernelContext(gates=[_make_k7_pass(), _make_k8_pass()])
        ctx_b = KernelContext(gates=[_make_k7_pass(), _make_k8_pass()])
        # ctx_b is idle before ctx_a is even entered
        assert ctx_b.state == KernelState.IDLE
        async with ctx_a:
            assert ctx_a.state == KernelState.ACTIVE
            assert ctx_b.state == KernelState.IDLE  # unaffected by ctx_a entry


# ---------------------------------------------------------------------------
# TestExceptionClassIsolation  (6 tests)
# ---------------------------------------------------------------------------


class TestExceptionClassIsolation:
    """Structural invariant: K7 and K8 exception classes are mutually non-subclassing."""

    def test_confidence_error_not_subclass_of_eval_gate_failure(self) -> None:
        assert not issubclass(ConfidenceError, EvalGateFailure)

    def test_eval_gate_failure_not_subclass_of_confidence_error(self) -> None:
        assert not issubclass(EvalGateFailure, ConfidenceError)

    def test_approval_timeout_not_subclass_of_eval_error(self) -> None:
        assert not issubclass(ApprovalTimeout, EvalError)

    def test_eval_error_not_subclass_of_approval_timeout(self) -> None:
        assert not issubclass(EvalError, ApprovalTimeout)

    def test_all_k7_exceptions_are_kernel_error(self) -> None:
        for exc_cls in _K7_EXCEPTIONS:
            assert issubclass(exc_cls, KernelError), f"{exc_cls.__name__} not KernelError subclass"

    def test_all_k8_exceptions_are_kernel_error(self) -> None:
        for exc_cls in _K8_EXCEPTIONS:
            assert issubclass(exc_cls, KernelError), f"{exc_cls.__name__} not KernelError subclass"


# ---------------------------------------------------------------------------
# TestPropertyBased  (2 tests)
# ---------------------------------------------------------------------------


class TestPropertyBased:
    """Hypothesis: gate failure independence holds across arbitrary inputs."""

    @given(
        score=st.floats(
            min_value=0.0,
            max_value=0.84,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=30)
    def test_k7_low_confidence_raises_k7_not_k8(self, score: float) -> None:
        """Any sub-threshold confidence score → K7 exception, never K8 exception."""

        async def _inner() -> None:
            channel = InMemoryApprovalChannel()
            channel.set_timeout_all()
            gate = k7_gate(
                operation_type="prop_test",
                payload={"score": score},
                evaluator=FixedConfidenceEvaluator(score),
                threshold_config=FixedThresholdConfig(_THRESHOLD),
                approval_channel=channel,
                timeout_seconds=0.01,
            )
            _, exc = await _run_gates_raising(gate)
            assert isinstance(exc, _K7_EXCEPTIONS)
            assert not isinstance(exc, _K8_EXCEPTIONS)

        asyncio.run(_inner())

    @given(which=st.sampled_from(["fail", "not_found", "error"]))
    @settings(max_examples=20)
    def test_k8_failure_raises_k8_not_k7(self, which: str) -> None:
        """Each K8 failure mode raises a K8 exception, never a K7 exception."""

        async def _inner() -> None:
            PredicateRegistry.clear()
            if which == "fail":
                gate = _make_k8_fail()
            elif which == "not_found":
                gate = _make_k8_not_found()
            else:
                gate = _make_k8_eval_error()
            _, exc = await _run_gates_raising(gate)
            assert isinstance(exc, _K8_EXCEPTIONS)
            assert not isinstance(exc, _K7_EXCEPTIONS)

        asyncio.run(_inner())
