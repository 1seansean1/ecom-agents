"""
Tool definitions and executors for Claude Code mode.
Provides file operations and command execution with security safeguards.
"""

import os
import re
import asyncio
from pathlib import Path
from typing import Optional

# ---- Security ----

BLOCKED_COMMANDS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\brm\s+-rf\s+/",
        r"\bmkfs\b",
        r"\bdd\s+.*of=/dev/",
        r":()\s*\{\s*:\|:\s*&\s*\}\s*;",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bformat\s+[a-zA-Z]:",
        r"\bdel\s+/[sS]\s+/[qQ]",
    ]
]

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build"}


def validate_working_dir(working_dir: str) -> Path:
    p = Path(working_dir).resolve()
    if not p.exists() or not p.is_dir():
        raise ValueError(f"Working directory does not exist: {p}")
    return p


def sanitize_path(file_path: str, working_dir: Path) -> Path:
    resolved = (working_dir / file_path).resolve()
    if not str(resolved).startswith(str(working_dir)):
        raise ValueError(f"Path escapes working directory: {file_path}")
    return resolved


def check_command_safety(command: str) -> Optional[str]:
    for pattern in BLOCKED_COMMANDS:
        if pattern.search(command):
            return f"Blocked dangerous command: {pattern.pattern}"
    return None


# ---- Tool Definitions (Anthropic Schema) ----

TOOL_DEFINITIONS = [
    {
        "name": "bash_exec",
        "description": (
            "Execute a shell command and return stdout/stderr. "
            "Use for running programs, git, npm, pip, etc. "
            "Commands run in the working directory. Timeout: 120s."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120, max 300)", "default": 120},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file's contents. Use offset/limit for large files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path relative to working directory"},
                "offset": {"type": "integer", "description": "Start line (1-based)"},
                "limit": {"type": "integer", "description": "Max lines to read"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories. Overwrites existing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path relative to working directory"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit a file by replacing an exact string match. "
            "old_string must be unique in the file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path relative to working directory"},
                "old_string": {"type": "string", "description": "Exact string to find"},
                "new_string": {"type": "string", "description": "Replacement string"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_files",
        "description": "List files matching a glob pattern. Skips .git, node_modules, __pycache__, .venv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')", "default": "**/*"},
                "max_results": {"type": "integer", "description": "Max results (default 200)", "default": 200},
            },
            "required": [],
        },
    },
    {
        "name": "search_files",
        "description": "Search file contents with regex. Returns matching lines with paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "file_glob": {"type": "string", "description": "Glob to filter files (e.g. '*.py')", "default": "**/*"},
                "max_results": {"type": "integer", "description": "Max matches (default 50)", "default": 50},
            },
            "required": ["pattern"],
        },
    },
]


# ---- Tool Execution ----

async def execute_tool(name: str, input_data: dict, working_dir: Path) -> dict:
    try:
        if name == "bash_exec":
            return await _exec_bash(input_data, working_dir)
        elif name == "read_file":
            return await _exec_read_file(input_data, working_dir)
        elif name == "write_file":
            return await _exec_write_file(input_data, working_dir)
        elif name == "edit_file":
            return await _exec_edit_file(input_data, working_dir)
        elif name == "list_files":
            return await _exec_list_files(input_data, working_dir)
        elif name == "search_files":
            return await _exec_search_files(input_data, working_dir)
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)}"}


async def _exec_bash(inp: dict, wd: Path) -> dict:
    command = inp["command"]
    timeout = min(inp.get("timeout", 120), 300)

    err = check_command_safety(command)
    if err:
        return {"error": err}

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(wd),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        result = ""
        if stdout:
            result += stdout.decode("utf-8", errors="replace")
        if stderr:
            result += ("\n--- stderr ---\n" if result else "") + stderr.decode("utf-8", errors="replace")

        if len(result) > 30000:
            result = result[:30000] + "\n\n... (truncated at 30000 chars)"

        return {"output": (result or "(no output)") + f"\n[exit code: {proc.returncode}]"}
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": f"Command timed out after {timeout}s"}


async def _exec_read_file(inp: dict, wd: Path) -> dict:
    fp = sanitize_path(inp["file_path"], wd)
    if not fp.exists():
        return {"error": f"File not found: {inp['file_path']}"}
    if not fp.is_file():
        return {"error": f"Not a file: {inp['file_path']}"}

    content = fp.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines(keepends=True)

    offset = max(0, inp.get("offset", 1) - 1)
    limit = inp.get("limit", len(lines))
    selected = lines[offset : offset + limit]

    numbered = [f"{i:>6}\t{line}" for i, line in enumerate(selected, start=offset + 1)]
    result = "".join(numbered)

    if len(result) > 50000:
        result = result[:50000] + "\n... (truncated)"

    return {"output": result or "(empty file)"}


async def _exec_write_file(inp: dict, wd: Path) -> dict:
    fp = sanitize_path(inp["file_path"], wd)
    content = inp["content"]
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    lc = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return {"output": f"Wrote {len(content)} bytes ({lc} lines) to {inp['file_path']}"}


async def _exec_edit_file(inp: dict, wd: Path) -> dict:
    fp = sanitize_path(inp["file_path"], wd)
    if not fp.exists():
        return {"error": f"File not found: {inp['file_path']}"}

    content = fp.read_text(encoding="utf-8", errors="replace")
    old = inp["old_string"]
    new = inp["new_string"]

    if old == "":
        new_content = new + content
    else:
        count = content.count(old)
        if count == 0:
            return {"error": f"old_string not found in {inp['file_path']}"}
        if count > 1:
            return {"error": f"old_string found {count} times -- must be unique. Add more context."}
        new_content = content.replace(old, new, 1)

    fp.write_text(new_content, encoding="utf-8")
    return {"output": f"Edited {inp['file_path']}: replaced {old.count(chr(10))+1} line(s) with {new.count(chr(10))+1} line(s)"}


async def _exec_list_files(inp: dict, wd: Path) -> dict:
    pattern = inp.get("pattern", "**/*")
    max_r = min(inp.get("max_results", 200), 1000)

    matches = []
    for p in wd.glob(pattern):
        if p.is_file():
            rel = p.relative_to(wd)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            matches.append(str(rel))
            if len(matches) >= max_r:
                break

    matches.sort()
    return {"output": "\n".join(matches) or "(no files matched)"}


async def _exec_search_files(inp: dict, wd: Path) -> dict:
    try:
        pattern = re.compile(inp["pattern"], re.IGNORECASE)
    except re.error as e:
        return {"error": f"Invalid regex: {e}"}

    file_glob = inp.get("file_glob", "**/*")
    max_r = min(inp.get("max_results", 50), 200)
    results = []

    for fp in wd.glob(file_glob):
        if not fp.is_file():
            continue
        rel_parts = fp.relative_to(wd).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                results.append(f"{fp.relative_to(wd)}:{i}: {line.rstrip()}")
                if len(results) >= max_r:
                    break
        if len(results) >= max_r:
            break

    output = "\n".join(results)
    if len(results) >= max_r:
        output += f"\n\n... (limited to {max_r} results)"
    return {"output": output or "(no matches found)"}
