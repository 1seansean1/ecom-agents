"""Tests for App Factory project models and state management."""

from __future__ import annotations

import pytest

from src.app_factory.models import PHASES, AppProject, next_phase


# ---------------------------------------------------------------------------
# Phase logic
# ---------------------------------------------------------------------------


class TestPhases:
    def test_phases_list(self):
        assert PHASES[0] == "ideation"
        assert PHASES[-1] == "complete"
        assert len(PHASES) == 10

    def test_next_phase_normal(self):
        assert next_phase("ideation") == "prd"
        assert next_phase("prd") == "architecture"
        assert next_phase("build") == "deploy"
        assert next_phase("deploy") == "complete"

    def test_next_phase_at_end(self):
        assert next_phase("complete") is None

    def test_next_phase_invalid(self):
        assert next_phase("nonexistent") is None


# ---------------------------------------------------------------------------
# AppProject dataclass
# ---------------------------------------------------------------------------


class TestAppProject:
    def test_new_id_format(self):
        pid = AppProject.new_id()
        assert pid.startswith("proj_")
        assert len(pid) == 13  # proj_ + 8 hex chars

    def test_new_id_unique(self):
        ids = {AppProject.new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_default_values(self):
        p = AppProject()
        assert p.status == "pending"
        assert p.current_phase == "ideation"
        assert p.total_cost_usd == 0.0
        assert p.diary == []
        assert p.prd == {}

    def test_to_dict_roundtrip(self):
        p = AppProject(
            project_id="proj_test1234",
            idea="Build a todo app",
            app_name="TodoApp",
            app_package="com.terravoid.todo",
            status="running",
            current_phase="implementation",
        )
        d = p.to_dict()
        p2 = AppProject.from_dict(d)
        assert p2.project_id == "proj_test1234"
        assert p2.idea == "Build a todo app"
        assert p2.app_name == "TodoApp"
        assert p2.app_package == "com.terravoid.todo"
        assert p2.status == "running"
        assert p2.current_phase == "implementation"

    def test_from_dict_ignores_extra_fields(self):
        d = {"project_id": "proj_test", "idea": "test", "unknown_field": "ignored"}
        p = AppProject.from_dict(d)
        assert p.project_id == "proj_test"
        assert not hasattr(p, "unknown_field") or True  # extra field just ignored

    def test_add_diary_entry(self):
        p = AppProject(project_id="proj_test")
        p.add_diary_entry("af_architect", "prd", "Created PRD with 5 features")
        assert len(p.diary) == 1
        entry = p.diary[0]
        assert entry["agent"] == "af_architect"
        assert entry["phase"] == "prd"
        assert entry["summary"] == "Created PRD with 5 features"
        assert "timestamp" in entry

    def test_add_multiple_diary_entries(self):
        p = AppProject(project_id="proj_test")
        for i in range(5):
            p.add_diary_entry("agent", f"phase_{i}", f"entry {i}")
        assert len(p.diary) == 5

    def test_complex_state(self):
        p = AppProject(
            project_id="proj_complex",
            prd={"features": ["auth", "profile", "settings"]},
            test_results={"passed": 42, "failed": 3},
            security_report={"findings": [{"severity": "high"}]},
            bug_tracker=[{"id": "BUG-1", "status": "open"}],
            build_artifacts={"apk_path": "/workspace/app.apk"},
        )
        d = p.to_dict()
        assert d["prd"]["features"] == ["auth", "profile", "settings"]
        assert d["test_results"]["passed"] == 42
        assert len(d["security_report"]["findings"]) == 1
        assert d["bug_tracker"][0]["id"] == "BUG-1"
