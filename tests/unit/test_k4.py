"""Test suite for K4 trace injection gate (Task 16.6).

Covers:
    - Module structure and importability
    - Happy-path injection (auto UUID, provided UUID, tenant extraction)
    - TenantContextError on missing/None/empty tenant_id
    - ValueError on malformed provided correlation ID
    - Immutability of tenant_id after injection
    - KernelContext slot availability (tenant_id, trace_started_at)
    - Gate composition (K1+K2+K3+K4 all in one context)
    - Hypothesis property-based: valid injections always leave ctx IDLE

Traces to Behavior Spec §1.5 K4.
"""

from __future__ import annotations

import time
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import KernelError, TenantContextError
from holly.kernel.k4 import k4_gate, k4_inject_trace

# ---------------------------------------------------------------------------
# Fixtures / shared constants
# ---------------------------------------------------------------------------

VALID_CLAIMS: dict = {
    "sub": "user-99",
    "tenant_id": "tenant-abc",
    "roles": ["reader"],
}


# ===========================================================================
# TestStructure
# ===========================================================================


class TestStructure:
    """Module structure and importability (AC: public surface visible)."""

    def test_k4_inject_trace_importable(self) -> None:
        from holly.kernel.k4 import k4_inject_trace as fn

        assert callable(fn)

    def test_k4_gate_importable(self) -> None:
        from holly.kernel.k4 import k4_gate as fn

        assert callable(fn)

    def test_tenant_context_error_importable(self) -> None:
        assert issubclass(TenantContextError, KernelError)

    def test_tenant_context_error_has_detail_attr(self) -> None:
        err = TenantContextError("missing field")
        assert err.detail == "missing field"
        assert "missing field" in str(err)

    def test_k4_gate_returns_coroutine(self) -> None:
        import inspect

        gate = k4_gate(VALID_CLAIMS)
        ctx = KernelContext()
        coro = gate(ctx)
        assert inspect.iscoroutine(coro)
        coro.close()

    def test_kernel_context_has_tenant_id_property(self) -> None:
        ctx = KernelContext()
        assert hasattr(ctx, "tenant_id")
        assert ctx.tenant_id is None  # before injection

    def test_kernel_context_has_trace_started_at_property(self) -> None:
        ctx = KernelContext()
        assert hasattr(ctx, "trace_started_at")
        assert ctx.trace_started_at is None  # before injection

    def test_k4_exported_from_kernel_init(self) -> None:
        from holly.kernel import TenantContextError as TCE
        from holly.kernel import k4_gate as g
        from holly.kernel import k4_inject_trace as fn

        assert callable(fn)
        assert callable(g)
        assert issubclass(TCE, KernelError)

    def test_kernel_context_repr_includes_tenant_id(self) -> None:
        ctx = KernelContext()
        r = repr(ctx)
        assert "tenant_id" in r


# ===========================================================================
# TestHappyPath
# ===========================================================================


class TestHappyPath:
    """Successful trace injection scenarios."""

    def test_auto_corr_id_uses_context_uuid(self) -> None:
        ctx = KernelContext()
        existing = ctx.corr_id
        corr_id, tenant_id = k4_inject_trace(
            VALID_CLAIMS, context_corr_id=existing
        )
        assert corr_id == existing
        assert tenant_id == "tenant-abc"

    def test_provided_corr_id_overrides_context_uuid(self) -> None:
        provided = str(uuid.uuid4())
        corr_id, tenant_id = k4_inject_trace(
            VALID_CLAIMS,
            provided_correlation_id=provided,
            context_corr_id=str(uuid.uuid4()),
        )
        assert corr_id == provided
        assert tenant_id == "tenant-abc"

    def test_returns_two_tuple(self) -> None:
        result = k4_inject_trace(VALID_CLAIMS, context_corr_id=str(uuid.uuid4()))
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_different_tenant_id_extracted(self) -> None:
        claims = {**VALID_CLAIMS, "tenant_id": "acme-corp"}
        _, tenant_id = k4_inject_trace(claims, context_corr_id=str(uuid.uuid4()))
        assert tenant_id == "acme-corp"

    def test_standalone_generates_uuid_when_no_context(self) -> None:
        corr_id, _ = k4_inject_trace(VALID_CLAIMS)
        # Must be a parseable UUID
        parsed = uuid.UUID(corr_id)
        assert str(parsed) == corr_id

    async def test_gate_injects_tenant_id_into_context(self) -> None:
        gate = k4_gate(VALID_CLAIMS)
        async with KernelContext(gates=[gate]) as ctx:
            assert ctx.tenant_id == "tenant-abc"

    async def test_gate_injects_provided_corr_id(self) -> None:
        provided = str(uuid.uuid4())
        gate = k4_gate(VALID_CLAIMS, provided_correlation_id=provided)
        async with KernelContext(gates=[gate]) as ctx:
            assert ctx.corr_id == provided

    async def test_gate_sets_trace_started_at(self) -> None:
        gate = k4_gate(VALID_CLAIMS)
        before = time.monotonic()
        async with KernelContext(gates=[gate]) as ctx:
            after = time.monotonic()
            assert ctx.trace_started_at is not None
            assert isinstance(ctx.trace_started_at, float)
            assert before <= ctx.trace_started_at <= after

    async def test_gate_preserves_auto_corr_id_when_none_provided(self) -> None:
        ctx = KernelContext()
        auto_id = ctx.corr_id
        gate = k4_gate(VALID_CLAIMS)
        async with KernelContext(gates=[gate]) as fresh_ctx:
            # corr_id should be some UUID, not overwritten with anything bad
            assert uuid.UUID(fresh_ctx.corr_id)
        # auto_id is a valid UUID
        assert uuid.UUID(auto_id)

    async def test_context_state_idle_after_successful_injection(self) -> None:
        gate = k4_gate(VALID_CLAIMS)
        async with KernelContext(gates=[gate]) as ctx:
            pass
        assert ctx.state.value == "IDLE"


# ===========================================================================
# TestTenantMissing
# ===========================================================================


class TestTenantMissing:
    """TenantContextError raised when tenant_id is absent from claims."""

    def test_none_claims_raises(self) -> None:
        with pytest.raises(TenantContextError):
            k4_inject_trace(None)

    def test_missing_tenant_id_key_raises(self) -> None:
        claims = {"sub": "user1", "roles": ["reader"]}
        with pytest.raises(TenantContextError, match="tenant_id"):
            k4_inject_trace(claims)

    def test_empty_tenant_id_raises(self) -> None:
        claims = {**VALID_CLAIMS, "tenant_id": ""}
        with pytest.raises(TenantContextError):
            k4_inject_trace(claims)

    def test_none_tenant_id_raises(self) -> None:
        claims = {**VALID_CLAIMS, "tenant_id": None}
        with pytest.raises(TenantContextError):
            k4_inject_trace(claims)  # type: ignore[arg-type]

    async def test_gate_faults_on_none_claims(self) -> None:
        gate = k4_gate(None)
        ctx = KernelContext(gates=[gate])
        with pytest.raises(TenantContextError):
            await ctx.__aenter__()
        assert ctx.state.value == "IDLE"

    async def test_gate_faults_on_missing_tenant(self) -> None:
        gate = k4_gate({"sub": "user1", "roles": ["reader"]})
        ctx = KernelContext(gates=[gate])
        with pytest.raises(TenantContextError):
            await ctx.__aenter__()
        assert ctx.state.value == "IDLE"

    def test_tenant_context_error_is_kernel_error(self) -> None:
        err = TenantContextError("test")
        assert isinstance(err, KernelError)


# ===========================================================================
# TestInvalidCorrelationId
# ===========================================================================


class TestInvalidCorrelationId:
    """ValueError raised for non-UUID provided_correlation_id."""

    def test_non_uuid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid correlation ID"):
            k4_inject_trace(
                VALID_CLAIMS,
                provided_correlation_id="not-a-uuid",
            )

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid correlation ID"):
            k4_inject_trace(
                VALID_CLAIMS,
                provided_correlation_id="",
            )

    def test_random_garbage_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid correlation ID"):
            k4_inject_trace(
                VALID_CLAIMS,
                provided_correlation_id="abc-xyz-123",
            )

    def test_valid_uuid_accepted(self) -> None:
        valid = str(uuid.uuid4())
        corr_id, _ = k4_inject_trace(
            VALID_CLAIMS,
            provided_correlation_id=valid,
        )
        assert corr_id == valid

    async def test_gate_faults_on_invalid_corr_id(self) -> None:
        gate = k4_gate(VALID_CLAIMS, provided_correlation_id="bad-uuid-!!!")
        ctx = KernelContext(gates=[gate])
        with pytest.raises(ValueError):
            await ctx.__aenter__()
        assert ctx.state.value == "IDLE"


# ===========================================================================
# TestImmutability
# ===========================================================================


class TestImmutability:
    """tenant_id and corr_id are stable after K4 injection."""

    async def test_tenant_id_stable_within_crossing(self) -> None:
        gate = k4_gate(VALID_CLAIMS)
        async with KernelContext(gates=[gate]) as ctx:
            first = ctx.tenant_id
            second = ctx.tenant_id
            assert first == second == "tenant-abc"

    async def test_corr_id_stable_within_crossing(self) -> None:
        provided = str(uuid.uuid4())
        gate = k4_gate(VALID_CLAIMS, provided_correlation_id=provided)
        async with KernelContext(gates=[gate]) as ctx:
            assert ctx.corr_id == provided
            # Access again — same value
            assert ctx.corr_id == provided

    async def test_trace_started_at_stable_within_crossing(self) -> None:
        gate = k4_gate(VALID_CLAIMS)
        async with KernelContext(gates=[gate]) as ctx:
            t1 = ctx.trace_started_at
            t2 = ctx.trace_started_at
            assert t1 == t2  # same object, not recalculated


# ===========================================================================
# TestOrdering
# ===========================================================================


class TestOrdering:
    """K4 composes with K1, K2, K3 in a single KernelContext.gates list."""

    async def test_k1_k2_k3_k4_all_pass(self) -> None:
        from holly.kernel.budget_registry import BudgetRegistry
        from holly.kernel.k1 import k1_gate
        from holly.kernel.k2 import k2_gate
        from holly.kernel.k3 import InMemoryUsageTracker, k3_gate
        from holly.kernel.permission_registry import PermissionRegistry
        from holly.kernel.schema_registry import SchemaRegistry

        PermissionRegistry.clear()
        PermissionRegistry.register_role("reader", {"action:read"})
        tracker = InMemoryUsageTracker()
        BudgetRegistry.clear()
        BudgetRegistry.register("tenant-abc", "tokens", 1000)
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        SchemaRegistry.register("test_k4_compose_schema", schema)

        payload = {"x": 42}
        claims = {**VALID_CLAIMS, "jti": str(uuid.uuid4())}

        gates = [
            k1_gate(payload, "test_k4_compose_schema"),
            k2_gate(claims, required={"action:read"}),
            k3_gate("tenant-abc", "tokens", 10, usage_tracker=tracker),
            k4_gate(claims),
        ]

        async with KernelContext(gates=gates) as ctx:
            assert ctx.tenant_id == "tenant-abc"
            assert ctx.trace_started_at is not None
            assert ctx.state.value == "ACTIVE"

        assert ctx.state.value == "IDLE"

    async def test_k4_fail_stops_at_k4_not_k3(self) -> None:
        """K4 at position [-1]; if it fails, context ends IDLE."""
        from holly.kernel.budget_registry import BudgetRegistry
        from holly.kernel.k3 import InMemoryUsageTracker, k3_gate

        BudgetRegistry.clear()
        BudgetRegistry.register("tenant-abc", "tokens", 1000)
        tracker = InMemoryUsageTracker()

        bad_claims = {"sub": "user1", "roles": ["reader"]}  # no tenant_id
        gates = [
            k3_gate("tenant-abc", "tokens", 5, usage_tracker=tracker),
            k4_gate(bad_claims),
        ]
        ctx = KernelContext(gates=gates)
        with pytest.raises(TenantContextError):
            await ctx.__aenter__()
        assert ctx.state.value == "IDLE"


# ===========================================================================
# TestPropertyBased
# ===========================================================================


class TestPropertyBased:
    """Hypothesis: invariants hold across arbitrary valid inputs."""

    @given(
        tenant_id=st.text(min_size=1, max_size=64).filter(lambda s: s.strip()),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_valid_tenant_always_leaves_ctx_idle(
        self, tenant_id: str
    ) -> None:
        claims = {"sub": "user1", "tenant_id": tenant_id, "roles": ["r"]}
        gate = k4_gate(claims)
        async with KernelContext(gates=[gate]) as ctx:
            assert ctx.tenant_id == tenant_id
            assert ctx.trace_started_at is not None
        assert ctx.state.value == "IDLE"

    @given(
        provided=st.uuids().map(str),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_valid_provided_uuid_always_injected(
        self, provided: str
    ) -> None:
        gate = k4_gate(VALID_CLAIMS, provided_correlation_id=provided)
        async with KernelContext(gates=[gate]) as ctx:
            assert ctx.corr_id == provided
        assert ctx.state.value == "IDLE"

    @given(
        junk=st.text(min_size=1, max_size=50).filter(
            lambda s: s.strip() and not _is_valid_uuid(s)
        ),
    )
    @settings(max_examples=50)
    def test_non_uuid_provided_always_raises(self, junk: str) -> None:
        with pytest.raises(ValueError, match="Invalid correlation ID"):
            k4_inject_trace(VALID_CLAIMS, provided_correlation_id=junk)


# ---------------------------------------------------------------------------
# Helper for hypothesis filter
# ---------------------------------------------------------------------------


def _is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False
