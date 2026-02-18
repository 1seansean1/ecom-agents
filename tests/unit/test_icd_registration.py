"""Tests for Task 5.6 — ICD registration in architecture.yaml.

Acceptance criteria:
    - Registry serves ICD lookups for all 49 ICDs
    - Each ICD entry has valid source and target components
    - get_icd_entry() returns correct entry by ID
    - get_all_icds() returns all 49 entries
    - get_icds_for_component() returns correct subset
    - ICDNotFoundError raised for unknown ICD IDs
    - Schema validates ICD entries during YAML load
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from holly.arch.registry import (
    ArchitectureRegistry,
    ComponentNotFoundError,
    ICDNotFoundError,
)
from holly.arch.schema import ICDEntry

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Ensure every test starts with a clean singleton."""
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None
    yield
    ArchitectureRegistry.reset()
    ArchitectureRegistry._yaml_path = None


@pytest.fixture()
def real_registry() -> ArchitectureRegistry:
    """Load the actual architecture.yaml from the repo."""
    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "docs" / "architecture.yaml"
    ArchitectureRegistry.configure(yaml_path)
    return ArchitectureRegistry.get()


@pytest.fixture()
def minimal_yaml(tmp_path: Path) -> Path:
    """Write a minimal architecture.yaml with ICD entries for unit testing."""
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
            "A": {
                "id": "A",
                "name": "Component A",
                "layer": "L1",
                "subgraph_id": "S1",
                "source": {"file": "test.mermaid", "line": 1},
            },
            "B": {
                "id": "B",
                "name": "Component B",
                "layer": "L2",
                "subgraph_id": "S2",
                "source": {"file": "test.mermaid", "line": 2},
            },
            "C": {
                "id": "C",
                "name": "Component C",
                "layer": "L3",
                "subgraph_id": "S3",
                "source": {"file": "test.mermaid", "line": 3},
            },
        },
        "connections": [],
        "kernel_invariants": [],
        "icds": [
            {
                "id": "ICD-TEST-001",
                "name": "A → B",
                "source_component": "A",
                "target_component": "B",
                "protocol": "in-process",
                "sil": "SIL-3",
            },
            {
                "id": "ICD-TEST-002",
                "name": "B → C",
                "source_component": "B",
                "target_component": "C",
                "protocol": "gRPC",
                "sil": "SIL-2",
            },
            {
                "id": "ICD-TEST-003",
                "name": "A → C",
                "source_component": "A",
                "target_component": "C",
                "protocol": "HTTPS",
                "sil": "SIL-1",
            },
        ],
    }
    path = tmp_path / "architecture.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


# ── TestICDRegistrationReal (integration with actual YAML) ────


class TestICDRegistrationReal:
    """Integration tests against the real architecture.yaml."""

    def test_all_49_icds_registered(self, real_registry: ArchitectureRegistry) -> None:
        icds = real_registry.get_all_icds()
        assert len(icds) == 49

    def test_icd_ids_sequential(self, real_registry: ArchitectureRegistry) -> None:
        icds = real_registry.get_all_icds()
        expected_ids = [f"ICD-{i:03d}" for i in range(1, 50)]
        actual_ids = [e.id for e in icds]
        assert actual_ids == expected_ids

    @pytest.mark.parametrize("icd_id", [f"ICD-{i:03d}" for i in range(1, 50)])
    def test_lookup_each_icd(self, real_registry: ArchitectureRegistry, icd_id: str) -> None:
        entry = real_registry.get_icd_entry(icd_id)
        assert isinstance(entry, ICDEntry)
        assert entry.id == icd_id

    @pytest.mark.parametrize("icd_id", [f"ICD-{i:03d}" for i in range(1, 50)])
    def test_source_component_valid(self, real_registry: ArchitectureRegistry, icd_id: str) -> None:
        entry = real_registry.get_icd_entry(icd_id)
        assert entry.source_component in real_registry.document.components

    @pytest.mark.parametrize("icd_id", [f"ICD-{i:03d}" for i in range(1, 50)])
    def test_target_component_valid(self, real_registry: ArchitectureRegistry, icd_id: str) -> None:
        entry = real_registry.get_icd_entry(icd_id)
        assert entry.target_component in real_registry.document.components

    def test_all_icds_have_protocol(self, real_registry: ArchitectureRegistry) -> None:
        for entry in real_registry.get_all_icds():
            assert entry.protocol, f"{entry.id} missing protocol"

    def test_all_icds_have_sil(self, real_registry: ArchitectureRegistry) -> None:
        for entry in real_registry.get_all_icds():
            assert entry.sil in {"SIL-1", "SIL-2", "SIL-3"}, f"{entry.id} bad SIL: {entry.sil}"

    def test_kernel_component_has_icds(self, real_registry: ArchitectureRegistry) -> None:
        kernel_icds = real_registry.get_icds_for_component("KERNEL")
        assert len(kernel_icds) >= 2  # ICD-006, ICD-007, ICD-038

    def test_core_component_has_icds(self, real_registry: ArchitectureRegistry) -> None:
        core_icds = real_registry.get_icds_for_component("CORE")
        assert len(core_icds) >= 5  # Many ICDs involve CORE


# ── TestICDLookups (unit tests with minimal YAML) ────────────


class TestICDLookups:
    """Unit tests for ICD lookup methods."""

    def test_get_icd_entry(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        entry = reg.get_icd_entry("ICD-TEST-001")
        assert entry.name == "A → B"
        assert entry.source_component == "A"
        assert entry.target_component == "B"

    def test_get_icd_entry_not_found(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ICDNotFoundError, match="ICD-999"):
            reg.get_icd_entry("ICD-999")

    def test_get_all_icds(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert len(reg.get_all_icds()) == 3

    def test_get_icds_for_component_source(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        icds_a = reg.get_icds_for_component("A")
        assert len(icds_a) == 2  # A is source in TEST-001 and TEST-003

    def test_get_icds_for_component_target(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        icds_c = reg.get_icds_for_component("C")
        assert len(icds_c) == 2  # C is target in TEST-002 and TEST-003

    def test_get_icds_for_component_both(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        icds_b = reg.get_icds_for_component("B")
        assert len(icds_b) == 2  # B is target in TEST-001, source in TEST-002

    def test_get_icds_for_unknown_component(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        with pytest.raises(ComponentNotFoundError):
            reg.get_icds_for_component("NONEXISTENT")

    def test_icd_entry_has_all_fields(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        entry = reg.get_icd_entry("ICD-TEST-002")
        assert entry.protocol == "gRPC"
        assert entry.sil == "SIL-2"
        assert entry.model_module == "holly.kernel.icd_models"


# ── TestICDSchemaValidation ───────────────────────────────


class TestICDSchemaValidation:
    """Verify ICDEntry Pydantic model validates correctly."""

    def test_valid_entry(self) -> None:
        entry = ICDEntry(
            id="ICD-001",
            name="Test ICD",
            source_component="A",
            target_component="B",
        )
        assert entry.id == "ICD-001"
        assert entry.protocol == ""
        assert entry.sil == ""

    def test_missing_required_fields(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ICDEntry(id="ICD-001")  # type: ignore[call-arg]

    def test_roundtrip_serialization(self) -> None:
        entry = ICDEntry(
            id="ICD-001",
            name="Test ICD",
            source_component="A",
            target_component="B",
            protocol="HTTPS",
            sil="SIL-3",
        )
        dumped = entry.model_dump()
        restored = ICDEntry.model_validate(dumped)
        assert restored == entry


# ── TestNoICDsBackwardCompat ──────────────────────────────


class TestNoICDsBackwardCompat:
    """Verify architecture.yaml without icds section still loads."""

    def test_empty_icds_default(self, tmp_path: Path) -> None:
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
            "components": {},
            "connections": [],
            "kernel_invariants": [],
            # No "icds" key — should default to empty list
        }
        path = tmp_path / "architecture.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        ArchitectureRegistry.configure(path)
        reg = ArchitectureRegistry.get()
        assert reg.get_all_icds() == []
