# Holly Grace — SIL Classification Matrix v1.0

**Generated:** 17 February 2026 | **Standard:** IEC 61508 (tailored for autonomous systems) | **Source:** SAD v0.1.0.5, Component Behavior Specs, ICD v0.1

---

## Purpose

This document assigns a Safety Integrity Level (SIL-1, SIL-2, or SIL-3) to every component in the System Architecture Document based on failure consequence analysis and failure mode severity. It defines the verification requirements at each level and serves as the binding reference for all development tasks that cite the "SIL matrix" as an input.

The classification follows ISO 26262 / IEC 61508 principles tailored to autonomous agent systems:

- **Failure consequence** is specific to Holly's mission: loss of user control, loss of audit trail, unauthorized goal execution, or corruption of core invariants.
- **Verification rigor** is stratified: SIL-3 requires formal specification + model checking + property-based tests; SIL-2 requires property-based tests + integration tests; SIL-1 requires unit and integration tests.
- **SIL inheritance** operates on boundaries: an interface inherits the higher SIL of its two endpoints, per ICD v0.1.

---

## SIL Level Definitions (Holly-Tailored)

| Level | Failure Consequence | Severity | Verification Requirements | Examples |
|---|---|---|---|---|
| **SIL-3** | Loss of core safety invariant (safety constraint violated), loss of audit trail, corruption of inter-agent contracts, unauthorized goal execution, or sandbox/egress escape | **Critical** | Formal specification (TLA+); Model checking (zero violations); Property-based testing (Hypothesis); Unit testing (pytest); Integration testing; Independent verification (dissimilar channel); FMEA with residual risk register; RTM chain completeness; Executive sign-off on residual risk | Kernel (K1–K8), Sandbox (SEXEC/SSEC), Egress (L7/L3) |
| **SIL-2** | Loss of operational control, significant goal deadline miss, multi-agent topology incoherence, or loss of observability trace for a single operation | **Major** | Property-based testing (Hypothesis); Unit testing (pytest); Integration testing; FMEA with mitigations identified; RTM chain completeness; Design review with SIL-2 checklist | Core layer (Intent, Goals, APS, Topology), Storage layer (RLS enforcement), API layer (JWT, Auth) |
| **SIL-1** | Single user operation fails silently, single metric is incorrect, or config revert incomplete | **Minor** | Unit testing (pytest); Integration testing; RTM chain completeness; Code review by responsible engineer | Console UI, Config Control Plane (standard keys), cron scheduling |

---

## Classification Matrix

Every component in the SAD is classified below. The matrix uses exact node names from the mermaid flowchart (SAD v0.1.0.5).

### Layer 0: Infrastructure & Networking

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Application Load Balancer (ALB) | ALB | 0 | 2 | TLS termination failure exposes plaintext traffic; WAF rules bypass allows injection attacks; health checks fail silently and route to dead instance | Network boundary enforcement is safety-critical; TLS and WAF are first line of defense against external attack. Loss of WAF allows goal injection via malformed JSON. | ICD-001/002 integration tests; TLS handshake property-based tests; WAF rule validation (simulate 100 known attack patterns); health check monitoring; latency budget: p99 < 100ms verified via load tests |
| Web Application Firewall (WAF) | WAF | 0 | 2 | Attack payloads bypass WAF and reach Core unparsed; schema-based injection bypasses filter | WAF is the outer defensive layer; bypass allows malformed goals to reach Intent Classifier. Rule misconfiguration is high-likelihood threat. | Property-based injection testing (100+ OWASP payloads); regex fuzzing; rate-limit boundary tests; false positive regression on legitimate traffic |

### Layer 1: Kernel (In-Process Invariant Enforcement)

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| KernelContext (async context manager) | KCTX | 1 | 3 | Re-entrancy allows untraced boundary crossing; cancellation bypass loses WAL atomicity; state machine violation causes silent failures | Core safety mechanism. Every boundary crossing depends on KernelContext correctness. Re-entrancy or state corruption directly enables invariant violation. Failure is unrecoverable. | Formal TLA+ specification of state machine (5-state finite automaton with 8 transitions); Model checking (TLC) to verify no unreachable states, deadlock freedom, and proper WAL finality; Property-based tests (Hypothesis) to generate random operation sequences and verify state machine soundness; Unit tests for each state transition; Integration tests for concurrent entry, cancellation handling, and WAL durability; Dissimilar verification: independent code review of state machine logic |
| K1 — Schema Validation | K1 | 1 | 3 | Invalid schema rejected; malformed payload reaches downstream (Goal Decomposer receives untyped data); type confusion triggers goal corruption | First gate on every boundary crossing. Failure to validate allows semantically invalid operations to execute. All downstream logic assumes input conforms to ICD schema. | Formal grammar specification (ABNF or similar); Property-based schema fuzzing (Hypothesis: generate random JSON, verify against all known ICD schemas); Unit tests for each ICD schema (ICD-006 through ICD-049); Integration tests: send malformed payloads for each boundary, verify rejection; Adversarial tests: try to construct minimal payload that violates schema but passes initial check; RTM: link to ICD-006/007 core boundary contracts |
| K2 — Permission Gates | K2 | 1 | 3 | Unauthorized agent executes privileged operation (e.g., topology steer without contract); tenant isolation bypassed (agent reads another tenant's goals) | Permission gate enforces multi-tenant isolation and contract binding. Failure allows privilege escalation or cross-tenant data leak. Directly violates Celestial L0 (Safety) goal. | Formal access control matrix definition (agent_id × operation × tenant_id → allowed/denied); Property-based test generation (Hypothesis): enumerate all (agent, operation, tenant) combinations, verify each returns correct allow/deny; Unit tests for JWT claim extraction and role verification; Integration tests: attempt to call Topology.steer as read-only agent, verify rejection; Tenant isolation tests: create 2 agents in 2 tenants, verify neither can read the other's goal state; RTM to RBAC policy document |
| K3 — Bounds Checking | K3 | 1 | 3 | Resource budget exceeded but not detected; memory allocation fails silently mid-operation; message depth unbounded (stack overflow in recursive goal decomposition) | Bounds checking prevents resource exhaustion and algorithmic complexity DoS. Failure allows a single user's goal to consume all cluster resources (CPU, memory, latency). Denial of service. | Formal definition of all bounded resources (message queue depth, execution time per lane, memory per agent, goal nesting depth); Property-based tests (Hypothesis): generate payloads of increasing size, verify bounds are enforced at critical points; Unit tests for each bounds check (K3 checks message depth in K4.trace_injection, time in K7.hitl_gates, memory in goal decomposer); Integration tests: submit goal with depth=1000 (>max), verify rejection with BoundsExceeded exception; Adversarial: slow-loris style gradual exhaustion, verify monitoring catches degradation; RTM to Resource Allocation Policy |
| K4 — Trace Injection | K4 | 1 | 3 | Correlation ID collision (two operations get same ID); trace injection fails silently (operation executes untraced); trace redaction misses sensitive field | Traceability is essential for audit trail and failure investigation. Collision allows operations to be confused in logs. Failure to trace hides unauthorized operations. | Formal specification of correlation ID generation (RFC 8785 + CSPRNG properties); Property-based UUID collision test (Hypothesis: generate 10M IDs, verify zero collisions); Unit tests for redaction masking (verify PII patterns are stripped); Integration tests: 1000 concurrent boundary crossings, verify each has unique correlation ID; Audit trail verification: replay operation, verify all steps in trace; Redaction validation: create operation with API key in payload, verify not present in final log; RTM to Audit Trail Policy |
| K5 — Idempotency Key Generation | K5 | 1 | 3 | Duplicate request not detected; two identical operations both execute (double charge, duplicate goal creation); key hash collision | Idempotency prevents workflow engine redundancy from causing double-execution side effects. Failure allows external side effects (API calls, tool invocations) to occur twice. Violates Celestial L2 (Consistency). | Formal spec of idempotency key derivation (hash(request_content)); Property-based collision test (Hypothesis: mutate small parts of request, verify different keys); Unit tests for hash collision detection; Integration tests: submit identical goal twice, verify second returns cached result with same ID; Workflow tests: execute compensating action recovery, verify idempotency key prevents re-execution of already-executed steps; RTM to Durability Policy (ICD-021) |
| K6 — Durability WAL | K6 | 1 | 3 | WAL write fails silently (operation appears to execute but not recorded); partial write (correlation ID recorded, tenant ID lost); crash during EXITING loses audit trail | Audit trail is non-repudiable record of all operations. Failure corrupts compliance audit and failure investigation. K6 is the only persistent record of "who did what when." Failure is catastrophic for governance. | Formal specification of WAL entry schema (correlation_id, tenant_id, agent_id, operation, timestamp, result); Property-based WAL corruption test (Hypothesis: simulate Postgres failures during write, verify atomicity or explicit failure); Unit tests for WAL entry assembly; Integration tests: execute boundary crossing, verify WAL entry exists in Postgres; Crash recovery tests: kill process mid-WAL-write, verify Postgres consistency check finds no orphan entries; Dissimilar verification: audit log replay tool independently verifies every WAL entry is present and correctly ordered; RTM to Audit Trail Policy and Durability SLA |
| K7 — HITL Gates | K7 | 1 | 3 | HITL requirement ignored; human reviewer unreachable (goes timeout without decision); ambiguous HITL decision (status=? not {allow,deny}) | HITL gate is the human control point in the loop. For sensitive operations (topology restructure, goal injection, Celestial L4 override), human approval is required. Failure allows agent autonomy to exceed human's comfort threshold. | Formal HITL decision model (state machine: pending → {human_decide, timeout}; decision ∈ {allow, deny}); Property-based test (Hypothesis: simulate network latency, reviewer inactivity, concurrent decisions); Unit tests for timeout logic and decision serialization; Integration tests: request HITL, verify reviewer receives notification, submit decision, verify operation proceeds; Timeout test: wait beyond deadline, verify timeout triggers compensating action (deny); Dissimilar verification: manual end-to-end: submit goal, observe HITL UI, make decision, verify operation respects decision; RTM to HITL Policy (Phase D) |
| K8 — Eval Gates | K8 | 1 | 3 | Behavioral spec predicate evaluates to True (allows violation); predicate timeout (hangs indefinitely); predicate throws exception but gate doesn't catch | Eval gate is the final safety check before operation commits. It checks that output behavior matches constitution predicates. Failure allows operations that violate Celestial L0–L4 goals to execute. Constitution becomes unenforceable. | Formal specification of constitution predicates (one per L0–L4 goal, each returns bool); Property-based predicate testing (Hypothesis: vary operation parameters, verify predicate correctly identifies violations and non-violations); Unit tests for each predicate function; Integration tests: attempt to violate each Celestial constraint, verify K8 predicate detects and blocks; Timeout test: predicate hangs for 10s, verify timeout triggers compensating action; Exception test: predicate raises ValueError, verify caught and logged; Dissimilar verification: dedicated safety-focused test suite that adversarially tries to construct operations that violate Celestial goals; run via separate CI/CD pipeline independent of main build; RTM to Constitution Specification (Phase J, step 65) |

### Layer 2: Core (Orchestration & Intent Processing)

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| JWT Middleware | JWTMW | 2 | 2 | Signature verification bypass (attacker forges JWT); expired token accepted (past user's session); revocation cache inconsistency (revoked token still accepted) | Authentication is first-line access control. Bypass allows unauthorized access to Core. However, Kernel's K2 permission gates provide second line of defense. Failure is serious but not unrecoverable (K2 catches privilege escalation). | Unit tests for JWKS verification (test valid/invalid signatures, expiry, missing claims); Property-based tests (Hypothesis: mutate JWT fields, verify only valid tokens accepted); Redis revocation cache consistency tests (verify revoked token lookup works correctly); Timeout tests: Redis slow, verify timeout and fail-open behavior is correct; Integration tests: submit request with revoked token, verify 401; RTM: link to ICD-002/003 and Authentik OIDC spec |
| Conversation Interface (CONV) | CONV | 2 | 2 | User input lost (message never reaches Intent Classifier); bidirectional channel closes (user can send but not receive responses); WebSocket connection drops silently without client knowing | Conversation interface is the user's entry point. Failure breaks the user's ability to communicate intent. However, channel is idempotent (user can retry). Observability layer still has event log. | Unit tests for WebSocket message routing; Property-based tests (Hypothesis: send messages while connection is degraded, verify backpressure/drop behavior is explicit); Integration tests: send chat message, verify it appears in Intent Classifier input; Connection drop test: kill WebSocket mid-message, verify client receives explicit disconnect (not silent); Message loss test: inject random message drops, verify Event Bus captures all attempts; Latency: p99 < 50ms verified by load test; RTM: link to ICD-001 and WebSocket channel spec (ICD-027) |
| Intent Classifier (INTENT) | INTENT | 2 | 2 | Classification error (clarify classified as direct_solve, agent invokes without user input); classifier hangs (LLM timeout); token budget exceeded mid-classification | Intent Classifier routes user input into one of three paths: direct_solve, team_spawn, clarify. Misclassification routes request to wrong code path (e.g., spawns team without asking). Failure is recoverable: user can see result and retry. However, spawning team without clarification is UX failure and may violate L6 (Terrestrial user intent). | Unit tests for each classification outcome (test examples that should be direct_solve, verify output is direct_solve); Property-based tests (Hypothesis: generate random user intents, verify classifier always picks one of three categories); Token budget test: use LLM with explicit token limit, verify classifier respects it; Timeout test: LLM times out, verify fallback to clarify (safest default); Integration tests: send direct_solve intent, verify gets to direct path; send team_spawn intent, verify team gets spawned; send ambiguous intent, verify clarify response; Eval suite: property-based evaluations checking that classification is consistent across rephrased inputs; RTM to Intent Classification Spec |
| Goal Decomposer (GOALS) | GOALS | 2 | 2 | Goal hierarchy depth unbounded (L7, L8 created); Terrestrial goal violates Celestial constraint (L6 overrides L0); lexicographic gating not enforced (lower-level goal executes despite L0 violation) | Goal Decomposer builds the 7-level goal hierarchy and enforces lexicographic (total) ordering: no L5/L6 goal can execute if an L0–L4 goal is unsatisfied. Failure allows agent to execute user intent even if it violates safety constraints. Directly violates constitution. | Formal specification of goal hierarchy (7 levels: L0=Safety, L1=Consistency, L2=Availability, L3=Tenancy, L4=Constitutional, L5=User Intent, L6=Subgoal); Invariant: ∀ goal.level ∈ [0,6]; Property-based tests (Hypothesis: generate random goal sequences, verify hierarchy is always valid and levels don't exceed 6); Unit tests for lexicographic gating (test that L5 cannot execute if L0 is unsatisfied); Violation test: create goal that violates known constraint, verify decomposer rejects it with detailed reason; Depth test: attempt to create L7 goal, verify error; Integration tests: user submits intent that requires team spawn, verify decomposer creates L2 (Consistency), L3 (Tenancy), L4 (Constitutional), then L5/L6 user intent; Celestial constraint override test: attempt to create goal that contradicts L0 safety, verify decomposer rejects; RTM to Goal Hierarchy Formal Spec and Celestial goals definition (phase E, step 36) |
| APS Controller (APS) | APS | 2 | 2 | Tier classification wrong (morphogenetic goal routed as reflexive, no team spawning); Assembly Index incorrect (team composition doesn't match goal requirements) | APS (Autonomous Planning System) routes goals into four tiers: T0 Reflexive, T1 Deliberative, T2 Collaborative, T3 Morphogenetic. Misclassification routes single-agent goal to team, or vice versa, wasting resources or creating incomplete teams. Failure is correctable in next execution cycle (user resubmits goal). | Formal spec of tier classification criteria (T0: single agent, one step; T1: single agent, multi-step; T2: multiple agents, fixed contracts; T3: multiple agents, dynamic topology); Unit tests for each tier (test examples that should be T0, verify output is T0); Property-based tests (Hypothesis: vary goal complexity, verify tier assignment follows criteria); Assembly Index test: verify team composition matches goal dimension and coupling requirements; Complexity analysis: measure goal execution path, verify matches tier capability; Integration tests: reflexive goal runs in single lane; deliberative goal plans multi-step; collaborative goal spawns team; morphogenetic goal creates dynamic team that restarts; RTM to APS Tier Classification (phase E, step 37) |
| Team Topology Manager (TOPO) | TOPO | 2 | 2 | Contract violation (agent uses tool outside contract); tool permission mask not enforced (agent can invoke MCP tool without permission); eigenspectrum divergence not detected (team communication goes out of sync, but system doesn't notice) | Topology Manager maintains inter-agent contracts (who can call whom, with what resources) and detects when actual topology diverges from contracted topology via eigenspectrum monitoring. Failure allows agent to exceed its contract or team coherence to degrade silently. Direct violation of L2 (Consistency) goal. | Formal spec of inter-agent contracts (agent_id, allowed_callees, resource_budget, tool_permissions); Property-based contract test (Hypothesis: generate random agent communications, verify each respects contract); Unit tests for eigenspectrum computation (verify monitors communication patterns correctly); Contract violation test: agent attempts to call unauthorized peer, verify rejection; Tool permission test: agent attempts to invoke MCP tool outside its mask, verify rejection; Eigenspectrum divergence test: manually inject out-of-contract message, verify monitoring detects and triggers steer/dissolve; Integration tests: spawn collaborative team, verify all contracts enforced; Dynamic team (T3) restructures, verify contracts updated and new topology enforced; Dissimilar verification: separate topology auditor re-computes eigenspectrum from communication logs, compares to system's monitoring; RTM to Topology Spec (phase E, step 38) and Eigenspectrum Monitoring (README) |
| Memory System (MEM) | MEM | 2 | 2 | Short-term memory (Redis) loses session (restart causes goal context loss); medium-term memory (Postgres) RLS fails (agent reads another agent's stored memory); long-term memory (Chroma) vector search returns wrong embedding (hallucinates facts) | Memory system is 3-tier: Redis for short-term (volatile), Postgres for medium-term (durable, RLS-protected), Chroma for long-term (vector search). Failure of any tier breaks agent's ability to maintain context or retrieve past facts. However, system remains functional with degraded memory (goals can restart from prior checkpoints). | Unit tests for each tier: Redis key isolation, Postgres RLS policies, Chroma tenant isolation; Property-based tests (Hypothesis: generate random agent queries, verify each gets correct data from correct tenant); Memory loss simulation: kill Redis, verify system recovers from Postgres checkpoint; RLS test: create 2 agents in 2 tenants, verify each sees only own memory; Vector search sanity test: encode known facts, search for them, verify retrieval is accurate; Integration tests: agent creates memory entry, submits goal using that entry, verify goal uses correct fact; RTM to Memory System Spec (phase E, step 39) and RLS Policy |
| Config Control Plane (CFG) | CFG | 2 | 2 | Dangerous key change not gated (HITL bypass allows unsafe config without human review); rollback fails (bad config not reverted); hot reload crashes system (config parsing error during reload) | Config Control Plane manages runtime settings with HITL gates on dangerous keys. Failure allows unsafe configuration (e.g., disabling eval gates, increasing resource limits beyond safety margin) to take effect without review. | Formal spec of safe vs. dangerous config keys (dangerous ⊂ all keys); Unit tests for HITL gate on dangerous keys; Property-based tests (Hypothesis: generate random config values, verify valid ones pass parsing); Dangerous key test: attempt to change K8_eval_enabled to false, verify HITL requirement; Safe key test: change non-dangerous key, verify no HITL required; Rollback test: apply bad config that fails parsing, verify automatic rollback to previous version; Integration tests: change config, verify hot reload completes without restart; Monitoring: track config change rate, alert on unexpected churn; RTM to Config Control Spec (phase L) |

### Layer 2.5: Storage Layer (Multi-Tenant Isolation)

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| PostgreSQL (PG) | PG | 2.5 | 2 | Row-Level Security (RLS) policy failure (one tenant reads another's data); Partition failure (archival to S3 doesn't trigger, table grows unbounded); Transaction isolation violation (concurrent updates corrupt goal state) | PostgreSQL is the durable store for all operational data (agents, goals, checkpoints, audit logs). RLS is the only enforcement point for multi-tenant isolation at rest. Partition failure causes unbounded table growth and query slowdown. Transaction violation corrupts goal state. | Unit tests: verify RLS policy blocks cross-tenant reads; Property-based tests (Hypothesis: generate random tenant_id values, verify each query filters correctly); RLS bypass test: attempt to disable RLS, verify it re-enables on next connection; Partition test: trigger archival, verify old partition gets moved to S3; Query isolation test: two concurrent transactions modifying goal state, verify final state is consistent; Failover test: kill Postgres, verify standby takes over (if HA configured); RTM to RLS Policy and Partitioning Spec (phase C, steps 22–23) |
| Redis (RD) | RD | 2.5 | 2 | Session cache eviction under load (user session lost mid-operation); Pub/Sub message drop (event notification never reaches subscriber); Queue backpressure exceeded (task queue overflows, tasks lost) | Redis is the short-term store for sessions, message queues, and real-time metrics. Failure causes loss of in-flight state (user sessions, task queue). However, Postgres acts as recovery point (goals can restart from checkpoint). | Unit tests: verify key eviction policy is LRU (not random); Pub/Sub test: publish message, verify subscriber receives it; Queue test: enqueue tasks, verify all are processed in order; Backpressure test: overload queue, verify backpressure mechanism (either block publisher or drop oldest task); HA test: kill Redis node in cluster, verify failover completes; Persistence test: Redis restarts with AOF, verify all data recovered; RTM to Redis Config Spec |
| ChromaDB (CHROMA) | CHROMA | 2.5 | 2 | Vector embedding corrupted (search returns wrong document); Tenant collection isolation fails (agent searches other tenant's memories); Vector search timeout (embedding retrieval hangs) | ChromaDB stores long-term memory as vector embeddings. Corruption or isolation failure causes agent to retrieve wrong facts or cross-tenant data leak. Timeout breaks agent execution. However, agent can fall back to text search if vector search unavailable. | Unit tests: verify embeddings are correctly stored and retrieved; Tenant isolation test: create 2 collections for 2 tenants, verify each search only finds own collection; Corruption test: manually corrupt an embedding, verify search detects and handles it; Timeout test: force slow embedding operation, verify timeout triggers fallback to text search; Performance: verify vector search p99 < 100ms for typical dataset size; RTM to Memory System Spec |
| Ollama (OLLAMA) | OLLAMA | 2.5 | 2 | Local inference timeout (LLM response never arrives); Model cache miss (model not loaded, cold start adds 10s latency); Response truncation (output token limit hit mid-sentence) | Ollama provides cost-sensitive local inference (smaller models). Failure degrades performance or forces fallback to Claude API (cost increase). Not a safety-critical component; fallback always exists. | Unit tests: verify model loading, basic inference; Timeout test: force inference to exceed 30s budget, verify timeout and fallback to Claude API; Token limit test: set very small token limit, verify response is truncated cleanly (not mid-word); Cold start test: restart Ollama, measure first inference latency; Performance: verify p99 latency < 10s for standard models; RTM to Ollama Config Spec |

### Layer 3: Execution Engine (Durable Workflows)

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Main Lane (MAIN) | MAIN | 3 | 2 | User-initiated task hangs (never completes); task result lost (task executes but completion never recorded); lane policy not enforced (concurrency limit exceeded, resource quota exceeded) | Main Lane executes user-initiated tasks from Conversation interface. Failure causes user's operation to hang or vanish. However, tasks are checkpoint-resumable (workflow engine provides recovery). Multiple lanes provide isolation. | Unit tests for task dispatch; Property-based tests (Hypothesis: generate random task sequences, verify lanes enforce policy limits); Hang test: submit task, force execution to hang, verify timeout triggers compensating action; Result loss test: task completes, Postgres write fails, verify checkpointing catches this; Lane policy test: submit tasks exceeding concurrency limit, verify excess are queued; RTM to Lane Manager Spec (phase F, step 41) |
| Cron Lane (CRON) | CRON | 3 | 2 | Scheduled task misfires (runs at wrong time); cron expression parsing error (invalid cron syntax crashes scheduler); task runs twice (race condition in scheduler) | Cron Lane executes scheduled operations. Misfire causes stale data (e.g., memory consolidation doesn't run, stale embeddings not pruned). Parsing error crashes scheduler. Double-run violates idempotency. However, K5 idempotency key generation and K6 durability WAL provide safeguards. | Unit tests for cron expression parsing (test valid/invalid expressions); Property-based tests (Hypothesis: generate random cron schedules, verify parser accepts/rejects correctly); Misfire test: submit cron task, verify it runs at scheduled time within 1min tolerance; Double-run test: trigger race condition in scheduler, verify idempotency key prevents double execution; Expression parsing test: invalid cron expression, verify error is caught and logged; RTM to Cron Lane Spec (phase F, step 41) |
| Subagent Lane (SUB) | SUB | 3 | 2 | Subagent task gets wrong goal (routing error); subagent lifecycle not cleaned up (orphan agent still consuming resources); spawned agent exceeds resource budget (Morphogenetic team member uses too much memory) | Subagent Lane spawns and manages agents created by topology manager for collaborative/morphogenetic goals. Failure causes goal misrouting (agent works on wrong problem) or resource leaks. However, eigenspectrum monitoring detects zombie agents, and resource limits (enforced by K3) prevent unbounded consumption. | Unit tests for subagent lifecycle (spawn, execute, cleanup); Property-based tests (Hypothesis: generate random agent spawn/shutdown sequences, verify state machine); Goal routing test: create collaborative goal, verify each subagent receives correct subgoal; Resource limit test: subagent exceeds budget, verify K3 bounds check halts execution; Cleanup test: kill subagent mid-task, verify cleanup runs and frees resources; RTM to Topology Manager and Subagent Lane Spec (phase E, step 38; phase F, step 41) |
| MCP Tool Registry (MCP) | MCP | 3 | 2 | Tool permission mask not applied (agent invokes tool it doesn't have permission for); tool signature schema missing (agent calls tool with wrong parameters); tool registry out of sync (new tool available, registry not updated) | MCP Registry is the catalog of tools agents can invoke. Permission mask enforces per-agent tool access. Signature schema defines input/output contracts. Failure allows privilege escalation (agent uses tool outside its contract) or silent tool invocation errors. However, K2 permission gates provide second line of defense. | Unit tests for tool permission enforcement; Property-based tests (Hypothesis: enumerate all (agent, tool) combinations, verify each allows/denies correctly); Permission test: agent without permission attempts to invoke tool, verify rejection with reason; Schema test: tool invoked with wrong parameter types, verify error before execution; Registry sync test: add new tool, verify it appears in registry within 1s; Tool discovery test: list available tools for specific agent, verify only permitted tools appear; RTM to MCP Registry Spec (phase F, step 42) |
| Workflow Engine (WF) | WF | 3 | 2 | Task DAG execution deadlocks (circular dependency not detected); compensation action fails (rollback incomplete, system left in inconsistent state); checkpoint read stale (resume uses old state, loses recent updates) | Workflow Engine executes durable task graphs with effectively-once semantics and compensating actions for failure recovery. Deadlock blocks execution indefinitely. Failed compensation leaves system in inconsistent state (partial rollback, user sees wrong outcome). Stale checkpoint causes loss of recent work. | Formal spec of task DAG execution (DAG properties: acyclic, no cycles); Unit tests for deadlock detection (test DAGs with cycles, verify error); Property-based tests (Hypothesis: generate random DAGs, verify acyclicity check is correct); Compensation test: execute workflow, trigger failure mid-execution, verify compensation action rolls back all changes; Checkpoint test: take checkpoint, simulate Postgres failure mid-task, restart, verify resume uses latest checkpoint; Idempotency test: retry same task, verify K5 idempotency key prevents re-execution of tool invocation; RTM to Workflow Engine Spec (phase F, step 44) and Durability Policy |
| Lane Policy (LANEPOL) | LANEPOL | 3 | 2 | Concurrency limit not enforced (all 1000 requests execute simultaneously instead of 100); per-tenant quota exceeded but not detected; per-workflow budget exhausted mid-workflow (fails to prevent overage) | Lane Policy governs concurrency, quotas, and budgets across lanes. Failure allows resource exhaustion (all requests execute concurrently, CPU saturates). Quota bypass allows one tenant to starve others. Budget overrun causes workflow to exceed SLA. | Unit tests for quota enforcement; Property-based tests (Hypothesis: generate random request patterns, verify quotas enforced); Concurrency limit test: submit 1000 tasks, verify no more than policy limit execute simultaneously; Quota test: track per-tenant usage, verify usage never exceeds quota; Budget test: workflow approaches budget limit, verify it halts before exceeding; Fairness test: two tenants submit tasks, verify each gets fair share of capacity; RTM to Lane Policy Spec (phase F, step 41) |

### Layer 4: Observability & Safety Infrastructure

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Event Bus (EVBUS) | EVBUS | 4 | 2 | Event dropped (audit event never reaches logging system); backpressure mechanism fails (event producer crashes when overwhelmed); event redaction misses sensitive field (PII reaches observability store) | Event Bus is the unified ingest for all observability data. Dropped events break audit trail. Backpressure failure causes cascade (producer crashes, upstream also crashes). Redaction failure is security incident (PII in logs). However, K6 WAL in Kernel provides backup audit record. | Unit tests for event routing; Property-based tests (Hypothesis: generate random event sequences, verify none are dropped); Backpressure test: overwhelm event bus, verify backpressure mechanism (producer blocks or events are dropped with warning); Redaction test: emit event with known PII pattern (API key, phone number), verify not present in final log storage; Latency test: measure event-to-log latency, verify < 100ms p99; RTM to Event Bus Spec (phase I, step 57) |
| WebSocket Channels (WS) | WS | 4 | 2 | Channel subscription fails (UI doesn't receive goal progress updates); channel message corruption (update arrives corrupted); per-tenant authz not enforced (user sees other tenant's updates) | WebSocket provides real-time updates to UI. Subscription failure breaks UI liveness (user doesn't see status updates). Corruption is visible to user (bad data in dashboard). Authz failure is security incident. However, audit log viewer provides fallback (user can reconstruct events from logs). | Unit tests for subscription mechanism; Per-tenant authorization tests (verify one tenant cannot subscribe to another's channels); Corruption test: intentionally corrupt message, verify it's detected or logged with error; Message loss test: disconnect mid-message, verify user receives explicit "disconnected" notification; Latency test: measure message delivery latency, verify < 100ms p99; RTM to WebSocket Channel Spec (phase H, step 55) |
| Structured Logging (LOGS) | LOGS | 4 | 2 | Log entry dropped (critical failure not recorded); correlation ID missing (traces cannot be reconstructed); sensitive data logged before redaction (PII persisted) | Structured Logging is the authoritative audit trail. Dropped entries break compliance audits. Missing correlation IDs break failure investigation (can't reconstruct execution flow). Unredacted PII is regulatory violation. K6 WAL provides backup, but primary log is the audit source of truth. | Unit tests for log entry assembly; Property-based tests (Hypothesis: generate random operations, verify log entries created with correct structure); Redaction test: log operation with secrets, verify secrets are redacted; Correlation ID test: trace multi-hop operation, verify each hop has correct correlation ID; Storage test: write 10M log entries, verify all are persisted correctly; Search test: query logs by correlation ID, verify all entries for that operation appear; RTM to Logging Spec (phase I, step 58) |
| Goal Dashboard (DASH) | DASH | 4 | 2 | Dashboard queries return stale data (user sees goal as incomplete when it succeeded); goal mutation history incomplete (user can't see how goal evolved); failure rate metric incorrect (dashboard shows false success rate) | Goal Dashboard is the user-facing view of system state. Stale data is UX problem (user sees wrong state). Incomplete history makes debugging hard (user can't see where things went wrong). Incorrect metrics misdirect operational response. However, all data is read-only (no mutations), so failures are non-destructive. | Unit tests for dashboard data queries; Property-based tests (Hypothesis: generate random goal mutations, verify dashboard shows correct state); Staleness test: mutate goal, query dashboard, verify updated state appears within 1s; History test: trace goal through multiple mutations, verify all steps appear in dashboard; Metric test: verify failure rate calculation, test boundary cases (all fail, all succeed); Performance test: dashboard query on 10k concurrent goals, verify p99 < 500ms; RTM to Dashboard Spec (phase M, step 76) |

### Layer 5: User Interfaces & External Systems

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Chat Interface (CHAT) | CHAT | 5 | 1 | User message not sent (WebSocket dropped, message lost); chat panel unresponsive (freezes UI); message history cleared (user loses conversation context) | Chat Interface is the user-facing message entry point. Lost message is UX failure (user must re-type). Unresponsive UI is unusable. Lost history is annoying but not critical (all operations are stored server-side). Failures are non-destructive; retry always works. | Unit tests for message dispatch; Integration tests: send message, verify it appears in chat and reaches server; Unresponsiveness test: simulate network latency, verify UI remains responsive; History test: refresh page, verify chat history reloads; Connection drop test: kill WebSocket, verify UI shows "disconnected" and allows reconnect; RTM to Chat Interface Spec (phase M, step 74) |
| Topology Visualizer (TOPOVIZ) | TOPOVIZ | 5 | 1 | Live topology graph doesn't update (UI shows stale agent composition); agent node mislabeled (wrong agent name displayed); visualization crash on large team (1000 agents) | Topology Visualizer shows live agent graph and contracts. Stale graph is cosmetic (actual topology is in memory, UI lags). Mislabeled node is confusing (wrong label displayed). Crash at scale means tool unusable for large teams. None of these affect operation; they're UX issues. | Unit tests for graph generation; Property-based tests (Hypothesis: generate random topologies, verify graph renders); Staleness test: agent joins team, verify graph updates within 2s; Label test: verify each agent is labeled correctly; Scale test: create 1000-agent graph, verify visualization renders without crashing; RTM to Topology Visualizer Spec (phase M, step 75) |
| Goal Tree Explorer (GOALVIZ) | GOALVIZ | 5 | 1 | Goal tree depth not visible (deep nesting is collapsed, user can't see L5/L6); Celestial vs. Terrestrial marker missing (user can't tell which goals are safety); tree node click doesn't show details (expand is broken) | Goal Tree Explorer shows the 7-level goal hierarchy. Missing depth indicator is confusing (user doesn't understand nesting). Missing Celestial/Terrestrial marker means user can't distinguish safety from intent. Broken expand is UX issue. All failures are UI-level; goal execution is unaffected. | Unit tests for tree rendering; Property-based tests (Hypothesis: generate random goal trees, verify depth markers appear); Celestial marking test: verify L0–L4 goals have safety badge; Terrestrial marking test: verify L5–L6 goals have user-intent badge; Expand test: click node, verify details appear; Scale test: 1000-node tree, verify scroll performance is acceptable; RTM to Goal Tree Explorer Spec (phase M, step 76) |
| Audit Log Viewer (AUDIT) | AUDIT | 5 | 1 | Log query times out (large result set causes slow query); sensitive data visible in audit log (PII not redacted in viewer); log entry truncated (long messages cut off mid-word) | Audit Log Viewer is read-only access to K6 WAL audit trail. Timeout is operational issue (user can't query logs). Visible PII is security/compliance issue, but it's a display problem (data in storage is already redacted by K4). Truncation is cosmetic. Failures don't affect core operation. | Unit tests for log query; Query performance test: query with broad date range, verify completes in < 5s; Redaction test: verify sensitive fields are still redacted in viewer output; Truncation test: submit long message, verify it's either shown in full or clearly marked as truncated; Pagination test: large result set, verify pagination works; RTM to Audit Log Viewer Spec (phase M, step 78) |

### Layer 5.5: External APIs & Services

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Authentik (AUTH) | AUTH | 5.5 | 2 | OIDC token issuance fails (user can't log in); RBAC policy not enforced (user gets wrong roles); JWKS public key not updated (JWT verification fails after key rotation) | Authentik is the out-of-band identity provider. Token issuance failure blocks all access (denial of service). RBAC policy failure grants wrong roles (privilege escalation). Stale JWKS prevents legitimate users from logging in. However, failures are external to Holly and recoverable (Authentik restart, key re-publish). | Unit tests for OIDC flow (test login, token issuance); Property-based tests (Hypothesis: generate random user claims, verify RBAC policy applied correctly); Token issuance test: initiate login, verify token is issued with correct claims; RBAC test: create user with specific role, verify token includes that role; JWKS update test: verify key rotation completes and new keys are used within 1 min; Failover test: if Authentik HA configured, kill primary, verify secondary issues tokens; RTM to Authentik Spec (phase H, step 81) |
| Claude API (LLM) | LLM | 5.5 | 2 | LLM request times out (inference hangs > 30s); response token limit exceeded (output truncated mid-sentence); invalid response format (LLM returns non-JSON, parser crashes) | Claude API provides primary inference. Timeout causes operation to stall. Token limit exceeded causes incomplete output (agent tries to use partial response, may fail). Invalid format breaks parser. However, fallback to Ollama exists (lower quality but continues), and operation can be retried. K7/K8 gates catch malformed outputs. | Unit tests for LLM request formatting; Property-based tests (Hypothesis: generate random prompts, verify all produce valid JSON responses); Timeout test: submit complex prompt, verify timeout < 30s and fallback triggers; Token limit test: request with max_tokens=10, verify response stops cleanly at token limit; Response format test: verify response always conforms to expected JSON schema; Error handling test: API returns error (rate limit, overloaded), verify graceful degradation; RTM to Claude API Integration Spec (phase E) |

### Layer 3.5: Sandbox (Isolated Code Execution)

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Code Executor (SEXEC) | SEXEC | 3.5 | 3 | Code execution vulnerability (attacker breaks out of sandbox, gains access to host system); memory limit not enforced (unbounded allocation crashes executor); timeout not enforced (infinite loop hangs executor indefinitely) | Code Executor runs user-generated code (Python scripts, shell commands). Sandbox escape is catastrophic (attacker gains root on host). Memory overrun crashes executor. Timeout failure allows DoS (single script hangs system). Directly threatens system integrity and availability. | Formal spec of sandbox isolation model (namespace, seccomp, rlimits); Property-based fuzzing (Hypothesis: generate random code payloads, verify none escape sandbox); Unit tests for each isolation mechanism (namespace test, seccomp profile test, rlimit test); Escape test: known escape techniques (e.g., fork bomb, filesystem access), verify sandbox prevents each; Memory test: code allocates 10GB, verify limit is enforced and process is killed; Timeout test: infinite loop, verify killed after timeout; Network test: code attempts to bind socket, verify network is disabled; Dissimilar verification: gVisor/Firecracker audit by security team independent of implementation; RTM to Sandbox Security Spec (phase G, step 47–50) |
| Security Boundary (SSEC) | SSEC | 3.5 | 3 | Namespace isolation bypassed (code sees parent filesystem); seccomp profile too permissive (code can call disallowed syscalls); resource limits disabled (memory/CPU unbounded) | Security Boundary enforces four isolation layers: namespace (PID, NET, MNT, UTS), seccomp (disallow privileged syscalls), resource limits (memory, CPU, file descriptors), and optional gVisor/Firecracker. Any layer failure allows escape or resource exhaustion. Directly threatens integrity and availability. | Formal spec of isolation mechanisms (which namespaces, which seccomp rules, which limits); Property-based isolation tests (Hypothesis: generate random isolation rule combinations, verify no gaps); Namespace test: code lists processes, verify only sandbox processes visible (not parent); Seccomp test: code attempts sys_mount, verify blocked; Resource test: code forks in loop (fork bomb), verify stopped at limit; gVisor/Firecracker test: run code under both runtimes, verify same isolation; Dissimilar verification: security team manually verifies seccomp rule set against Linux kernel security guide; RTM to Security Boundary Spec (phase G, step 48) |

### Layer 2 (Continued): Infrastructure

| Component | SAD Node | Layer | SIL | Failure Consequence | Justification | Verification Methods |
|---|---|---|---|---|---|---|
| Egress Control (L7 & L3) | EGRESS | 2 | 3 | Domain allowlist bypass (code reaches unauthorized external API); response redaction misses sensitive data (API response with PII reaches user); rate limits not enforced (attacker uses tool 1000x per second, exhausts API quota) | Egress Control is the egress enforcement layer (L7 application + L3 NAT). Bypass allows unauthorized external communication (data exfiltration, lateral movement). Redaction failure exposes PII (privacy violation). Rate limit bypass causes API quota exhaustion and service denial. Directly threatens security and availability. | Formal spec of domain allowlist (which domains permitted); Property-based egress fuzzing (Hypothesis: generate random egress requests, verify only allowlisted domains allowed); Unit tests for redaction masking (verify API response secrets are stripped); Allowlist test: code requests allowlisted domain (allowed), code requests blocked domain (denied); Redaction test: API response contains API key, verify key is redacted in response to user; Rate limit test: code invokes tool 1000x/sec, verify rate limit is enforced (reject excess, return 429); RTM to Egress Control Spec (phase D, step 31) and L7 Policy |
| Secrets Manager (KMS) | KMS | 2 | 3 | API key credential leaked (key material exposed in logs or memory); key rotation fails (old key still used after rotation); credential access not audited (no record of who accessed secret) | KMS (AWS KMS / HashiCorp Vault) stores sensitive credentials (API keys, database passwords, Authentik client secret). Leaked credential compromises external systems. Failed rotation means revoked key still works (exposure continues). Unaudited access hides unauthorized use. Directly threatens confidentiality. | Formal spec of key rotation (old key → new key, timeline for clients to pick up new key); Unit tests for credential retrieval; Property-based tests (Hypothesis: generate random key access patterns, verify audit log captures all); Key leak test: credential stored in KMS, verify not exposed in app logs, Postgres logs, or Redis; Rotation test: rotate key, verify clients pick up new key within 5 min, old key is revoked; Audit test: retrieve credential, verify access logged with requestor ID and timestamp; Unauthorized access test: unauthorized component attempts to retrieve API key, verify denial and alert; RTM to KMS Spec (phase D, step 32) |

---

## Verification Requirements by Level

### SIL-3 Verification Requirements

SIL-3 components (Kernel, Sandbox, Egress Control, KMS, Secrets Manager, MCP Registry) require the highest rigor:

1. **Formal Specification (TLA+ or similar)**
   - Every state machine must be formally specified with explicit states, transitions, and guard conditions
   - Invariants must be stated as first-order logic predicates
   - Acceptance criteria (what constitutes success/failure) must be formally defined
   - Example: KernelContext state machine: 5 states (IDLE, ENTERING, ACTIVE, EXITING, FAULTED), 8 transitions, 7 invariants (re-entrancy prevention, atomicity, WAL finality)

2. **Model Checking (TLC or similar)**
   - Execute the formal spec against a model checker to find any logical errors
   - Verify zero unreachable states (all reachable code is used)
   - Verify no deadlocks (all execution paths terminate or explicitly loop)
   - Verify all invariants hold in all reachable states
   - Example: K1 Schema Validation: verify that no valid schema accepts invalid payload, and no invalid schema rejects valid payload

3. **Property-Based Testing (Hypothesis or equivalent)**
   - Generate random inputs across the full domain
   - Verify component behavior matches specification for all inputs
   - Use symbolic execution where possible (e.g., fuzz seccomp rules)
   - Minimum 10,000 test cases per property, 100+ properties per component
   - Example: Sandbox isolation: 10k random code payloads, verify zero escapes

4. **Unit Testing (pytest)**
   - 100% code coverage (every branch tested)
   - Every failure mode has a specific test
   - Every state transition has a test
   - Example: KernelContext: test IDLE→ENTERING, ENTERING→ACTIVE, ACTIVE→EXITING, EXITING→IDLE, and all error transitions

5. **Integration Testing**
   - End-to-end test of component with all dependencies
   - Test failure scenarios in integrated environment (e.g., Postgres unavailable during K6 WAL write)
   - Verify latency budgets are met under load
   - Example: K1 Schema Validation integrated with ICD schema registry: submit 1000 payloads per second, verify validation < 1ms p99

6. **Independent Verification (Dissimilar Channel)**
   - Second team or tool re-implements critical safety checks independently
   - Example: Sandbox: security team independently reviews seccomp rules against Linux kernel security guide; separate fuzzing tool (not the one that built the sandbox) attempts 100+ known escape techniques
   - Example: Kernel WAL: separate audit log analyzer re-reads Postgres audit trail and verifies consistency with in-memory state
   - Dissimilar channel must be truly independent (different team, different tools, different methodology)

7. **FMEA with Residual Risk Register**
   - Failure Mode Effects Analysis: enumerate every way the component can fail
   - For each failure mode, identify: severity (critical/major/minor), likelihood (high/medium/low), existing mitigation, residual risk
   - Residual risk (unmitigated failures) must be explicitly accepted by responsible engineer with documented justification
   - Example: K8 Eval Gates: failure mode "predicate timeout" has existing mitigation (timeout handler, fallback to deny), residual risk "timeout handler itself times out" is accepted with justification "catch-all timeout at Kernel level enforces outer bound"

8. **Living RTM Chain**
   - Every requirement traces to a design decision (ADR), code implementation, and test
   - RTM is auto-generated from decorators; CI blocks merge if links are broken
   - Example: "K1 schema validation" requirement → ICD-006/007 interface spec → K1 implementation in Kernel library → unit test for K1 → property-based test for K1

9. **Executive Sign-off**
   - Responsible engineer signs off on all residual risks
   - Documented in safety case (claims → evidence → context)
   - Sign-off is binding; any changes require re-signature

### SIL-2 Verification Requirements

SIL-2 components (Core, Engine, Storage, API layer) require moderate rigor:

1. **Property-Based Testing (Hypothesis)**
   - 1000+ test cases per property (vs. 10000+ for SIL-3)
   - Minimum 50 properties per component
   - Example: Intent Classifier: 1000 random user intents, verify each classified as one of {direct_solve, team_spawn, clarify}

2. **Unit Testing (pytest)**
   - Minimum 80% code coverage (vs. 100% for SIL-3)
   - Critical paths (happy path + all error paths) must be covered
   - Example: Goal Decomposer: test valid goal hierarchy, test goal that violates constraint, test goal that exceeds depth limit

3. **Integration Testing**
   - Test component with real dependencies (not mocks)
   - Latency budgets verified under realistic load
   - Failure scenarios tested (e.g., Postgres connection timeout)
   - Example: APS Controller with Topology Manager: submit morphogenetic goal, verify APS correctly identifies T3, topology manager spawns team correctly

4. **FMEA with Mitigations**
   - Failure modes and mitigations identified
   - Residual risk register; all residual risks have documented mitigation or explicit acceptance
   - Example: Main Lane "task hangs" failure mode has mitigation "timeout at 30 min, checkpoint resume" and residual risk "timeout handler crashes" with mitigation "outer timeout at 40 min"

5. **RTM Chain Completeness**
   - Every requirement has design decision, code, and test
   - RTM is living, auto-checked in CI
   - Example: "Conversation Interface message delivery" requirement → ICD-001 spec → Conversation component implementation → integration test

### SIL-1 Verification Requirements

SIL-1 components (Console, Config non-dangerous keys, Observability dashboards) require lightweight rigor:

1. **Unit Testing (pytest)**
   - Minimum 70% code coverage
   - Happy path + common error paths tested
   - Example: Chat Interface: test message send, test WebSocket connect, test disconnect

2. **Integration Testing**
   - Test component with real dependencies
   - Example: Chat Interface with WebSocket server: send message, verify it reaches server

3. **RTM Chain Completeness**
   - Requirements linked to code and tests
   - Example: "Chat Interface message send" requirement → Chat Interface component → unit test

---

## Interface SIL Inheritance Rules

Every interface in the ICD inherits the SIL of its higher-rated endpoint. The inheritance rule is:

**Interface SIL = max(SIL(from_component), SIL(to_component))**

This ensures that if a high-SIL component calls a low-SIL component, the interface is treated as high-SIL (the low-SIL component must meet higher verification standards for that particular call).

Examples from ICD v0.1:

| ICD # | From | To | From SIL | To SIL | Interface SIL | Justification |
|---|---|---|---|---|---|---|
| ICD-006 | Core (SIL-2) | Kernel (SIL-3) | 2 | 3 | **3** | Kernel is SIL-3; interface inherits SIL-3. Core's call to K1–K8 gates must meet SIL-3 rigor (formal spec of gate contracts, property-based input fuzzing). |
| ICD-022 | MCP Registry (SIL-2) | Sandbox (SIL-3) | 2 | 3 | **3** | Sandbox is SIL-3; interface inherits SIL-3. MCP's gRPC call to Sandbox must have SIL-3 error handling (timeouts, retries, isolation guarantees formally specified). |
| ICD-030 | Egress (SIL-3) | Claude API (SIL-2) | 3 | 2 | **3** | Egress is SIL-3; interface inherits SIL-3. Egress's call to Claude API must enforce SIL-3 contracts (rate limits, response redaction, timeout budgets formally enforced). |
| ICD-041 | Memory System (SIL-2) | Redis (SIL-2) | 2 | 2 | **2** | Both SIL-2; interface is SIL-2. Memory's calls to Redis must meet SIL-2 rigor (property-based tests of key isolation, pub/sub delivery, queue ordering). |

---

## SIL Boundary Crossings

When a component of one SIL level calls a component of a different SIL level, the interface is a "boundary crossing." Extra verification is required to ensure that the lower-SIL component does not compromise the higher-SIL component.

### SIL-3 → SIL-2 Boundaries (Higher calling Lower)

These are the most critical boundaries. The SIL-3 component depends on the SIL-2 component's correctness, so the interface must be designed defensively:

- **Contract:** SIL-2 component must return result that SIL-3 component can validate before use
- **Error handling:** SIL-3 component must assume SIL-2 component might fail and have explicit recovery
- **Idempotency:** If SIL-2 component fails mid-operation, SIL-3 component must be able to retry safely
- **Isolation:** Failure in SIL-2 component must not corrupt SIL-3 state

Examples:

1. **Kernel (SIL-3) → Intent Classifier (SIL-2)** [ICD-008]
   - Kernel invokes Intent Classifier as part of boundary crossing
   - If Intent Classifier times out (SIL-2 failure), Kernel must timeout and halt the operation (not propagate timeout to downstream)
   - Verification: Property-based tests of Kernel's timeout handling; test that SIL-2 timeout is caught and converted to SIL-3 exception

2. **Egress (SIL-3) → PostgreSQL (SIL-2)** [ICD-045]
   - Egress stores audit trail in Postgres (critical for SIL-3 egress audit)
   - If Postgres write fails, Egress must fail safely (not silently drop audit record)
   - Verification: Explicit test of Postgres connection failure during egress audit write; verify Egress halts and raises exception

3. **Sandbox (SIL-3) → MCP (SIL-2)** [ICD-022]
   - Sandbox gets tool request from MCP via gRPC
   - If MCP sends malformed request (SIL-2 bug), Sandbox must validate and reject (not execute invalid code)
   - Verification: Property-based fuzzing of MCP request format; Sandbox must reject requests that don't match proto schema

### SIL-2 → SIL-3 Boundaries (Lower calling Higher)

These boundaries are inherently safe if SIL-3 component is defensive. SIL-2 component calling SIL-3 is expected to happen (e.g., Core calling Kernel gates).

- **Contract:** SIL-3 component must be re-entrant and handle any input
- **Timeout:** SIL-2 caller must have timeout budget; SIL-3 component must respect timeout
- **Isolation:** Failure in SIL-2 caller must not corrupt SIL-3 state

Examples:

1. **Intent Classifier (SIL-2) → Kernel (SIL-3)** [ICD-006]
   - Intent Classifier invokes Kernel gates as part of boundary crossing
   - Kernel must accept any incoming payload, validate it, and respond with clear pass/fail
   - Verification: Property-based fuzzing of Intent Classifier inputs; Kernel must handle all inputs correctly (SIL-3 guarantees)

2. **Core (SIL-2) → KMS (SIL-3)** [ICD-044]
   - Core requests credential from KMS as part of Egress setup
   - KMS must be bulletproof (never leak credentials, always audit access)
   - Verification: Property-based tests of KMS request/response; verify credentials never appear in logs or responses outside expected channels

---

## Compliance Notes

### Rules for Using This Matrix During Development

1. **Every component is assigned a SIL level.** No component is "not yet classified." If a component exists in the SAD, it is in this matrix.

2. **Verification methods are binding.** A SIL-3 component that is implemented with only unit tests (no formal spec, no model checking) is non-compliant. CI must check compliance.

3. **SIL inheritance is enforced at interfaces.** An interface defined in ICD must be implemented with at least the interface's SIL-level rigor. If ICD-022 is SIL-3, the gRPC proto schema, error handling, and timeout behavior must be formally specified and model-checked.

4. **Boundary crossings require explicit verification.** Every interface crossing a SIL boundary (e.g., Kernel → Intent Classifier) must have dedicated integration tests in the test suite named `test_sil_boundary_[component]_[component].py`.

5. **Residual risks are documented.** If a SIL-3 or SIL-2 component has a failure mode that cannot be mitigated, the residual risk must be documented in the FMEA appendix with:
   - Failure mode description
   - Why it cannot be eliminated
   - Acceptance by responsible engineer (name, date, signature)
   - Monitoring strategy (how the system detects if residual risk occurs)

6. **RTM is continuously validated.** Every code change must preserve RTM completeness. CI gate: `python scripts/rtm_check.py` must pass before merge. Any broken link (requirement → code → test) blocks the merge.

7. **FMEA is living.** As new failure modes are discovered (in tests, in production), they are added to FMEA with mitigation or acceptance. FMEA review happens quarterly.

8. **Dissimilar verification for SIL-3 requires independence.** The dissimilar channel (independent re-implementation, separate tool, security team review) must be truly independent:
   - Different team writes the verification (not the original component developer)
   - Different tools/languages used (e.g., K1 validation verified by hand-written state machine, not by re-running Hypothesis)
   - Different methodology (e.g., Sandbox verified by both fuzzing and security code review, not just fuzzing)

9. **Sign-offs are binding.** Responsible engineer sign-off on residual risk register is binding. Any change to residual risk acceptance requires re-signature.

10. **SIL downgrades are forbidden.** Once a component is assigned SIL-3 (e.g., Kernel), it cannot be downgraded to SIL-2 without architectural review and written justification. SIL upgrades (e.g., SIL-1 → SIL-2) require only task addition, no re-design.

---

## Appendix A: Component Criticality Summary

| SIL | Count | Components | Total Verification Effort (person-weeks) |
|---|---|---|---|
| **SIL-3** | 9 | Kernel (KCTX, K1–K8), Sandbox (SEXEC, SSEC), Egress (L7/L3), KMS | ~180 (formal spec, model-check, dissimilar verify, property-based tests) |
| **SIL-2** | 35 | Core layer (Intent, Goals, APS, Topology, Memory, Config), Engine layer (Lanes, MCP, Workflow, Policy), Storage (PG, Redis, Chroma, OLlama), API (JWT, Auth, WebSocket, Event Bus, Logs, Dashboard), Authentik, LLM integration | ~140 (property-based tests, integration, FMEA, RTM) |
| **SIL-1** | 10 | Console UI (Chat, Topology Viz, Goal Viz, Audit Viewer), Cron scheduling, standard Config keys | ~20 (unit + integration tests, RTM) |

**Total Verification Effort:** ~340 person-weeks (6.5 person-years of effort). This is a major undertaking and justifies the spiral execution model (thin vertical slice early, validate loop before backfilling).

---

## Appendix B: Glossary of SIL Terms (Per IEC 61508)

- **Failure Mode:** A way a component can fail (e.g., "K1 schema validation returns false positive")
- **Failure Consequence:** What happens to the system if failure occurs (e.g., "malformed payload reaches downstream, causes incorrect goal")
- **Mitigation:** Action taken to prevent or recover from failure (e.g., "K2 permission gate validates after K1 passes")
- **Residual Risk:** Failure that persists even after mitigations are applied; must be explicitly accepted
- **SIL Assignment:** The Safety Integrity Level assigned to a component based on failure consequence severity
- **Verification Method:** Technique used to confirm component meets its SIL level (formal spec, model checking, testing, review)
- **Interface SIL:** The SIL level of a boundary crossing (inherited from higher-SIL endpoint)
- **Boundary Crossing:** A call from one component to another (e.g., Core → Kernel); every crossing is wrapped by KernelContext

---

## Appendix C: References

- ISO 26262: Functional Safety — Electrical/Electronic Systems (automotive standard, adapted)
- IEC 61508: Functional Safety of Electrical/Electronic/Programmable Electronic Safety-Related Systems
- Allen, S. P. (2026). *Informational Monism, Morphogenetic Agency, and Goal-Specification Engineering: A Unified Framework.* v2.0
- Holly Grace README.md: Meta Procedure, Task Derivation Protocol, Execution Model, Designer's Diary
- Component Behavior Specifications v1.0: SIL-3 state machines (Kernel, Sandbox, Egress)
- Interface Control Document v0.1: 49 interface contracts with SIL assignments
- System Architecture Document v0.1.0.5: Component structure and connections

---

**Document Prepared By:** Claude Opus 4.6 Agent (Design & Safety) | **Date:** 17 February 2026 | **Status:** DRAFT — Awaiting Responsible Engineer Review | **Next Action:** Phase A spiral gate (validate Kernel SIL-3 enforcement loop end-to-end before backfilling)
