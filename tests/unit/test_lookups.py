"""Tests for Task 2.7 — component / boundary / ICD lookups.

Acceptance criteria:
- Every SAD component queryable via get_component()
- Unknown keys raise ComponentNotFoundError
- get_boundary returns only crosses_boundary=True connections matching layers
- get_icd returns boundary-crossing connections involving the given component

Property-based approach: iterate over the *actual* architecture.yaml
to verify exhaustive queryability rather than hard-coding IDs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from holly.arch.registry import ArchitectureRegistry, ComponentNotFoundError
from holly.arch.schema import Component, LayerID

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure every test starts with a clean singleton."""
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None
    yield
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None


@pytest.fixture()
def rich_yaml(tmp_path: Path) -> Path:
    """Write a multi-component architecture.yaml with boundary crossings."""
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
                "source": {"file": "t.mermaid", "line": 1, "raw": "K1"},
            },
            "CONV": {
                "id": "CONV",
                "name": "Conversation Interface",
                "layer": "L2",
                "subgraph_id": "CORE",
                "source": {"file": "t.mermaid", "line": 2, "raw": "CONV"},
            },
            "PG": {
                "id": "PG",
                "name": "PostgreSQL 16",
                "layer": "DATA",
                "subgraph_id": "DATA",
                "source": {"file": "t.mermaid", "line": 3, "raw": "PG"},
            },
            "CORE": {
                "id": "CORE",
                "name": "CORE",
                "layer": "L2",
                "subgraph_id": "",
                "source": {"file": "t.mermaid", "line": 4, "raw": "CORE"},
            },
            "KERNEL": {
                "id": "KERNEL",
                "name": "KERNEL",
                "layer": "L1",
                "subgraph_id": "",
                "source": {"file": "t.mermaid", "line": 5, "raw": "KERNEL"},
            },
        },
        "connections": [
            {
                "source_id": "CORE",
                "target_id": "KERNEL",
                "label": "in-process",
                "kind": "in_process",
                "style": "dotted",
                "crosses_boundary": True,
                "source_layer": "L2",
                "target_layer": "L1",
                "source_ref": {"file": "t.mermaid", "line": 10, "raw": ""},
            },
            {
                "source_id": "CORE",
                "target_id": "PG",
                "label": "State",
                "kind": "data_access",
                "style": "solid",
                "crosses_boundary": True,
                "source_layer": "L2",
                "target_layer": "DATA",
                "source_ref": {"file": "t.mermaid", "line": 11, "raw": ""},
            },
            {
                "source_id": "CONV",
                "target_id": "CORE",
                "label": "",
                "kind": "internal_flow",
                "style": "solid",
                "crosses_boundary": False,
                "source_layer": "L2",
                "target_layer": "L2",
                "source_ref": {"file": "t.mermaid", "line": 12, "raw": ""},
            },
        ],
        "kernel_invariants": [],
    }
    p = tmp_path / "architecture.yaml"
    p.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture()
def real_yaml() -> Path | None:
    """Return path to real architecture.yaml if it exists."""
    candidates = [
        Path("docs/architecture.yaml"),
        Path.cwd() / "docs" / "architecture.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ── get_component ─────────────────────────────────────


class TestGetComponent:
    """Test component lookup by mermaid node ID."""

    def test_returns_correct_component(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        comp = reg.get_component("K1")
        assert isinstance(comp, Component)
        assert comp.id == "K1"
        assert comp.name == "Schema Validation"
        assert comp.layer == LayerID.L1_KERNEL

    def test_all_fixture_components_queryable(self, rich_yaml: Path) -> None:
        """Property: every component in the YAML is queryable."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        for cid in reg.document.components:
            comp = reg.get_component(cid)
            assert comp.id == cid

    def test_unknown_key_raises_component_not_found(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ComponentNotFoundError, match="NONEXISTENT"):
            reg.get_component("NONEXISTENT")

    def test_error_is_key_error_subclass(self, rich_yaml: Path) -> None:
        """ComponentNotFoundError should be catchable as KeyError."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(KeyError):
            reg.get_component("NOPE")

    def test_error_has_component_id_attribute(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ComponentNotFoundError) as exc_info:
            reg.get_component("MISSING")
        assert exc_info.value.component_id == "MISSING"

    def test_empty_string_raises(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ComponentNotFoundError):
            reg.get_component("")


# ── get_boundary ──────────────────────────────────────


class TestGetBoundary:
    """Test boundary-crossing connection lookup by layer pair."""

    def test_returns_crossing_connections(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        edges = reg.get_boundary(LayerID.L2_CORE, LayerID.L1_KERNEL)
        assert len(edges) == 1
        assert edges[0].source_id == "CORE"
        assert edges[0].target_id == "KERNEL"
        assert edges[0].crosses_boundary is True

    def test_filters_by_layer_pair(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        edges = reg.get_boundary(LayerID.L2_CORE, LayerID.DATA)
        assert len(edges) == 1
        assert edges[0].target_id == "PG"

    def test_excludes_non_crossing(self, rich_yaml: Path) -> None:
        """Internal flows (crosses_boundary=False) are excluded."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        # L2→L2 has one internal_flow but crosses_boundary=False.
        edges = reg.get_boundary(LayerID.L2_CORE, LayerID.L2_CORE)
        assert len(edges) == 0

    def test_nonexistent_layer_pair_returns_empty(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        edges = reg.get_boundary(LayerID.L5_CONSOLE, LayerID.SANDBOX)
        assert edges == []

    def test_all_results_have_crosses_boundary_true(self, rich_yaml: Path) -> None:
        """Property: every returned connection must cross a boundary."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        for conn in reg.document.connections:
            if not conn.crosses_boundary:
                continue
            edges = reg.get_boundary(conn.source_layer, conn.target_layer)
            assert all(e.crosses_boundary for e in edges)

    def test_accepts_string_layer_ids(self, rich_yaml: Path) -> None:
        """LayerID coercion: string values are accepted."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        edges = reg.get_boundary(LayerID("L2"), LayerID("L1"))
        assert len(edges) == 1


# ── get_icd ───────────────────────────────────────────


class TestGetICD:
    """Test Interface Control Document lookup per component."""

    def test_returns_boundary_connections_for_component(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        icd = reg.get_icd("CORE")
        # CORE has 2 boundary crossings: CORE→KERNEL, CORE→PG
        assert len(icd) == 2
        ids = {(c.source_id, c.target_id) for c in icd}
        assert ("CORE", "KERNEL") in ids
        assert ("CORE", "PG") in ids

    def test_excludes_internal_flows(self, rich_yaml: Path) -> None:
        """CONV→CORE is internal (crosses_boundary=False), not in ICD."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        icd = reg.get_icd("CONV")
        assert len(icd) == 0

    def test_target_side_included(self, rich_yaml: Path) -> None:
        """PG appears as target in CORE→PG; should appear in PG's ICD."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        icd = reg.get_icd("PG")
        assert len(icd) == 1
        assert icd[0].source_id == "CORE"

    def test_unknown_component_raises(self, rich_yaml: Path) -> None:
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ComponentNotFoundError, match="GHOST"):
            reg.get_icd("GHOST")

    def test_component_with_no_crossings_returns_empty(self, rich_yaml: Path) -> None:
        """K1 has no connections at all in the fixture → empty ICD."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        icd = reg.get_icd("K1")
        assert icd == []

    def test_all_icd_connections_cross_boundary(self, rich_yaml: Path) -> None:
        """Property: every connection in any ICD must cross a boundary."""
        ArchitectureRegistry.configure(rich_yaml)
        reg = ArchitectureRegistry.get()
        for cid in reg.document.components:
            for conn in reg.get_icd(cid):
                assert conn.crosses_boundary is True


# ── Property-based: exhaustive real YAML ──────────────


class TestExhaustiveRealYAML:
    """Property tests against the full generated architecture.yaml.

    These verify the acceptance criteria: every SAD component is
    queryable and unknown keys raise errors.
    """

    def test_every_component_queryable(self, real_yaml: Path | None) -> None:
        """Property: for ALL component IDs in the real YAML,
        get_component returns a Component with matching id."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()
        for cid, expected in reg.document.components.items():
            result = reg.get_component(cid)
            assert result is expected
            assert result.id == cid

    def test_every_component_has_valid_layer(self, real_yaml: Path | None) -> None:
        """Property: every queryable component has a valid LayerID."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()
        valid_layers = set(LayerID)
        for cid in reg.document.components:
            comp = reg.get_component(cid)
            assert comp.layer in valid_layers, f"{cid} has invalid layer {comp.layer}"

    def test_unknown_ids_raise(self, real_yaml: Path | None) -> None:
        """Negative property: synthetic IDs always raise."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()
        for bad_id in ("ZZZZZ", "__NOPE__", "", "k1", "kernel"):
            with pytest.raises(ComponentNotFoundError):
                reg.get_component(bad_id)

    def test_boundary_crossings_exhaustive(self, real_yaml: Path | None) -> None:
        """Property: union of all get_boundary() calls equals the
        set of all crosses_boundary=True connections."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()

        # Collect all boundary crossings from direct iteration.
        all_crossings = {
            (c.source_id, c.target_id, c.source_layer, c.target_layer)
            for c in reg.document.connections
            if c.crosses_boundary
        }

        # Collect via get_boundary for every observed layer pair.
        layer_pairs = {(c.source_layer, c.target_layer) for c in reg.document.connections if c.crosses_boundary}
        reconstructed = set()
        for sl, tl in layer_pairs:
            for c in reg.get_boundary(sl, tl):
                reconstructed.add((c.source_id, c.target_id, c.source_layer, c.target_layer))

        assert reconstructed == all_crossings

    def test_icd_union_covers_all_boundary_crossings(self, real_yaml: Path | None) -> None:
        """Property: union of get_icd() for all components covers every
        boundary-crossing connection (each appears at least once)."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()

        all_crossings = {
            (c.source_id, c.target_id)
            for c in reg.document.connections
            if c.crosses_boundary
        }

        covered = set()
        for cid in reg.document.components:
            for c in reg.get_icd(cid):
                covered.add((c.source_id, c.target_id))

        assert covered == all_crossings

    def test_icd_symmetry(self, real_yaml: Path | None) -> None:
        """Property: if a boundary connection goes A→B, it appears
        in both get_icd('A') and get_icd('B')."""
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()

        for conn in reg.document.connections:
            if not conn.crosses_boundary:
                continue
            src_icd = reg.get_icd(conn.source_id)
            tgt_icd = reg.get_icd(conn.target_id)
            assert conn in src_icd, f"{conn.source_id}→{conn.target_id} not in source ICD"
            assert conn in tgt_icd, f"{conn.source_id}→{conn.target_id} not in target ICD"
