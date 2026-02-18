"""ICD Pydantic models - one model per boundary crossing.

Task 5.5 - Implement ICD as Pydantic models.

Each ICD from ICD v0.1 maps to one or more Pydantic ``BaseModel``
subclasses.  Models capture the **Schema** field from the ICD
specification and are registered with ``ICDSchemaRegistry`` during
bootstrap via ``register_all_icd_models()``.

Organisation
------------
Models are grouped by protocol / domain cluster:

- **Auth & Ingress** (ICD-001 to ICD-005, ICD-047 to ICD-049)
- **Kernel** (ICD-006 to ICD-007)
- **Core Pipeline** (ICD-008 to ICD-012)
- **Lanes & Policy** (ICD-013 to ICD-018)
- **MCP & Workflow** (ICD-019 to ICD-022)
- **Event Bus & Observability** (ICD-023 to ICD-027)
- **Egress & LLM** (ICD-028 to ICD-031)
- **Data Stores** (ICD-032 to ICD-043)
- **KMS** (ICD-044 to ICD-046, ICD-048)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════
# Shared types
# ═══════════════════════════════════════════════════════════


class Direction(StrEnum):
    """ICD direction."""

    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class Severity(StrEnum):
    """Event severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class LogLevel(StrEnum):
    """Structured log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LaneType(StrEnum):
    """Execution lane types."""

    MAIN = "main"
    CRON = "cron"
    SUBAGENT = "subagent"


class IntentType(StrEnum):
    """Intent classification types."""

    DIRECT_SOLVE = "direct_solve"
    TEAM_SPAWN = "team_spawn"
    CLARIFY = "clarify"


class APSTier(StrEnum):
    """APS classification tiers."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class MemoryType(StrEnum):
    """Memory store types."""

    CONVERSATION = "conversation"
    DECISION = "decision"
    FACT = "fact"


class SandboxLanguage(StrEnum):
    """Sandbox execution languages."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"


# ═══════════════════════════════════════════════════════════
# Auth & Ingress (ICD-001 to ICD-005, ICD-047 to ICD-049)
# ═══════════════════════════════════════════════════════════


class ICD001Request(BaseModel):
    """ICD-001: UI -> ALB — HTTPS request."""

    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    content_type: str = "application/json"
    authorization: str | None = None


class ICD002Request(BaseModel):
    """ICD-002: ALB -> JWT Middleware — forwarded request."""

    method: str
    path: str
    headers: dict[str, str]
    body: Any = None
    source_ip: str
    request_id: str
    tenant_id: str


class ICD002Response(BaseModel):
    """ICD-002: JWT Middleware validated claims."""

    sub: str
    tenant_id: str
    roles: list[str]
    exp: int


class ICD003Request(BaseModel):
    """ICD-003: JWT Middleware -> Core — authenticated request."""

    method: str
    path: str
    validated_claims: ICD002Response
    body: Any = None
    headers: dict[str, str] = Field(default_factory=dict)
    source_ip: str = ""


class ICD004Request(BaseModel):
    """ICD-004: UI -> Authentik — OIDC authorize request."""

    client_id: str
    redirect_uri: str
    response_type: str = "code"
    scope: str = "openid profile email"
    state: str
    code_challenge: str


class ICD004Response(BaseModel):
    """ICD-004: Authentik -> UI — OIDC redirect response."""

    code: str
    state: str
    redirect_uri: str


class ICD005Request(BaseModel):
    """ICD-005: ALB -> Authentik — token exchange."""

    code: str
    client_id: str
    client_secret: str
    grant_type: str = "authorization_code"
    redirect_uri: str
    code_verifier: str


class ICD005Response(BaseModel):
    """ICD-005: Authentik -> ALB — token response."""

    access_token: str
    id_token: str
    token_type: str = "Bearer"
    expires_in: int = 600


class ICD047JWK(BaseModel):
    """ICD-047: Single JWK entry."""

    kty: str = "RSA"
    kid: str
    use: str = "sig"
    n: str
    e: str
    alg: str = "RS256"


class ICD047Response(BaseModel):
    """ICD-047: Authentik -> JWT Middleware — JWKS."""

    keys: list[ICD047JWK]


class ICD048Response(BaseModel):
    """ICD-048: KMS -> Authentik — client credentials."""

    client_id: str
    client_secret: str
    issuer_url: str


class ICD049Request(BaseModel):
    """ICD-049: JWT Middleware -> Redis — token revocation check."""

    jti: str
    exp: int


# ═══════════════════════════════════════════════════════════
# Kernel (ICD-006, ICD-007)
# ═══════════════════════════════════════════════════════════


class ICD006Request(BaseModel):
    """ICD-006: Core -> Kernel — KernelContext entry."""

    boundary_id: str
    tenant_id: str
    user_id: str
    operation: str
    schema_definition: dict[str, Any] | None = None
    permission_mask: list[str] = Field(default_factory=list)


class ICD006Response(BaseModel):
    """ICD-006: Kernel -> Core — KernelContext result."""

    result: Any = None
    audit_log_entry: dict[str, Any] = Field(default_factory=dict)


class ICD007Request(BaseModel):
    """ICD-007: Engine -> Kernel — KernelContext entry (same as ICD-006)."""

    boundary_id: str
    tenant_id: str
    user_id: str
    operation: str
    schema_definition: dict[str, Any] | None = None
    permission_mask: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Core Pipeline (ICD-008 to ICD-012)
# ═══════════════════════════════════════════════════════════


class ICD008Request(BaseModel):
    """ICD-008: Conversation -> Intent Classifier."""

    message: str
    user_id: str
    tenant_id: str
    conversation_context: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str = ""


class ICD008Response(BaseModel):
    """ICD-008: Intent classification result."""

    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    next_action: str = ""


class GoalSpec(BaseModel):
    """A single goal in the hierarchy (used by ICD-009)."""

    level: int = Field(ge=0, le=6)
    codimension: int = 1
    predicate: str = ""
    lexicographic_parent: str | None = None
    celestial: bool = False
    deadline: int | None = None
    resource_budget: float | None = None


class ICD009Request(BaseModel):
    """ICD-009: Intent Classifier -> Goal Decomposer."""

    intent: IntentType
    original_message: str
    user_id: str
    tenant_id: str
    conversation_context: dict[str, Any] = Field(default_factory=dict)


class ICD009Response(BaseModel):
    """ICD-009: Goal decomposition result."""

    goals: list[GoalSpec]
    hierarchy: dict[str, Any] = Field(default_factory=dict)


class ICD010Request(BaseModel):
    """ICD-010: Goal Decomposer -> APS Controller."""

    goals: list[GoalSpec]
    hierarchy: dict[str, Any] = Field(default_factory=dict)
    user_id: str = ""
    tenant_id: str = ""
    conversation_id: str = ""
    deadline: int | None = None


class ICD010Response(BaseModel):
    """ICD-010: APS tier classification."""

    tier: APSTier
    assembly_index: dict[str, Any] = Field(default_factory=dict)
    dispatch_plan: dict[str, Any] = Field(default_factory=dict)
    resource_allocation: dict[str, Any] = Field(default_factory=dict)


class AgentBinding(BaseModel):
    """Agent binding in a topology (used by ICD-011, ICD-015)."""

    agent_id: str
    agent_type: str
    role: str = ""
    assigned_goals: list[str] = Field(default_factory=list)
    mcp_permissions: list[str] = Field(default_factory=list)
    resource_limit: float | None = None


class ICD011Request(BaseModel):
    """ICD-011: APS Controller -> Topology Manager."""

    tier: APSTier
    dispatch_plan: dict[str, Any] = Field(default_factory=dict)
    goals: list[GoalSpec] = Field(default_factory=list)
    user_id: str = ""
    tenant_id: str = ""
    deadline: int | None = None
    resource_budget: float | None = None


class ICD011Response(BaseModel):
    """ICD-011: Topology Manager — spawned topology."""

    topology_id: str
    agents: list[AgentBinding]
    inter_agent_contracts: dict[str, Any] = Field(default_factory=dict)
    monitoring: dict[str, Any] = Field(default_factory=dict)


class LaneSpec(BaseModel):
    """Lane specification in execution plan (used by ICD-012)."""

    lane_id: str
    lane_type: LaneType
    max_concurrency: int = 1
    mcp_registry_handle: str = ""


class ICD012Request(BaseModel):
    """ICD-012: Topology Manager -> Engine."""

    topology_id: str
    goals: list[GoalSpec] = Field(default_factory=list)
    agents: list[AgentBinding] = Field(default_factory=list)
    dispatch_plan: dict[str, Any] = Field(default_factory=dict)
    deadline: int | None = None
    user_id: str = ""
    tenant_id: str = ""


class ICD012Response(BaseModel):
    """ICD-012: Engine execution plan."""

    execution_id: str
    lanes: list[LaneSpec]
    monitoring_channels: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Lanes & Policy (ICD-013 to ICD-018)
# ═══════════════════════════════════════════════════════════


class ICD013Task(BaseModel):
    """ICD-013: Core -> Main Lane — task envelope."""

    task_id: str
    goal: str = ""
    user_id: str = ""
    tenant_id: str = ""
    deadline: int | None = None
    idempotency_key: str = ""
    resource_budget: float | None = None
    mcp_tools: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class ICD014ScheduledTask(BaseModel):
    """ICD-014: Core -> Cron Lane — scheduled task."""

    task_id: str
    goal: str = ""
    user_id: str = ""
    tenant_id: str = ""
    scheduled_time: int
    recurrence: str = ""
    max_retries: int = 3


class ICD014Response(BaseModel):
    """ICD-014: Cron Lane schedule confirmation."""

    schedule_id: str
    next_execution_time: int


class ICD015Request(BaseModel):
    """ICD-015: Topology Manager -> Subagent Lane."""

    agent_binding: AgentBinding
    goals: list[str] = Field(default_factory=list)
    parent_execution_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    deadline: int | None = None
    message_queue: str = ""


class ICD015Response(BaseModel):
    """ICD-015: Subagent Lane execution confirmation."""

    subagent_execution_id: str
    monitoring_channels: list[str] = Field(default_factory=list)


class PolicyUpdate(BaseModel):
    """ICD-016/017/018: Lane Policy update (shared)."""

    max_concurrency: int = 10
    per_tenant_limit: int = 100
    rate_limit_rps: float = 100.0
    max_queue_depth: int = 500
    timeout_ms: int = 5000


class LaneMetrics(BaseModel):
    """ICD-016/017/018: Lane metrics (shared base)."""

    queue_depth: int = 0
    active_tasks: int = 0
    completed_tasks_5min: int = 0
    error_rate_5min: float = 0.0
    p99_latency_ms: float = 0.0


class ICD016Metrics(LaneMetrics):
    """ICD-016: Main Lane metrics."""


class ICD017Metrics(LaneMetrics):
    """ICD-017: Cron Lane metrics."""

    scheduled_tasks_count: int = 0
    overdue_tasks: int = 0
    next_scheduled_time: int | None = None


class ICD018Metrics(LaneMetrics):
    """ICD-018: Subagent Lane metrics."""

    spawned_agents: int = 0
    agents_by_type: dict[str, int] = Field(default_factory=dict)
    inter_agent_messages: int = 0


# ═══════════════════════════════════════════════════════════
# MCP & Workflow (ICD-019 to ICD-022)
# ═══════════════════════════════════════════════════════════


class ICD019Request(BaseModel):
    """ICD-019/020: Lane -> MCP Registry — tool invocation."""

    tool_name: str
    agent_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""


class ICD019Response(BaseModel):
    """ICD-019/020: MCP Registry — tool result."""

    tool_result: Any = None
    execution_time_ms: float = 0.0
    tokens_used: int = 0
    error: str | None = None
    error_code: str | None = None


class ICD021TaskRequest(BaseModel):
    """ICD-021: MCP Registry -> Workflow Engine — task request."""

    task_graph_id: str
    node_id: str
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    parent_nodes: list[str] = Field(default_factory=list)
    deadline: int | None = None


class ICD021Checkpoint(BaseModel):
    """ICD-021: Workflow Engine -> MCP Registry — checkpoint."""

    workflow_id: str
    node_id: str
    output_state: dict[str, Any] = Field(default_factory=dict)
    timestamp: int = 0
    output_hash: str = ""


class ICD022Request(BaseModel):
    """ICD-022: MCP Registry -> Sandbox — gRPC execution request."""

    code: str
    language: SandboxLanguage
    input_data: Any = None
    timeout_ms: int = 30000
    memory_limit_mb: int = 256
    allowed_syscalls: list[str] = Field(default_factory=list)


class ICD022Response(BaseModel):
    """ICD-022: Sandbox -> MCP Registry — execution result."""

    output: Any = None
    exit_code: int = 0
    stderr: str = ""
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0


# ═══════════════════════════════════════════════════════════
# Event Bus & Observability (ICD-023 to ICD-027)
# ═══════════════════════════════════════════════════════════


class ICD023Event(BaseModel):
    """ICD-023/024: Event Bus event."""

    event_type: str
    source: str
    tenant_id: str = ""
    user_id: str = ""
    timestamp: int = 0
    trace_id: str = ""
    span_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    severity: Severity = Severity.INFO


class ICD025Subscription(BaseModel):
    """ICD-025: Event Bus -> WebSocket channel fanout."""

    channel: str
    subscribed_types: list[str] = Field(default_factory=list)
    tenant_id: str = ""


class ICD026LogEntry(BaseModel):
    """ICD-026: Event Bus -> Structured Logging."""

    timestamp: int = 0
    level: LogLevel = LogLevel.INFO
    logger: str = ""
    message: str = ""
    trace_id: str = ""
    span_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    component: str = ""
    event_data: dict[str, Any] = Field(default_factory=dict)
    http_method: str = ""
    http_path: str = ""
    status_code: int = 0
    latency_ms: float = 0.0
    error_type: str = ""
    error_message: str = ""
    request_id: str = ""
    user_agent: str = ""


class ICD027ClientMessage(BaseModel):
    """ICD-027: UI -> Observability — WebSocket subscribe."""

    action: str = "subscribe"
    channel: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)


class ICD027ServerMessage(BaseModel):
    """ICD-027: Observability -> UI — WebSocket event."""

    channel: str
    event: ICD023Event
    sequence_number: int = 0


# ═══════════════════════════════════════════════════════════
# Egress & LLM (ICD-028 to ICD-031)
# ═══════════════════════════════════════════════════════════


class ICD028Request(BaseModel):
    """ICD-028/029: Core/Subagent -> Egress Gateway — LLM request."""

    prompt: str
    model: str = "claude-sonnet-4.5"
    temperature: float = 1.0
    max_tokens: int = 4096
    system: str = ""
    context_window_tokens: int = 0
    user_id: str = ""
    tenant_id: str = ""
    trace_id: str = ""
    idempotency_key: str = ""
    agent_id: str = ""


class TokenUsage(BaseModel):
    """Token usage breakdown."""

    input: int = 0
    output: int = 0


class ICD028Response(BaseModel):
    """ICD-028/029: Egress Gateway -> Core/Subagent — LLM response."""

    completion: str = ""
    tokens_used: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = ""
    model: str = ""
    latency_ms: float = 0.0
    error: str | None = None
    error_type: str | None = None
    retry_after_ms: int | None = None


class ICD030Request(BaseModel):
    """ICD-030: Egress Gateway -> Claude API — messages request."""

    model: str
    messages: list[dict[str, Any]]
    max_tokens: int = 4096
    system: str = ""
    temperature: float = 1.0
    top_k: int | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ICD030Response(BaseModel):
    """ICD-030: Claude API -> Egress Gateway — messages response."""

    id: str
    type: str = "message"
    content: list[dict[str, Any]] = Field(default_factory=list)
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    stop_reason: str = ""


class ICD031ChatRequest(BaseModel):
    """ICD-031: Core -> Ollama — chat request."""

    model: str = "mistral:latest"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.7
    num_ctx: int = 4096


class ICD031ChatResponse(BaseModel):
    """ICD-031: Ollama -> Core — chat response."""

    message: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# Data Stores (ICD-032 to ICD-043)
# ═══════════════════════════════════════════════════════════


class ICD032GoalRecord(BaseModel):
    """ICD-032: Core -> PostgreSQL — goal record."""

    goal_id: str
    tenant_id: str
    user_id: str
    level: int = 0
    predicate: str = ""
    status: str = "pending"
    created_at: int = 0
    updated_at: int = 0


class ICD033CacheEntry(BaseModel):
    """ICD-033: Core -> Redis — cache entry."""

    key: str
    value: Any = None
    ttl_seconds: int = 3600


class ICD034Document(BaseModel):
    """ICD-034: Core -> ChromaDB — document upsert."""

    id: str
    embedding: list[float] = Field(default_factory=list)
    metadatas: dict[str, Any] = Field(default_factory=dict)
    documents: list[str] = Field(default_factory=list)


class ICD035QueueEntry(BaseModel):
    """ICD-035: Engine -> Redis — queue entry."""

    queue_name: str
    task_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: float = 0.0
    tenant_id: str = ""


class ICD036LogRecord(BaseModel):
    """ICD-036: Observability -> PostgreSQL — log record."""

    tenant_id: str
    timestamp: int = 0
    level: LogLevel = LogLevel.INFO
    logger: str = ""
    message: str = ""
    trace_id: str = ""
    span_id: str = ""
    user_id: str = ""
    component: str = ""
    event_data: dict[str, Any] = Field(default_factory=dict)
    redacted_hash: str = ""


class ICD037MetricsEntry(BaseModel):
    """ICD-037: Observability -> Redis — metrics stream entry."""

    tenant_id: str
    p99_latency_ms: float = 0.0
    active_tasks: int = 0
    error_rate_5m: float = 0.0
    agents_spawned: int = 0


class ICD038AuditRecord(BaseModel):
    """ICD-038: Kernel -> PostgreSQL — kernel audit log."""

    tenant_id: str
    boundary_id: str
    operation: str
    input_hash: str = ""
    output_hash: str = ""
    violations: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: int = 0
    trace_id: str = ""
    user_id: str = ""
    permission_mask: list[str] = Field(default_factory=list)


class ICD039Checkpoint(BaseModel):
    """ICD-039: Workflow Engine -> PostgreSQL — workflow checkpoint."""

    workflow_id: str
    node_id: str
    output_state: dict[str, Any] = Field(default_factory=dict)
    checkpoint_timestamp: int = 0
    idempotency_key: str = ""
    output_hash: str = ""
    execution_time_ms: float = 0.0
    parent_node_ids: list[str] = Field(default_factory=list)
    tenant_id: str = ""
    user_id: str = ""
    trace_id: str = ""


class ICD040TaskState(BaseModel):
    """ICD-040: Engine -> PostgreSQL — task state."""

    task_id: str
    execution_id: str
    status: str = "pending"
    started_at: int | None = None
    completed_at: int | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    retries_attempted: int = 0
    next_retry_time: int | None = None
    lane_type: LaneType = LaneType.MAIN
    tenant_id: str = ""
    user_id: str = ""
    trace_id: str = ""


class ICD041MemoryCache(BaseModel):
    """ICD-041: Memory System -> Redis — memory cache entry."""

    key: str
    value: Any = None
    ttl_seconds: int = 1800


class ICD042MemoryRecord(BaseModel):
    """ICD-042: Memory System -> PostgreSQL — memory store record."""

    id: str = ""
    conversation_id: str = ""
    agent_id: str = ""
    memory_type: MemoryType = MemoryType.CONVERSATION
    content: str = ""
    embedding_id: str = ""
    timestamp: int = 0
    tenant_id: str = ""
    retention_days: int = 30


class ICD043ChromaDoc(BaseModel):
    """ICD-043: Memory System -> ChromaDB — memory embedding."""

    id: str
    embedding: list[float] = Field(default_factory=list)
    metadatas: dict[str, Any] = Field(default_factory=dict)
    documents: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# KMS (ICD-044 to ICD-046, ICD-048)
# ═══════════════════════════════════════════════════════════


class ICD044Response(BaseModel):
    """ICD-044: KMS -> Egress Gateway — Claude API key."""

    secret: str
    arn: str = ""
    version_id: str = ""
    rotation_timestamp: int = 0


class ICD045Response(BaseModel):
    """ICD-045: KMS -> PostgreSQL — database credentials."""

    user: str
    password: str
    host: str
    port: int = 5432


class ICD046Response(BaseModel):
    """ICD-046: KMS -> MCP Registry — tool credentials."""

    api_key: str = ""
    auth_header: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
# Model registry — maps ICD ID to its primary model class
# ═══════════════════════════════════════════════════════════

ICD_MODEL_MAP: dict[str, type[BaseModel]] = {
    "ICD-001": ICD001Request,
    "ICD-002": ICD002Request,
    "ICD-003": ICD003Request,
    "ICD-004": ICD004Request,
    "ICD-005": ICD005Request,
    "ICD-006": ICD006Request,
    "ICD-007": ICD007Request,
    "ICD-008": ICD008Request,
    "ICD-009": ICD009Request,
    "ICD-010": ICD010Request,
    "ICD-011": ICD011Request,
    "ICD-012": ICD012Request,
    "ICD-013": ICD013Task,
    "ICD-014": ICD014ScheduledTask,
    "ICD-015": ICD015Request,
    "ICD-016": PolicyUpdate,
    "ICD-017": PolicyUpdate,
    "ICD-018": PolicyUpdate,
    "ICD-019": ICD019Request,
    "ICD-020": ICD019Request,
    "ICD-021": ICD021TaskRequest,
    "ICD-022": ICD022Request,
    "ICD-023": ICD023Event,
    "ICD-024": ICD023Event,
    "ICD-025": ICD025Subscription,
    "ICD-026": ICD026LogEntry,
    "ICD-027": ICD027ClientMessage,
    "ICD-028": ICD028Request,
    "ICD-029": ICD028Request,
    "ICD-030": ICD030Request,
    "ICD-031": ICD031ChatRequest,
    "ICD-032": ICD032GoalRecord,
    "ICD-033": ICD033CacheEntry,
    "ICD-034": ICD034Document,
    "ICD-035": ICD035QueueEntry,
    "ICD-036": ICD036LogRecord,
    "ICD-037": ICD037MetricsEntry,
    "ICD-038": ICD038AuditRecord,
    "ICD-039": ICD039Checkpoint,
    "ICD-040": ICD040TaskState,
    "ICD-041": ICD041MemoryCache,
    "ICD-042": ICD042MemoryRecord,
    "ICD-043": ICD043ChromaDoc,
    "ICD-044": ICD044Response,
    "ICD-045": ICD045Response,
    "ICD-046": ICD046Response,
    "ICD-047": ICD047Response,
    "ICD-048": ICD048Response,
    "ICD-049": ICD049Request,
}


def register_all_icd_models() -> int:
    """Register all 49 ICD models with ICDSchemaRegistry.

    Returns the number of models registered.
    """
    from holly.kernel.icd_schema_registry import ICDSchemaRegistry

    count = 0
    for schema_id, model_cls in ICD_MODEL_MAP.items():
        if not ICDSchemaRegistry.has(schema_id):
            ICDSchemaRegistry.register(schema_id, model_cls)
            count += 1
    return count
