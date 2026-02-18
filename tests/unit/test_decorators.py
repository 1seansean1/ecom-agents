"""Tests for Task 3.6 - core architectural decorators.

Acceptance criteria: each decorator stamps correct metadata.
Verification: property-based tests + explicit unit tests.

Test count: 25 tests across 9 test classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.arch.decorators import (
    DecoratorRegistryError,
    eval_gated,
    get_holly_meta,
    has_holly_decorator,
    kernel_boundary,
    lane_dispatch,
    mcp_tool,
    tenant_scoped,
)
from holly.arch.registry import ArchitectureRegistry

if TYPE_CHECKING:
    import pathlib

# ── Helpers ───────────────────────────────────────────

def _sample_fn() -> str:
    """A trivial function for decoration."""
    return "ok"


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """Ensure clean registry state per test."""
    from holly.kernel.predicate_registry import PredicateRegistry

    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None
    PredicateRegistry.clear()
    # Register the test predicate used by cross-decorator tests.
    PredicateRegistry.register("test_pred", lambda o: True)
    yield  # type: ignore[misc]
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None
    PredicateRegistry.clear()


@pytest.fixture()
def architecture_yaml(tmp_path: pathlib.Path) -> str:
    """Write a minimal architecture.yaml and configure the registry."""
    data = {
        "metadata": {
            "sad_version": "0.1.0.5",
            "sad_file": "test.mermaid",
            "chart_type": "flowchart",
            "chart_direction": "TB",
            "generated_by": "test",
            "schema_version": "1.0.0",
        },
        "layers": {},
        "components": {
            "K1": {
                "id": "K1",
                "name": "Schema Validation",
                "layer": "L1",
                "subgraph_id": "KERNEL",
                "source": {"file": "test.mermaid", "line": 1, "raw": "K1"},
            },
        },
        "connections": [],
        "kernel_invariants": [],
    }
    p = tmp_path / "architecture.yaml"
    p.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    ArchitectureRegistry.configure(p)
    ArchitectureRegistry.get()  # Force load.
    return str(p)


# ── Test: @kernel_boundary ────────────────────────────


class TestKernelBoundaryBare:
    """@kernel_boundary without arguments."""

    def test_stamps_kind(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == "kernel_boundary"

    def test_preserves_behavior(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        assert decorated() == "ok"

    def test_preserves_name(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        assert decorated.__name__ == "_sample_fn"

    def test_default_fields(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["gate_id"] == ""
        assert meta["invariant"] == ""
        assert meta["component_id"] is None
        assert meta["layer"] == "L1"


class TestKernelBoundaryParameterized:
    """@kernel_boundary with arguments."""

    def test_stamps_gate_id(self) -> None:
        decorated = kernel_boundary(gate_id="K1", invariant="schema_validation")(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["gate_id"] == "K1"
        assert meta["invariant"] == "schema_validation"

    @given(gate=st.text(min_size=1, max_size=10), inv=st.text(min_size=1, max_size=30))
    @settings(max_examples=20)
    def test_arbitrary_gate_and_invariant(self, gate: str, inv: str) -> None:
        """Property: any string pair is preserved in metadata."""
        decorated = kernel_boundary(gate_id=gate, invariant=inv)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["gate_id"] == gate
        assert meta["invariant"] == inv
        assert meta["kind"] == "kernel_boundary"


# ── Test: @tenant_scoped ──────────────────────────────


class TestTenantScoped:

    def test_bare_stamps_kind(self) -> None:
        decorated = tenant_scoped(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == "tenant_scoped"
        assert meta["isolation"] == "row_level_security"

    def test_custom_isolation(self) -> None:
        decorated = tenant_scoped(isolation="schema_per_tenant")(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["isolation"] == "schema_per_tenant"

    def test_preserves_behavior(self) -> None:
        decorated = tenant_scoped(_sample_fn)
        assert decorated() == "ok"

    @given(iso=st.sampled_from(["row_level_security", "schema_per_tenant", "database_per_tenant"]))
    def test_all_isolation_strategies(self, iso: str) -> None:
        """Property: all valid strategies are preserved."""
        decorated = tenant_scoped(isolation=iso)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["isolation"] == iso


# ── Test: @lane_dispatch ──────────────────────────────


class TestLaneDispatch:

    def test_bare_stamps_kind(self) -> None:
        decorated = lane_dispatch(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == "lane_dispatch"
        assert meta["semantics"] == "concurrent"

    def test_custom_semantics(self) -> None:
        decorated = lane_dispatch(semantics="fan_out_fan_in")(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["semantics"] == "fan_out_fan_in"

    @given(sem=st.sampled_from(["concurrent", "sequential", "fan_out_fan_in"]))
    def test_all_semantics(self, sem: str) -> None:
        """Property: all valid lane semantics are preserved."""
        decorated = lane_dispatch(semantics=sem)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["semantics"] == sem


# ── Test: @mcp_tool ───────────────────────────────────


class TestMcpTool:

    def test_bare_stamps_kind(self) -> None:
        decorated = mcp_tool(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == "mcp_tool"
        assert meta["tool_name"] == "_sample_fn"  # derived from fn name
        assert meta["permission_mask"] == "*"

    def test_explicit_tool_name(self) -> None:
        decorated = mcp_tool(tool_name="search", permission_mask="read")(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["tool_name"] == "search"
        assert meta["permission_mask"] == "read"

    @given(name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    @settings(max_examples=20)
    def test_arbitrary_tool_names(self, name: str) -> None:
        """Property: any tool name string is preserved."""
        decorated = mcp_tool(tool_name=name)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["tool_name"] == name


# ── Test: @eval_gated ─────────────────────────────────


class TestEvalGated:

    def test_bare_stamps_kind(self) -> None:
        decorated = eval_gated(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == "eval_gated"
        assert meta["gate_id"] == "K8"
        assert meta["predicate"] == ""

    def test_custom_predicate(self) -> None:
        decorated = eval_gated(predicate="L0_safety_check", gate_id="K8")(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["predicate"] == "L0_safety_check"

    @given(pred=st.text(min_size=1, max_size=40))
    @settings(max_examples=20)
    def test_arbitrary_predicates(self, pred: str) -> None:
        """Property: any predicate string is preserved."""
        decorated = eval_gated(predicate=pred)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["predicate"] == pred


# ── Test: helper functions ────────────────────────────


class TestHelpers:

    def test_get_holly_meta_undecorated(self) -> None:
        assert get_holly_meta(_sample_fn) is None

    def test_has_holly_decorator_undecorated(self) -> None:
        assert has_holly_decorator(_sample_fn) is False

    def test_has_holly_decorator_any(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        assert has_holly_decorator(decorated) is True

    def test_has_holly_decorator_specific_kind(self) -> None:
        decorated = kernel_boundary(_sample_fn)
        assert has_holly_decorator(decorated, kind="kernel_boundary") is True
        assert has_holly_decorator(decorated, kind="tenant_scoped") is False


# ── Test: registry validation ─────────────────────────


class TestRegistryValidation:
    """Tests for component_id validation against the registry."""

    def test_invalid_component_when_registry_loaded(
        self, architecture_yaml: str, tmp_path: object
    ) -> None:
        """Validation rejects unknown component_id when registry is loaded."""
        with pytest.raises(DecoratorRegistryError) as exc_info:
            kernel_boundary(
                gate_id="K99",
                component_id="NONEXISTENT",
                validate=True,
            )(_sample_fn)
        assert exc_info.value.component_id == "NONEXISTENT"
        assert exc_info.value.decorator_kind == "kernel_boundary"

    def test_valid_component_when_registry_loaded(
        self, architecture_yaml: str, tmp_path: object
    ) -> None:
        """Validation passes for a known component_id."""
        # Should not raise — "K1" exists in the fixture YAML.
        decorated = kernel_boundary(
            gate_id="K1",
            component_id="K1",
            validate=True,
        )(_sample_fn)
        assert get_holly_meta(decorated) is not None

    def test_skips_validation_when_registry_not_loaded(self) -> None:
        """If registry isn't loaded, decoration succeeds without validation."""
        ArchitectureRegistry.reset()
        try:
            decorated = kernel_boundary(
                gate_id="K1",
                component_id="NONEXISTENT",
                validate=True,
            )(_sample_fn)
            assert get_holly_meta(decorated) is not None
        finally:
            ArchitectureRegistry.reset()

    def test_skips_validation_when_validate_false(
        self, architecture_yaml: str
    ) -> None:
        """validate=False skips component lookup entirely."""
        decorated = kernel_boundary(
            gate_id="K1",
            component_id="NONEXISTENT",
            validate=False,
        )(_sample_fn)
        assert get_holly_meta(decorated) is not None


# ── Test: cross-decorator properties ──────────────────


class TestCrossDecoratorProperties:
    """Property-based tests across all five decorators."""

    ALL_DECORATORS: ClassVar[list[tuple[str, dict[str, str]]]] = [
        ("kernel_boundary", {"gate_id": "K1"}),
        ("tenant_scoped", {"isolation": "row_level_security"}),
        ("lane_dispatch", {"semantics": "concurrent"}),
        ("mcp_tool", {"tool_name": "test"}),
        ("eval_gated", {"predicate": "test_pred"}),
    ]

    @pytest.mark.parametrize(
        "kind,kwargs",
        ALL_DECORATORS,
        ids=[d[0] for d in ALL_DECORATORS],
    )
    def test_all_stamp_kind_correctly(self, kind: str, kwargs: dict[str, str]) -> None:
        """Every decorator stamps its own kind."""
        import holly.arch.decorators as mod

        dec_fn = getattr(mod, kind)
        decorated = dec_fn(**kwargs)(_sample_fn)
        meta = get_holly_meta(decorated)
        assert meta is not None
        assert meta["kind"] == kind

    @pytest.mark.parametrize(
        "kind,kwargs",
        ALL_DECORATORS,
        ids=[d[0] for d in ALL_DECORATORS],
    )
    def test_all_preserve_callable(self, kind: str, kwargs: dict[str, str]) -> None:
        """Every decorator preserves the original callable's return value."""
        import holly.arch.decorators as mod

        dec_fn = getattr(mod, kind)
        decorated = dec_fn(**kwargs)(_sample_fn)
        assert decorated() == "ok"
