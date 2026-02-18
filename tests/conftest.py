"""Shared fixtures for Holly Grace test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def repo_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture()
def sad_path(repo_root: Path) -> Path:
    """Return path to the current SAD mermaid file."""
    return repo_root / "docs" / "architecture" / "SAD_0.1.0.5.mermaid"


@pytest.fixture()
def rtd_path(repo_root: Path) -> Path:
    """Return path to the current RTD mermaid file."""
    return repo_root / "docs" / "architecture" / "RTD_0.1.0.4.mermaid"
