"""Thread-safe singleton registry for architecture.yaml.

Task 2.6 — Implement singleton loader.

The ``ArchitectureRegistry`` is the single Python entry-point for
querying the machine-readable SAD.  It lazily loads and validates
``architecture.yaml`` on first access, is safe under concurrent
thread access (``threading.Lock``), and exposes the full
``ArchitectureDocument`` model for downstream consumers (decorators,
drift detection, traceability matrix).

Design decisions (per Task 2.3 ADR scope):
- **Singleton via class-level lock** rather than module-level global:
  avoids import-time side effects; allows explicit ``reset()`` for
  testing and hot-reload (Task 2.8).
- **Lazy init**: YAML is not read until the first query, so importing
  the module has zero I/O cost.
- **Thread-safety**: a single ``threading.Lock`` guards the load path;
  once loaded, reads are lock-free (the reference swap is atomic in
  CPython, and we use a snapshot pattern for correctness on other
  runtimes).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar

import yaml

from holly.arch.schema import ArchitectureDocument


class RegistryNotLoadedError(RuntimeError):
    """Raised when the registry is accessed before any YAML is available."""


class RegistryValidationError(ValueError):
    """Raised when architecture.yaml fails Pydantic validation."""


class ArchitectureRegistry:
    """Thread-safe singleton accessor for architecture.yaml.

    Usage::

        reg = ArchitectureRegistry.get()      # lazy-loads on first call
        doc = reg.document                     # ArchitectureDocument
        comp = doc.components["KERNEL"]        # Component lookup

    The default YAML path is ``docs/architecture.yaml`` relative to the
    repo root.  Override via ``ArchitectureRegistry.configure(path)``.
    """

    # ── class-level singleton state ──────────────────────
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _instance: ClassVar[ArchitectureRegistry | None] = None
    _yaml_path: ClassVar[Path | None] = None

    # ── instance state ───────────────────────────────────
    __slots__ = ("_document",)

    def __init__(self, document: ArchitectureDocument) -> None:
        self._document = document

    # ── public API ───────────────────────────────────────

    @classmethod
    def configure(cls, yaml_path: Path | str) -> None:
        """Set the YAML path before first access.

        Can also be called to point at a different file before a
        subsequent ``reset()`` + ``get()`` cycle.
        """
        cls._yaml_path = Path(yaml_path)

    @classmethod
    def get(cls) -> ArchitectureRegistry:
        """Return the singleton, loading on first call.

        Thread-safe: concurrent callers block on the lock; only one
        performs the actual load.

        Raises
        ------
        FileNotFoundError
            If the YAML path does not exist.
        RegistryValidationError
            If the YAML fails Pydantic schema validation.
        """
        # Fast path — already initialised (lock-free read).
        inst = cls._instance
        if inst is not None:
            return inst

        with cls._lock:
            # Double-checked locking.
            if cls._instance is not None:
                return cls._instance

            path = cls._resolve_path()
            doc = cls._load(path)
            cls._instance = cls(doc)
            return cls._instance

    @classmethod
    def is_loaded(cls) -> bool:
        """Return ``True`` if the singleton has been initialised."""
        return cls._instance is not None

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton (for testing / hot-reload)."""
        with cls._lock:
            cls._instance = None

    @property
    def document(self) -> ArchitectureDocument:
        """The validated ``ArchitectureDocument``."""
        return self._document

    @property
    def path(self) -> Path:
        """Resolved path of the loaded YAML."""
        return self._resolve_path()

    # ── internal helpers ─────────────────────────────────

    @classmethod
    def _resolve_path(cls) -> Path:
        """Determine YAML path: explicit config > repo-root heuristic."""
        if cls._yaml_path is not None:
            return cls._yaml_path

        # Walk up from CWD to find repo root (docs/ + holly/).
        p = Path.cwd()
        for _ in range(10):
            candidate = p / "docs" / "architecture.yaml"
            if candidate.exists():
                return candidate
            if p.parent == p:
                break
            p = p.parent

        # Fallback: relative to CWD.
        return Path("docs") / "architecture.yaml"

    @classmethod
    def _load(cls, path: Path) -> ArchitectureDocument:
        """Read YAML and validate against Pydantic schema.

        Raises
        ------
        FileNotFoundError
            If *path* does not exist.
        RegistryValidationError
            If the YAML payload fails schema validation.
        """
        if not path.exists():
            msg = f"architecture.yaml not found: {path}"
            raise FileNotFoundError(msg)

        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        if not isinstance(data, dict):
            msg = f"Expected YAML mapping at top level, got {type(data).__name__}"
            raise RegistryValidationError(msg)

        try:
            doc = ArchitectureDocument.model_validate(data)
        except Exception as exc:
            msg = f"architecture.yaml validation failed: {exc}"
            raise RegistryValidationError(msg) from exc

        return doc
