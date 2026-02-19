"""Tests for k3 — K3 resource bounds checking gate.

Task 16.5 — K3 bounds checking per TLA+.

Traces to: Behavior Spec §1.4 K3, TLA+ spec (14.1), KernelContext (15.4).
SIL: 3

Acceptance criteria verified (per Task_Manifest.md §16.5):
  AC1  Within-budget request passes gate; state -> ACTIVE then IDLE
  AC2  Over-budget request raises BoundsExceeded; state -> IDLE
  AC3  Unknown budget raises BudgetNotFoundError; state -> IDLE
  AC4  Invalid (negative) budget raises InvalidBudgetError; state -> IDLE
  AC5  Usage tracker failure raises UsageTrackingError (fail-safe deny)
  AC6  Per-tenant isolation: T1 exhausted does not affect T2
  AC7  Usage increments correctly after successful crossing
  AC8  k3_gate integrates with KernelContext; Gate protocol satisfied

Test taxonomy
-------------
Structure        k3 importable; gate factory; UsageTracker protocol; BudgetRegistry
HappyPath        within budget; zero usage; zero requested; multi-resource independent;
                 IDLE after; usage incremented
BoundsExceeded   over-budget raises; attributes correct; usage=0+big request; partial usage
BudgetNotFound   missing budget -> BudgetNotFoundError + IDLE
InvalidBudget    negative limit -> InvalidBudgetError at register time
NegativeRequest  requested < 0 -> ValueError
UsageTrackerFail tracker unavailable -> UsageTrackingError (fail-safe deny) + IDLE
PerTenantIsolation T1 exhausted; T2 unaffected
UsageAccumulation multiple crossings accumulate usage
Ordering         k3_gate composes with k1_gate + k2_gate; fail stops subsequent
Property         Hypothesis: within-budget always IDLE; over-budget always BoundsExceeded+IDLE
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.budget_registry import BudgetRegistry
from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    BoundsExceeded,
    BudgetNotFoundError,
    InvalidBudgetError,
    UsageTrackingError,
)
from holly.kernel.k3 import (
    FailUsageTracker,
    InMemoryUsageTracker,
    UsageTracker,
    k3_check_bounds,
    k3_gate,
)
from holly.kernel.state_machine import KernelState

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
RES_TOKENS = "tokens"
RES_CPU = "cpu_ms"


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    BudgetRegistry.clear()
    yield
    BudgetRegistry.clear()


@pytest.fixture()
def tracker() -> InMemoryUsageTracker:
    return InMemoryUsageTracker()


@pytest.fixture()
def budget_ab(tracker: InMemoryUsageTracker) -> InMemoryUsageTracker:
    """Register 1000 tokens for T_A and T_B; return tracker."""
    BudgetRegistry.register(TENANT_A, RES_TOKENS, 1000)
    BudgetRegistry.register(TENANT_B, RES_TOKENS, 1000)
    return tracker


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestStructure:
    def test_k3_gate_importable(self) -> None:
        from holly.kernel.k3 import k3_gate as _g

        assert _g is not None

    def test_k3_gate_importable_from_kernel_init(self) -> None:
        from holly.kernel import k3_gate as _g

        assert _g is not None

    def test_k3_check_permissions_importable(self) -> None:
        from holly.kernel.k3 import k3_check_bounds as _f

        assert _f is not None

    def test_in_memory_tracker_is_usage_tracker(self) -> None:
        assert isinstance(InMemoryUsageTracker(), UsageTracker)

    def test_fail_tracker_is_usage_tracker(self) -> None:
        assert isinstance(FailUsageTracker(), UsageTracker)

    def test_k3_gate_returns_callable(self, budget_ab: InMemoryUsageTracker) -> None:
        gate = k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=budget_ab)
        assert callable(gate)

    def test_returned_gate_is_coroutine_function(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        import inspect

        gate = k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=budget_ab)
        assert inspect.iscoroutinefunction(gate)

    def test_budget_registry_register_and_get(self) -> None:
        BudgetRegistry.register("t1", "cpu", 500)
        assert BudgetRegistry.get("t1", "cpu") == 500

    def test_budget_registry_has_budget(self) -> None:
        BudgetRegistry.register("t2", "mem", 200)
        assert BudgetRegistry.has_budget("t2", "mem")
        assert not BudgetRegistry.has_budget("t2", "disk")

    def test_budget_registry_duplicate_raises(self) -> None:
        BudgetRegistry.register("t3", "net", 100)
        with pytest.raises(ValueError, match="already registered"):
            BudgetRegistry.register("t3", "net", 200)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_within_budget_passes(self, budget_ab: InMemoryUsageTracker) -> None:
        """AC1: within-budget request passes gate."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=budget_ab)]
        )
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_zero_requested_always_passes(self, budget_ab: InMemoryUsageTracker) -> None:
        """Zero-amount request: budget is never consumed."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 0, usage_tracker=budget_ab)]
        )
        async with ctx:
            pass
        assert ctx.state == KernelState.IDLE
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 0

    @pytest.mark.asyncio
    async def test_exact_budget_passes(self, budget_ab: InMemoryUsageTracker) -> None:
        """Request exactly equal to budget: passes (usage + requested == budget, not >)."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 1000, usage_tracker=budget_ab)]
        )
        async with ctx:
            pass
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_usage_incremented_after_success(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """AC7: successful crossing increments usage."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 300, usage_tracker=budget_ab)]
        )
        async with ctx:
            pass
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 300

    @pytest.mark.asyncio
    async def test_multiple_crossings_accumulate_usage(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """Three crossings of 100 tokens: usage = 300 after all."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=budget_ab)]
        )
        for _ in range(3):
            async with ctx:
                pass
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 300
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_multiple_resource_types_independent(
        self, tracker: InMemoryUsageTracker
    ) -> None:
        """Different resource types are independent."""
        BudgetRegistry.register(TENANT_A, RES_TOKENS, 1000)
        BudgetRegistry.register(TENANT_A, RES_CPU, 5000)
        ctx = KernelContext(
            gates=[
                k3_gate(TENANT_A, RES_TOKENS, 500, usage_tracker=tracker),
                k3_gate(TENANT_A, RES_CPU, 2000, usage_tracker=tracker),
            ]
        )
        async with ctx:
            pass
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 500
        assert tracker.get_usage(TENANT_A, RES_CPU) == 2000


# ---------------------------------------------------------------------------
# BoundsExceeded
# ---------------------------------------------------------------------------


class TestBoundsExceeded:
    @pytest.mark.asyncio
    async def test_over_budget_raises(self, budget_ab: InMemoryUsageTracker) -> None:
        """AC2: usage + requested > budget → BoundsExceeded + IDLE."""
        # pre-load 800 usage so 300 more exceeds 1000
        budget_ab.increment(TENANT_A, RES_TOKENS, 800)
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 300, usage_tracker=budget_ab)]
        )
        with pytest.raises(BoundsExceeded) as exc_info:
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE
        exc = exc_info.value
        assert exc.tenant_id == TENANT_A
        assert exc.resource_type == RES_TOKENS
        assert exc.budget == 1000
        assert exc.current == 800
        assert exc.requested == 300
        assert exc.remaining == 200

    @pytest.mark.asyncio
    async def test_single_request_exceeds_budget(
        self, tracker: InMemoryUsageTracker
    ) -> None:
        """Single request > budget with zero usage."""
        BudgetRegistry.register(TENANT_A, RES_TOKENS, 100)
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 500, usage_tracker=tracker)]
        )
        with pytest.raises(BoundsExceeded):
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE
        # Usage must NOT have been incremented
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 0

    @pytest.mark.asyncio
    async def test_usage_not_incremented_on_failure(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """After BoundsExceeded, usage counter is unchanged."""
        budget_ab.increment(TENANT_A, RES_TOKENS, 900)
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 200, usage_tracker=budget_ab)]
        )
        with pytest.raises(BoundsExceeded):
            async with ctx:
                pass
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 900  # unchanged

    def test_check_bounds_direct_raises(self, budget_ab: InMemoryUsageTracker) -> None:
        budget_ab.increment(TENANT_A, RES_TOKENS, 800)
        with pytest.raises(BoundsExceeded):
            k3_check_bounds(TENANT_A, RES_TOKENS, 300, usage_tracker=budget_ab)


# ---------------------------------------------------------------------------
# Budget not found
# ---------------------------------------------------------------------------


class TestBudgetNotFound:
    @pytest.mark.asyncio
    async def test_missing_budget_raises(self, tracker: InMemoryUsageTracker) -> None:
        """AC3: no budget for (tenant, resource) → BudgetNotFoundError + IDLE."""
        ctx = KernelContext(
            gates=[k3_gate("unknown-tenant", RES_TOKENS, 100, usage_tracker=tracker)]
        )
        with pytest.raises(BudgetNotFoundError) as exc_info:
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE
        exc = exc_info.value
        assert exc.tenant_id == "unknown-tenant"
        assert exc.resource_type == RES_TOKENS

    def test_get_unknown_budget_raises(self) -> None:
        with pytest.raises(BudgetNotFoundError):
            BudgetRegistry.get("ghost-tenant", "unknown-resource")


# ---------------------------------------------------------------------------
# Invalid budget
# ---------------------------------------------------------------------------


class TestInvalidBudget:
    def test_negative_limit_raises_at_register(self) -> None:
        """AC4: negative limit → InvalidBudgetError at registration time."""
        with pytest.raises(InvalidBudgetError) as exc_info:
            BudgetRegistry.register(TENANT_A, RES_TOKENS, -1)
        exc = exc_info.value
        assert exc.limit == -1
        assert exc.tenant_id == TENANT_A

    def test_zero_limit_is_valid(self) -> None:
        """Zero budget is valid (all requests immediately exceed it)."""
        BudgetRegistry.register(TENANT_A, RES_TOKENS, 0)
        assert BudgetRegistry.get(TENANT_A, RES_TOKENS) == 0

    @pytest.mark.asyncio
    async def test_zero_budget_rejects_positive_request(
        self, tracker: InMemoryUsageTracker
    ) -> None:
        """Zero budget: any positive request is immediately rejected."""
        BudgetRegistry.register(TENANT_A, RES_TOKENS, 0)
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 1, usage_tracker=tracker)]
        )
        with pytest.raises(BoundsExceeded):
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE


# ---------------------------------------------------------------------------
# Negative requested
# ---------------------------------------------------------------------------


class TestNegativeRequested:
    @pytest.mark.asyncio
    async def test_negative_requested_raises_value_error(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """requested < 0 → ValueError (not a KernelError)."""
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, -1, usage_tracker=budget_ab)]
        )
        with pytest.raises(ValueError):
            async with ctx:
                pass

    def test_check_bounds_negative_raises(self, budget_ab: InMemoryUsageTracker) -> None:
        with pytest.raises(ValueError):
            k3_check_bounds(TENANT_A, RES_TOKENS, -10, usage_tracker=budget_ab)


# ---------------------------------------------------------------------------
# Usage tracker failure (fail-safe deny)
# ---------------------------------------------------------------------------


class TestUsageTrackerFail:
    @pytest.mark.asyncio
    async def test_tracker_fail_raises_usage_tracking_error(self) -> None:
        """AC5: tracker unavailable → UsageTrackingError (fail-safe deny) + IDLE."""
        BudgetRegistry.register(TENANT_A, RES_TOKENS, 1000)
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=FailUsageTracker())]
        )
        with pytest.raises(UsageTrackingError):
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE

    def test_fail_tracker_get_raises(self) -> None:
        with pytest.raises(UsageTrackingError):
            FailUsageTracker().get_usage(TENANT_A, RES_TOKENS)

    def test_fail_tracker_increment_raises(self) -> None:
        with pytest.raises(UsageTrackingError):
            FailUsageTracker().increment(TENANT_A, RES_TOKENS, 10)


# ---------------------------------------------------------------------------
# Per-tenant isolation
# ---------------------------------------------------------------------------


class TestPerTenantIsolation:
    @pytest.mark.asyncio
    async def test_exhausted_tenant_does_not_affect_other(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """AC6: T_A exhausted; T_B still passes."""
        # Exhaust T_A
        budget_ab.increment(TENANT_A, RES_TOKENS, 1000)
        ctx_a = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 1, usage_tracker=budget_ab)]
        )
        with pytest.raises(BoundsExceeded):
            async with ctx_a:
                pass

        # T_B should still have 1000 budget available
        ctx_b = KernelContext(
            gates=[k3_gate(TENANT_B, RES_TOKENS, 500, usage_tracker=budget_ab)]
        )
        async with ctx_b:
            pass
        assert ctx_b.state == KernelState.IDLE
        assert budget_ab.get_usage(TENANT_B, RES_TOKENS) == 500

    @pytest.mark.asyncio
    async def test_independent_usage_counters(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """T_A and T_B usage counters are independent."""
        ctx_a = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, 300, usage_tracker=budget_ab)]
        )
        ctx_b = KernelContext(
            gates=[k3_gate(TENANT_B, RES_TOKENS, 700, usage_tracker=budget_ab)]
        )
        async with ctx_a:
            pass
        async with ctx_b:
            pass
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 300
        assert budget_ab.get_usage(TENANT_B, RES_TOKENS) == 700


# ---------------------------------------------------------------------------
# Ordering / composition
# ---------------------------------------------------------------------------


class TestOrdering:
    @pytest.mark.asyncio
    async def test_k3_composes_with_k1_and_k2_gates(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """AC8: k1_gate + k2_gate + k3_gate all in KernelContext.gates list."""
        from holly.kernel.k1 import k1_gate
        from holly.kernel.k2 import k2_gate
        from holly.kernel.permission_registry import PermissionRegistry
        from holly.kernel.schema_registry import SchemaRegistry

        SchemaRegistry.clear()
        PermissionRegistry.clear()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        }
        SchemaRegistry.register("ICD-K3-COMPOSE", schema)
        PermissionRegistry.register_role("op", {"read:data"})

        claims = {"sub": "svc-1", "roles": ["op"]}

        ctx = KernelContext(
            gates=[
                k1_gate({"name": "Alice"}, "ICD-K3-COMPOSE"),
                k2_gate(claims, required={"read:data"}),
                k3_gate(TENANT_A, RES_TOKENS, 100, usage_tracker=budget_ab),
            ]
        )
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE
        assert budget_ab.get_usage(TENANT_A, RES_TOKENS) == 100

        SchemaRegistry.clear()
        PermissionRegistry.clear()

    @pytest.mark.asyncio
    async def test_k3_fail_stops_subsequent_gates(
        self, budget_ab: InMemoryUsageTracker
    ) -> None:
        """First-fail-abort: k3 failure prevents subsequent gate execution."""
        ran: list[bool] = []

        async def _should_not_run(ctx: KernelContext) -> None:
            ran.append(True)

        # Pre-load T_A to 900; request 200 → exceeds 1000
        budget_ab.increment(TENANT_A, RES_TOKENS, 900)
        ctx = KernelContext(
            gates=[
                k3_gate(TENANT_A, RES_TOKENS, 200, usage_tracker=budget_ab),
                _should_not_run,
            ]
        )
        with pytest.raises(BoundsExceeded):
            async with ctx:
                pass
        assert not ran


# ---------------------------------------------------------------------------
# InMemoryUsageTracker unit tests
# ---------------------------------------------------------------------------


class TestInMemoryTracker:
    def test_initial_usage_is_zero(self, tracker: InMemoryUsageTracker) -> None:
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 0

    def test_increment_and_get(self, tracker: InMemoryUsageTracker) -> None:
        tracker.increment(TENANT_A, RES_TOKENS, 100)
        tracker.increment(TENANT_A, RES_TOKENS, 50)
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 150

    def test_reset_specific_key(self, tracker: InMemoryUsageTracker) -> None:
        tracker.increment(TENANT_A, RES_TOKENS, 100)
        tracker.reset(TENANT_A, RES_TOKENS)
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 0

    def test_reset_all(self, tracker: InMemoryUsageTracker) -> None:
        tracker.increment(TENANT_A, RES_TOKENS, 100)
        tracker.increment(TENANT_B, RES_CPU, 200)
        tracker.reset()
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 0
        assert tracker.get_usage(TENANT_B, RES_CPU) == 0


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------


class TestPropertyBased:
    @given(
        requested=st.integers(min_value=0, max_value=999),
        budget=st.integers(min_value=1000, max_value=5000),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_within_budget_always_idles(
        self, requested: int, budget: int
    ) -> None:
        """Property: any request ≤ budget (with zero usage) → IDLE after gate."""
        BudgetRegistry.clear()
        BudgetRegistry.register(TENANT_A, RES_TOKENS, budget)
        tracker = InMemoryUsageTracker()
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, requested, usage_tracker=tracker)]
        )
        async with ctx:
            assert ctx.state == KernelState.ACTIVE
        assert ctx.state == KernelState.IDLE
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == requested
        BudgetRegistry.clear()

    @given(
        excess=st.integers(min_value=1, max_value=1000),
        budget=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_over_budget_always_raises_and_idles(
        self, excess: int, budget: int
    ) -> None:
        """Property: request = budget + excess → BoundsExceeded + IDLE."""
        BudgetRegistry.clear()
        BudgetRegistry.register(TENANT_A, RES_TOKENS, budget)
        tracker = InMemoryUsageTracker()
        requested = budget + excess
        ctx = KernelContext(
            gates=[k3_gate(TENANT_A, RES_TOKENS, requested, usage_tracker=tracker)]
        )
        with pytest.raises(BoundsExceeded) as exc_info:
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE
        assert exc_info.value.requested == requested
        assert tracker.get_usage(TENANT_A, RES_TOKENS) == 0  # NOT incremented
        BudgetRegistry.clear()
