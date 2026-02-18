# Holly 3.0 — Repository Tree

```
holly-3/
├── pyproject.toml                          # PEP 621, deps, entry points
├── Makefile                                # dev, test, lint, docker shortcuts
├── Dockerfile                              # holly API container
├── Dockerfile.production
├── docker-compose.yml                      # holly + pg + redis + chroma + ollama + nginx + authentik + sandbox
├── alembic.ini
├── ARCHITECTURE.md                         # pointer to arch-tool SAD
├── CHANGELOG.md
├── VERSION
│
├── deploy/
│   ├── aws/
│   │   ├── ecs-task-def.json               # Fargate task definitions (holly + sandbox)
│   │   ├── vpc-cfn.yaml                    # CloudFormation: VPC, subnets, SGs
│   │   └── alb.yaml                        # ALB + target groups + WAF rules (production edge)
│   ├── nginx/
│   │   ├── README.md                       # DEV-ONLY — ALB owns production edge
│   │   ├── nginx.conf                      # local TLS termination, rate limit, WS upgrade
│   │   └── upstreams.conf
│   └── authentik/
│       ├── flows.yaml                      # SSO/OIDC provider config
│       ├── rbac-policies.yaml              # role → permission mappings
│       └── README.md                       # Authentik MUST be browser-reachable for OIDC
│                                           # redirects — exposed via ALB on /auth/* path
│
├── sandbox/                                # Isolated code execution environment
│   ├── Dockerfile                          # minimal image, no network egress
│   ├── pyproject.toml                      # standalone package, no holly deps
│   ├── sandbox/
│   │   ├── __init__.py
│   │   ├── server.py                       # gRPC server: accepts ExecutionRequest, returns ExecutionResult
│   │   ├── executor.py                     # run code in tmpfs, enforce resource limits (cgroups)
│   │   ├── runtime.py                      # language runtime wrappers (python, node, shell)
│   │   ├── proto/
│   │   │   └── execution.proto             # gRPC service definition
│   │   └── security/
│   │       ├── __init__.py
│   │       ├── namespace.py                # Linux namespace isolation (PID, NET, MNT)
│   │       ├── seccomp.py                  # syscall whitelist profiles
│   │       └── limits.py                   # wall-clock timeout, memory cap, disk quota
│   ├── tests/
│   │   ├── test_executor.py
│   │   ├── test_isolation.py               # verify no network, no filesystem escape
│   │   └── test_resource_limits.py
│   └── deploy/
│       ├── gvisor-runsc.yaml               # gVisor runtime config (production)
│       └── firecracker.yaml                # Firecracker microVM config (alternative)
│
├── migrations/
│   └── versions/                           # Alembic migration scripts
│
├── holly/                                  # main package
│   ├── __init__.py
│   ├── __main__.py                         # uvicorn entry: `python -m holly`
│   │
│   ├── kernel/                             # Layer 1: In-Process Library (NOT a service)
│   │                                       # Universal invariants only — keep thin
│   │   ├── __init__.py
│   │   ├── context.py                      # KernelContext — async context manager wrapping every
│   │   │                                   # boundary crossing: LLM calls, tool invocations,
│   │   │                                   # state mutations, external calls, event emissions,
│   │   │                                   # outbound streams, workflow resume
│   │   │                                   # IN-PROCESS: no network hop, no latency penalty
│   │   ├── schema_validation.py            # K1: JSON schema enforcement on all I/O
│   │   ├── permissions.py                  # K2: tool-level RBAC per agent identity
│   │   ├── bounds.py                       # K3: token budgets, cost caps, rate limits per lane
│   │   ├── trace.py                        # K4: correlation ID injection, parent span tagging
│   │   ├── idempotency.py                  # K5: RFC 8785 canonical JSON → idempotency key generation
│   │   │                                   # kernel generates/validates keys; workflow engine dedupes
│   │   ├── durability.py                   # K6: audit WAL (who did what — NOT replay/recovery)
│   │   ├── hitl.py                         # K7: human-in-the-loop gates (L0-L2 always require)
│   │   ├── eval_gate.py                    # K8: post-execution quality/hallucination checks
│   │   └── exceptions.py                   # KernelViolation, BoundsExceeded, HITLRequired
│   │
│   ├── core/                               # Layer 2: Holly Core — The Orchestrator
│   │   ├── __init__.py
│   │   ├── conversation.py                 # bidirectional WS chat interface
│   │   ├── intent.py                       # classifier: direct_solve | team_spawn | clarify
│   │   ├── goals/
│   │   │   ├── __init__.py
│   │   │   ├── decomposer.py              # high-level intent → goal tree
│   │   │   ├── hierarchy.py               # 7-level: Celestial L0-L4, Terrestrial L5-L6
│   │   │   ├── lexicographic.py           # lexicographic gating & priority resolution
│   │   │   ├── coupling.py               # eigenspectrum analysis, coupling matrices
│   │   │   └── predicates.py             # 37 goal predicates from v1
│   │   ├── aps/
│   │   │   ├── __init__.py
│   │   │   ├── controller.py              # Adaptive Partition Selection cascade
│   │   │   ├── tiers.py                   # T0 reflexive → T1 deliberative → T2 collab → T3 morphogenetic
│   │   │   ├── assembly.py                # Assembly Index computation
│   │   │   └── partitions.py              # partition definitions and dynamic rebalancing
│   │   ├── topology/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py                 # spawn/steer/dissolve agent teams
│   │   │   ├── contracts.py               # tool permissions, goal scope, resource budgets
│   │   │   ├── eigenspectrum.py           # goal-coupling matrix analysis for team mutation
│   │   │   └── templates.py              # predefined team compositions (research, build, review)
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── short_term.py              # Redis: conversation context, active task state
│   │   │   ├── medium_term.py             # Postgres: session history, completed results, patterns
│   │   │   └── long_term.py               # ChromaDB: semantic knowledge, document embeddings
│   │   └── session.py                      # user session lifecycle
│   │
│   ├── engine/                             # Layer 3: Execution Engine
│   │   ├── __init__.py
│   │   ├── lanes/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py                 # lane dispatcher, concurrency enforcement
│   │   │   ├── policy.py                  # dynamic concurrency limits, per-tenant quotas,
│   │   │   │                              # per-workflow resource budgets (not hard-coded constants)
│   │   │   ├── main.py                    # main lane — user-initiated tasks
│   │   │   ├── cron.py                    # cron lane — scheduled ops, health checks
│   │   │   └── subagent.py                # subagent lane — spawned team member tasks
│   │   ├── mcp/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py                # introspectable tool catalog
│   │   │   ├── permissions.py             # per-agent permission masks
│   │   │   ├── introspection.py           # tool schema discovery, capability reporting
│   │   │   └── builtin/                   # built-in MCP tool implementations
│   │   │       ├── __init__.py
│   │   │       ├── code.py                # thin gRPC client → sandbox service (no local exec)
│   │   │       ├── web.py                 # web search/fetch
│   │   │       ├── filesystem.py          # file operations (governed)
│   │   │       └── database.py            # query tools
│   │   └── workflow/
│   │       ├── __init__.py
│   │       ├── engine.py                  # durable task graph execution
│   │       ├── checkpoint.py              # state snapshot & resume — effectively-once
│   │       │                              # semantics (idempotency keys + dedupe +
│   │       │                              # compensating actions for external side effects)
│   │       │                              # source of truth for crash recovery
│   │       ├── retry.py                   # backoff, dead-letter
│   │       └── compiler.py                # DAG compilation from goal decomposition
│   │
│   ├── agents/                             # agent definitions and base classes
│   │   ├── __init__.py
│   │   ├── base.py                         # BaseAgent: lifecycle, message protocol, kernel binding
│   │   ├── registry.py                     # agent type catalog, capability declarations
│   │   ├── prompts/                        # system prompts per agent role
│   │   │   ├── __init__.py
│   │   │   ├── holly.py                   # Holly core orchestrator prompt
│   │   │   ├── researcher.py              # research/analysis agent prompt
│   │   │   ├── builder.py                 # code generation agent prompt
│   │   │   ├── reviewer.py                # code review / QA agent prompt
│   │   │   └── planner.py                 # strategic planning agent prompt
│   │   └── constitution/
│   │       ├── __init__.py
│   │       ├── celestial.py               # L0-L4 immutable constraints
│   │       └── terrestrial.py             # L5-L6 optimization goals
│   │
│   ├── llm/                                # LLM provider abstraction
│   │   ├── __init__.py
│   │   ├── router.py                       # model selection: opus/sonnet/haiku/ollama
│   │   ├── claude.py                       # Anthropic Claude API client
│   │   ├── ollama.py                       # local Ollama inference
│   │   ├── budget.py                       # token/cost tracking per session & agent
│   │   └── retry.py                        # rate limit handling, exponential backoff
│   │
│   ├── api/                                # Starlette/FastAPI HTTP + WS server
│   │   ├── __init__.py
│   │   ├── server.py                       # app factory, middleware stack
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── jwt.py                     # JWKS public key verification + claims extraction
│   │   │   │                              # fetches Authentik JWKS from well-known endpoint (cached)
│   │   │   │                              # no IdP call per request — offline validation only
│   │   │   │                              # short-lived tokens (5-15min) + refresh flow
│   │   │   │                              # revocation cache in Redis (bloom filter / small set)
│   │   │   ├── auth.py                    # RBAC enforcement from JWT claims
│   │   │   ├── cors.py
│   │   │   ├── rate_limit.py
│   │   │   └── trace.py                   # request correlation ID propagation
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                    # POST /chat, WS /ws/chat
│   │   │   ├── goals.py                   # CRUD goal trees
│   │   │   ├── agents.py                  # agent registry, status
│   │   │   ├── topology.py                # team compositions, mutations
│   │   │   ├── execution.py               # lane status, task history
│   │   │   ├── memory.py                  # memory queries
│   │   │   ├── tools.py                   # MCP tool catalog
│   │   │   ├── audit.py                   # trace replay, log queries
│   │   │   ├── config.py                  # config CRUD, audit log, rollback
│   │   │   └── health.py                  # liveness, readiness
│   │   └── websockets/
│   │       ├── __init__.py
│   │       ├── manager.py                 # connection lifecycle, room management
│   │       │                              # per-tenant authz on stream subscriptions
│   │       │                              # WS re-auth on JWT expiry
│   │       ├── channels.py                # 9 channel definitions
│   │       │                              #   agent_trace, goal_progress, team_topology,
│   │       │                              #   lane_status, memory_ops, tool_invocations,
│   │       │                              #   error_stream, metrics, notifications
│   │       └── serializers.py             # event → wire format
│   │
│   ├── observability/                      # Layer 4: Full Visibility
│   │   ├── __init__.py
│   │   ├── event_bus.py                    # unified event ingest, sampling, filters,
│   │   │                                   # backpressure control — prevents debug UI
│   │   │                                   # from amplifying prod load
│   │   │                                   # event-level PII/secret redaction before emit
│   │   │                                   # tenant-scoped fanout (every event carries tenant_id)
│   │   ├── logger.py                       # structured JSON logger, correlation ID aware
│   │   │                                   # redact-before-persist policy on all log writes
│   │   ├── metrics.py                      # Prometheus-compatible metric collectors
│   │   ├── events.py                       # event bus: engine/core → WS channels
│   │   ├── trace_store.py                  # agent decision tree persistence
│   │   │                                   # redact-before-persist on trace payloads
│   │   └── exporters/
│   │       ├── __init__.py
│   │       ├── postgres.py                # log/trace → Postgres (partitioned tables)
│   │       └── redis.py                   # real-time metric streams
│   │
│   ├── storage/                            # data layer abstractions
│   │   ├── __init__.py
│   │   ├── postgres/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py              # async pool (asyncpg)
│   │   │   ├── models.py                  # SQLAlchemy models
│   │   │   │                              # Row-Level Security (RLS) policies per tenant
│   │   │   ├── partitioning.py            # time-based partitioning: audit_logs, execution_history,
│   │   │   │                              # agent_traces (daily/weekly), auto-create future partitions
│   │   │   ├── archival.py                # retention policies, S3 cold storage export,
│   │   │   │                              # partition detach + drop for expired windows
│   │   │   └── queries/
│   │   │       ├── agents.py
│   │   │       ├── goals.py
│   │   │       ├── execution.py
│   │   │       ├── audit.py
│   │   │       └── topology.py
│   │   ├── redis/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py              # async Redis pool (Sentinel/Cluster HA)
│   │   │   ├── pubsub.py                  # pub/sub channel management (tenant-namespaced)
│   │   │   ├── queues.py                  # execution lane queues
│   │   │   ├── cache.py                   # session cache, hot config
│   │   │   └── ha.py                      # Sentinel/Cluster config, persistence (AOF+RDB),
│   │   │                                  # degradation behavior on Redis hiccup
│   │   └── chroma/
│   │       ├── __init__.py
│   │       ├── client.py                  # ChromaDB async client
│   │       ├── collections.py             # knowledge, documents, decisions (tenant-isolated)
│   │       └── embeddings.py              # embedding pipeline
│   │
│   ├── safety/                             # cross-cutting safety concerns
│   │   ├── __init__.py
│   │   ├── redaction.py                    # canonical redaction library — single source of truth
│   │   │                                   # all redactors (event_bus, logger, egress, ws serializers,
│   │   │                                   # secret_scanner, guardrails/output) import from here
│   │   ├── guardrails/
│   │   │   ├── __init__.py
│   │   │   ├── input.py                   # input sanitization, injection detection
│   │   │   └── output.py                  # PII redaction, secret stripping
│   │   ├── governance/
│   │   │   ├── __init__.py
│   │   │   ├── forbidden_paths.py         # file/network path restrictions
│   │   │   └── code_review.py             # generated code safety analysis
│   │   └── secret_scanner.py               # secret detection and redaction in traces
│   │                                       # (renamed from secrets.py to avoid collision with infra/secrets.py)
│   │
│   ├── infra/                              # runtime infrastructure concerns
│   │   ├── __init__.py
│   │   ├── egress.py                       # L7 egress control (application-layer):
│   │   │                                   # domain allowlist, redact before egress,
│   │   │                                   # prompt/response redaction, request logging,
│   │   │                                   # rate limits, budget enforcement for LLM calls
│   │   │                                   # L3 outbound routing via NAT Gateway (infra-level)
│   │   └── secrets.py                      # KMS / Vault client, API key rotation,
│   │                                       # tool credential store, Authentik client secret,
│   │                                       # audit trail, least-privilege access
│   │
│   └── config/
│       ├── __init__.py
│       ├── settings.py                     # pydantic Settings: env-driven config
│       ├── defaults.yaml                   # default configuration values
│       ├── hot_reload.py                   # runtime config updates without restart
│       ├── audit.py                        # every config change logged: who, what, when, diff
│       │                                   # HITL gate for dangerous keys (model, safety thresholds)
│       └── rollback.py                     # config version history, instant revert to prior state
│
├── console/                                # Layer 5: React Console UI
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── public/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── client.ts                  # HTTP + WS client
│   │   │   └── types.ts                   # API response types
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts            # WS connection + channel subscription
│   │   │   ├── useGoalTree.ts
│   │   │   ├── useTopology.ts
│   │   │   └── useAgentTrace.ts
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   │   ├── ChatPanel.tsx          # bidirectional conversation
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   └── InputBar.tsx
│   │   │   ├── Topology/
│   │   │   │   ├── TopologyViewer.tsx     # live agent composition graph
│   │   │   │   ├── AgentNode.tsx
│   │   │   │   └── ContractCard.tsx
│   │   │   ├── Goals/
│   │   │   │   ├── GoalTreeExplorer.tsx   # interactive hierarchy
│   │   │   │   ├── GoalNode.tsx
│   │   │   │   └── CelestialBadge.tsx
│   │   │   ├── Execution/
│   │   │   │   ├── LaneMonitor.tsx        # 3 lane status cards
│   │   │   │   └── TaskTimeline.tsx
│   │   │   ├── Audit/
│   │   │   │   ├── AuditLogViewer.tsx     # searchable trace replay
│   │   │   │   ├── TraceTree.tsx
│   │   │   │   └── MetricsDashboard.tsx
│   │   │   └── Layout/
│   │   │       ├── Sidebar.tsx
│   │   │       ├── Header.tsx
│   │   │       └── StatusBar.tsx
│   │   ├── stores/                        # zustand state management
│   │   │   ├── chatStore.ts
│   │   │   ├── topologyStore.ts
│   │   │   ├── goalStore.ts
│   │   │   └── metricsStore.ts
│   │   └── utils/
│   │       ├── mermaid.ts                 # live topology → mermaid rendering
│   │       └── formatters.ts
│   └── tests/
│
│   └── arch/                               # Development tooling (Phase ε infrastructure)
│       ├── __init__.py
│       ├── __main__.py                     # entry: `python -m holly.arch`
│       ├── cli.py                          # CLI: gantt, extract, validate subcommands
│       ├── sad_parser.py                   # mermaid SAD → structured AST (Task 1.5)
│       ├── schema.py                       # Pydantic models for architecture.yaml (Task 1.6)
│       ├── extract.py                      # SAD mermaid → architecture.yaml pipeline (Task 1.7)
│       ├── manifest_parser.py              # Task_Manifest.md → Manifest model (Task 1.8)
│       ├── dependencies.py                 # task dependency DAG, MP-based duration estimation
│       ├── tracker.py                      # status.yaml + Manifest → Gantt + PROGRESS.md
│       └── gantt_validator.py              # mermaid Gantt rendering validation gate
│
├── tests/                                  # Python test suite
│   ├── conftest.py                         # fixtures: test DB, Redis mock, agent stubs
│   ├── unit/
│   │   ├── kernel/
│   │   │   ├── test_context.py             # KernelContext wraps all boundary types
│   │   │   ├── test_schema_validation.py
│   │   │   ├── test_permissions.py
│   │   │   ├── test_bounds.py
│   │   │   ├── test_idempotency.py
│   │   │   └── test_hitl.py
│   │   ├── core/
│   │   │   ├── test_intent.py
│   │   │   ├── test_goal_decomposer.py
│   │   │   ├── test_aps_controller.py
│   │   │   └── test_topology_manager.py
│   │   ├── engine/
│   │   │   ├── test_lane_manager.py
│   │   │   ├── test_mcp_registry.py
│   │   │   └── test_workflow_engine.py
│   │   ├── sandbox/
│   │   │   ├── test_sandbox_client.py      # code.py gRPC dispatch
│   │   │   └── test_isolation.py           # verify blast-radius separation
│   │   ├── storage/
│   │   │   ├── test_partitioning.py        # partition creation, rotation
│   │   │   └── test_archival.py            # retention enforcement, S3 export
│   │   ├── config/
│   │   │   ├── test_audit.py               # config change logging, HITL triggers
│   │   │   └── test_rollback.py            # version revert
│   │   ├── safety/
│   │   │   ├── test_guardrails.py
│   │   │   └── test_governance.py
│   │   └── arch/                          # 98 tests for holly/arch tooling (7 modules)
│   │       ├── __init__.py
│   │       ├── test_sad_parser.py         # SAD mermaid parsing
│   │       ├── test_schema.py             # architecture.yaml schema validation
│   │       ├── test_extract.py            # extraction pipeline
│   │       ├── test_manifest_parser.py    # Task Manifest parsing
│   │       ├── test_dependencies.py       # DAG construction, cycle breaking
│   │       ├── test_tracker.py            # Gantt + PROGRESS.md generation
│   │       └── test_gantt_validator.py    # rendering validation checks
│   ├── integration/
│   │   ├── test_kernel_context.py          # KernelContext across all boundary types
│   │   ├── test_goal_to_execution.py       # goal → decompose → APS → lane → complete
│   │   ├── test_team_lifecycle.py          # spawn → monitor → mutate → dissolve
│   │   ├── test_sandbox_e2e.py             # holly API → code.py → gRPC → sandbox → result
│   │   └── test_observability.py           # event → WS → client
│   └── e2e/
│       ├── test_chat_flow.py               # user message → Holly response
│       └── test_team_spawn.py              # user goal → team spawn → execution → result
│
├── scripts/
│   ├── seed_db.py                          # populate initial data
│   ├── migrate.sh                          # alembic upgrade head
│   ├── dev.sh                              # docker-compose up + hot reload
│   ├── partition_maintenance.sh            # cron: create future partitions, archive expired
│   └── generate_architecture.py            # arch-tool → architecture.yaml → validate decorators
│
└── docs/
    ├── architecture.yaml                   # extracted from Arch Tool published SAD
    ├── goal-hierarchy.md                   # Celestial/Terrestrial goal definitions
    ├── morphogenetic-agency.md             # APS cascade theory reference
    ├── api-reference.md                    # generated from route docstrings
    ├── sandbox-security.md                 # isolation model, threat surface, escape mitigations
    ├── egress-model.md                     # NAT gateway, allowlists, LLM call logging, redaction
    ├── glossary.md                         # Celestial/Terrestrial, APS T0-T3, Eigenspectrum,
    │                                       # KernelContext — each term → operational behavior
    ├── deployment-topology.md              # multi-AZ layout, ECS/EKS scaling policies,
    │                                       # DB HA (Aurora/replicas/failover), Redis HA under load,
    │                                       # DR/backups, restore testing, per-tenant rate limits
    └── runbook.md                          # operational procedures
```

## Mapping to Architecture Diagram Layers

| Diagram Layer | Package | Key Files |
|---|---|---|
| **L0 Infrastructure** | `deploy/` | `alb.yaml` (prod edge), `nginx/` (dev-only), `authentik/` |
| **L1 Kernel** | `holly/kernel/` | `context.py` — KernelContext, in-process library (not a service) |
| **L2 Holly Core** | `holly/core/` | `conversation.py`, `intent.py`, `goals/`, `aps/`, `topology/`, `memory/` |
| **L3 Execution Engine** | `holly/engine/` | `lanes/`, `mcp/`, `workflow/` |
| **L3a Sandbox** | `sandbox/` (separate container) | `executor.py`, `security/`, gRPC interface |
| **L4 Observability** | `holly/observability/` + `holly/api/websockets/` | 9 WS channels, structured logging, trace store |
| **L5 Console** | `console/` | React + Vite + Zustand + Tailwind |
| **Data Stores** | `holly/storage/` | `postgres/` (partitioned), `redis/`, `chroma/` |
| **LLM** | `holly/llm/` | `claude.py`, `ollama.py`, `router.py` |
| **Safety** | `holly/safety/` + `holly/agents/constitution/` | `redaction.py` (canonical), guardrails, governance, celestial/terrestrial constraints |
| **Config** | `holly/config/` | `hot_reload.py`, `audit.py`, `rollback.py` |
| **Infra** | `holly/infra/` | `egress.py` (LLM proxy, allowlist, redaction), `secrets.py` (KMS/Vault) |
| **Auth** | `holly/api/middleware/` | `jwt.py` (JWKS verification), Authentik is out-of-band IdP |
| **Dev Tooling** | `holly/arch/` | `sad_parser.py`, `extract.py`, `tracker.py`, `gantt_validator.py`, `cli.py` — Phase ε infrastructure |

## Lineage from Prior Work

| Holly 3.0 Package | Derived From | What Changed |
|---|---|---|
| `holly/kernel/` | AutoBiz `autobiz/kernel/` | `pipeline.py` → `context.py`: in-process library, wraps all boundary crossings |
| `holly/core/aps/` | ecom-agents `src/aps/` | Generalized beyond e-commerce, APS tiers 0-3 |
| `holly/core/goals/` | ecom-agents `goal-hierarchy/` | Same 7-level hierarchy, adds coupling matrices |
| `holly/core/topology/` | ecom-agents `src/morphogenetic/` | Assembly Index + eigenspectrum for team mutation |
| `holly/core/memory/` | holly-v2 `holly_v2/storage/` + ecom-agents `src/holly/memory.py` | Unified 3-tier: Redis/Postgres/ChromaDB |
| `holly/engine/lanes/` | holly-v2 `holly_v2/core/lanes.py` | Same 3-lane model (main/4, cron/1, subagent/8) |
| `holly/engine/mcp/` | holly-v2 `holly_v2/mcp/` | Adds per-agent permission masks |
| `holly/engine/mcp/builtin/code.py` | holly-v2 `holly_v2/tools/` | Thin gRPC client — no local exec, dispatches to sandbox |
| `sandbox/` | **New** | Container-per-run isolation, gVisor/Firecracker, no network egress |
| `holly/storage/postgres/partitioning.py` | **New** | Time-based partitioning for audit, traces, execution history |
| `holly/storage/postgres/archival.py` | **New** | Retention windows, S3 cold storage, partition lifecycle |
| `holly/config/audit.py` | **New** | Config change logging, HITL gate for dangerous keys |
| `holly/config/rollback.py` | **New** | Config versioning, instant revert |
| `holly/infra/egress.py` | **New** | L7 egress control: domain allowlist, redact-before-egress, prompt/response redaction, LLM budget enforcement; L3 NAT routing is infra-level |
| `holly/safety/redaction.py` | **New** | Canonical redaction library — single import for event_bus, logger, egress, ws serializers, secret_scanner, guardrails |
| `holly/infra/secrets.py` | **New** | KMS/Vault client, API key rotation, tool credential store, audit trail |
| `holly/api/middleware/jwt.py` | **New** | JWKS public key verification (Authentik issuer), short-lived tokens (5-15min), revocation cache in Redis, WS re-auth on expiry |
| `holly/observability/event_bus.py` | **New** | Unified event ingest with sampling, filtering, backpressure control, event-level PII/secret redaction, tenant-scoped fanout |
| `holly/api/websockets/manager.py` | **Updated** | Per-tenant authz on stream subscriptions, WS re-auth on JWT expiry |
| `docs/deployment-topology.md` | **New** | Multi-AZ, scaling policies, DB HA, Redis HA, DR/backups, per-tenant rate limits |
| `holly/engine/lanes/policy.py` | **New** | Dynamic concurrency limits, per-tenant quotas (replaces hard-coded 4/1/8) |
| `holly/storage/redis/ha.py` | **New** | Sentinel/Cluster HA config, persistence strategy, degradation behavior |
| `holly/api/` | holly-v2 `holly_v2/api/` | Starlette, 9 WS channels, adds goal/topology/config routes |
| `holly/agents/constitution/` | ecom-agents `CONSTITUTION.md` + `goal-hierarchy/celestial-goals.md` | Programmatic enforcement, not just prompt text |
| `holly/safety/` | AutoBiz `autobiz/risks/` + ecom-agents `src/guardrails/` + `src/security/` | Unified: input/output guardrails + code governance + secret redaction |
| `console/` | ecom-agents `console/` | Same React base, adds topology viz + goal tree + audit replay |
