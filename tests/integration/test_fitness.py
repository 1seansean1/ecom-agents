"""Integration tests for architecture fitness functions.

Task 9.2 — Verify fitness functions against the live codebase and
synthetic fixtures.

Tests cover:
- Layer violation detection (positive + negative)
- Coupling metric computation (afferent, efferent, thresholds)
- Dependency depth measurement (DFS with cycle detection)
- Combined runner (run_all)
- Import graph construction accuracy
- Edge cases: empty repos, single-module repos, cycles
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from holly.arch.fitness import (
    ALLOWED_CROSS_LAYER,
    LAYER_RANK,
    MODULE_LAYER_MAP,
    CouplingEntry,
    FitnessResult,
    LayerViolation,
    _extract_imports,
    _module_prefix,
    _resolve_layer,
    _resolve_to_graph,
    build_import_graph,
    build_import_graph_with_lines,
    check_coupling,
    check_dependency_depth,
    check_layer_violations,
    run_all,
)
from holly.arch.schema import LayerID

# ── Repo root for live-codebase tests ────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════
# Helper: create synthetic source trees in tmp_path
# ═══════════════════════════════════════════════════════════


def _write_module(root: Path, dotted: str, source: str) -> None:
    """Write a Python source file at the location implied by *dotted*."""
    parts = dotted.split(".")
    folder = root.joinpath(*parts[:-1])
    folder.mkdir(parents=True, exist_ok=True)
    # Ensure __init__.py files exist along the path.
    for i in range(1, len(parts)):
        init = root.joinpath(*parts[:i]) / "__init__.py"
        if not init.exists():
            init.write_text("")
    (folder / f"{parts[-1]}.py").write_text(textwrap.dedent(source))


# ═══════════════════════════════════════════════════════════
# Unit-level helpers
# ═══════════════════════════════════════════════════════════


class TestResolveLayer:
    """Test _resolve_layer mapping."""

    def test_kernel_module(self) -> None:
        assert _resolve_layer("holly.kernel.k1") == LayerID.L1_KERNEL

    def test_core_module(self) -> None:
        assert _resolve_layer("holly.core.types") == LayerID.L2_CORE

    def test_engine_module(self) -> None:
        assert _resolve_layer("holly.engine.pipeline") == LayerID.L3_ENGINE

    def test_observability_module(self) -> None:
        assert _resolve_layer("holly.observability.metrics") == LayerID.L4_OBSERVABILITY

    def test_storage_module(self) -> None:
        assert _resolve_layer("holly.storage.db") == LayerID.DATA

    def test_infra_module(self) -> None:
        assert _resolve_layer("holly.infra.config") == LayerID.INFRA

    def test_arch_module(self) -> None:
        assert _resolve_layer("holly.arch.schema") == LayerID.INFRA

    def test_unknown_module(self) -> None:
        assert _resolve_layer("requests.api") is None

    def test_holly_no_sub(self) -> None:
        # "holly" alone doesn't match any prefix.
        assert _resolve_layer("holly") is None


class TestModulePrefix:
    """Test _module_prefix extraction."""

    def test_three_parts(self) -> None:
        assert _module_prefix("holly.kernel.k1") == "holly.kernel"

    def test_two_parts(self) -> None:
        assert _module_prefix("holly.kernel") == "holly.kernel"

    def test_one_part(self) -> None:
        assert _module_prefix("holly") == "holly"

    def test_deep_path(self) -> None:
        assert _module_prefix("holly.core.types.base") == "holly.core"


class TestExtractImports:
    """Test AST-based import extraction."""

    def test_import_statement(self) -> None:
        src = "import holly.kernel.k1\nimport os"
        result = _extract_imports(src)
        names = [name for name, _line in result]
        assert "holly.kernel.k1" in names
        assert "os" in names

    def test_from_import(self) -> None:
        src = "from holly.core.types import Msg"
        result = _extract_imports(src)
        assert result == [("holly.core.types", 1)]

    def test_syntax_error(self) -> None:
        src = "def broken(:"
        assert _extract_imports(src) == []

    def test_empty_source(self) -> None:
        assert _extract_imports("") == []

    def test_relative_import_skipped(self) -> None:
        # Relative imports have node.module=None for `from . import x`.
        src = "from . import foo"
        result = _extract_imports(src)
        assert result == []


class TestResolveToGraph:
    """Test _resolve_to_graph parent-walking."""

    def test_exact_match(self) -> None:
        graph = {"holly.kernel": [], "holly.core": []}
        assert _resolve_to_graph("holly.kernel", graph) == "holly.kernel"

    def test_child_resolves_to_parent(self) -> None:
        graph = {"holly.kernel": [], "holly.core": []}
        assert _resolve_to_graph("holly.kernel.k1", graph) == "holly.kernel"

    def test_no_match(self) -> None:
        graph = {"holly.kernel": []}
        assert _resolve_to_graph("requests.api", graph) is None


class TestCouplingEntry:
    """Test CouplingEntry instability metric."""

    def test_zero_coupling(self) -> None:
        e = CouplingEntry(module="m", afferent=0, efferent=0)
        assert e.instability == 0.0

    def test_pure_efferent(self) -> None:
        e = CouplingEntry(module="m", afferent=0, efferent=5)
        assert e.instability == 1.0

    def test_pure_afferent(self) -> None:
        e = CouplingEntry(module="m", afferent=5, efferent=0)
        assert e.instability == 0.0

    def test_balanced(self) -> None:
        e = CouplingEntry(module="m", afferent=3, efferent=3)
        assert e.instability == pytest.approx(0.5)


class TestFitnessResult:
    """Test FitnessResult status property."""

    def test_pass(self) -> None:
        r = FitnessResult(name="t", passed=True, measurement=0.0)
        assert r.status == "PASS"

    def test_fail(self) -> None:
        r = FitnessResult(name="t", passed=False, measurement=1.0)
        assert r.status == "FAIL"


# ═══════════════════════════════════════════════════════════
# Configuration consistency
# ═══════════════════════════════════════════════════════════


class TestConfiguration:
    """Verify LAYER_RANK, MODULE_LAYER_MAP, ALLOWED_CROSS_LAYER consistency."""

    def test_all_layer_ids_have_ranks(self) -> None:
        for lid in LayerID:
            assert lid in LAYER_RANK, f"LayerID.{lid} missing from LAYER_RANK"

    def test_ranked_layers_are_ordered(self) -> None:
        ordered = [
            LayerID.L1_KERNEL,
            LayerID.L2_CORE,
            LayerID.L3_ENGINE,
            LayerID.L4_OBSERVABILITY,
            LayerID.L5_CONSOLE,
        ]
        for i in range(len(ordered) - 1):
            assert LAYER_RANK[ordered[i]] < LAYER_RANK[ordered[i + 1]]

    def test_utility_layers_rank_zero(self) -> None:
        for lid in (LayerID.DATA, LayerID.INFRA, LayerID.SANDBOX, LayerID.EXTERNAL, LayerID.L0_VPC):
            assert LAYER_RANK[lid] == 0

    def test_module_layer_map_values_in_layer_rank(self) -> None:
        for _prefix, lid in MODULE_LAYER_MAP.items():
            assert lid in LAYER_RANK

    def test_allowed_cross_layer_pairs_are_holly_prefixed(self) -> None:
        for src, dst in ALLOWED_CROSS_LAYER:
            assert src.startswith("holly.")
            assert dst.startswith("holly.")


# ═══════════════════════════════════════════════════════════
# Import graph construction (synthetic)
# ═══════════════════════════════════════════════════════════


class TestBuildImportGraph:
    """Test import graph building with synthetic source trees."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        graph = build_import_graph(tmp_path, package="holly")
        assert graph == {}

    def test_single_module_no_imports(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        graph = build_import_graph(tmp_path, package="holly")
        assert "holly.kernel.k1" in graph
        assert graph["holly.kernel.k1"] == []

    def test_internal_import_captured(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "from holly.core.types import Msg\n")
        _write_module(tmp_path, "holly.core.types", "Msg = str\n")
        graph = build_import_graph(tmp_path, package="holly")
        assert "holly.core.types" in graph["holly.kernel.k1"]

    def test_external_import_excluded(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "import os\nimport requests\n")
        graph = build_import_graph(tmp_path, package="holly")
        assert graph["holly.kernel.k1"] == []

    def test_with_lines_retains_lineno(self, tmp_path: Path) -> None:
        src = "x = 1\nfrom holly.core.types import Msg\n"
        _write_module(tmp_path, "holly.kernel.k1", src)
        _write_module(tmp_path, "holly.core.types", "Msg = str\n")
        graph = build_import_graph_with_lines(tmp_path, package="holly")
        entries = graph["holly.kernel.k1"]
        assert len(entries) == 1
        assert entries[0] == ("holly.core.types", 2)

    def test_init_module_resolved_to_package(self, tmp_path: Path) -> None:
        pkg = tmp_path / "holly" / "kernel"
        pkg.mkdir(parents=True)
        (tmp_path / "holly" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("from holly.core import something\n")
        _write_module(tmp_path, "holly.core", "something = 1\n")
        graph = build_import_graph(tmp_path, package="holly")
        # __init__.py → package name (holly.kernel), not holly.kernel.__init__
        assert "holly.kernel" in graph


# ═══════════════════════════════════════════════════════════
# Fitness function 1: Layer violations (synthetic)
# ═══════════════════════════════════════════════════════════


class TestCheckLayerViolations:
    """Test layer violation detection with synthetic fixtures."""

    def test_no_violations_when_higher_imports_lower(self, tmp_path: Path) -> None:
        """L3 importing L2 is allowed."""
        _write_module(tmp_path, "holly.engine.pipe", "from holly.core.types import X\n")
        _write_module(tmp_path, "holly.core.types", "X = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is True
        assert result.measurement == 0.0

    def test_violation_lower_imports_higher(self, tmp_path: Path) -> None:
        """L1 importing L3 is a violation."""
        _write_module(tmp_path, "holly.kernel.k1", "from holly.engine.pipe import P\n")
        _write_module(tmp_path, "holly.engine.pipe", "P = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is False
        assert result.measurement >= 1.0
        assert len(result.details) >= 1
        v = result.details[0]
        assert isinstance(v, LayerViolation)
        assert v.source_layer == LayerID.L1_KERNEL
        assert v.imported_layer == LayerID.L3_ENGINE

    def test_same_layer_import_ok(self, tmp_path: Path) -> None:
        """Modules in the same layer may import each other."""
        _write_module(tmp_path, "holly.core.a", "from holly.core.b import X\n")
        _write_module(tmp_path, "holly.core.b", "X = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is True

    def test_utility_layer_import_ok(self, tmp_path: Path) -> None:
        """Any layer may import utility layers (rank 0)."""
        _write_module(tmp_path, "holly.kernel.k1", "from holly.storage.db import D\n")
        _write_module(tmp_path, "holly.storage.db", "D = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is True

    def test_allowed_exception_not_flagged(self, tmp_path: Path) -> None:
        """Allowed cross-layer pairs should not produce violations."""
        _write_module(tmp_path, "holly.kernel.k1", "from holly.arch.schema import S\n")
        _write_module(tmp_path, "holly.arch.schema", "S = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is True

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = check_layer_violations(tmp_path, package="holly")
        assert result.passed is True
        assert result.measurement == 0.0

    def test_result_metadata(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        result = check_layer_violations(tmp_path, package="holly")
        assert result.name == "layer_violations"
        assert result.unit == "violations"
        assert result.threshold == 0.0


# ═══════════════════════════════════════════════════════════
# Fitness function 2: Coupling metrics (synthetic)
# ═══════════════════════════════════════════════════════════


class TestCheckCoupling:
    """Test coupling metric computation with synthetic fixtures."""

    def test_no_coupling(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        _write_module(tmp_path, "holly.core.types", "y = 1\n")
        result = check_coupling(tmp_path, package="holly")
        assert result.passed is True
        for entry in result.details:
            assert isinstance(entry, CouplingEntry)
            assert entry.efferent == 0
            assert entry.afferent == 0

    def test_efferent_counted(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            "from holly.core.types import X\nfrom holly.storage.db import D\n",
        )
        _write_module(tmp_path, "holly.core.types", "X = 1\n")
        _write_module(tmp_path, "holly.storage.db", "D = 1\n")
        result = check_coupling(tmp_path, package="holly")
        k1 = next(e for e in result.details if e.module == "holly.kernel.k1")
        assert k1.efferent == 2

    def test_afferent_counted(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "from holly.core.types import X\n")
        _write_module(tmp_path, "holly.engine.pipe", "from holly.core.types import X\n")
        _write_module(tmp_path, "holly.core.types", "X = 1\n")
        result = check_coupling(tmp_path, package="holly")
        types_entry = next(e for e in result.details if e.module == "holly.core.types")
        assert types_entry.afferent == 2

    def test_threshold_violation(self, tmp_path: Path) -> None:
        # Create a module with efferent > 2 (threshold).
        imports = "\n".join(f"from holly.core.m{i} import X{i}" for i in range(5))
        _write_module(tmp_path, "holly.kernel.k1", imports + "\n")
        for i in range(5):
            _write_module(tmp_path, f"holly.core.m{i}", f"X{i} = 1\n")
        result = check_coupling(
            tmp_path,
            package="holly",
            max_efferent=2,
            max_afferent=20,
        )
        assert result.passed is False
        assert result.measurement >= 1.0

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = check_coupling(tmp_path, package="holly")
        assert result.passed is True
        assert result.measurement == 0.0

    def test_result_metadata(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        result = check_coupling(tmp_path, package="holly")
        assert result.name == "coupling_metrics"
        assert result.unit == "modules_exceeding_threshold"


# ═══════════════════════════════════════════════════════════
# Fitness function 3: Dependency depth (synthetic)
# ═══════════════════════════════════════════════════════════


class TestCheckDependencyDepth:
    """Test dependency depth measurement with synthetic fixtures."""

    def test_single_module_depth_zero(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        result = check_dependency_depth(tmp_path, package="holly")
        assert result.passed is True
        assert result.measurement == 0.0

    def test_chain_of_two(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "from holly.core.types import X\n")
        _write_module(tmp_path, "holly.core.types", "X = 1\n")
        result = check_dependency_depth(tmp_path, package="holly")
        assert result.measurement == 1.0
        assert result.passed is True  # default max_depth=8

    def test_chain_exceeds_threshold(self, tmp_path: Path) -> None:
        # Build chain: a → b → c → d (depth 3) with max_depth=2.
        _write_module(tmp_path, "holly.kernel.a", "from holly.kernel.b import X\n")
        _write_module(tmp_path, "holly.kernel.b", "from holly.kernel.c import X\n")
        _write_module(tmp_path, "holly.kernel.c", "from holly.kernel.d import X\n")
        _write_module(tmp_path, "holly.kernel.d", "X = 1\n")
        result = check_dependency_depth(tmp_path, package="holly", max_depth=2)
        assert result.passed is False
        assert result.measurement == 3.0

    def test_cycle_does_not_infinite_loop(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.a", "from holly.kernel.b import X\n")
        _write_module(tmp_path, "holly.kernel.b", "from holly.kernel.a import Y\n")
        result = check_dependency_depth(tmp_path, package="holly")
        # Should terminate and report depth=1 (a→b, cycle stops).
        assert result.measurement >= 1.0
        assert result.passed is True

    def test_diamond_dependency(self, tmp_path: Path) -> None:
        # a → b, a → c, b → d, c → d.
        _write_module(
            tmp_path,
            "holly.kernel.a",
            "from holly.kernel.b import X\nfrom holly.kernel.c import Y\n",
        )
        _write_module(tmp_path, "holly.kernel.b", "from holly.kernel.d import X\n")
        _write_module(tmp_path, "holly.kernel.c", "from holly.kernel.d import Y\n")
        _write_module(tmp_path, "holly.kernel.d", "X = Y = 1\n")
        result = check_dependency_depth(tmp_path, package="holly")
        assert result.measurement == 2.0  # a → b → d

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = check_dependency_depth(tmp_path, package="holly")
        assert result.passed is True
        assert result.measurement == 0.0

    def test_result_metadata(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        result = check_dependency_depth(tmp_path, package="holly")
        assert result.name == "dependency_depth"
        assert result.unit == "chain_length"
        assert result.threshold == 8.0


# ═══════════════════════════════════════════════════════════
# Combined runner
# ═══════════════════════════════════════════════════════════


class TestRunAll:
    """Test the combined runner."""

    def test_returns_three_results(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        results = run_all(tmp_path, package="holly")
        assert len(results) == 3
        names = {r.name for r in results}
        assert names == {"layer_violations", "coupling_metrics", "dependency_depth"}

    def test_all_pass_on_clean_tree(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        results = run_all(tmp_path, package="holly")
        for r in results:
            assert r.passed is True

    def test_propagates_thresholds(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "x = 1\n")
        results = run_all(
            tmp_path,
            package="holly",
            max_efferent=5,
            max_afferent=10,
            max_depth=3,
        )
        depth_result = next(r for r in results if r.name == "dependency_depth")
        assert depth_result.threshold == 3.0


# ═══════════════════════════════════════════════════════════
# Live codebase tests
# ═══════════════════════════════════════════════════════════


class TestLiveCodebase:
    """Run fitness functions against the actual Holly codebase."""

    def test_no_layer_violations(self) -> None:
        """The real codebase must have zero layer violations."""
        result = check_layer_violations(REPO_ROOT, package="holly")
        if not result.passed:
            violations = "\n".join(
                f"  {v.source_module} ({v.source_layer}) → "
                f"{v.imported_module} ({v.imported_layer}) "
                f"at {v.source_file}:{v.line}"
                for v in result.details
            )
            pytest.fail(f"Layer violations found:\n{violations}")

    def test_coupling_within_thresholds(self) -> None:
        """No module exceeds default coupling thresholds."""
        result = check_coupling(REPO_ROOT, package="holly")
        if not result.passed:
            offenders = [
                e
                for e in result.details
                if isinstance(e, CouplingEntry)
                and (e.efferent > 15 or e.afferent > 20)
            ]
            details = "\n".join(
                f"  {e.module}: Ca={e.afferent} Ce={e.efferent}"
                for e in offenders
            )
            pytest.fail(f"Coupling threshold exceeded:\n{details}")

    def test_dependency_depth_within_threshold(self) -> None:
        """Longest import chain ≤ 8."""
        result = check_dependency_depth(REPO_ROOT, package="holly")
        if not result.passed:
            chain = " → ".join(result.details)
            pytest.fail(
                f"Dependency depth {result.measurement} exceeds 8: {chain}"
            )

    def test_run_all_passes(self) -> None:
        """All three fitness functions pass on the real codebase."""
        results = run_all(REPO_ROOT, package="holly")
        for r in results:
            assert r.passed, f"{r.name} FAILED: {r.measurement} {r.unit}"

    def test_import_graph_not_empty(self) -> None:
        """The live codebase must produce a non-trivial import graph."""
        graph = build_import_graph(REPO_ROOT, package="holly")
        assert len(graph) > 10, f"Import graph too small: {len(graph)} modules"

    def test_coupling_entries_populated(self) -> None:
        """Coupling check should produce entries for all graphed modules."""
        result = check_coupling(REPO_ROOT, package="holly")
        assert len(result.details) > 10
