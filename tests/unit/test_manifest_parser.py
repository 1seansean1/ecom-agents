"""Tests for holly.arch.manifest_parser — Task Manifest markdown parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from holly.arch.manifest_parser import parse_manifest, parse_manifest_file

if TYPE_CHECKING:
    from pathlib import Path

MINIMAL_MANIFEST = """\
# Holly Grace — Task Manifest (REVISED)

## Slice 1 — Phase A Spiral (Steps 1, 2, 3, 3a)

### Tasks

#### Step 1 — Extract (SAD → architecture.yaml)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 1.1 | 1 | Map SAD terms to monograph definitions | SAD | Traceability | Review | Traces |
| 1.2 | 2 | Preserve 42010 viewpoint structure | SAD | Schema | Review | Viewpoints survive |
| 1.5 | 8 | Write SAD parser (mermaid → AST) | SAD file | Parser | Test | Parses |
| 1.6 | 8 | Define `architecture.yaml` schema | Structure | Pydantic | Test | Validates |
| 1.7 | 8 | Build extraction pipeline | Parser | YAML | Test | Round-trips |
| 1.8 | 9 | Link YAML entries to SAD source lines | SAD, YAML | Annotations | CI | Has refs |

#### Step 2 — Registry (Python singleton, YAML lookups)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 2.6 | 8 | Implement singleton loader | YAML | Registry class | Test | Loads |
| 2.7 | 8 | Implement lookups | Registry | get_component() | Test | Queryable |

### Critical Path

```
1.5 → 1.6 → 1.7 → 1.8 → 2.6 → 2.7
```

## Slice 2 — Phase A Backfill (Steps 4-11)

### Tasks

#### Step 4 — Scaffold (generate package skeleton)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 4.1 | 1 | Verify package names trace to monograph | Mono | Mapping | Review | Traces |
| 4.2 | 2 | Generate packages per 42010 viewpoint | YAML | Skeleton | Test | Correct |

### Critical Path

```
4.1 → 4.2
```
"""


class TestParseMinimal:
    """Test parsing of minimal synthetic manifest."""

    def test_slice_count(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert len(manifest.slices) == 2

    def test_slice_metadata(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert manifest.slices[0].slice_num == 1
        assert "Phase A Spiral" in manifest.slices[0].title
        assert manifest.slices[1].slice_num == 2

    def test_step_count(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert len(manifest.slices[0].steps) == 2  # Step 1 and Step 2
        assert len(manifest.slices[1].steps) == 1  # Step 4

    def test_step_metadata(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        step1 = manifest.slices[0].steps[0]
        assert step1.step_id == "1"
        assert "Extract" in step1.name

    def test_task_count(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert manifest.total_tasks == 10

    def test_task_ids(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert "1.5" in manifest.tasks
        assert "2.6" in manifest.tasks
        assert "4.1" in manifest.tasks

    def test_task_names(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert "parser" in manifest.tasks["1.5"].name.lower()
        assert "singleton" in manifest.tasks["2.6"].name.lower()

    def test_task_slice_assignment(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert manifest.tasks["1.5"].slice_num == 1
        assert manifest.tasks["4.1"].slice_num == 2

    def test_task_step_assignment(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert manifest.tasks["1.5"].step_id == "1"
        assert manifest.tasks["2.6"].step_id == "2"

    def test_critical_path_slice1(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        cp = manifest.slices[0].critical_path
        assert cp == ["1.5", "1.6", "1.7", "1.8", "2.6", "2.7"]

    def test_critical_path_slice2(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        cp = manifest.slices[1].critical_path
        assert cp == ["4.1", "4.2"]

    def test_all_critical_path_ids(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        assert "1.5" in manifest.all_critical_path_ids
        assert "2.7" in manifest.all_critical_path_ids
        assert "4.2" in manifest.all_critical_path_ids
        # Non-critical task should not be in the set
        assert "1.1" not in manifest.all_critical_path_ids

    def test_tasks_in_slice(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        slice1_tasks = manifest.tasks_in_slice(1)
        assert len(slice1_tasks) == 8
        # Should be sorted by sort_key
        ids = [t.task_id for t in slice1_tasks]
        assert ids[0] == "1.1"
        assert ids[-1] == "2.7"

    def test_markdown_cleanup(self) -> None:
        manifest = parse_manifest(MINIMAL_MANIFEST)
        # Backtick-wrapped names should be cleaned
        t16 = manifest.tasks["1.6"]
        assert "`" not in t16.name


class TestParseRealManifest:
    """Test parsing of the real Task_Manifest.md."""

    def test_real_manifest(self, repo_root: Path) -> None:
        manifest_path = repo_root / "docs" / "Task_Manifest.md"
        if not manifest_path.exists():
            return

        manifest = parse_manifest_file(manifest_path)

        # Should have 15 slices
        assert len(manifest.slices) == 15

        # Manifest claims 583 but actual table rows are 442
        # (delta summary double-counts acceptance-criteria refinements as tasks)
        assert manifest.total_tasks >= 400, f"Got {manifest.total_tasks}"

        # Every slice should have a critical path
        for sl in manifest.slices:
            assert len(sl.critical_path) >= 2, f"Slice {sl.slice_num} has no critical path"

        # Specific tasks from the manifest
        assert "1.5" in manifest.tasks
        assert "3a.8" in manifest.tasks
        assert "84.8" in manifest.tasks
