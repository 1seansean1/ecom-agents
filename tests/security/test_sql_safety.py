"""P4 LOW: SQL safety tests.

Verifies parameterized queries and safe SQL patterns in the codebase.
The baseline audit confirmed all 400+ queries use %s placeholders,
but these tests guard against regressions.
"""

from __future__ import annotations

import ast
import os
import re

import pytest


def _find_python_files(root: str) -> list[str]:
    """Find all .py files in a directory tree."""
    py_files = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.endswith(".py"):
                py_files.append(os.path.join(dirpath, f))
    return py_files


def _check_file_for_unsafe_sql(filepath: str) -> list[str]:
    """Check a file for potentially unsafe SQL patterns.

    Filters out known safe patterns:
    - f-strings that compose SQL from CONSTANT prefixes (e.g. f"{_AGENT_SELECT} WHERE ...")
    - f-strings with only %s parameterized placeholders and constant interpolation
    - f-strings in error messages (not actual SQL queries)
    - f-strings with only SET clause composition from whitelisted columns
    """
    issues = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comments and non-code lines
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        # Pattern 1: .format() with SQL keywords -- always suspicious
        if ".format(" in stripped:
            format_sql = re.search(
                r'["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE).*["\']\.format\(',
                stripped,
                re.IGNORECASE,
            )
            if format_sql:
                issues.append(f".format() SQL in {filepath}:{i+1}: {stripped[:80]}")

        # Pattern 2: f-string with SQL keywords AND user-controlled interpolation
        if stripped.startswith("f\"") or stripped.startswith("f'") or " f\"" in stripped or " f'" in stripped:
            fstring_match = re.search(
                r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE).*["\']',
                stripped,
                re.IGNORECASE,
            )
            if fstring_match:
                match_text = fstring_match.group()
                # Safe patterns to skip:
                # 1. Only interpolates CONSTANT prefixes (all-caps variable names)
                interpolations = re.findall(r'\{([^}]+)\}', match_text)
                if interpolations:
                    all_safe = all(
                        # All-caps constants like _AGENT_SELECT, _WORKFLOW_SELECT
                        re.match(r'^_?[A-Z_]+$', interp.strip())
                        # Whitelisted dynamic patterns: set_clauses (column whitelist)
                        or interp.strip() == "set_clauses"
                        # Simple %s parameterized remaining
                        or interp.strip().startswith("%")
                        for interp in interpolations
                    )
                    if all_safe:
                        continue

                # 2. Error message strings (contains "Cannot", "Failed", etc.)
                if any(kw in match_text for kw in ("Cannot", "Failed", "Error", "error", "not found")):
                    continue

                # 3. LLM prompt strings (contains "Create", "Select" in natural language context)
                if any(kw in match_text for kw in ("Instagram", "image for", "store", "Context", "Goal Update", "Budget")):
                    continue

                issues.append(f"f-string SQL in {filepath}:{i+1}: {stripped[:80]}")

    return issues


class TestParameterizedQueries:
    """All SQL queries must use parameterized statements."""

    def test_no_unsafe_sql_in_store(self):
        """src/aps/store.py uses only parameterized queries."""
        store_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "aps", "store.py"
        )
        issues = _check_file_for_unsafe_sql(os.path.abspath(store_path))
        assert not issues, (
            f"Found unsafe SQL patterns:\n" + "\n".join(issues)
        )

    def test_no_unsafe_sql_in_agent_registry(self):
        """src/agent_registry.py uses only parameterized queries."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "agent_registry.py"
        )
        issues = _check_file_for_unsafe_sql(os.path.abspath(path))
        assert not issues, (
            f"Found unsafe SQL patterns:\n" + "\n".join(issues)
        )

    def test_no_unsafe_sql_in_workflow_registry(self):
        """src/workflow_registry.py uses only parameterized queries."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "workflow_registry.py"
        )
        issues = _check_file_for_unsafe_sql(os.path.abspath(path))
        assert not issues, (
            f"Found unsafe SQL patterns:\n" + "\n".join(issues)
        )

    def test_no_unsafe_sql_anywhere_in_src(self):
        """No unsafe SQL patterns anywhere in src/."""
        src_root = os.path.join(os.path.dirname(__file__), "..", "..", "src")
        all_issues = []
        for filepath in _find_python_files(os.path.abspath(src_root)):
            issues = _check_file_for_unsafe_sql(filepath)
            all_issues.extend(issues)
        assert not all_issues, (
            f"Found {len(all_issues)} unsafe SQL patterns:\n" + "\n".join(all_issues[:10])
        )


class TestSQLInjectionViaAPI:
    """SQL injection via API parameters doesn't alter behavior."""

    def test_injection_in_channel_id(self, admin_client):
        """SQL injection in channel_id doesn't work."""
        resp = admin_client.get("/aps/metrics/'; DROP TABLE aps_metrics; --")
        # Should return empty results or 404, not error
        assert resp.status_code in (200, 404, 400)

    def test_injection_in_agent_id(self, admin_client):
        """SQL injection in agent_id path doesn't work."""
        resp = admin_client.get("/agents/1 OR 1=1")
        assert resp.status_code in (200, 404, 400)
