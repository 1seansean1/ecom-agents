"""App Factory tools: file I/O, shell exec, Docker management, project state.

Security:
- Path traversal blocked (no `..` in paths)
- Shell command whitelist (no curl/wget/python/pip/npm/bash -c/eval)
- Output size caps (50KB shell, 100KB file read, 1MB file write)
- Docker exec scoped to project workspace
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import PurePosixPath
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.app_factory.models import AppProject, get_project, update_project

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTAINER_NAME = "ecom-android-builder"
_WORKSPACE_ROOT = "/workspace"
_MAX_FILE_WRITE = 1_048_576  # 1MB
_MAX_FILE_READ = 102_400  # 100KB
_MAX_SHELL_OUTPUT = 51_200  # 50KB
_SHELL_TIMEOUT = 300  # 5 min

# Allowed shell commands (whitelist)
_ALLOWED_COMMANDS = {
    "gradlew", "./gradlew", "gradle", "kotlin", "kotlinc", "java", "javac",
    "adb", "ls", "find", "grep", "mkdir", "cp", "mv", "rm", "cat", "chmod",
    "touch", "echo", "pwd", "wc", "sort", "uniq", "diff", "head", "tail",
    "tree", "test", "sed",
}

# Blocked patterns (security)
_BLOCKED_PATTERNS = re.compile(
    r"(curl|wget|python|pip|npm|npx|node|bash\s+-c|eval\s|exec\s|"
    r"nc\s|ncat|socat|ssh|scp|apt|yum|dnf|apk\s|chmod\s+[0-7]*s)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


def _validate_path(project_id: str, path: str) -> str:
    """Validate and normalize a path within a project workspace.

    Returns the full container path. Raises ValueError on traversal attempts.
    """
    if ".." in path:
        raise ValueError(f"Path traversal blocked: {path}")

    # Normalize the path
    clean = PurePosixPath(path).as_posix().lstrip("/")
    full = f"{_WORKSPACE_ROOT}/{project_id}/{clean}"
    return full


def _validate_command(command: str) -> None:
    """Validate a shell command against the whitelist.

    Raises ValueError if the command is not allowed.
    """
    if _BLOCKED_PATTERNS.search(command):
        raise ValueError(f"Blocked command pattern: {command}")

    # Extract the base command (first token)
    tokens = command.strip().split()
    if not tokens:
        raise ValueError("Empty command")

    base_cmd = tokens[0].split("/")[-1]  # Handle ./gradlew etc.
    if base_cmd not in _ALLOWED_COMMANDS and tokens[0] not in _ALLOWED_COMMANDS:
        raise ValueError(
            f"Command '{base_cmd}' not in whitelist. "
            f"Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"
        )


def _docker_exec(project_id: str, command: str, timeout: int = _SHELL_TIMEOUT) -> dict:
    """Execute a command inside the Android builder container."""
    workdir = f"{_WORKSPACE_ROOT}/{project_id}"
    full_cmd = [
        "docker", "exec", "-w", workdir, _CONTAINER_NAME,
        "sh", "-c", command,
    ]
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout[:_MAX_SHELL_OUTPUT]
        stderr = result.stderr[:_MAX_SHELL_OUTPUT]
        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(result.stdout) > _MAX_SHELL_OUTPUT,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s", "truncated": False}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e), "truncated": False}


# ---------------------------------------------------------------------------
# Tool 1: af_write_file
# ---------------------------------------------------------------------------


class AFWriteFileInput(BaseModel):
    project_id: str = Field(description="The project ID")
    path: str = Field(description="Relative path within the project workspace")
    content: str = Field(description="File content to write")


@tool(args_schema=AFWriteFileInput)
def af_write_file(project_id: str, path: str, content: str) -> str:
    """Write a file to the project workspace in the Android builder container."""
    try:
        full_path = _validate_path(project_id, path)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if len(content) > _MAX_FILE_WRITE:
        return json.dumps({"error": f"Content too large: {len(content)} bytes (max {_MAX_FILE_WRITE})"})

    # Ensure parent directory exists
    parent = str(PurePosixPath(full_path).parent)
    _docker_exec(project_id, f"mkdir -p {parent}")

    # Write via stdin to avoid shell escaping issues
    full_cmd = [
        "docker", "exec", "-i", _CONTAINER_NAME,
        "sh", "-c", f"cat > {full_path}",
    ]
    try:
        result = subprocess.run(
            full_cmd,
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return json.dumps({"error": f"Write failed: {result.stderr[:500]}"})
        return json.dumps({"status": "written", "path": path, "size": len(content)})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 2: af_read_file
# ---------------------------------------------------------------------------


class AFReadFileInput(BaseModel):
    project_id: str = Field(description="The project ID")
    path: str = Field(description="Relative path within the project workspace")


@tool(args_schema=AFReadFileInput)
def af_read_file(project_id: str, path: str) -> str:
    """Read a file from the project workspace."""
    try:
        full_path = _validate_path(project_id, path)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    result = _docker_exec(project_id, f"cat {full_path}", timeout=30)
    if result["exit_code"] != 0:
        return json.dumps({"error": f"Read failed: {result['stderr'][:500]}"})

    content = result["stdout"][:_MAX_FILE_READ]
    return json.dumps({
        "path": path,
        "content": content,
        "size": len(content),
        "truncated": len(result["stdout"]) > _MAX_FILE_READ,
    })


# ---------------------------------------------------------------------------
# Tool 3: af_list_files
# ---------------------------------------------------------------------------


class AFListFilesInput(BaseModel):
    project_id: str = Field(description="The project ID")
    directory: str = Field(default=".", description="Directory to list (relative)")
    pattern: str = Field(default="", description="Optional glob pattern for find")


@tool(args_schema=AFListFilesInput)
def af_list_files(project_id: str, directory: str = ".", pattern: str = "") -> str:
    """List files in the project workspace."""
    try:
        full_dir = _validate_path(project_id, directory)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if pattern:
        cmd = f"find {full_dir} -name '{pattern}' -type f 2>/dev/null | head -200"
    else:
        cmd = f"find {full_dir} -type f 2>/dev/null | head -200"

    result = _docker_exec(project_id, cmd, timeout=30)
    if result["exit_code"] != 0:
        return json.dumps({"error": result["stderr"][:500]})

    # Strip workspace prefix for cleaner output
    prefix = f"{_WORKSPACE_ROOT}/{project_id}/"
    files = [
        line.replace(prefix, "")
        for line in result["stdout"].strip().split("\n")
        if line.strip()
    ]
    return json.dumps({"directory": directory, "files": files, "count": len(files)})


# ---------------------------------------------------------------------------
# Tool 4: af_shell
# ---------------------------------------------------------------------------


class AFShellInput(BaseModel):
    project_id: str = Field(description="The project ID")
    command: str = Field(description="Shell command to execute (whitelisted commands only)")
    timeout: int = Field(default=300, description="Timeout in seconds (max 300)")


@tool(args_schema=AFShellInput)
def af_shell(project_id: str, command: str, timeout: int = 300) -> str:
    """Execute a whitelisted shell command in the project's Docker workspace."""
    try:
        _validate_command(command)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    timeout = min(timeout, _SHELL_TIMEOUT)
    result = _docker_exec(project_id, command, timeout=timeout)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool 5: af_docker_start
# ---------------------------------------------------------------------------


class AFDockerStartInput(BaseModel):
    project_id: str = Field(description="The project ID")


@tool(args_schema=AFDockerStartInput)
def af_docker_start(project_id: str) -> str:
    """Ensure the Android builder container is running and create the project workspace."""
    try:
        # Check if container is running
        check = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", _CONTAINER_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if check.stdout.strip() != "true":
            # Start the container
            subprocess.run(
                ["docker", "start", _CONTAINER_NAME],
                capture_output=True, text=True, timeout=30,
            )

        # Create project workspace
        _docker_exec(project_id, f"mkdir -p {_WORKSPACE_ROOT}/{project_id}")

        return json.dumps({"status": "running", "workspace": f"{_WORKSPACE_ROOT}/{project_id}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 6: af_docker_stop
# ---------------------------------------------------------------------------


class AFDockerStopInput(BaseModel):
    project_id: str = Field(description="The project ID")


@tool(args_schema=AFDockerStopInput)
def af_docker_stop(project_id: str) -> str:
    """Clean up the project workspace (does not stop the shared container)."""
    try:
        # Remove project workspace (container stays running for other projects)
        _docker_exec(project_id, f"rm -rf {_WORKSPACE_ROOT}/{project_id}")
        return json.dumps({"status": "cleaned", "project_id": project_id})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 7: af_play_store
# ---------------------------------------------------------------------------


class AFPlayStoreInput(BaseModel):
    project_id: str = Field(description="The project ID")
    aab_path: str = Field(description="Path to the .aab bundle in the workspace")
    track: str = Field(default="internal", description="Play Store track: internal, alpha, beta, production")
    release_notes: str = Field(default="", description="Release notes for this version")


@tool(args_schema=AFPlayStoreInput)
def af_play_store(project_id: str, aab_path: str, track: str = "internal", release_notes: str = "") -> str:
    """Upload an AAB to Google Play Store. HIGH RISK — requires approval.

    This tool is gated by ApprovalGate and will create a pending approval
    before executing. The upload uses the Google Play Developer API.
    """
    # Validate inputs
    if track not in ("internal", "alpha", "beta", "production"):
        return json.dumps({"error": f"Invalid track: {track}"})

    try:
        _validate_path(project_id, aab_path)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Check that the AAB exists
    full_path = f"{_WORKSPACE_ROOT}/{project_id}/{aab_path.lstrip('/')}"
    check = _docker_exec(project_id, f"test -f {full_path} && echo exists", timeout=10)
    if "exists" not in check.get("stdout", ""):
        return json.dumps({"error": f"AAB not found: {aab_path}"})

    # Load project to get package name
    project = get_project(project_id)
    if not project:
        return json.dumps({"error": "Project not found"})

    # For now, return a deployment-ready status
    # Actual Play Store upload requires google-auth + google-api-python-client
    # which will be configured when the user provides their service account key
    return json.dumps({
        "status": "ready_for_upload",
        "package": project.app_package,
        "aab_path": aab_path,
        "track": track,
        "release_notes": release_notes,
        "note": "Play Store upload requires GOOGLE_PLAY_SERVICE_ACCOUNT_KEY env var. "
                "Set it to the path of your service account JSON key file.",
    })


# ---------------------------------------------------------------------------
# Tool 8: af_state
# ---------------------------------------------------------------------------


class AFStateInput(BaseModel):
    project_id: str = Field(description="The project ID")
    action: str = Field(description="Action: 'read', 'update', or 'diary'")
    field: str = Field(default="", description="Field to update (for 'update' action)")
    value: Any = Field(default=None, description="Value to set (for 'update' action)")


@tool(args_schema=AFStateInput)
def af_state(project_id: str, action: str, field: str = "", value: Any = None) -> str:
    """Read or update App Factory project state in the database."""
    project = get_project(project_id)
    if not project:
        return json.dumps({"error": f"Project not found: {project_id}"})

    if action == "read":
        return json.dumps(project.to_dict(), default=str)

    elif action == "update":
        if not field:
            return json.dumps({"error": "field is required for update action"})

        allowed_fields = {
            "app_name", "app_package", "status", "current_phase",
            "prd", "architecture", "dev_plan", "file_manifest",
            "test_results", "security_report", "bug_tracker",
            "build_artifacts", "deploy_status", "total_cost_usd", "total_tokens",
        }
        if field not in allowed_fields:
            return json.dumps({"error": f"Cannot update field: {field}. Allowed: {sorted(allowed_fields)}"})

        setattr(project, field, value)
        if update_project(project):
            return json.dumps({"status": "updated", "field": field})
        return json.dumps({"error": "Failed to persist update"})

    elif action == "diary":
        # value should be {"agent": "...", "phase": "...", "summary": "..."}
        if isinstance(value, dict):
            project.add_diary_entry(
                agent=value.get("agent", "unknown"),
                phase=value.get("phase", project.current_phase),
                summary=value.get("summary", ""),
            )
            if update_project(project):
                return json.dumps({"status": "diary_entry_added", "total_entries": len(project.diary)})
        return json.dumps({"error": "diary action requires value: {agent, phase, summary}"})

    else:
        return json.dumps({"error": "Unknown action: %s. Use 'read', 'update', or 'diary'" % action})
