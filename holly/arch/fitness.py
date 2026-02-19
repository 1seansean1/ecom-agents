"""Architecture fitness functions — executable per-commit checks.

Task 9.2 — Implement fitness functions.

Three continuous checks enforced on every commit:

1. **Layer violations** — detect imports that cross forbidden layer
   boundaries (e.g. L4 importing from L3).
2. **Coupling metrics** — measure afferent (fan-in) and efferent
   (fan-out) coupling per module with configurable thresholds.
3. **Dependency depth** — measure the longest import chain from any
   module to its deepest transitive dependency.

Each function returns a typed result with pass/fail status *and* a
numeric measurement for observability dashboards.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from holly.arch.schema import LayerID

# ═══════════════════════════════════════════════════════════
# Layer ordering — defines allowed import directions
# ═══════════════════════════════════════════════════════════

# Numeric rank per layer.  Higher ranks MAY import from lower ranks.
# Equal ranks MAY import from each other.
# Lower ranks MUST NOT import from higher ranks.
LAYER_RANK: dict[str, int] = {
    LayerID.L1_KERNEL: 1,
    LayerID.L2_CORE: 2,
    LayerID.L3_ENGINE: 3,
    LayerID.L4_OBSERVABILITY: 4,
    LayerID.L5_CONSOLE: 5,
    LayerID.DATA: 0,       # Data layer is utility — importable by all.
    LayerID.INFRA: 0,      # Infra is utility — importable by all.
    LayerID.SANDBOX: 0,    # Sandbox is isolated — importable by all.
    LayerID.EXTERNAL: 0,   # External is utility — importable by all.
    LayerID.L0_VPC: 0,     # VPC is infrastructure — importable by all.
}

# Layer ordering constraint: source layer rank MUST be >= imported
# layer rank.  Exception: utility layers (rank 0) may be imported
# by anyone but may NOT import non-utility layers.

# Module prefix → LayerID mapping.
MODULE_LAYER_MAP: dict[str, LayerID] = {
    "holly.kernel": LayerID.L1_KERNEL,
    "holly.core": LayerID.L2_CORE,
    "holly.engine": LayerID.L3_ENGINE,
    "holly.observability": LayerID.L4_OBSERVABILITY,
    "holly.storage": LayerID.DATA,
    "holly.infra": LayerID.INFRA,
    "holly.arch": LayerID.INFRA,  # arch tooling — utility.
}

# Allowed cross-layer import exceptions (pairs that are architecturally
# sanctioned despite rank ordering).
ALLOWED_CROSS_LAYER: set[tuple[str, str]] = {
    # Kernel may import arch for registry access during decorator validation.
    ("holly.kernel", "holly.arch"),
    # Arch tooling may introspect any layer.
    ("holly.arch", "holly.kernel"),
    ("holly.arch", "holly.core"),
    ("holly.arch", "holly.engine"),
    ("holly.arch", "holly.observability"),
}


# ═══════════════════════════════════════════════════════════
# Result types
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class LayerViolation:
    """A single forbidden import."""

    source_module: str
    source_layer: str
    imported_module: str
    imported_layer: str
    source_file: str
    line: int


@dataclass(frozen=True, slots=True)
class FitnessResult:
    """Result of a single fitness function check."""

    name: str
    passed: bool
    measurement: float
    details: list[Any] = field(default_factory=list)
    threshold: float = 0.0
    unit: str = ""

    @property
    def status(self) -> str:
        """Return ``'PASS'`` or ``'FAIL'``."""
        return "PASS" if self.passed else "FAIL"


@dataclass(frozen=True, slots=True)
class CouplingEntry:
    """Coupling metrics for a single module."""

    module: str
    afferent: int   # fan-in: how many modules import this one.
    efferent: int   # fan-out: how many modules this one imports.

    @property
    def instability(self) -> float:
        """Martin instability metric: Ce / (Ca + Ce)."""
        total = self.afferent + self.efferent
        return self.efferent / total if total > 0 else 0.0


# ═══════════════════════════════════════════════════════════
# Import graph construction
# ═══════════════════════════════════════════════════════════


def _resolve_layer(module_path: str) -> LayerID | None:
    """Resolve a dotted module path to its LayerID.

    Returns ``None`` if the module is not in the Holly namespace or
    has no defined layer mapping.
    """
    for prefix, layer in sorted(
        MODULE_LAYER_MAP.items(), key=lambda kv: -len(kv[0]),
    ):
        if module_path.startswith(prefix):
            return layer
    return None


def _extract_imports(source: str) -> list[tuple[str, int]]:
    """Extract top-level import module names from Python source.

    Returns ``(module_name, line_number)`` tuples.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.module, node.lineno))
    return imports


def build_import_graph(
    root: Path,
    *,
    package: str = "holly",
) -> dict[str, list[str]]:
    """Build a directed import graph from the source tree.

    Returns a dict mapping ``module_path`` → list of imported
    ``module_path`` names (Holly-internal only).
    """
    graph: dict[str, list[str]] = {}
    src_root = root / package.replace(".", os.sep)

    if not src_root.exists():
        return graph

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_path = ".".join(parts)

        source = py_file.read_text(encoding="utf-8", errors="replace")
        raw_imports = _extract_imports(source)

        holly_imports: list[str] = []
        for imp_name, _line in raw_imports:
            if imp_name.startswith(f"{package}."):
                holly_imports.append(imp_name)
        graph[module_path] = holly_imports

    return graph


def build_import_graph_with_lines(
    root: Path,
    *,
    package: str = "holly",
) -> dict[str, list[tuple[str, int]]]:
    """Like ``build_import_graph`` but retains line numbers."""
    graph: dict[str, list[tuple[str, int]]] = {}
    src_root = root / package.replace(".", os.sep)

    if not src_root.exists():
        return graph

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_path = ".".join(parts)

        source = py_file.read_text(encoding="utf-8", errors="replace")
        raw_imports = _extract_imports(source)

        holly_imports: list[tuple[str, int]] = []
        for imp_name, line in raw_imports:
            if imp_name.startswith(f"{package}."):
                holly_imports.append((imp_name, line))
        graph[module_path] = holly_imports

    return graph


# ═══════════════════════════════════════════════════════════
# Fitness function 1: Layer violations
# ═══════════════════════════════════════════════════════════


def check_layer_violations(
    root: Path,
    *,
    package: str = "holly",
) -> FitnessResult:
    """Detect imports that cross forbidden layer boundaries.

    A **violation** occurs when a module in layer A imports a module
    in layer B and ``LAYER_RANK[A] < LAYER_RANK[B]`` (i.e. a lower
    layer imports from a higher layer).

    Parameters
    ----------
    root:
        Repository root directory.
    package:
        Top-level Python package name.

    Returns
    -------
    FitnessResult:
        ``passed=True`` if zero violations found.
        ``measurement`` = violation count.
    """
    graph = build_import_graph_with_lines(root, package=package)
    violations: list[LayerViolation] = []

    for module_path, imports in graph.items():
        src_layer = _resolve_layer(module_path)
        if src_layer is None:
            continue
        src_rank = LAYER_RANK.get(src_layer, 0)

        for imp_name, line in imports:
            imp_layer = _resolve_layer(imp_name)
            if imp_layer is None:
                continue
            imp_rank = LAYER_RANK.get(imp_layer, 0)

            # Skip same-layer imports.
            if src_layer == imp_layer:
                continue

            # Skip utility layers (rank 0).
            if src_rank == 0 or imp_rank == 0:
                continue

            # Check allowed exceptions.
            src_prefix = _module_prefix(module_path)
            imp_prefix = _module_prefix(imp_name)
            if (src_prefix, imp_prefix) in ALLOWED_CROSS_LAYER:
                continue

            # Violation: lower rank importing higher rank.
            if src_rank < imp_rank:
                violations.append(LayerViolation(
                    source_module=module_path,
                    source_layer=src_layer,
                    imported_module=imp_name,
                    imported_layer=imp_layer,
                    source_file=module_path.replace(".", os.sep) + ".py",
                    line=line,
                ))

    return FitnessResult(
        name="layer_violations",
        passed=len(violations) == 0,
        measurement=float(len(violations)),
        details=violations,
        threshold=0.0,
        unit="violations",
    )


def _module_prefix(module_path: str) -> str:
    """Extract two-level prefix: ``'holly.kernel.k1'`` → ``'holly.kernel'``."""
    parts = module_path.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else module_path


# ═══════════════════════════════════════════════════════════
# Fitness function 2: Coupling metrics
# ═══════════════════════════════════════════════════════════


def check_coupling(
    root: Path,
    *,
    package: str = "holly",
    max_efferent: int = 15,
    max_afferent: int = 20,
) -> FitnessResult:
    """Measure afferent and efferent coupling per module.

    Parameters
    ----------
    root:
        Repository root directory.
    package:
        Top-level Python package name.
    max_efferent:
        Maximum allowed outgoing imports per module.
    max_afferent:
        Maximum allowed incoming imports per module.

    Returns
    -------
    FitnessResult:
        ``passed=True`` if no module exceeds thresholds.
        ``measurement`` = number of modules exceeding threshold.
    """
    graph = build_import_graph(root, package=package)

    # Compute efferent (fan-out) per module.
    efferent: dict[str, int] = {}
    for module_path, imports in graph.items():
        efferent[module_path] = len(imports)

    # Compute afferent (fan-in) per module.
    afferent: dict[str, int] = {m: 0 for m in graph}
    for _module_path, imports in graph.items():
        for imp in imports:
            # Resolve to the closest actual module in the graph.
            resolved = _resolve_to_graph(imp, graph)
            if resolved:
                afferent[resolved] = afferent.get(resolved, 0) + 1

    # Build entries and check thresholds.
    entries: list[CouplingEntry] = []
    violations = 0
    for module_path in sorted(graph.keys()):
        entry = CouplingEntry(
            module=module_path,
            afferent=afferent.get(module_path, 0),
            efferent=efferent.get(module_path, 0),
        )
        entries.append(entry)
        if entry.efferent > max_efferent or entry.afferent > max_afferent:
            violations += 1

    return FitnessResult(
        name="coupling_metrics",
        passed=violations == 0,
        measurement=float(violations),
        details=entries,
        threshold=0.0,
        unit="modules_exceeding_threshold",
    )


def _resolve_to_graph(
    import_path: str,
    graph: dict[str, list[str]],
) -> str | None:
    """Resolve an import path to the nearest module in the graph.

    Tries exact match first, then walks up to parent packages.
    """
    candidate = import_path
    while candidate:
        if candidate in graph:
            return candidate
        parts = candidate.rsplit(".", 1)
        candidate = parts[0] if len(parts) > 1 else ""
    return None


# ═══════════════════════════════════════════════════════════
# Fitness function 3: Dependency depth
# ═══════════════════════════════════════════════════════════


def check_dependency_depth(
    root: Path,
    *,
    package: str = "holly",
    max_depth: int = 8,
) -> FitnessResult:
    """Measure the longest import chain in the codebase.

    Uses DFS with cycle detection to find the longest acyclic path
    through the import graph.

    Parameters
    ----------
    root:
        Repository root directory.
    package:
        Top-level Python package name.
    max_depth:
        Maximum allowed chain length.

    Returns
    -------
    FitnessResult:
        ``passed=True`` if max depth ≤ ``max_depth``.
        ``measurement`` = longest chain length found.
    """
    graph = build_import_graph(root, package=package)

    max_found = 0
    longest_chain: list[str] = []

    # Memoized DFS: depth_cache[module] = (depth, chain).
    depth_cache: dict[str, tuple[int, list[str]]] = {}

    def _dfs(module: str, visited: set[str]) -> tuple[int, list[str]]:
        if module in depth_cache:
            return depth_cache[module]
        if module not in graph or module in visited:
            return (0, [module])

        visited.add(module)
        best_depth = 0
        best_chain: list[str] = [module]

        for imp in graph[module]:
            resolved = _resolve_to_graph(imp, graph)
            if resolved and resolved not in visited:
                child_depth, child_chain = _dfs(resolved, visited)
                if child_depth + 1 > best_depth:
                    best_depth = child_depth + 1
                    best_chain = [module, *child_chain]

        visited.discard(module)
        depth_cache[module] = (best_depth, best_chain)
        return (best_depth, best_chain)

    for module in graph:
        depth, chain = _dfs(module, set())
        if depth > max_found:
            max_found = depth
            longest_chain = chain

    return FitnessResult(
        name="dependency_depth",
        passed=max_found <= max_depth,
        measurement=float(max_found),
        details=longest_chain,
        threshold=float(max_depth),
        unit="chain_length",
    )


# ═══════════════════════════════════════════════════════════
# Combined runner
# ═══════════════════════════════════════════════════════════


def run_all(
    root: Path,
    *,
    package: str = "holly",
    max_efferent: int = 15,
    max_afferent: int = 20,
    max_depth: int = 8,
) -> list[FitnessResult]:
    """Run all fitness functions and return results.

    Parameters
    ----------
    root:
        Repository root directory.
    package:
        Top-level Python package.
    max_efferent:
        Max outgoing imports per module.
    max_afferent:
        Max incoming imports per module.
    max_depth:
        Max dependency chain length.
    """
    return [
        check_layer_violations(root, package=package),
        check_coupling(
            root,
            package=package,
            max_efferent=max_efferent,
            max_afferent=max_afferent,
        ),
        check_dependency_depth(root, package=package, max_depth=max_depth),
    ]
