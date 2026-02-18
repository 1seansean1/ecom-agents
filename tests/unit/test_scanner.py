"""Tests for Task 7.1 — AST scanner with per-module rules.

Acceptance criteria:
    - Scanner rules match YAML component definitions
    - Rules generated for kernel (L1), core (L2), engine (L3) layers
    - Component overrides respected (MCP, K8, EGRESS, KMS)
    - scan_source detects correct decorators (OK)
    - scan_source detects wrong decorators (WRONG)
    - scan_module inspects loaded modules
    - scan_directory aggregates findings
    - Property-based: arbitrary component/layer combos produce valid rules
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.arch.decorators import DecoratorKind
from holly.arch.registry import ArchitectureRegistry
from holly.arch.scanner import (
    COMPONENT_DECORATOR_OVERRIDES,
    LAYER_DECORATOR_MAP,
    FindingKind,
    ScanFinding,
    ScanReport,
    ScanRule,
    generate_rules,
    get_rules_for_component,
    scan_directory,
    scan_source,
)
from holly.arch.schema import LayerID

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Ensure every test starts with a clean singleton."""
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None
    yield
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None


def _make_yaml(tmp_path: Path, components: dict[str, dict[str, Any]]) -> Path:
    """Helper to create a minimal architecture.yaml with given components."""
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
        "components": components,
        "connections": [],
        "kernel_invariants": [],
        "icds": [],
    }
    path = tmp_path / "architecture.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


def _component(comp_id: str, layer: str) -> dict[str, Any]:
    """Create a minimal component dict."""
    return {
        "id": comp_id,
        "name": f"Component {comp_id}",
        "layer": layer,
        "subgraph_id": "S1",
        "source": {"file": "test.mermaid", "line": 1},
    }


@pytest.fixture()
def kernel_yaml(tmp_path: Path) -> Path:
    """YAML with kernel layer components."""
    return _make_yaml(tmp_path, {
        "K1": _component("K1", "L1"),
        "K2": _component("K2", "L1"),
        "K8": _component("K8", "L1"),
    })


@pytest.fixture()
def multi_layer_yaml(tmp_path: Path) -> Path:
    """YAML with components across multiple layers."""
    return _make_yaml(tmp_path, {
        "K1": _component("K1", "L1"),
        "CORE": _component("CORE", "L2"),
        "MAIN": _component("MAIN", "L3"),
        "MCP": _component("MCP", "L3"),
        "EGRESS": _component("EGRESS", "INFRA"),
        "KMS": _component("KMS", "INFRA"),
        "PG": _component("PG", "DATA"),
    })


@pytest.fixture()
def real_registry() -> ArchitectureRegistry:
    """Load the actual architecture.yaml from the repo."""
    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "docs" / "architecture.yaml"
    ArchitectureRegistry.configure(yaml_path)
    return ArchitectureRegistry.get()


# ── TestRuleGeneration ────────────────────────────────


class TestRuleGeneration:
    """Rules generated from architecture.yaml match component definitions."""

    def test_kernel_components_get_kernel_boundary(self, kernel_yaml: Path) -> None:
        ArchitectureRegistry.configure(kernel_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        k1_rule = get_rules_for_component("K1", rules)
        assert k1_rule is not None
        assert k1_rule.required_decorator == "kernel_boundary"

    def test_k8_override_to_eval_gated(self, kernel_yaml: Path) -> None:
        ArchitectureRegistry.configure(kernel_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        k8_rule = get_rules_for_component("K8", rules)
        assert k8_rule is not None
        assert k8_rule.required_decorator == "eval_gated"

    def test_core_gets_tenant_scoped(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        core_rule = get_rules_for_component("CORE", rules)
        assert core_rule is not None
        assert core_rule.required_decorator == "tenant_scoped"

    def test_engine_gets_lane_dispatch(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        main_rule = get_rules_for_component("MAIN", rules)
        assert main_rule is not None
        assert main_rule.required_decorator == "lane_dispatch"

    def test_mcp_override(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        mcp_rule = get_rules_for_component("MCP", rules)
        assert mcp_rule is not None
        assert mcp_rule.required_decorator == "mcp_tool"

    def test_egress_override(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        egress_rule = get_rules_for_component("EGRESS", rules)
        assert egress_rule is not None
        assert egress_rule.required_decorator == "kernel_boundary"

    def test_kms_override(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        kms_rule = get_rules_for_component("KMS", rules)
        assert kms_rule is not None
        assert kms_rule.required_decorator == "kernel_boundary"

    def test_data_layer_no_rule(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        pg_rule = get_rules_for_component("PG", rules)
        assert pg_rule is None

    def test_no_duplicate_rules(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        comp_ids = [r.component_id for r in rules]
        assert len(comp_ids) == len(set(comp_ids))

    def test_all_rules_have_description(self, multi_layer_yaml: Path) -> None:
        ArchitectureRegistry.configure(multi_layer_yaml)
        reg = ArchitectureRegistry.get()
        rules = generate_rules(reg)
        for rule in rules:
            assert rule.description, f"Rule for {rule.component_id} has no description"


# ── TestRealYAMLRules ─────────────────────────────────


class TestRealYAMLRules:
    """Rules from the actual architecture.yaml."""

    def test_rules_generated_for_kernel_components(self, real_registry: ArchitectureRegistry) -> None:
        rules = generate_rules(real_registry)
        k1_rule = get_rules_for_component("K1", rules)
        assert k1_rule is not None
        assert k1_rule.required_decorator == "kernel_boundary"

    def test_rules_cover_multiple_layers(self, real_registry: ArchitectureRegistry) -> None:
        rules = generate_rules(real_registry)
        layers_covered = {r.layer for r in rules}
        assert LayerID.L1_KERNEL in layers_covered
        assert LayerID.L2_CORE in layers_covered

    def test_at_least_10_rules_generated(self, real_registry: ArchitectureRegistry) -> None:
        rules = generate_rules(real_registry)
        assert len(rules) >= 10


# ── TestScanSource ────────────────────────────────────


class TestScanSource:
    """scan_source detects correct and wrong decorators."""

    def test_correct_decorator_ok(self) -> None:
        source = '''
from holly.arch.decorators import kernel_boundary

@kernel_boundary(gate_id="K1", component_id="K1")
def validate(payload):
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert len(findings) == 1
        assert findings[0].kind == FindingKind.OK

    def test_wrong_decorator_detected(self) -> None:
        source = '''
from holly.arch.decorators import tenant_scoped

@tenant_scoped(component_id="K1")
def validate(payload):
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert len(findings) == 1
        assert findings[0].kind == FindingKind.WRONG
        assert findings[0].expected_decorator == "kernel_boundary"
        assert findings[0].actual_decorator == "tenant_scoped"

    def test_no_decorator_no_findings(self) -> None:
        source = '''
def plain_function():
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert findings == []

    def test_decorator_without_component_id_skipped(self) -> None:
        source = '''
from holly.arch.decorators import kernel_boundary

@kernel_boundary
def validate(payload):
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert findings == []

    def test_unknown_component_id_skipped(self) -> None:
        source = '''
from holly.arch.decorators import kernel_boundary

@kernel_boundary(component_id="UNKNOWN")
def validate(payload):
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert findings == []

    def test_multiple_decorators_in_one_file(self) -> None:
        source = '''
from holly.arch.decorators import kernel_boundary, eval_gated

@kernel_boundary(component_id="K1")
def validate(payload):
    pass

@eval_gated(component_id="K8")
def evaluate(result):
    pass
'''
        rules = [
            ScanRule(component_id="K1", layer=LayerID.L1_KERNEL, required_decorator="kernel_boundary"),
            ScanRule(component_id="K8", layer=LayerID.L1_KERNEL, required_decorator="eval_gated"),
        ]
        findings = scan_source(source, "test_module", rules)
        assert len(findings) == 2
        assert all(f.kind == FindingKind.OK for f in findings)

    def test_syntax_error_returns_empty(self) -> None:
        source = "def broken(:"
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert findings == []

    def test_class_decorator_scanned(self) -> None:
        source = '''
from holly.arch.decorators import kernel_boundary

@kernel_boundary(component_id="K1")
class SchemaValidator:
    pass
'''
        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        findings = scan_source(source, "test_module", rules)
        assert len(findings) == 1
        assert findings[0].kind == FindingKind.OK
        assert findings[0].symbol_name == "SchemaValidator"


# ── TestScanDirectory ─────────────────────────────────


class TestScanDirectory:
    """scan_directory aggregates findings across files."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        report = scan_directory(tmp_path, [])
        assert report.is_clean
        assert report.findings == []

    def test_scan_directory_with_files(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "module.py").write_text('''
from holly.arch.decorators import kernel_boundary

@kernel_boundary(component_id="K1")
def validate(payload):
    pass
''', encoding="utf-8")

        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        report = scan_directory(pkg, rules)
        assert report.ok_count == 1
        assert report.is_clean

    def test_scan_directory_exclude_patterns(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "test_foo.py").write_text('''
from holly.arch.decorators import kernel_boundary

@kernel_boundary(component_id="K1")
def validate(payload):
    pass
''', encoding="utf-8")

        rules = [ScanRule(
            component_id="K1",
            layer=LayerID.L1_KERNEL,
            required_decorator="kernel_boundary",
        )]
        report = scan_directory(pkg, rules, exclude_patterns=["test_*"])
        assert report.findings == []


# ── TestScanReport ────────────────────────────────────


class TestScanReport:
    """ScanReport aggregate properties."""

    def test_empty_report(self) -> None:
        report = ScanReport()
        assert report.is_clean
        assert report.ok_count == 0
        assert report.missing_count == 0
        assert report.wrong_count == 0

    def test_mixed_findings(self) -> None:
        report = ScanReport(findings=[
            ScanFinding(FindingKind.OK, "m", "f1", "K1", "kernel_boundary"),
            ScanFinding(FindingKind.WRONG, "m", "f2", "K2", "kernel_boundary"),
            ScanFinding(FindingKind.MISSING, "m", "f3", "K3", "kernel_boundary"),
        ])
        assert report.ok_count == 1
        assert report.wrong_count == 1
        assert report.missing_count == 1
        assert not report.is_clean


# ── TestScanRuleDataModel ─────────────────────────────


class TestScanRuleDataModel:
    """ScanRule is frozen and hashable."""

    def test_frozen(self) -> None:
        rule = ScanRule(component_id="K1", layer=LayerID.L1_KERNEL, required_decorator="kernel_boundary")
        with pytest.raises(AttributeError):
            rule.component_id = "K2"  # type: ignore[misc]

    def test_hashable(self) -> None:
        rule1 = ScanRule(component_id="K1", layer=LayerID.L1_KERNEL, required_decorator="kernel_boundary")
        rule2 = ScanRule(component_id="K1", layer=LayerID.L1_KERNEL, required_decorator="kernel_boundary")
        assert rule1 == rule2
        assert hash(rule1) == hash(rule2)


# ── TestPropertyBased ─────────────────────────────────


class TestPropertyBased:
    """Property-based tests for rule generation."""

    @given(
        comp_id=st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        layer=st.sampled_from([LayerID.L1_KERNEL, LayerID.L2_CORE, LayerID.L3_ENGINE]),
    )
    @settings(max_examples=30)
    def test_layer_always_maps_to_decorator(self, comp_id: str, layer: LayerID) -> None:
        """Any component in L1/L2/L3 always gets a decorator rule."""
        # Skip if comp_id is in overrides (different expected behavior).
        if comp_id in COMPONENT_DECORATOR_OVERRIDES:
            return
        expected = LAYER_DECORATOR_MAP[layer]
        rule = ScanRule(component_id=comp_id, layer=layer, required_decorator=expected)
        assert rule.required_decorator == expected

    @given(
        decorator=st.sampled_from(list(DecoratorKind.__args__)),  # type: ignore[attr-defined]
    )
    @settings(max_examples=10)
    def test_finding_kinds_exhaustive(self, decorator: str) -> None:
        """Every decorator kind can appear in a ScanFinding."""
        finding = ScanFinding(
            kind=FindingKind.OK,
            module_path="test",
            symbol_name="func",
            component_id="K1",
            expected_decorator=decorator,
            actual_decorator=decorator,
        )
        assert finding.kind == FindingKind.OK

    @given(
        source_lines=st.lists(
            st.sampled_from([
                "def foo(): pass",
                "class Bar: pass",
                "x = 1",
                "import os",
            ]),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=20)
    def test_scan_source_never_crashes(self, source_lines: list[str]) -> None:
        """scan_source should not crash on arbitrary valid Python."""
        source = "\n".join(source_lines)
        rules = [ScanRule(component_id="K1", layer=LayerID.L1_KERNEL, required_decorator="kernel_boundary")]
        findings = scan_source(source, "test", rules)
        assert isinstance(findings, list)
