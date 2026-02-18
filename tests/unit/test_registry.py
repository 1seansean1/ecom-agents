"""Tests for holly.arch.registry — Task 2.6 singleton loader.

Covers:
- Singleton lifecycle (get, reset, double-get)
- Thread-safety under concurrent access
- Validation gate (malformed YAML, missing file)
- Configure / path override
- Integration with real architecture.yaml via extract pipeline
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import yaml

from holly.arch.registry import ArchitectureRegistry, RegistryValidationError
from holly.arch.schema import ArchitectureDocument

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
def minimal_yaml(tmp_path: Path) -> Path:
    """Write a minimal but valid architecture.yaml."""
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
    return p


@pytest.fixture()
def real_yaml() -> Path | None:
    """Return path to real architecture.yaml if it exists (integration)."""
    candidates = [
        Path("docs/architecture.yaml"),
        Path.cwd() / "docs" / "architecture.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


# ── Singleton lifecycle ───────────────────────────────


class TestSingletonLifecycle:
    """Test basic singleton get / reset / is_loaded."""

    def test_not_loaded_initially(self) -> None:
        assert not ArchitectureRegistry.is_loaded()

    def test_get_returns_same_instance(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        a = ArchitectureRegistry.get()
        b = ArchitectureRegistry.get()
        assert a is b

    def test_is_loaded_after_get(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        ArchitectureRegistry.get()
        assert ArchitectureRegistry.is_loaded()

    def test_reset_clears_instance(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        ArchitectureRegistry.get()
        ArchitectureRegistry.reset()
        assert not ArchitectureRegistry.is_loaded()

    def test_get_after_reset_reloads(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        first = ArchitectureRegistry.get()
        ArchitectureRegistry.reset()
        second = ArchitectureRegistry.get()
        assert first is not second
        # But documents have same content.
        assert first.document.metadata.sad_version == second.document.metadata.sad_version


# ── Document access ───────────────────────────────────


class TestDocumentAccess:
    """Test that the loaded document is valid and queryable."""

    def test_document_is_architecture_document(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert isinstance(reg.document, ArchitectureDocument)

    def test_component_lookup(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert "K1" in reg.document.components
        assert reg.document.components["K1"].name == "Schema Validation"

    def test_metadata_preserved(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert reg.document.metadata.sad_version == "0.1.0.5"


# ── Thread safety ─────────────────────────────────────


class TestThreadSafety:
    """Verify concurrent access returns the same singleton."""

    def test_concurrent_get_returns_same_instance(self, minimal_yaml: Path) -> None:
        """Launch N threads that all call get(); assert single instance."""
        ArchitectureRegistry.configure(minimal_yaml)
        results: list[ArchitectureRegistry] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                results.append(ArchitectureRegistry.get())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 8
        # All must be the same object.
        assert all(r is results[0] for r in results)

    def test_concurrent_get_consistent_document(self, minimal_yaml: Path) -> None:
        """All threads see the same document content."""
        ArchitectureRegistry.configure(minimal_yaml)
        versions: list[str] = []
        barrier = threading.Barrier(4)

        def worker() -> None:
            barrier.wait(timeout=5)
            reg = ArchitectureRegistry.get()
            versions.append(reg.document.metadata.sad_version)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(versions) == 4
        assert all(v == "0.1.0.5" for v in versions)


# ── Validation gate ───────────────────────────────────


class TestValidationGate:
    """Test that bad YAML is rejected cleanly."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        ArchitectureRegistry.configure(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError, match="not found"):
            ArchitectureRegistry.get()

    def test_invalid_yaml_structure_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("- just a list\n- not a mapping\n", encoding="utf-8")
        ArchitectureRegistry.configure(p)
        with pytest.raises(RegistryValidationError, match="mapping"):
            ArchitectureRegistry.get()

    def test_schema_violation_raises(self, tmp_path: Path) -> None:
        """Valid YAML mapping but missing required fields."""
        p = tmp_path / "partial.yaml"
        p.write_text(
            yaml.dump({"metadata": {"sad_version": "1.0"}}),
            encoding="utf-8",
        )
        ArchitectureRegistry.configure(p)
        with pytest.raises(RegistryValidationError, match="validation failed"):
            ArchitectureRegistry.get()

    def test_reset_after_error_allows_retry(self, tmp_path: Path, minimal_yaml: Path) -> None:
        """After a failed load, reset + reconfigure succeeds."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: architecture:", encoding="utf-8")
        ArchitectureRegistry.configure(bad)
        with pytest.raises((RegistryValidationError, Exception)):
            ArchitectureRegistry.get()

        ArchitectureRegistry.reset()
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert reg.document.metadata.sad_version == "0.1.0.5"


# ── Configure / path override ────────────────────────


class TestConfigure:
    """Test explicit path configuration."""

    def test_configure_accepts_string(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(str(minimal_yaml))
        reg = ArchitectureRegistry.get()
        assert reg.document.metadata.sad_version == "0.1.0.5"

    def test_configure_accepts_path(self, minimal_yaml: Path) -> None:
        ArchitectureRegistry.configure(minimal_yaml)
        reg = ArchitectureRegistry.get()
        assert isinstance(reg.document, ArchitectureDocument)


# ── Integration with real architecture.yaml ───────────


class TestIntegration:
    """Integration tests against the real generated architecture.yaml."""

    def test_real_yaml_loads(self, real_yaml: Path | None) -> None:
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found; run extract first")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()
        doc = reg.document
        assert doc.metadata.sad_version == "0.1.0.5"
        assert doc.component_count >= 40  # SAD has ~48 components
        assert doc.connection_count >= 40  # SAD has ~49 connections

    def test_real_yaml_kernel_invariants(self, real_yaml: Path | None) -> None:
        if real_yaml is None:
            pytest.skip("docs/architecture.yaml not found; run extract first")
        ArchitectureRegistry.configure(real_yaml)
        reg = ArchitectureRegistry.get()
        k_ids = {ki.id for ki in reg.document.kernel_invariants}
        # At minimum K1-K8 should be present.
        for kid in ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"):
            assert kid in k_ids, f"Missing kernel invariant {kid}"
