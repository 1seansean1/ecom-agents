"""Structured Safety Argument implementation.

Implements Goal Structuring Notation (GSN) and ISO 42010 safety case concepts
for Holly Grace safety assurance. Provides dataclasses and graph structures for
building, validating, and exporting safety arguments.

References:
  - ISO/IEC 42010:2011 (Architecture description)
  - Goal Structuring Notation (GSN) by Tim Kelly
  - Holly Grace Goal Hierarchy §2.0–2.4 (L0–L4 Celestial constraints)
"""

from __future__ import annotations

import dataclasses
import enum
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable
from collections import defaultdict


class SILLevel(enum.Enum):
    """Safety Integrity Level per IEC 61508."""

    SIL0 = 0
    SIL1 = 1
    SIL2 = 2
    SIL3 = 3
    SIL4 = 4


class VerificationMethod(enum.Enum):
    """Verification method for safety evidence."""

    TESTING = "testing"
    ANALYSIS = "analysis"
    INSPECTION = "inspection"
    DEMONSTRATION = "demonstration"
    REVIEW = "review"
    FORMAL_PROOF = "formal_proof"


class ClaimStatus(enum.Enum):
    """Status of a safety claim."""

    PROVEN = "proven"
    ASSUMED = "assumed"
    PENDING = "pending"
    UNPROVEN = "unproven"


@dataclasses.dataclass(slots=True)
class SafetyGoal:
    """Top-level safety goal in the argument structure.

    Attributes:
        goal_id: Unique identifier (e.g., 'G1', 'G-celestial-001')
        description: Human-readable goal statement
        rationale: Why this goal is necessary for system safety
        sil_level: Required Safety Integrity Level
        context: Additional constraints or context
    """

    goal_id: str
    description: str
    rationale: str
    sil_level: SILLevel
    context: str = ""
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Validate goal data."""
        if not self.goal_id or not self.description or not self.rationale:
            raise ValueError(
                f"SafetyGoal {self.goal_id}: description and rationale required"
            )


@dataclasses.dataclass(slots=True)
class SafetyStrategy:
    """Strategy for achieving a safety goal.

    Attributes:
        strategy_id: Unique identifier (e.g., 'S1', 'S-verification')
        description: How this strategy contributes to the goal
        context: Additional constraints or assumptions
        parent_goal_id: Reference to parent goal
    """

    strategy_id: str
    description: str
    parent_goal_id: str
    context: str = ""
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Validate strategy data."""
        if not self.strategy_id or not self.description or not self.parent_goal_id:
            raise ValueError(
                f"SafetyStrategy {self.strategy_id}: description and parent_goal_id required"
            )


@dataclasses.dataclass(slots=True)
class SafetyEvidence:
    """Evidence supporting a safety claim.

    Attributes:
        evidence_id: Unique identifier (e.g., 'E1', 'E-test-001')
        artifact_ref: Reference to test, analysis, or documentation
        verification_method: How evidence was obtained
        status: Current status of evidence
        description: What this evidence demonstrates
    """

    evidence_id: str
    artifact_ref: str
    verification_method: VerificationMethod
    description: str = ""
    status: str = "available"
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Validate evidence data."""
        if not self.evidence_id or not self.artifact_ref:
            raise ValueError(
                f"SafetyEvidence {self.evidence_id}: artifact_ref required"
            )


@dataclasses.dataclass(slots=True)
class SafetyClaim:
    """Claim in the safety argument linking goals to evidence.

    Attributes:
        claim_id: Unique identifier (e.g., 'C1', 'C-main-001')
        description: Claim statement
        goal_ref: Reference to parent goal
        evidence_refs: List of evidence IDs supporting this claim
        status: Proven, assumed, or pending
        rationale: Why evidence supports the claim
    """

    claim_id: str
    description: str
    goal_ref: str
    evidence_refs: list[str] = dataclasses.field(default_factory=list)
    status: ClaimStatus = ClaimStatus.PENDING
    rationale: str = ""
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """Validate claim data."""
        if not self.claim_id or not self.description or not self.goal_ref:
            raise ValueError(
                f"SafetyClaim {self.claim_id}: description and goal_ref required"
            )

    def set_proven(self, rationale: str = "") -> None:
        """Mark claim as proven with optional rationale."""
        self.status = ClaimStatus.PROVEN
        if rationale:
            self.rationale = rationale

    def set_assumed(self, rationale: str = "") -> None:
        """Mark claim as assumed with rationale."""
        self.status = ClaimStatus.ASSUMED
        if rationale:
            self.rationale = rationale


@runtime_checkable
class SafetyArgumentNode(Protocol):
    """Protocol for safety argument nodes (Goal/Strategy/Evidence/Claim)."""

    @property
    def node_id(self) -> str:
        """Unique identifier for this node."""
        ...


@dataclasses.dataclass(slots=True)
class SafetyArgumentGraph:
    """Directed acyclic graph of safety case structure.

    Implements ISO 42010 architecture with nodes (goals, strategies, evidence)
    and edges (traceability links).

    Attributes:
        goals: Dictionary mapping goal_id → SafetyGoal
        strategies: Dictionary mapping strategy_id → SafetyStrategy
        evidence: Dictionary mapping evidence_id → SafetyEvidence
        claims: Dictionary mapping claim_id → SafetyClaim
        edges: Dictionary of edges (parent_id → [child_ids])
    """

    goals: dict[str, SafetyGoal] = dataclasses.field(default_factory=dict)
    strategies: dict[str, SafetyStrategy] = dataclasses.field(default_factory=dict)
    evidence: dict[str, SafetyEvidence] = dataclasses.field(default_factory=dict)
    claims: dict[str, SafetyClaim] = dataclasses.field(default_factory=dict)
    edges: dict[str, list[str]] = dataclasses.field(default_factory=lambda: defaultdict(list))
    created_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add_goal(self, goal: SafetyGoal) -> None:
        """Add a goal to the argument graph."""
        if goal.goal_id in self.goals:
            raise ValueError(f"Duplicate goal ID: {goal.goal_id}")
        self.goals[goal.goal_id] = goal

    def add_strategy(self, strategy: SafetyStrategy) -> None:
        """Add a strategy to the argument graph."""
        if strategy.strategy_id in self.strategies:
            raise ValueError(f"Duplicate strategy ID: {strategy.strategy_id}")
        if strategy.parent_goal_id not in self.goals:
            raise ValueError(f"Parent goal {strategy.parent_goal_id} not found")
        self.strategies[strategy.strategy_id] = strategy
        self.edges[strategy.parent_goal_id].append(strategy.strategy_id)

    def add_evidence(self, evidence: SafetyEvidence) -> None:
        """Add evidence to the argument graph."""
        if evidence.evidence_id in self.evidence:
            raise ValueError(f"Duplicate evidence ID: {evidence.evidence_id}")
        self.evidence[evidence.evidence_id] = evidence

    def add_claim(self, claim: SafetyClaim) -> None:
        """Add a claim to the argument graph."""
        if claim.claim_id in self.claims:
            raise ValueError(f"Duplicate claim ID: {claim.claim_id}")
        if claim.goal_ref not in self.goals:
            raise ValueError(f"Goal {claim.goal_ref} not found")
        for evid_id in claim.evidence_refs:
            if evid_id not in self.evidence:
                raise ValueError(f"Evidence {evid_id} not found")
        self.claims[claim.claim_id] = claim
        self.edges[claim.goal_ref].append(claim.claim_id)

    def link_claim_to_strategy(self, claim_id: str, strategy_id: str) -> None:
        """Link a claim to a strategy in the graph."""
        if claim_id not in self.claims:
            raise ValueError(f"Claim {claim_id} not found")
        if strategy_id not in self.strategies:
            raise ValueError(f"Strategy {strategy_id} not found")
        self.edges[strategy_id].append(claim_id)

    def get_goal_descendants(self, goal_id: str) -> set[str]:
        """Get all descendants of a goal (strategies, claims, evidence)."""
        if goal_id not in self.goals:
            raise ValueError(f"Goal {goal_id} not found")
        descendants = set()
        visited = set()

        def traverse(node_id: str) -> None:
            if node_id in visited:
                return
            visited.add(node_id)
            if node_id in self.edges:
                for child_id in self.edges[node_id]:
                    descendants.add(child_id)
                    traverse(child_id)

        traverse(goal_id)
        return descendants

    def has_cycle(self) -> bool:
        """Check if graph contains cycles (should be DAG)."""
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for child_id in self.edges.get(node_id, []):
                if child_id not in visited:
                    if dfs(child_id):
                        return True
                elif child_id in rec_stack:
                    return True
            rec_stack.remove(node_id)
            return False

        all_nodes = set(self.goals.keys()) | set(self.strategies.keys()) | set(self.claims.keys())
        for node_id in all_nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return True
        return False

    def node_count(self) -> int:
        """Return total number of nodes."""
        return len(self.goals) + len(self.strategies) + len(self.claims) + len(self.evidence)

    def edge_count(self) -> int:
        """Return total number of edges."""
        return sum(len(children) for children in self.edges.values())


def build_safety_argument(
    goals: list[SafetyGoal],
    strategies: list[SafetyStrategy],
    claims: list[SafetyClaim],
    evidence: list[SafetyEvidence],
) -> SafetyArgumentGraph:
    """Construct complete Holly Grace safety argument.

    Args:
        goals: List of safety goals
        strategies: List of safety strategies
        claims: List of safety claims
        evidence: List of safety evidence

    Returns:
        Fully constructed SafetyArgumentGraph

    Raises:
        ValueError: If graph contains cycles or references are invalid
    """
    graph = SafetyArgumentGraph()

    # Add goals first
    for goal in goals:
        graph.add_goal(goal)

    # Add evidence
    for evid in evidence:
        graph.add_evidence(evid)

    # Add strategies
    for strategy in strategies:
        graph.add_strategy(strategy)

    # Add claims
    for claim in claims:
        graph.add_claim(claim)

    # Verify DAG property
    if graph.has_cycle():
        raise ValueError("Safety argument graph contains cycles")

    return graph


def validate_argument_completeness(graph: SafetyArgumentGraph) -> dict[str, list[str]]:
    """Validate that all goals have proven claims and evidence.

    Returns:
        Dictionary with keys:
          - 'unproven_claims': List of claim IDs with status != PROVEN
          - 'goals_without_claims': List of goal IDs with no claims
          - 'claims_without_evidence': List of claim IDs with empty evidence_refs
          - 'valid': Boolean indicating if all checks pass

    Example:
        >>> result = validate_argument_completeness(graph)
        >>> if result['valid']:
        ...     print("Argument is complete and proven")
    """
    gaps = {
        "unproven_claims": [],
        "goals_without_claims": [],
        "claims_without_evidence": [],
        "valid": True,
    }

    # Check for unproven claims
    for claim_id, claim in graph.claims.items():
        if claim.status != ClaimStatus.PROVEN:
            gaps["unproven_claims"].append(claim_id)

    # Check for claims without evidence
    for claim_id, claim in graph.claims.items():
        if not claim.evidence_refs:
            gaps["claims_without_evidence"].append(claim_id)

    # Check for goals without claims
    claimed_goals = {claim.goal_ref for claim in graph.claims.values()}
    for goal_id in graph.goals.keys():
        if goal_id not in claimed_goals:
            gaps["goals_without_claims"].append(goal_id)

    gaps["valid"] = (
        len(gaps["unproven_claims"]) == 0
        and len(gaps["goals_without_claims"]) == 0
        and len(gaps["claims_without_evidence"]) == 0
    )

    return gaps


def export_argument_gsn(graph: SafetyArgumentGraph) -> str:
    """Export safety argument in Goal Structuring Notation (GSN) format.

    Returns a human-readable GSN representation suitable for documentation
    and review.

    Args:
        graph: SafetyArgumentGraph to export

    Returns:
        GSN text representation
    """
    lines = ["# Holly Grace Safety Argument (GSN Format)\n"]
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    lines.append(f"Nodes: {graph.node_count()} | Edges: {graph.edge_count()}\n")
    lines.append("=" * 70 + "\n")

    # Goals section
    lines.append("\n## Goals (L0 - Celestial Constraints)\n")
    for goal_id, goal in sorted(graph.goals.items()):
        lines.append(f"\nG [{goal_id}]\n")
        lines.append(f"  Description: {goal.description}\n")
        lines.append(f"  Rationale: {goal.rationale}\n")
        lines.append(f"  SIL: {goal.sil_level.name}\n")
        if goal.context:
            lines.append(f"  Context: {goal.context}\n")

    # Strategies section
    lines.append("\n## Strategies\n")
    for strategy_id, strategy in sorted(graph.strategies.items()):
        lines.append(f"\nS [{strategy_id}]\n")
        lines.append(f"  Description: {strategy.description}\n")
        lines.append(f"  Parent: {strategy.parent_goal_id}\n")
        if strategy.context:
            lines.append(f"  Context: {strategy.context}\n")

    # Claims section
    lines.append("\n## Claims\n")
    for claim_id, claim in sorted(graph.claims.items()):
        lines.append(f"\nC [{claim_id}]\n")
        lines.append(f"  Description: {claim.description}\n")
        lines.append(f"  Goal: {claim.goal_ref}\n")
        lines.append(f"  Status: {claim.status.value}\n")
        if claim.evidence_refs:
            lines.append(f"  Evidence: {', '.join(claim.evidence_refs)}\n")
        if claim.rationale:
            lines.append(f"  Rationale: {claim.rationale}\n")

    # Evidence section
    lines.append("\n## Evidence\n")
    for evidence_id, evidence in sorted(graph.evidence.items()):
        lines.append(f"\nE [{evidence_id}]\n")
        lines.append(f"  Description: {evidence.description}\n")
        lines.append(f"  Artifact: {evidence.artifact_ref}\n")
        lines.append(f"  Method: {evidence.verification_method.value}\n")
        lines.append(f"  Status: {evidence.status}\n")

    # Completeness check
    lines.append("\n## Completeness Check\n")
    gaps = validate_argument_completeness(graph)
    lines.append(f"Valid: {gaps['valid']}\n")
    if not gaps["valid"]:
        if gaps["unproven_claims"]:
            lines.append(
                f"Unproven Claims: {', '.join(gaps['unproven_claims'])}\n"
            )
        if gaps["goals_without_claims"]:
            lines.append(
                f"Goals Without Claims: {', '.join(gaps['goals_without_claims'])}\n"
            )
        if gaps["claims_without_evidence"]:
            lines.append(
                f"Claims Without Evidence: {', '.join(gaps['claims_without_evidence'])}\n"
            )

    return "".join(lines)


def export_argument_json(graph: SafetyArgumentGraph) -> str:
    """Export safety argument in JSON format for machine processing.

    Args:
        graph: SafetyArgumentGraph to export

    Returns:
        JSON string representation
    """
    data = {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "node_count": graph.node_count(),
            "edge_count": graph.edge_count(),
            "has_cycle": graph.has_cycle(),
        },
        "goals": {
            goal_id: {
                "description": goal.description,
                "rationale": goal.rationale,
                "sil_level": goal.sil_level.name,
                "context": goal.context,
            }
            for goal_id, goal in graph.goals.items()
        },
        "strategies": {
            strategy_id: {
                "description": strategy.description,
                "parent_goal_id": strategy.parent_goal_id,
                "context": strategy.context,
            }
            for strategy_id, strategy in graph.strategies.items()
        },
        "claims": {
            claim_id: {
                "description": claim.description,
                "goal_ref": claim.goal_ref,
                "status": claim.status.value,
                "evidence_refs": claim.evidence_refs,
                "rationale": claim.rationale,
            }
            for claim_id, claim in graph.claims.items()
        },
        "evidence": {
            evidence_id: {
                "description": evidence.description,
                "artifact_ref": evidence.artifact_ref,
                "verification_method": evidence.verification_method.value,
                "status": evidence.status,
            }
            for evidence_id, evidence in graph.evidence.items()
        },
    }
    return json.dumps(data, indent=2)
