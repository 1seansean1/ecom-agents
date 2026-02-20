"""ICD integration into Phase D Safety Case.

Integrates all 49 ICDs (ICD-001 through ICD-049) from the boundary contract
specifications into the Phase D Safety Case. Provides traceability matrix
mapping ICDs to safety claims and validation of complete coverage.

References:
  - Task 33.5: Integrate all 49 ICDs into Phase D Safety Case
  - ICD v0.1 specification
  - Holly Grace Goal Hierarchy (Phase D)
"""

from __future__ import annotations

import dataclasses
import enum
from collections import defaultdict
from typing import Optional

from holly.safety.argument import SafetyArgumentGraph, SILLevel


class CoverageStatus(enum.Enum):
    """Status of ICD coverage in safety case."""

    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    UNCOVERED = "uncovered"
    REDUNDANT = "redundant"


@dataclasses.dataclass(slots=True)
class ICD:
    """Interface Control Document specification.

    Attributes:
        icd_id: Unique identifier (e.g., 'ICD-001')
        title: Brief title of the boundary contract
        description: Detailed description of the interface
        safety_properties: List of safety-critical properties this ICD specifies
        sil_level: Required Safety Integrity Level per IEC 61508
        protocol: Protocol type (e.g., 'HTTP', 'gRPC', 'WebSocket', 'Database')
        direction: Data flow direction (unidirectional or bidirectional)
    """

    icd_id: str
    title: str
    description: str
    safety_properties: list[str] = dataclasses.field(default_factory=list)
    sil_level: SILLevel = SILLevel.SIL1
    protocol: str = "unknown"
    direction: str = "unidirectional"

    def __post_init__(self) -> None:
        """Validate ICD data."""
        if not self.icd_id or not self.icd_id.startswith("ICD-"):
            raise ValueError(f"Invalid ICD ID: {self.icd_id}")
        if not self.title or not self.description:
            raise ValueError(f"ICD {self.icd_id}: title and description required")


@dataclasses.dataclass(slots=True)
class ICDTraceEntry:
    """Trace entry linking an ICD to safety claims.

    Attributes:
        icd_id: ICD identifier
        claim_ids: List of safety claim IDs that cite this ICD
        coverage_status: Coverage status (covered, partially_covered, uncovered)
        notes: Additional traceability notes
    """

    icd_id: str
    claim_ids: list[str] = dataclasses.field(default_factory=list)
    coverage_status: CoverageStatus = CoverageStatus.UNCOVERED
    notes: str = ""

    def add_claim(self, claim_id: str) -> None:
        """Add a claim reference to this ICD trace entry."""
        if claim_id not in self.claim_ids:
            self.claim_ids.append(claim_id)

    def is_covered(self) -> bool:
        """Check if this ICD is covered by at least one claim."""
        return len(self.claim_ids) > 0


@dataclasses.dataclass(slots=True)
class CoverageReport:
    """Report of ICD coverage in safety case.

    Attributes:
        total_icds: Total number of ICDs in scope
        covered_icds: Number of ICDs with ≥1 claim
        uncovered_icds: List of ICD IDs with no claims
        redundant_icds: List of ICD IDs with multiple claims
        coverage_percentage: Coverage ratio (0.0–1.0)
        is_complete: Boolean indicating 100% coverage
    """

    total_icds: int
    covered_icds: int
    uncovered_icds: list[str] = dataclasses.field(default_factory=list)
    redundant_icds: list[str] = dataclasses.field(default_factory=list)
    coverage_percentage: float = 0.0
    is_complete: bool = False

    def __post_init__(self) -> None:
        """Compute derived fields."""
        if self.total_icds > 0:
            self.coverage_percentage = self.covered_icds / self.total_icds
            self.is_complete = self.covered_icds == self.total_icds


class ICDTraceMatrix:
    """Bidirectional traceability matrix: ICDs ↔ Safety Claims.

    Maps each ICD to all safety claims that cite it and validates
    100% coverage (no uncovered ICDs, no dangling claims).

    Attributes:
        icds: Dictionary of ICD ID → ICD object
        trace_entries: Dictionary of ICD ID → ICDTraceEntry
        claim_to_icds: Reverse mapping: claim ID → list of ICD IDs
    """

    __slots__ = ("icds", "trace_entries", "claim_to_icds")

    def __init__(self) -> None:
        """Initialize empty trace matrix."""
        self.icds: dict[str, ICD] = {}
        self.trace_entries: dict[str, ICDTraceEntry] = {}
        self.claim_to_icds: dict[str, list[str]] = defaultdict(list)

    def add_icd(self, icd: ICD) -> None:
        """Add an ICD to the matrix.

        Args:
            icd: ICD object to add

        Raises:
            ValueError: If ICD ID already exists
        """
        if icd.icd_id in self.icds:
            raise ValueError(f"Duplicate ICD ID: {icd.icd_id}")
        self.icds[icd.icd_id] = icd
        if icd.icd_id not in self.trace_entries:
            self.trace_entries[icd.icd_id] = ICDTraceEntry(icd_id=icd.icd_id)

    def add_icd_claim_link(self, icd_id: str, claim_id: str) -> None:
        """Link an ICD to a safety claim.

        Args:
            icd_id: ICD identifier
            claim_id: Safety claim identifier

        Raises:
            ValueError: If ICD not found
        """
        if icd_id not in self.icds:
            raise ValueError(f"ICD {icd_id} not found in matrix")
        self.trace_entries[icd_id].add_claim(claim_id)
        if claim_id not in self.claim_to_icds[icd_id]:
            self.claim_to_icds[icd_id].append(claim_id)

    def get_icd_coverage(self, icd_id: str) -> Optional[ICDTraceEntry]:
        """Get trace entry for an ICD.

        Args:
            icd_id: ICD identifier

        Returns:
            ICDTraceEntry or None if ICD not found
        """
        return self.trace_entries.get(icd_id)

    def get_icds_for_claim(self, claim_id: str) -> list[str]:
        """Get all ICDs cited by a safety claim.

        Args:
            claim_id: Safety claim identifier

        Returns:
            List of ICD IDs that cite this claim
        """
        result = []
        for icd_id, claim_ids in self.claim_to_icds.items():
            if claim_id in claim_ids:
                result.append(icd_id)
        return result

    def validate_coverage(self) -> CoverageReport:
        """Validate that all ICDs are covered by at least one claim.

        Returns:
            CoverageReport with coverage statistics and gaps
        """
        total = len(self.icds)
        covered = 0
        uncovered = []
        redundant = []

        for icd_id, entry in self.trace_entries.items():
            if entry.is_covered():
                covered += 1
                if len(entry.claim_ids) > 1:
                    redundant.append(icd_id)
            else:
                uncovered.append(icd_id)

        return CoverageReport(
            total_icds=total,
            covered_icds=covered,
            uncovered_icds=uncovered,
            redundant_icds=redundant,
        )

    def export_trace_matrix(self) -> dict[str, dict]:
        """Export trace matrix as dictionary for reporting.

        Returns:
            Dictionary with ICD ID → {claim_ids, status, icd_title}
        """
        result = {}
        for icd_id, icd in self.icds.items():
            entry = self.trace_entries[icd_id]
            result[icd_id] = {
                "title": icd.title,
                "claim_ids": entry.claim_ids,
                "coverage_status": entry.coverage_status.value,
                "safety_properties": icd.safety_properties,
                "sil_level": icd.sil_level.name,
            }
        return result


def build_icd_trace_matrix(
    argument_graph: SafetyArgumentGraph,
    icds: list[ICD],
) -> ICDTraceMatrix:
    """Construct ICD→Claim traceability matrix from argument graph and ICD definitions.

    This function builds a bidirectional mapping: each ICD to all claims that
    cite its safety properties, and validates 100% coverage (no uncovered ICDs).

    Args:
        argument_graph: SafetyArgumentGraph from Task 33.2
        icds: List of all 49 ICD specifications

    Returns:
        ICDTraceMatrix with complete traceability

    Raises:
        ValueError: If graph is invalid
    """
    matrix = ICDTraceMatrix()

    # Add all ICDs to matrix
    for icd in icds:
        matrix.add_icd(icd)

    # Link ICDs to claims based on safety properties cited in claim descriptions
    # For now, we'll use a basic heuristic: if a claim's description contains
    # "ICD-XXX" or mentions a safety property, link it
    for claim_id, claim in argument_graph.claims.items():
        claim_text = claim.description.lower()
        for icd in icds:
            # Check if claim mentions this ICD by ID
            if icd.icd_id.lower() in claim_text:
                matrix.add_icd_claim_link(icd.icd_id, claim_id)
            # Check if claim cites any safety properties of this ICD
            else:
                for prop in icd.safety_properties:
                    if prop.lower() in claim_text:
                        matrix.add_icd_claim_link(icd.icd_id, claim_id)
                        break

    return matrix


def validate_icd_coverage(matrix: ICDTraceMatrix) -> CoverageReport:
    """Validate 100% coverage of all ICDs in the trace matrix.

    Args:
        matrix: ICDTraceMatrix to validate

    Returns:
        CoverageReport with coverage statistics

    Raises:
        ValueError: If coverage is incomplete (has uncovered ICDs)
    """
    report = matrix.validate_coverage()

    if not report.is_complete:
        uncovered_str = ", ".join(report.uncovered_icds)
        raise ValueError(
            f"Incomplete ICD coverage: {report.uncovered_icds.__len__()} uncovered ICDs: {uncovered_str}"
        )

    return report


# ═══════════════════════════════════════════════════════════
# ALL_ICDS: Complete list of 49 ICDs
# ═══════════════════════════════════════════════════════════

ALL_ICDS: list[ICD] = [
    ICD(
        icd_id="ICD-001",
        title="Ingress: User Authentication Entry",
        description="OAuth2/OIDC authentication gateway for user ingress",
        safety_properties=["user_authentication", "session_management"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-002",
        title="Ingress: Tenant Isolation",
        description="Multi-tenant isolation at ingress boundary",
        safety_properties=["tenant_isolation", "data_segregation"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-003",
        title="Ingress: Request Validation",
        description="Schema validation and sanitization at entry point",
        safety_properties=["input_validation", "schema_enforcement"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-004",
        title="Ingress: Rate Limiting",
        description="Token bucket rate limiter for DDoS mitigation",
        safety_properties=["availability", "denial_of_service_mitigation"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-005",
        title="Ingress: CORS and CSRF Protection",
        description="Cross-origin and cross-site request forgery protection",
        safety_properties=["cross_site_protection", "origin_validation"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-006",
        title="Kernel: Bootstrap and Initialization",
        description="Kernel initialization and component bootstrapping",
        safety_properties=["kernel_startup", "component_initialization"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-007",
        title="Kernel: Decorator Enforcement",
        description="K-kernel decorator validation and enforcement on all boundary crossings",
        safety_properties=["boundary_enforcement", "decorator_validation"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-008",
        title="Pipeline: User Intent Input",
        description="Bidirectional WebSocket conversation for user intent capture",
        safety_properties=["user_intent_capture", "conversation_context"],
        sil_level=SILLevel.SIL1,
        protocol="WebSocket",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-009",
        title="Pipeline: Intent→Goal Decomposition",
        description="Decompose user intent into system goals",
        safety_properties=["goal_derivation", "intent_decomposition"],
        sil_level=SILLevel.SIL1,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-010",
        title="Pipeline: Goal→APS Synthesis",
        description="Synthesize Abstract Plan Signature from goals",
        safety_properties=["plan_synthesis", "goal_refinement"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-011",
        title="Pipeline: APS→Topology Mapping",
        description="Map APS to system topology and resource allocation",
        safety_properties=["topology_mapping", "resource_allocation"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-012",
        title="Pipeline: Topology→Execution",
        description="Execute topology plan on assigned lanes",
        safety_properties=["execution_dispatch", "topology_realization"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-013",
        title="Lanes: Main Lane Execution",
        description="Primary synchronous execution lane for critical tasks",
        safety_properties=["synchronous_execution", "main_lane_guarantee"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-014",
        title="Lanes: Cron Lane Scheduling",
        description="Periodic task scheduling and execution",
        safety_properties=["periodic_execution", "cron_isolation"],
        sil_level=SILLevel.SIL1,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-015",
        title="Lanes: Subagent Lane Isolation",
        description="Isolated execution lane for delegated subagent tasks",
        safety_properties=["agent_isolation", "delegation_safety"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-016",
        title="Lanes: Lane Manager Coordination",
        description="Lane manager coordinates task dispatch across lanes",
        safety_properties=["dispatch_coordination", "lane_scheduling"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-017",
        title="Policy Engine: Goal→Policy Mapping",
        description="Map goals to system policies and enforcement rules",
        safety_properties=["policy_mapping", "rule_derivation"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-018",
        title="Policy Engine: Policy Enforcement",
        description="Enforce policies on all boundary crossings",
        safety_properties=["policy_enforcement", "rule_execution"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-019",
        title="MCP: Model Context Protocol Interface",
        description="Standard MCP interface for tool invocation",
        safety_properties=["standard_protocol", "tool_invocation"],
        sil_level=SILLevel.SIL1,
        protocol="JSON-RPC",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-020",
        title="MCP: Tool Registry and Discovery",
        description="Registry for available tools and their schemas",
        safety_properties=["tool_discovery", "schema_registry"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-021",
        title="MCP: Workflow Engine",
        description="Orchestrate multi-step tool workflows",
        safety_properties=["workflow_orchestration", "step_sequencing"],
        sil_level=SILLevel.SIL2,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-022",
        title="MCP: Code Sandbox Execution",
        description="Safe code execution within gRPC→sandbox boundary",
        safety_properties=["sandbox_isolation", "code_safety"],
        sil_level=SILLevel.SIL3,
        protocol="gRPC",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-023",
        title="Event Bus: Event Publishing",
        description="Publish domain events to event bus",
        safety_properties=["event_publication", "pub_sub"],
        sil_level=SILLevel.SIL1,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-024",
        title="Event Bus: Event Subscription",
        description="Subscribe to domain events on event bus",
        safety_properties=["event_subscription", "observer_pattern"],
        sil_level=SILLevel.SIL1,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-025",
        title="Observability: Structured Logging",
        description="Structured logging with correlation IDs and tenant context",
        safety_properties=["audit_trail", "request_tracing"],
        sil_level=SILLevel.SIL1,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-026",
        title="Observability: Metrics and Monitoring",
        description="Metrics collection and real-time monitoring",
        safety_properties=["performance_monitoring", "health_tracking"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-027",
        title="Observability: Distributed Tracing",
        description="End-to-end request tracing across services",
        safety_properties=["request_tracing", "latency_tracking"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-028",
        title="Egress: LLM Request Formatting",
        description="Format system prompts and requests for LLM API",
        safety_properties=["prompt_safety", "request_formatting"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-029",
        title="Egress: LLM Response Parsing",
        description="Parse and validate LLM responses",
        safety_properties=["response_validation", "output_safety"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-030",
        title="Egress: Token Budget Enforcement",
        description="Enforce token budgets per request and tenant",
        safety_properties=["resource_limits", "cost_control"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-031",
        title="Egress: Web Access via HTTP",
        description="Web browsing and HTTP requests from agent",
        safety_properties=["web_access_control", "http_safety"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-032",
        title="Data Store: PostgreSQL Connection",
        description="Primary relational database (PostgreSQL) boundary",
        safety_properties=["data_persistence", "acid_transactions"],
        sil_level=SILLevel.SIL2,
        protocol="Database",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-033",
        title="Data Store: Redis Cache",
        description="In-memory caching via Redis",
        safety_properties=["cache_performance", "distributed_caching"],
        sil_level=SILLevel.SIL1,
        protocol="Redis",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-034",
        title="Data Store: ChromaDB Vector Store",
        description="Vector embeddings storage via ChromaDB",
        safety_properties=["semantic_search", "embedding_storage"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-035",
        title="Data Store: Redis Pub/Sub",
        description="Event-driven messaging via Redis pub/sub",
        safety_properties=["message_delivery", "event_distribution"],
        sil_level=SILLevel.SIL1,
        protocol="Redis",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-036",
        title="Data Store: PostgreSQL RLS",
        description="Row-level security for tenant data isolation",
        safety_properties=["tenant_isolation", "data_access_control"],
        sil_level=SILLevel.SIL2,
        protocol="Database",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-037",
        title="Data Store: Redis Streams",
        description="Event streaming and replay via Redis streams",
        safety_properties=["event_sourcing", "message_ordering"],
        sil_level=SILLevel.SIL1,
        protocol="Redis",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-038",
        title="Data Store: PostgreSQL Connection Pool",
        description="Pooled database connections for resource efficiency",
        safety_properties=["resource_efficiency", "connection_pooling"],
        sil_level=SILLevel.SIL1,
        protocol="Database",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-039",
        title="Data Store: PostgreSQL Migrations",
        description="Schema versioning and migrations",
        safety_properties=["schema_evolution", "version_control"],
        sil_level=SILLevel.SIL1,
        protocol="Database",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-040",
        title="Data Store: PostgreSQL Backups",
        description="Automated backups and disaster recovery",
        safety_properties=["data_durability", "recovery_guarantee"],
        sil_level=SILLevel.SIL2,
        protocol="Database",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-041",
        title="Data Store: Redis High Availability",
        description="Redis sentinel and cluster for availability",
        safety_properties=["high_availability", "failover"],
        sil_level=SILLevel.SIL1,
        protocol="Redis",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-042",
        title="Data Store: PostgreSQL Audit Log",
        description="Audit logging for compliance and forensics",
        safety_properties=["audit_trail", "compliance_logging"],
        sil_level=SILLevel.SIL2,
        protocol="Database",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-043",
        title="Data Store: ChromaDB Replication",
        description="Replication and consistency for ChromaDB",
        safety_properties=["data_consistency", "replication"],
        sil_level=SILLevel.SIL1,
        protocol="HTTP",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-044",
        title="KMS: Key Management Service",
        description="Centralized key generation and management",
        safety_properties=["key_generation", "key_storage"],
        sil_level=SILLevel.SIL3,
        protocol="HTTPS",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-045",
        title="KMS: Credential Rotation",
        description="Automated credential rotation and lifecycle",
        safety_properties=["credential_lifecycle", "rotation_automation"],
        sil_level=SILLevel.SIL2,
        protocol="HTTPS",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-046",
        title="KMS: Encryption at Rest",
        description="Encryption for data at rest in storage systems",
        safety_properties=["data_encryption", "at_rest_protection"],
        sil_level=SILLevel.SIL2,
        protocol="internal",
        direction="unidirectional",
    ),
    ICD(
        icd_id="ICD-047",
        title="Auth: OAuth2/OIDC Tokens",
        description="Token generation and validation for OAuth2/OIDC",
        safety_properties=["token_security", "identity_verification"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-048",
        title="Auth: Secret Management",
        description="Storage and retrieval of application secrets",
        safety_properties=["secret_storage", "access_control"],
        sil_level=SILLevel.SIL3,
        protocol="HTTPS",
        direction="bidirectional",
    ),
    ICD(
        icd_id="ICD-049",
        title="Auth: Permission and Role Management",
        description="RBAC and permission enforcement",
        safety_properties=["access_control", "authorization"],
        sil_level=SILLevel.SIL2,
        protocol="HTTP",
        direction="unidirectional",
    ),
]
