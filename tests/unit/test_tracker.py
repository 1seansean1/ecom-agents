"""Tests for holly.arch.tracker — status tracking and Gantt generation."""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from holly.arch.manifest_parser import parse_manifest

if TYPE_CHECKING:
    from pathlib import Path
from holly.arch.tracker import (
    StatusRegistry,
    TaskState,
    TaskStatus,
    build_registry,
    generate_gantt,
    generate_gantt_critical_only,
    generate_summary_table,
    load_status,
    save_status,
)

MINIMAL_MANIFEST = """\
# Holly Grace — Task Manifest

## Slice 1 — Phase A Spiral (Steps 1, 2)

### Tasks

#### Step 1 — Extract

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 1.1 | 1 | Map SAD terms | SAD | Trace | Review | Traces |
| 1.5 | 8 | Write parser | SAD | Parser | Test | Parses |
| 1.6 | 8 | Define schema | SAD | Schema | Test | Validates |

#### Step 2 — Registry

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 2.6 | 8 | Implement loader | YAML | Registry | Test | Loads |

### Critical Path

```
1.5 → 1.6 → 2.6
```
"""

STATUS_YAML = dedent("""\
    version: "1.0"
    generated: "2026-02-18"
    tasks:
      1.5:
        status: done
        commit: b829279
        date: "2026-02-18"
      1.6:
        status: done
        commit: b829279
        date: "2026-02-18"
      1.1: pending
      2.6: active
""")


class TestLoadStatus:
    """Test status.yaml loading."""

    def test_load_from_string(self, tmp_path: Path) -> None:
        status_file = tmp_path / "status.yaml"
        status_file.write_text(STATUS_YAML, encoding="utf-8")
        states = load_status(status_file)
        assert states["1.5"].status == TaskStatus.DONE
        assert states["1.5"].commit == "b829279"
        assert states["2.6"].status == TaskStatus.ACTIVE
        assert states["1.1"].status == TaskStatus.PENDING

    def test_load_missing_file(self, tmp_path: Path) -> None:
        states = load_status(tmp_path / "nonexistent.yaml")
        assert states == {}

    def test_save_roundtrip(self, tmp_path: Path) -> None:
        states = {
            "1.5": TaskState("1.5", TaskStatus.DONE, commit="abc", date_completed="2026-02-18"),
            "1.6": TaskState("1.6", TaskStatus.PENDING),
        }
        path = tmp_path / "out.yaml"
        save_status(states, path)
        loaded = load_status(path)
        assert loaded["1.5"].status == TaskStatus.DONE
        assert loaded["1.5"].commit == "abc"
        assert loaded["1.6"].status == TaskStatus.PENDING


class TestStatusRegistry:
    """Test merged registry operations."""

    def test_slice_progress(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        states = {
            "1.5": TaskState("1.5", TaskStatus.DONE),
            "1.6": TaskState("1.6", TaskStatus.DONE),
        }
        reg = StatusRegistry(manifest=manifest, states=states)
        done, total = reg.slice_progress(1)
        assert done == 2
        assert total == 4

    def test_overall_progress(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        states = {
            "1.5": TaskState("1.5", TaskStatus.DONE),
        }
        reg = StatusRegistry(manifest=manifest, states=states)
        done, total = reg.overall_progress()
        assert done == 1
        assert total == 4

    def test_state_of_unknown(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        state = reg.state_of("1.5")
        assert state.status == TaskStatus.PENDING


class TestGanttGeneration:
    """Test mermaid Gantt output."""

    def test_gantt_header(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        gantt = generate_gantt(reg)
        assert gantt.startswith("gantt")
        assert "title" in gantt
        assert "dateFormat" in gantt

    def test_gantt_sections(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        gantt = generate_gantt(reg)
        assert "section Slice 1" in gantt

    def test_gantt_done_task(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        states = {
            "1.5": TaskState("1.5", TaskStatus.DONE, date_completed="2026-02-18"),
        }
        reg = StatusRegistry(manifest=manifest, states=states)
        gantt = generate_gantt(reg)
        assert "done," in gantt
        assert "2026-02-18" in gantt

    def test_gantt_critical_task(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        gantt = generate_gantt(reg)
        # 1.5 is on critical path, so should have crit tag
        assert "crit," in gantt

    def test_gantt_critical_only(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        gantt = generate_gantt_critical_only(reg)
        assert "Critical Path" in gantt
        # Should include critical tasks
        assert "1.5" in gantt
        assert "2.6" in gantt
        # Should NOT include non-critical 1.1
        assert "1.1" not in gantt


class TestSummaryTable:
    """Test markdown summary table output."""

    def test_table_header(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        table = generate_summary_table(reg)
        assert "| Slice |" in table
        assert "| Progress |" in table

    def test_table_progress(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        states = {
            "1.5": TaskState("1.5", TaskStatus.DONE),
            "1.6": TaskState("1.6", TaskStatus.DONE),
        }
        reg = StatusRegistry(manifest=manifest, states=states)
        table = generate_summary_table(reg)
        assert "50%" in table  # 2/4 done

    def test_table_total_row(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        reg = StatusRegistry(manifest=manifest, states={})
        table = generate_summary_table(reg)
        assert "**Σ**" in table


class TestBuildRegistry:
    """Test high-level build_registry from files."""

    def test_build_from_files(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "manifest.md"
        manifest_file.write_text(MINIMAL_MANIFEST, encoding="utf-8")

        status_file = tmp_path / "status.yaml"
        status_file.write_text(STATUS_YAML, encoding="utf-8")

        reg = build_registry(manifest_file, status_file)
        assert reg.manifest.total_tasks == 4
        assert reg.state_of("1.5").status == TaskStatus.DONE
        assert reg.state_of("2.6").status == TaskStatus.ACTIVE

    def test_build_missing_status(self, tmp_path: Path) -> None:
        manifest_file = tmp_path / "manifest.md"
        manifest_file.write_text(MINIMAL_MANIFEST, encoding="utf-8")

        reg = build_registry(manifest_file, tmp_path / "nonexistent.yaml")
        assert reg.manifest.total_tasks == 4
        assert reg.state_of("1.5").status == TaskStatus.PENDING
