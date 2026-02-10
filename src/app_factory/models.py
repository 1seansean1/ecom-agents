"""App Factory project state: dataclass + Postgres CRUD.

An AppProject is the persistent state that agents read and write as they
progress through development phases.  Stored as a single JSONB blob
keyed by project_id.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

import psycopg

from src.aps.store import _get_conn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase definitions
# ---------------------------------------------------------------------------

PHASES = [
    "ideation",
    "prd",
    "architecture",
    "implementation",
    "testing",
    "security",
    "bugfix",
    "build",
    "deploy",
    "complete",
]


def next_phase(current: str) -> str | None:
    """Return the next phase or None if at the end."""
    try:
        idx = PHASES.index(current)
        return PHASES[idx + 1] if idx + 1 < len(PHASES) else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# AppProject dataclass
# ---------------------------------------------------------------------------


@dataclass
class AppProject:
    """Full project state persisted across orchestrator loops."""

    project_id: str = ""
    idea: str = ""
    app_name: str = ""
    app_package: str = ""
    status: str = "pending"  # pending | running | complete | failed
    current_phase: str = "ideation"

    # Phase artifacts
    prd: dict = field(default_factory=dict)
    architecture: dict = field(default_factory=dict)
    dev_plan: dict = field(default_factory=dict)
    file_manifest: list = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    security_report: dict = field(default_factory=dict)
    bug_tracker: list = field(default_factory=list)
    build_artifacts: dict = field(default_factory=dict)
    deploy_status: dict = field(default_factory=dict)

    # Observability
    diary: list = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0

    # Runtime
    workspace_path: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AppProject:
        return AppProject(**{k: v for k, v in d.items() if k in AppProject.__dataclass_fields__})

    def add_diary_entry(self, agent: str, phase: str, summary: str) -> None:
        self.diary.append({
            "timestamp": time.time(),
            "agent": agent,
            "phase": phase,
            "summary": summary,
        })

    @staticmethod
    def new_id() -> str:
        return f"proj_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Postgres CRUD
# ---------------------------------------------------------------------------


def create_project(project: AppProject) -> dict[str, Any] | None:
    """Insert a new project into the DB."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO app_factory_projects (project_id, data)
                   VALUES (%s, %s)
                   ON CONFLICT (project_id) DO NOTHING""",
                (project.project_id, json.dumps(project.to_dict())),
            )
        return project.to_dict()
    except Exception:
        logger.exception("Failed to create project %s", project.project_id)
        return None


def get_project(project_id: str) -> AppProject | None:
    """Load a project from the DB."""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT data FROM app_factory_projects WHERE project_id = %s",
                (project_id,),
            ).fetchone()
        if row:
            data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            return AppProject.from_dict(data)
        return None
    except Exception:
        logger.exception("Failed to get project %s", project_id)
        return None


def update_project(project: AppProject) -> bool:
    """Persist updated project state."""
    try:
        with _get_conn() as conn:
            conn.execute(
                """UPDATE app_factory_projects
                   SET data = %s, updated_at = NOW()
                   WHERE project_id = %s""",
                (json.dumps(project.to_dict()), project.project_id),
            )
        return True
    except Exception:
        logger.exception("Failed to update project %s", project.project_id)
        return False


def list_projects() -> list[dict[str, Any]]:
    """List all projects (summary only)."""
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT project_id, data->>'app_name' AS app_name,
                          data->>'status' AS status,
                          data->>'current_phase' AS current_phase,
                          (data->>'total_cost_usd')::FLOAT AS total_cost_usd,
                          created_at
                   FROM app_factory_projects
                   ORDER BY created_at DESC"""
            ).fetchall()
        return [
            {
                "project_id": r[0],
                "app_name": r[1] or "",
                "status": r[2] or "pending",
                "current_phase": r[3] or "ideation",
                "total_cost_usd": r[4] or 0.0,
                "created_at": str(r[5]),
            }
            for r in rows
        ]
    except Exception:
        logger.exception("Failed to list projects")
        return []


def delete_project(project_id: str) -> bool:
    """Delete a project."""
    try:
        with _get_conn() as conn:
            result = conn.execute(
                "DELETE FROM app_factory_projects WHERE project_id = %s",
                (project_id,),
            )
            return result.rowcount > 0
    except Exception:
        logger.exception("Failed to delete project %s", project_id)
        return False
