"""Task 18.3 — K7 HITL gate unit tests.

Acceptance criteria (Behavior Spec §1.8):
1. High-confidence operations pass without human review.
2. Low-confidence operations block and emit an ApprovalRequest.
3. Human approval unblocks the operation.
4. Human rejection raises OperationRejected.
5. Approval timeout raises ApprovalTimeout.
6. Reviewer ID is recorded in HumanDecision.
7. Confidence evaluator failure raises ConfidenceError (fail-safe deny).
8. Per-operation-type threshold configuration.
9. Approval channel emit failure raises ApprovalChannelError (fail-safe).
10. Invalid confidence score (outside [0,1]) raises ValueError (fail-safe).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    ApprovalChannelError,
    ApprovalTimeout,
    ConfidenceError,
    OperationRejected,
)
from holly.kernel.k7 import (
    ApprovalRequest,
    FailConfidenceEvaluator,
    FixedConfidenceEvaluator,
    FixedThresholdConfig,
    HumanDecision,
    InMemoryApprovalChannel,
    MappedThresholdConfig,
    k7_check_confidence,
    k7_gate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OP = "workflow:execute"
_PAYLOAD: dict[str, Any] = {"task": "run_pipeline", "steps": 3}


def _make_gate(
    score: float,
    threshold: float,
    channel: InMemoryApprovalChannel,
    *,
    op: str = _OP,
    payload: Any = _PAYLOAD,
    timeout: float = 1.0,
) -> Any:
    """Build a k7_gate with fixed score and threshold."""
    return k7_gate(
        operation_type=op,
        payload=payload,
        evaluator=FixedConfidenceEvaluator(score),
        threshold_config=FixedThresholdConfig(threshold),
        approval_channel=channel,
        timeout_seconds=timeout,
    )


async def _run_gate(
    score: float,
    threshold: float,
    channel: InMemoryApprovalChannel,
    *,
    op: str = _OP,
    timeout: float = 1.0,
) -> KernelContext:
    """Run a single k7_gate through KernelContext; return ctx after exit."""
    gate = _make_gate(score, threshold, channel, op=op, timeout=timeout)
    ctx = KernelContext(gates=[gate])
    async with ctx:
        pass
    return ctx


# ---------------------------------------------------------------------------
# TestK7CheckConfidence — pure guard tests (INV-4)
# ---------------------------------------------------------------------------


class TestK7CheckConfidence:
    """Tests for the pure k7_check_confidence guard."""

    def test_score_at_threshold_passes(self) -> None:
        assert k7_check_confidence(0.85, threshold=0.85) is True

    def test_score_above_threshold_passes(self) -> None:
        assert k7_check_confidence(0.90, threshold=0.85) is True

    def test_score_below_threshold_blocks(self) -> None:
        assert k7_check_confidence(0.70, threshold=0.85) is False

    def test_zero_threshold_always_passes(self) -> None:
        assert k7_check_confidence(0.0, threshold=0.0) is True

    def test_threshold_one_only_passes_at_one(self) -> None:
        assert k7_check_confidence(1.0, threshold=1.0) is True
        assert k7_check_confidence(0.999, threshold=1.0) is False

    def test_invalid_score_below_zero(self) -> None:
        with pytest.raises(ValueError, match="confidence score"):
            k7_check_confidence(-0.01, threshold=0.5)

    def test_invalid_score_above_one(self) -> None:
        with pytest.raises(ValueError, match="confidence score"):
            k7_check_confidence(1.01, threshold=0.5)

    def test_invalid_threshold_below_zero(self) -> None:
        with pytest.raises(ValueError, match="confidence threshold"):
            k7_check_confidence(0.5, threshold=-0.01)

    def test_invalid_threshold_above_one(self) -> None:
        with pytest.raises(ValueError, match="confidence threshold"):
            k7_check_confidence(0.5, threshold=1.01)

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=300, deadline=None)
    def test_determinism_property(self, score: float, threshold: float) -> None:
        """Guard is pure: same inputs always yield same output."""
        r1 = k7_check_confidence(score, threshold=threshold)
        r2 = k7_check_confidence(score, threshold=threshold)
        assert r1 == r2

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=300, deadline=None)
    def test_monotonicity_property(self, score: float, threshold: float) -> None:
        """score >= threshold ⟺ result is True (definition check)."""
        result = k7_check_confidence(score, threshold=threshold)
        assert result == (score >= threshold)


# ---------------------------------------------------------------------------
# TestK7HighConfidencePath — AC1
# ---------------------------------------------------------------------------


class TestK7HighConfidencePath:
    """High-confidence operations pass without human review (AC1)."""

    def test_high_confidence_passes(self) -> None:
        channel = InMemoryApprovalChannel()
        asyncio.run(_run_gate(score=0.95, threshold=0.85, channel=channel))
        assert len(channel.emitted) == 0

    def test_exactly_at_threshold_passes(self) -> None:
        channel = InMemoryApprovalChannel()
        asyncio.run(_run_gate(score=0.85, threshold=0.85, channel=channel))
        assert len(channel.emitted) == 0

    def test_score_1_0_always_passes(self) -> None:
        channel = InMemoryApprovalChannel()
        asyncio.run(_run_gate(score=1.0, threshold=1.0, channel=channel))
        assert len(channel.emitted) == 0

    def test_zero_threshold_always_passes(self) -> None:
        channel = InMemoryApprovalChannel()
        asyncio.run(_run_gate(score=0.0, threshold=0.0, channel=channel))
        assert len(channel.emitted) == 0

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_confident_path_no_approval_emitted(
        self, score: float, threshold: float
    ) -> None:
        """When score >= threshold, no approval request is emitted."""
        if score < threshold:
            return  # skip uncertain path in this test class
        channel = InMemoryApprovalChannel()

        async def _run() -> None:
            gate = k7_gate(
                operation_type=_OP,
                payload=_PAYLOAD,
                evaluator=FixedConfidenceEvaluator(score),
                threshold_config=FixedThresholdConfig(threshold),
                approval_channel=channel,
                timeout_seconds=1.0,
            )
            ctx = KernelContext(gates=[gate])
            async with ctx:
                pass

        asyncio.run(_run())
        assert len(channel.emitted) == 0


# ---------------------------------------------------------------------------
# TestK7LowConfidenceBlocks — AC2
# ---------------------------------------------------------------------------


class TestK7LowConfidenceBlocks:
    """Low-confidence operations block and emit an ApprovalRequest (AC2)."""

    def test_low_confidence_emits_approval_request(self) -> None:
        # Use a custom channel that auto-approves on emit.

        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id)

        auto_channel = AutoApproveChannel()
        gate2 = _make_gate(0.70, 0.85, auto_channel)
        ctx2 = KernelContext(gates=[gate2])
        asyncio.run(ctx2.__aenter__())
        asyncio.run(ctx2.__aexit__(None, None, None))

        assert len(auto_channel.emitted) == 1
        req = auto_channel.emitted[0]
        assert req.operation_type == _OP
        assert req.confidence_score == pytest.approx(0.70)
        assert req.threshold == pytest.approx(0.85)

    def test_approval_request_has_uuid_request_id(self) -> None:
        import re as _re

        class CaptureChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id)

        channel = CaptureChannel()
        gate = _make_gate(0.50, 0.85, channel)
        ctx_cap = KernelContext(gates=[gate])
        asyncio.run(ctx_cap.__aenter__())
        asyncio.run(ctx_cap.__aexit__(None, None, None))
        # Each gate run produces its own request
        for req in channel.emitted:
            assert _re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
                req.request_id,
            ), f"request_id {req.request_id!r} is not a valid UUID4"

    def test_approval_request_corr_id_matches_context(self) -> None:

        class CaptureChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id)

        channel = CaptureChannel()
        gate = _make_gate(0.50, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        assert len(channel.emitted) == 1
        # corr_id is the context's UUID or empty string
        assert channel.emitted[0].corr_id == (ctx.corr_id or "")


# ---------------------------------------------------------------------------
# TestK7HumanApproval — AC3
# ---------------------------------------------------------------------------


class TestK7HumanApproval:
    """Human approval unblocks the operation (AC3)."""

    def test_human_approval_allows_operation(self) -> None:
        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id, reviewer_id="reviewer-001")

        channel = AutoApproveChannel()
        # Should complete without exception
        asyncio.run(_run_gate(0.70, 0.85, channel))
        assert len(channel.emitted) == 1

    def test_human_approval_reviewer_id_recorded(self) -> None:
        reviewer = "alice@company.com"

        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id, reviewer_id=reviewer)

        channel = AutoApproveChannel()
        asyncio.run(_run_gate(0.60, 0.85, channel))
        # Verify the decision that was returned had the correct reviewer
        # (We trust inject_approve sets reviewer_id correctly)
        decision = channel._decisions.get(channel.emitted[0].request_id)
        assert decision is not None
        assert decision.reviewer_id == reviewer

    def test_multiple_sequential_approvals(self) -> None:
        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id)

        channel = AutoApproveChannel()
        for _ in range(5):
            gate = _make_gate(0.70, 0.85, channel)
            ctx = KernelContext(gates=[gate])
            asyncio.run(ctx.__aenter__())
            asyncio.run(ctx.__aexit__(None, None, None))
        assert len(channel.emitted) == 5


# ---------------------------------------------------------------------------
# TestK7HumanRejection — AC4
# ---------------------------------------------------------------------------


class TestK7HumanRejection:
    """Human rejection raises OperationRejected (AC4)."""

    def test_human_rejection_raises_operation_rejected(self) -> None:
        class AutoRejectChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_reject(
                    request.request_id,
                    reviewer_id="bob@company.com",
                    reason="policy violation",
                )

        channel = AutoRejectChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(OperationRejected) as exc_info:
            asyncio.run(ctx.__aenter__())
        err = exc_info.value
        assert err.reviewer_id == "bob@company.com"
        assert err.reason == "policy violation"

    def test_rejected_context_returns_to_idle(self) -> None:
        from holly.kernel.state_machine import KernelState

        class AutoRejectChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_reject(request.request_id, reviewer_id="reviewer")

        channel = AutoRejectChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(OperationRejected):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE

    def test_rejection_without_reason(self) -> None:
        class AutoRejectChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_decision(
                    request.request_id,
                    action="reject",
                    reviewer_id="reviewer",
                    reason="",
                )

        channel = AutoRejectChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(OperationRejected) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert exc_info.value.reason == ""


# ---------------------------------------------------------------------------
# TestK7ApprovalTimeout — AC5
# ---------------------------------------------------------------------------


class TestK7ApprovalTimeout:
    """Approval timeout raises ApprovalTimeout (AC5)."""

    def test_timeout_raises_approval_timeout(self) -> None:
        channel = InMemoryApprovalChannel()
        channel.set_timeout_all(timeout=True)

        class AutoEmitChannel(InMemoryApprovalChannel):
            """Emits but always times out on wait."""

            def wait_for_decision(
                self, request_id: str, *, timeout: float
            ) -> HumanDecision:
                raise ApprovalTimeout(request_id, timeout_seconds=timeout)

        tc = AutoEmitChannel()
        gate = _make_gate(0.70, 0.85, tc, timeout=30.0)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ApprovalTimeout) as exc_info:
            asyncio.run(ctx.__aenter__())
        assert exc_info.value.timeout_seconds == pytest.approx(30.0)

    def test_timeout_no_decision_injected(self) -> None:
        """InMemoryApprovalChannel times out when no decision is pre-injected."""

        class AutoEmitChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                # Deliberately do NOT inject a decision → triggers timeout

        tc = AutoEmitChannel()
        gate = _make_gate(0.70, 0.85, tc, timeout=5.0)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ApprovalTimeout):
            asyncio.run(ctx.__aenter__())

    def test_timeout_context_returns_to_idle(self) -> None:
        from holly.kernel.state_machine import KernelState

        class TimeoutChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)

            def wait_for_decision(
                self, request_id: str, *, timeout: float
            ) -> HumanDecision:
                raise ApprovalTimeout(request_id, timeout_seconds=timeout)

        channel = TimeoutChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(ApprovalTimeout):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE


# ---------------------------------------------------------------------------
# TestK7ReviewerRecorded — AC6
# ---------------------------------------------------------------------------


class TestK7ReviewerRecorded:
    """Human approvals and rejections record the reviewer (AC6)."""

    def test_approved_reviewer_recorded(self) -> None:
        reviewer = "carol@company.com"

        class RecordingChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id, reviewer_id=reviewer)

        channel = RecordingChannel()
        asyncio.run(_run_gate(0.70, 0.85, channel))
        decision = channel._decisions[channel.emitted[0].request_id]
        assert decision.reviewer_id == reviewer

    def test_rejected_reviewer_recorded(self) -> None:
        reviewer = "dave@company.com"

        class RecordingChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_reject(request.request_id, reviewer_id=reviewer)

        channel = RecordingChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(OperationRejected):
            asyncio.run(ctx.__aenter__())
        decision = channel._decisions[channel.emitted[0].request_id]
        assert decision.reviewer_id == reviewer

    def test_reviewer_id_non_empty(self) -> None:
        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id, reviewer_id="reviewer-99")

        channel = AutoApproveChannel()
        asyncio.run(_run_gate(0.70, 0.85, channel))
        decision = channel._decisions[channel.emitted[0].request_id]
        assert decision.reviewer_id != ""


# ---------------------------------------------------------------------------
# TestK7FailSafeDeny — AC7: evaluator failure
# ---------------------------------------------------------------------------


class TestK7FailSafeDeny:
    """Confidence evaluator failure raises ConfidenceError, operation denied (AC7)."""

    def test_evaluator_exception_raises_confidence_error(self) -> None:
        channel = InMemoryApprovalChannel()
        gate = k7_gate(
            operation_type=_OP,
            payload=_PAYLOAD,
            evaluator=FailConfidenceEvaluator("db timeout"),
            threshold_config=FixedThresholdConfig(0.85),
            approval_channel=channel,
            timeout_seconds=1.0,
        )
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ConfidenceError, match="db timeout"):
            asyncio.run(ctx.__aenter__())

    def test_evaluator_failure_no_approval_emitted(self) -> None:
        channel = InMemoryApprovalChannel()
        gate = k7_gate(
            operation_type=_OP,
            payload=_PAYLOAD,
            evaluator=FailConfidenceEvaluator(),
            threshold_config=FixedThresholdConfig(0.85),
            approval_channel=channel,
            timeout_seconds=1.0,
        )
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(ConfidenceError):
            asyncio.run(ctx.__aenter__())
        assert len(channel.emitted) == 0

    def test_evaluator_failure_context_to_idle(self) -> None:
        from holly.kernel.state_machine import KernelState

        channel = InMemoryApprovalChannel()
        gate = k7_gate(
            operation_type=_OP,
            payload=_PAYLOAD,
            evaluator=FailConfidenceEvaluator(),
            threshold_config=FixedThresholdConfig(0.85),
            approval_channel=channel,
            timeout_seconds=1.0,
        )
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(ConfidenceError):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE

    def test_invalid_score_raises_value_error(self) -> None:
        """Evaluator returning score > 1.0 triggers ValueError (fail-safe)."""

        class BadScoreEvaluator:
            def evaluate(self, operation_type: str, payload: Any) -> float:
                return 1.5  # invalid

        channel = InMemoryApprovalChannel()
        gate = k7_gate(
            operation_type=_OP,
            payload=_PAYLOAD,
            evaluator=BadScoreEvaluator(),
            threshold_config=FixedThresholdConfig(0.85),
            approval_channel=channel,
            timeout_seconds=1.0,
        )
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ValueError, match="outside"):
            asyncio.run(ctx.__aenter__())


# ---------------------------------------------------------------------------
# TestK7ThresholdConfiguration — AC8
# ---------------------------------------------------------------------------


class TestK7ThresholdConfiguration:
    """Different operation types have different thresholds (AC8)."""

    def test_mapped_threshold_different_per_op(self) -> None:
        config = MappedThresholdConfig(
            {"goal:modify": 0.95, "goal:read": 0.50},
            default_threshold=0.80,
        )
        assert config.get_threshold("goal:modify") == pytest.approx(0.95)
        assert config.get_threshold("goal:read") == pytest.approx(0.50)

    def test_modify_blocks_where_read_passes(self) -> None:
        """Same score (0.70) passes for read (threshold 0.50) but blocks for modify (0.95)."""
        config = MappedThresholdConfig({"goal:modify": 0.95, "goal:read": 0.50})

        # read passes
        read_channel = InMemoryApprovalChannel()
        gate_read = k7_gate(
            operation_type="goal:read",
            payload=_PAYLOAD,
            evaluator=FixedConfidenceEvaluator(0.70),
            threshold_config=config,
            approval_channel=read_channel,
            timeout_seconds=1.0,
        )
        ctx_read = KernelContext(gates=[gate_read])
        asyncio.run(ctx_read.__aenter__())
        asyncio.run(ctx_read.__aexit__(None, None, None))
        assert len(read_channel.emitted) == 0

        # modify blocks (no decision injected → timeout)
        class AutoEmitTimeout(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)

            def wait_for_decision(
                self, request_id: str, *, timeout: float
            ) -> HumanDecision:
                raise ApprovalTimeout(request_id, timeout_seconds=timeout)

        tc = AutoEmitTimeout()
        gate_mod = k7_gate(
            operation_type="goal:modify",
            payload=_PAYLOAD,
            evaluator=FixedConfidenceEvaluator(0.70),
            threshold_config=config,
            approval_channel=tc,
            timeout_seconds=1.0,
        )
        with pytest.raises(ApprovalTimeout):
            asyncio.run(KernelContext(gates=[gate_mod]).__aenter__())
        assert len(tc.emitted) == 1

    def test_default_threshold_used_for_unknown_op(self) -> None:
        config = MappedThresholdConfig({}, default_threshold=0.75)
        assert config.get_threshold("unknown:op") == pytest.approx(0.75)

    def test_fixed_threshold_same_for_all_ops(self) -> None:
        config = FixedThresholdConfig(0.80)
        assert config.get_threshold("goal:modify") == pytest.approx(0.80)
        assert config.get_threshold("goal:read") == pytest.approx(0.80)
        assert config.get_threshold("anything") == pytest.approx(0.80)


# ---------------------------------------------------------------------------
# TestK7ChannelFailSafe — AC9: emit failure
# ---------------------------------------------------------------------------


class TestK7ChannelFailSafe:
    """Approval channel failure raises ApprovalChannelError (AC9)."""

    def test_emit_failure_raises_channel_error(self) -> None:
        channel = InMemoryApprovalChannel()
        channel.set_fail_emit(fail=True)
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ApprovalChannelError, match="emit fail-mode"):
            asyncio.run(ctx.__aenter__())

    def test_emit_failure_context_to_idle(self) -> None:
        from holly.kernel.state_machine import KernelState

        channel = InMemoryApprovalChannel()
        channel.set_fail_emit(fail=True)
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with contextlib.suppress(ApprovalChannelError):
            asyncio.run(ctx.__aenter__())
        assert ctx.state == KernelState.IDLE

    def test_wait_raises_channel_error_on_unexpected_exception(self) -> None:
        class BadWaitChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)

            def wait_for_decision(
                self, request_id: str, *, timeout: float
            ) -> HumanDecision:
                raise ConnectionError("lost connection")

        channel = BadWaitChannel()
        gate = _make_gate(0.70, 0.85, channel)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ApprovalChannelError, match="ConnectionError"):
            asyncio.run(ctx.__aenter__())


# ---------------------------------------------------------------------------
# TestK7GateInterfaceAndComposition
# ---------------------------------------------------------------------------


class TestK7GateInterfaceAndComposition:
    """Gate factory returns a coroutine-function accepting KernelContext."""

    def test_k7_gate_returns_callable(self) -> None:
        import inspect

        channel = InMemoryApprovalChannel()
        gate = _make_gate(0.95, 0.85, channel)
        assert callable(gate)
        assert inspect.iscoroutinefunction(gate)

    def test_k7_gate_accepts_context_parameter(self) -> None:
        import inspect

        channel = InMemoryApprovalChannel()
        gate = _make_gate(0.95, 0.85, channel)
        sig = inspect.signature(gate)
        params = list(sig.parameters.keys())
        assert "ctx" in params

    def test_k7_composed_with_other_gates(self) -> None:
        """k7_gate composes correctly when used alongside other gates."""
        from holly.kernel.k5 import InMemoryIdempotencyStore, k5_gate

        class AutoApproveChannel(InMemoryApprovalChannel):
            def emit(self, request: ApprovalRequest) -> None:
                super().emit(request)
                self.inject_approve(request.request_id)

        store = InMemoryIdempotencyStore()
        channel = AutoApproveChannel()
        gate_k5 = k5_gate(payload={"op": "test"}, store=store)
        gate_k7 = k7_gate(
            operation_type="workflow:execute",
            payload={"op": "test"},
            evaluator=FixedConfidenceEvaluator(0.70),  # below threshold → approval
            threshold_config=FixedThresholdConfig(0.85),
            approval_channel=channel,
            timeout_seconds=1.0,
        )
        ctx = KernelContext(gates=[gate_k5, gate_k7])
        asyncio.run(ctx.__aenter__())
        asyncio.run(ctx.__aexit__(None, None, None))
        assert len(channel.emitted) == 1


# ---------------------------------------------------------------------------
# TestK7FixedConfidenceEvaluator
# ---------------------------------------------------------------------------


class TestK7FixedConfidenceEvaluator:
    """Unit tests for FixedConfidenceEvaluator helper."""

    def test_returns_fixed_score(self) -> None:
        e = FixedConfidenceEvaluator(0.75)
        assert e.evaluate("any:op", {}) == pytest.approx(0.75)

    def test_score_below_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            FixedConfidenceEvaluator(-0.01)

    def test_score_above_one_raises(self) -> None:
        with pytest.raises(ValueError):
            FixedConfidenceEvaluator(1.01)

    def test_boundary_values(self) -> None:
        assert FixedConfidenceEvaluator(0.0).evaluate("op", {}) == pytest.approx(0.0)
        assert FixedConfidenceEvaluator(1.0).evaluate("op", {}) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TestK7MappedThresholdConfig
# ---------------------------------------------------------------------------


class TestK7MappedThresholdConfig:
    """Unit tests for MappedThresholdConfig helper."""

    def test_invalid_threshold_raises(self) -> None:
        with pytest.raises(ValueError):
            MappedThresholdConfig({"op": 1.5})

    def test_invalid_default_raises(self) -> None:
        with pytest.raises(ValueError):
            MappedThresholdConfig({}, default_threshold=-0.1)

    def test_lookup_and_default(self) -> None:
        cfg = MappedThresholdConfig({"a": 0.9}, default_threshold=0.7)
        assert cfg.get_threshold("a") == pytest.approx(0.9)
        assert cfg.get_threshold("b") == pytest.approx(0.7)
