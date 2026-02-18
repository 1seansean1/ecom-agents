"""Unit tests: K8 eval gate — predicate registry + k8_evaluate.

Task 3a.10 — Validate the K8 eval gate per Behavior Spec §1.9.

Acceptance criteria from spec:
  AC1: Pass on valid output — predicate returns True → no exception
  AC2: Fail on invalid output — predicate returns False → EvalGateFailure
  AC3: Predicate loading — predicate_registry.get() called exactly once
  AC4: Timeout enforcement — deferred to full KernelContext (Task 18.9)
  AC5: Missing predicate → PredicateNotFoundError
  AC6: Deterministic evaluation — same output always same result
  AC7: Failure blocks output — EvalGateFailure means result not returned

Plus property-based tests for invariant-heavy paths.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.arch.decorators import eval_gated, get_holly_meta
from holly.kernel.exceptions import (
    EvalError,
    EvalGateFailure,
    PredicateAlreadyRegisteredError,
    PredicateNotFoundError,
)
from holly.kernel.k8 import k8_evaluate
from holly.kernel.predicate_registry import PredicateRegistry

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_predicate_registry() -> Any:
    """Reset the predicate registry before and after each test."""
    PredicateRegistry.clear()
    yield
    PredicateRegistry.clear()


# ── PredicateRegistry tests ────────────────────────────────────────────


class TestPredicateRegistry:
    """PredicateRegistry mirrors SchemaRegistry — thread-safe singleton."""

    def test_register_and_get(self) -> None:
        pred = lambda output: True  # noqa: E731
        PredicateRegistry.register("pred-001", pred)
        assert PredicateRegistry.get("pred-001") is pred

    def test_has_returns_true_when_registered(self) -> None:
        PredicateRegistry.register("pred-002", lambda o: True)
        assert PredicateRegistry.has("pred-002") is True

    def test_has_returns_false_when_missing(self) -> None:
        assert PredicateRegistry.has("nonexistent") is False

    def test_get_missing_raises_predicate_not_found(self) -> None:
        with pytest.raises(PredicateNotFoundError) as exc_info:
            PredicateRegistry.get("missing-pred")
        assert exc_info.value.predicate_id == "missing-pred"

    def test_duplicate_registration_raises(self) -> None:
        PredicateRegistry.register("dup", lambda o: True)
        with pytest.raises(PredicateAlreadyRegisteredError) as exc_info:
            PredicateRegistry.register("dup", lambda o: False)
        assert exc_info.value.predicate_id == "dup"

    def test_register_non_callable_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Expected callable"):
            PredicateRegistry.register("bad", "not_callable")  # type: ignore[arg-type]

    def test_clear_removes_all(self) -> None:
        PredicateRegistry.register("x", lambda o: True)
        PredicateRegistry.clear()
        assert PredicateRegistry.has("x") is False

    def test_registered_ids_returns_frozenset(self) -> None:
        PredicateRegistry.register("a", lambda o: True)
        PredicateRegistry.register("b", lambda o: False)
        ids = PredicateRegistry.registered_ids()
        assert ids == frozenset({"a", "b"})
        assert isinstance(ids, frozenset)


# ══════════════════════════════════════════════════════════════════════
# AC1: Valid output passes K8 (predicate returns True)
# ══════════════════════════════════════════════════════════════════════


class TestValidOutputPassesK8:
    """AC1: Output satisfying predicate passes K8 — no exception."""

    def test_pass_returns_true(self) -> None:
        PredicateRegistry.register("always-pass", lambda o: True)
        result = k8_evaluate({"data": "valid"}, "always-pass")
        assert result is True

    def test_pass_with_complex_output(self) -> None:
        PredicateRegistry.register(
            "check-name",
            lambda o: isinstance(o, dict) and "name" in o,
        )
        result = k8_evaluate({"name": "test", "value": 42}, "check-name")
        assert result is True

    def test_pass_with_none_output(self) -> None:
        """Predicate that accepts None should pass."""
        PredicateRegistry.register("accepts-none", lambda o: o is None)
        result = k8_evaluate(None, "accepts-none")
        assert result is True


# ══════════════════════════════════════════════════════════════════════
# AC2: Invalid output raises EvalGateFailure
# ══════════════════════════════════════════════════════════════════════


class TestInvalidOutputRaisesEvalGateFailure:
    """AC2: Output violating predicate raises EvalGateFailure."""

    def test_false_predicate_raises(self) -> None:
        PredicateRegistry.register("always-fail", lambda o: False)
        with pytest.raises(EvalGateFailure) as exc_info:
            k8_evaluate({"data": "bad"}, "always-fail")
        assert exc_info.value.predicate_id == "always-fail"
        assert len(exc_info.value.output_hash) == 64  # SHA-256

    def test_conditional_predicate_rejects_invalid(self) -> None:
        PredicateRegistry.register(
            "check-positive",
            lambda o: isinstance(o, dict) and o.get("value", 0) > 0,
        )
        with pytest.raises(EvalGateFailure) as exc_info:
            k8_evaluate({"value": -1}, "check-positive")
        assert exc_info.value.predicate_id == "check-positive"
        assert "violated eval gate" in exc_info.value.reason

    def test_failure_blocks_output(self) -> None:
        """AC7: When K8 fails, output is not returned to caller."""
        PredicateRegistry.register("blocker", lambda o: False)
        with pytest.raises(EvalGateFailure):
            # If this doesn't raise, the test fails — output must be blocked
            k8_evaluate({"secret": "data"}, "blocker")


# ══════════════════════════════════════════════════════════════════════
# AC3: Predicate loaded from registry exactly once
# ══════════════════════════════════════════════════════════════════════


class TestPredicateLoadedOnce:
    """AC3: Predicate is resolved via registry once per call."""

    def test_registry_get_called_once(self) -> None:
        real_pred = lambda o: True  # noqa: E731
        PredicateRegistry.register("tracked", real_pred)

        # Spy on PredicateRegistry.get
        original_get = PredicateRegistry.get
        call_count = 0

        @classmethod  # type: ignore[misc]
        def counting_get(cls: type, predicate_id: str) -> Any:
            nonlocal call_count
            call_count += 1
            return original_get(predicate_id)

        PredicateRegistry.get = counting_get  # type: ignore[assignment]
        try:
            k8_evaluate({"x": 1}, "tracked")
            assert call_count == 1
        finally:
            PredicateRegistry.get = original_get  # type: ignore[assignment]


# ══════════════════════════════════════════════════════════════════════
# AC5: Missing predicate raises PredicateNotFoundError
# ══════════════════════════════════════════════════════════════════════


class TestMissingPredicateError:
    """AC5: Unregistered predicate → PredicateNotFoundError."""

    def test_missing_predicate_raises(self) -> None:
        with pytest.raises(PredicateNotFoundError) as exc_info:
            k8_evaluate({"data": "any"}, "nonexistent-pred")
        assert exc_info.value.predicate_id == "nonexistent-pred"


# ══════════════════════════════════════════════════════════════════════
# AC6: Deterministic evaluation
# ══════════════════════════════════════════════════════════════════════


class TestDeterministicEvaluation:
    """AC6: Same output always produces the same result."""

    def test_same_output_same_result(self) -> None:
        PredicateRegistry.register("deterministic", lambda o: o.get("v") > 0)
        output = {"v": 5}
        r1 = k8_evaluate(output, "deterministic")
        r2 = k8_evaluate(output, "deterministic")
        assert r1 == r2 == True  # noqa: E712


# ══════════════════════════════════════════════════════════════════════
# Error paths: EvalError, non-bool predicates
# ══════════════════════════════════════════════════════════════════════


class TestEvalErrors:
    """Predicate evaluation errors are caught and wrapped as EvalError."""

    def test_exception_in_predicate_raises_eval_error(self) -> None:
        def bad_pred(output: Any) -> bool:
            msg = "internal predicate failure"
            raise RuntimeError(msg)

        PredicateRegistry.register("broken", bad_pred)
        with pytest.raises(EvalError) as exc_info:
            k8_evaluate({"x": 1}, "broken")
        assert exc_info.value.predicate_id == "broken"
        assert "internal predicate failure" in exc_info.value.detail

    def test_type_error_in_predicate_raises_eval_error(self) -> None:
        def type_bad(output: Any) -> bool:
            return output + 1  # type error if output is dict

        PredicateRegistry.register("type-bad", type_bad)
        with pytest.raises(EvalError) as exc_info:
            k8_evaluate({"x": 1}, "type-bad")
        assert exc_info.value.predicate_id == "type-bad"


# ══════════════════════════════════════════════════════════════════════
# Decorator integration: @eval_gated wires K8 enforcement
# ══════════════════════════════════════════════════════════════════════


class TestEvalGatedDecoratorIntegration:
    """@eval_gated with predicate wires K8 post-call enforcement."""

    def test_decorator_attaches_metadata(self) -> None:
        @eval_gated(predicate="test-pred", gate_id="K8", validate=False)
        def my_func() -> dict[str, str]:
            return {"result": "ok"}

        meta = get_holly_meta(my_func)
        assert meta is not None
        assert meta["kind"] == "eval_gated"
        assert meta["predicate"] == "test-pred"
        assert meta["gate_id"] == "K8"

    def test_decorator_enforces_k8_on_return(self) -> None:
        PredicateRegistry.register(
            "check-status",
            lambda o: isinstance(o, dict) and o.get("status") == "ok",
        )

        @eval_gated(predicate="check-status", gate_id="K8", validate=False)
        def good_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        # Valid output passes
        result = good_endpoint()
        assert result == {"status": "ok"}

    def test_decorator_blocks_invalid_return(self) -> None:
        PredicateRegistry.register(
            "check-status-2",
            lambda o: isinstance(o, dict) and o.get("status") == "ok",
        )

        @eval_gated(predicate="check-status-2", gate_id="K8", validate=False)
        def bad_endpoint() -> dict[str, str]:
            return {"status": "error"}

        with pytest.raises(EvalGateFailure) as exc_info:
            bad_endpoint()
        assert exc_info.value.predicate_id == "check-status-2"

    def test_decorator_without_predicate_is_passthrough(self) -> None:
        """@eval_gated with empty predicate does not enforce K8."""

        @eval_gated(validate=False)
        def passthrough_func() -> str:
            return "anything"

        assert passthrough_func() == "anything"


# ══════════════════════════════════════════════════════════════════════
# Property-based tests (Hypothesis)
# ══════════════════════════════════════════════════════════════════════


class TestK8PropertyBased:
    """Property-based tests for K8 invariants."""

    @given(value=st.integers())
    @settings(max_examples=50)
    def test_positive_predicate_invariant(self, value: int) -> None:
        """Invariant: predicate(output)=True ⟹ k8_evaluate returns True."""
        pred_id = "prop-positive"
        if not PredicateRegistry.has(pred_id):
            PredicateRegistry.register(pred_id, lambda o: o > 0)

        if value > 0:
            assert k8_evaluate(value, pred_id) is True
        else:
            with pytest.raises(EvalGateFailure):
                k8_evaluate(value, pred_id)

    @given(data=st.dictionaries(st.text(min_size=1, max_size=5), st.integers()))
    @settings(max_examples=50)
    def test_determinism_property(self, data: dict[str, int]) -> None:
        """Invariant 3: Same output always same predicate result."""
        pred_id = "prop-deterministic"
        if not PredicateRegistry.has(pred_id):
            PredicateRegistry.register(
                pred_id, lambda o: len(o) > 0
            )

        # Call twice — result must be identical
        try:
            r1 = k8_evaluate(data, pred_id)
        except EvalGateFailure:
            r1 = "FAIL"
        try:
            r2 = k8_evaluate(data, pred_id)
        except EvalGateFailure:
            r2 = "FAIL"
        assert r1 == r2

    @given(output=st.one_of(st.integers(), st.text(), st.none()))
    @settings(max_examples=50)
    def test_output_hash_is_sha256(self, output: Any) -> None:
        """Output hash in EvalGateFailure is always 64-char hex (SHA-256)."""
        pred_id = "prop-always-fail"
        if not PredicateRegistry.has(pred_id):
            PredicateRegistry.register(pred_id, lambda o: False)

        with pytest.raises(EvalGateFailure) as exc_info:
            k8_evaluate(output, pred_id)
        h = exc_info.value.output_hash
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
