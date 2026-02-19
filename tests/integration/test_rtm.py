"""Integration tests for RTM generator.

Task 10.2 — Verify the Requirements Traceability Matrix generator
against the live codebase and synthetic fixtures.

Tests cover:
- Decorated symbol discovery (AST walking)
- Test discovery and component mapping
- RTM generation (entry correlation, status assignment)
- CSV serialisation
- Report generation
- Live codebase validation (non-empty, correct structure)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from holly.arch.rtm import (
    RTM,
    CoverageStatus,
    RTMEntry,
    discover_decorated_symbols,
    discover_tests,
    generate_rtm,
    generate_rtm_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════
# Helper: synthetic source trees
# ═══════════════════════════════════════════════════════════


def _write_module(root: Path, dotted: str, source: str) -> None:
    """Write a Python file at the path implied by *dotted*."""
    parts = dotted.split(".")
    folder = root.joinpath(*parts[:-1])
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, len(parts)):
        init = root.joinpath(*parts[:i]) / "__init__.py"
        if not init.exists():
            init.write_text("")
    (folder / f"{parts[-1]}.py").write_text(textwrap.dedent(source))


# ═══════════════════════════════════════════════════════════
# DecoratedSymbol discovery
# ═══════════════════════════════════════════════════════════


class TestDiscoverDecoratedSymbols:
    """Test AST-based discovery of Holly-decorated callables."""

    def test_finds_kernel_boundary(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            from holly.arch.decorators import kernel_boundary

            @kernel_boundary(component_id="K1", invariant="schema")
            def validate(msg):
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert len(symbols) == 1
        assert symbols[0].decorator_kind == "kernel_boundary"
        assert symbols[0].component_id == "K1"
        assert symbols[0].symbol_name == "validate"

    def test_finds_eval_gated(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k8",
            '''\
            from holly.arch.decorators import eval_gated

            @eval_gated(component_id="K8", predicate="safety_check")
            def gate(ctx):
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert len(symbols) == 1
        assert symbols[0].decorator_kind == "eval_gated"
        assert symbols[0].component_id == "K8"

    def test_finds_icd_schema(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            from holly.arch.decorators import kernel_boundary

            @kernel_boundary(component_id="K1", invariant="schema", icd_schema="ICD-001")
            def validate(msg):
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert symbols[0].icd_schema == "ICD-001"

    def test_ignores_non_holly_decorators(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            import functools

            @functools.lru_cache
            def cached():
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert len(symbols) == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert symbols == []

    def test_multiple_symbols(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            from holly.arch.decorators import kernel_boundary

            @kernel_boundary(component_id="K1", invariant="schema")
            def validate(msg):
                pass

            @kernel_boundary(component_id="K1", invariant="bounds")
            def check_bounds(msg):
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert len(symbols) == 2

    def test_class_decorator(self, tmp_path: Path) -> None:
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            from holly.arch.decorators import kernel_boundary

            @kernel_boundary(component_id="K1", invariant="schema")
            class Validator:
                pass
            ''',
        )
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert len(symbols) == 1
        assert symbols[0].symbol_name == "Validator"

    def test_syntax_error_skipped(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "holly.kernel.k1", "def broken(:\n")
        symbols = discover_decorated_symbols(tmp_path, package="holly")
        assert symbols == []


# ═══════════════════════════════════════════════════════════
# Test discovery
# ═══════════════════════════════════════════════════════════


class TestDiscoverTests:
    """Test discovery of test functions from the test tree."""

    def test_finds_test_functions(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_k1.py").write_text(textwrap.dedent("""\
            from holly.kernel.k1 import validate

            def test_validate_ok():
                pass

            def test_validate_fail():
                pass
        """))
        tests = discover_tests(tmp_path, test_dir="tests")
        assert len(tests) == 2
        assert all(t.test_file.startswith("tests") for t in tests)

    def test_finds_class_methods(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_k1.py").write_text(textwrap.dedent("""\
            from holly.kernel.k1 import validate

            class TestValidation:
                def test_ok(self):
                    pass

                def test_fail(self):
                    pass
        """))
        tests = discover_tests(tmp_path, test_dir="tests")
        assert len(tests) == 2
        assert tests[0].test_class == "TestValidation"

    def test_infers_component_from_filename(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_k1.py").write_text(textwrap.dedent("""\
            def test_something():
                pass
        """))
        tests = discover_tests(tmp_path, test_dir="tests")
        assert tests[0].references_component == "K1"

    def test_infers_module_from_imports(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_example.py").write_text(textwrap.dedent("""\
            from holly.kernel.k1 import validate

            def test_something():
                pass
        """))
        tests = discover_tests(tmp_path, test_dir="tests")
        assert tests[0].references_module == "holly.kernel.k1"

    def test_empty_test_dir(self, tmp_path: Path) -> None:
        tests = discover_tests(tmp_path, test_dir="tests")
        assert tests == []

    def test_non_test_functions_ignored(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_k1.py").write_text(textwrap.dedent("""\
            def helper():
                pass

            def test_real():
                pass
        """))
        tests = discover_tests(tmp_path, test_dir="tests")
        assert len(tests) == 1
        assert tests[0].test_function == "test_real"


# ═══════════════════════════════════════════════════════════
# RTMEntry and RTM data models
# ═══════════════════════════════════════════════════════════


class TestRTMEntry:
    """Test RTMEntry data model."""

    def test_test_count(self) -> None:
        entry = RTMEntry(
            component_id="K1",
            component_name="Schema Validation",
            layer="L1_KERNEL",
            decorator_kind="kernel_boundary",
            module_path="holly.kernel.k1",
            symbol_name="validate",
            test_ids=["test_a", "test_b"],
        )
        assert entry.test_count == 2

    def test_default_status(self) -> None:
        entry = RTMEntry(
            component_id="K1",
            component_name="X",
            layer="L1",
            decorator_kind="kernel_boundary",
            module_path="holly.kernel.k1",
            symbol_name="validate",
        )
        assert entry.status == CoverageStatus.UNCOVERED


class TestRTM:
    """Test RTM aggregate data model."""

    def test_coverage_ratio_empty(self) -> None:
        rtm = RTM()
        assert rtm.coverage_ratio == 0.0

    def test_coverage_ratio(self) -> None:
        rtm = RTM(entries=[
            RTMEntry(
                component_id="K1",
                component_name="X",
                layer="L1",
                decorator_kind="kernel_boundary",
                module_path="m",
                symbol_name="f",
                status=CoverageStatus.COVERED,
            ),
            RTMEntry(
                component_id="K2",
                component_name="Y",
                layer="L1",
                decorator_kind="kernel_boundary",
                module_path="m",
                symbol_name="g",
                status=CoverageStatus.UNCOVERED,
            ),
        ])
        assert rtm.coverage_ratio == pytest.approx(0.5)

    def test_to_csv_headers(self) -> None:
        rtm = RTM()
        csv_str = rtm.to_csv()
        assert "component_id" in csv_str
        assert "test_count" in csv_str
        assert "status" in csv_str

    def test_to_csv_with_entries(self) -> None:
        rtm = RTM(entries=[
            RTMEntry(
                component_id="K1",
                component_name="Schema Validation",
                layer="L1_KERNEL",
                decorator_kind="kernel_boundary",
                module_path="holly.kernel.k1",
                symbol_name="validate",
                icd_ids=["ICD-001"],
                test_ids=["test_a"],
                status=CoverageStatus.COVERED,
            ),
        ])
        csv_str = rtm.to_csv()
        lines = csv_str.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert "K1" in lines[1]
        assert "ICD-001" in lines[1]
        assert "covered" in lines[1]

    def test_counts(self) -> None:
        rtm = RTM(entries=[
            RTMEntry(
                component_id="K1", component_name="", layer="", decorator_kind="",
                module_path="", symbol_name="", status=CoverageStatus.COVERED,
            ),
            RTMEntry(
                component_id="K2", component_name="", layer="", decorator_kind="",
                module_path="", symbol_name="", status=CoverageStatus.PARTIAL,
            ),
            RTMEntry(
                component_id="K3", component_name="", layer="", decorator_kind="",
                module_path="", symbol_name="", status=CoverageStatus.UNCOVERED,
            ),
        ])
        assert rtm.covered_count == 1
        assert rtm.partial_count == 1
        assert rtm.uncovered_count == 1


# ═══════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════


class TestGenerateReport:
    """Test human-readable RTM report."""

    def test_report_contains_summary(self) -> None:
        rtm = RTM(
            entries=[
                RTMEntry(
                    component_id="K1", component_name="X", layer="L1",
                    decorator_kind="kernel_boundary", module_path="m",
                    symbol_name="f", status=CoverageStatus.COVERED,
                ),
            ],
            component_count=48,
            decorated_count=1,
            test_count=100,
        )
        report = generate_rtm_report(rtm)
        assert "48" in report
        assert "COVERED" in report

    def test_report_lists_uncovered(self) -> None:
        rtm = RTM(entries=[
            RTMEntry(
                component_id="K1", component_name="X", layer="L1",
                decorator_kind="kernel_boundary", module_path="holly.kernel.k1",
                symbol_name="validate", status=CoverageStatus.UNCOVERED,
            ),
        ])
        report = generate_rtm_report(rtm)
        assert "Uncovered" in report
        assert "validate" in report


# ═══════════════════════════════════════════════════════════
# Live codebase tests
# ═══════════════════════════════════════════════════════════


class TestLiveCodebase:
    """Run RTM generator against the actual Holly codebase."""

    def test_discovers_decorated_symbols(self) -> None:
        """Discovery runs without error on the live codebase.

        Current state: most decorators are defined but not yet applied to
        production code (applied in later slices).  The count may be 0 or
        small — the key invariant is that discovery completes and returns
        a list of DecoratedSymbol instances.
        """
        symbols = discover_decorated_symbols(REPO_ROOT, package="holly")
        assert isinstance(symbols, list)

    def test_discovers_tests(self) -> None:
        """Should find a substantial number of tests."""
        tests = discover_tests(REPO_ROOT, test_dir="tests")
        assert len(tests) >= 100  # We have 1363+ tests

    def test_generate_rtm_runs(self) -> None:
        """RTM generation completes on the live codebase."""
        rtm = generate_rtm(REPO_ROOT, package="holly", test_dir="tests")
        assert rtm.component_count == 48
        assert rtm.test_count >= 100
        # Entries may be 0 if no production decorators applied yet.
        assert isinstance(rtm.entries, list)

    def test_rtm_csv_has_header(self) -> None:
        """CSV export always has a header row."""
        rtm = generate_rtm(REPO_ROOT, package="holly", test_dir="tests")
        csv_str = rtm.to_csv()
        assert "component_id" in csv_str
        assert "status" in csv_str

    def test_rtm_report_generated(self) -> None:
        """Human-readable report should be non-empty."""
        rtm = generate_rtm(REPO_ROOT, package="holly", test_dir="tests")
        report = generate_rtm_report(rtm)
        assert "Requirements Traceability Matrix" in report
        assert "Components in architecture: 48" in report

    def test_all_entries_have_decorator_kind(self) -> None:
        """Every RTM entry must have a decorator_kind."""
        rtm = generate_rtm(REPO_ROOT, package="holly", test_dir="tests")
        for entry in rtm.entries:
            assert entry.decorator_kind != ""

    def test_synthetic_end_to_end(self, tmp_path: Path) -> None:
        """End-to-end: synthetic source + tests → RTM with coverage.

        Creates a mini Holly tree with a decorated symbol and a
        matching test, then verifies the RTM correlates them.
        """
        # Production code with decorator.
        _write_module(
            tmp_path,
            "holly.kernel.k1",
            '''\
            from holly.arch.decorators import kernel_boundary

            @kernel_boundary(component_id="K1", invariant="schema", icd_schema="ICD-001")
            def validate(msg):
                return msg
            ''',
        )
        # Test file.
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "__init__.py").write_text("")
        (test_dir / "test_k1.py").write_text(textwrap.dedent("""\
            from holly.kernel.k1 import validate

            class TestValidation:
                def test_ok(self):
                    pass

                def test_fail(self):
                    pass
        """))
        # RTM generation uses the real registry (architecture.yaml).
        rtm = generate_rtm(tmp_path, package="holly", test_dir="tests")
        assert len(rtm.entries) >= 1
        entry = rtm.entries[0]
        assert entry.component_id == "K1"
        assert entry.decorator_kind == "kernel_boundary"
        assert "ICD-001" in entry.icd_ids
        assert entry.test_count >= 2
        assert entry.status == CoverageStatus.COVERED
