# FMEA — Kernel Invariant Desynchronization

**Document ID:** FMEA-K001–K109
**Task ref:** Task 13.1
**Input:** Behavior Spec §1.1–1.9 (KernelContext + K1–K8 gates)
**Version:** 0.1.0
**Date:** 2026-02-19
**Scope:** All eight kernel invariant-enforcement gates (K1–K8) plus the
KernelContext state machine (K001) that orchestrates them.

---

## Purpose

This worksheet documents the Failure Mode and Effects Analysis for the
Holly Grace kernel layer.  The specific failure class under examination is
**kernel invariant desynchronization** — any condition in which the system
believes an invariant has been satisfied (gate passed) when the underlying
condition it guards has in fact been violated, or vice versa.

Each gate is analysed independently.  For each gate at least two failure
modes are documented following IEC 61508 Part 3 FMEA conventions:

| Field | Definition |
|-------|-----------|
| **FM-ID** | Unique failure-mode identifier |
| **Mode** | Brief description of the failure |
| **Cause** | Root cause (hardware, software, design, operational) |
| **Effect** | System-level consequence if the failure occurs undetected |
| **S** | Severity 1–5 (5 = catastrophic) |
| **O** | Occurrence 1–5 (5 = likely per deployment cycle) |
| **D** | Detectability 1–5 (5 = undetectable until propagation) |
| **RPN** | Risk Priority Number = S × O × D |
| **Mitigation** | Design or operational control |
| **Residual** | Post-mitigation risk statement |

**Severity scale:**

| S | Label | Meaning |
|---|-------|---------|
| 5 | Catastrophic | Security breach, data exfiltration, unauthorised boundary crossing |
| 4 | Critical | Invariant bypass; audit trail gap; silent enforcement failure |
| 3 | Significant | Service disruption; partial mitigation failure; delayed detection |
| 2 | Marginal | Degraded performance; increased latency; warning-only |
| 1 | Minor | Logging gap; cosmetic; no functional impact |

**Occurrence scale:**

| O | Label | Probability per release cycle |
|---|-------|-------------------------------|
| 5 | Frequent | > 50 % |
| 4 | Occasional | 10 – 50 % |
| 3 | Possible | 1 – 10 % |
| 2 | Unlikely | 0.1 – 1 % |
| 1 | Rare | < 0.1 % |

**Detectability scale (1 = easy to detect, 5 = hard to detect):**

| D | Label | Meaning |
|---|-------|---------|
| 1 | Immediate | Exception raised; alarm fires synchronously |
| 2 | Fast | Monitoring alert within minutes |
| 3 | Delayed | Log analysis within hours |
| 4 | Forensic | Detectable only via deep post-incident forensics |
| 5 | Undetectable | No observable signal until cascading failure |

---

## 1. KernelContext — State-Machine Gate (FMEA-K001)

**Invariant:** Every boundary crossing must hold an active KernelContext in
state ACTIVE, implying all eight gates have evaluated successfully (Behavior
Spec §1.1 invariant 5).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-001-1 | Re-entrant context entry from same async task after cancellation / retry | `asyncio.Task` cancelled mid-ENTERING; retry logic creates second context without checking existing state | Two concurrent contexts on same task; invariant 2 (re-entrancy prevention) silently violated | 4 | 2 | 3 | 24 | Enforce single-context guard via task-local storage; raise `RuntimeError` on re-entry; property-based state-machine test | Low — guard detectable in test |
| FM-001-2 | FAULTED state transitions silently to IDLE without exception propagation | `__aexit__` exception handler catches base `Exception` before caller sees it | Caller believes crossing succeeded; no WAL entry written; audit gap | 5 | 2 | 4 | 40 | Never catch base `Exception` in `__aexit__`; propagate all kernel exceptions; test that each gate failure surfaces to caller | Medium — requires explicit exception propagation test |
| FM-001-3 | Async task cancellation during ACTIVE state prevents EXITING cleanup | `asyncio.CancelledError` raised while awaiting inside boundary; `finally` block skipped if not structured correctly | WAL entry never written; correlation ID trace broken; K6 invariant violated | 4 | 3 | 3 | 36 | Use `asyncio.shield` on WAL writes; defer cancellation via `contextlib.AsyncExitStack`; cancel test in CI | Medium — requires explicit cancellation harness |

---

## 2. K1 — Schema Validation (FMEA-K102)

**Invariant:** No payload crosses a boundary unless it conforms to the
registered ICD JSON Schema for that boundary (Behavior Spec §1.2).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-102-1 | SchemaRegistry serves stale schema after in-memory state desynchronisation | `SchemaRegistry._schemas` dict mutated by test teardown leaking into production process (class-level singleton); or registry not cleared between unit-test isolation failures | Payloads validated against wrong schema version; malformed data crosses boundary | 4 | 2 | 3 | 24 | `SchemaRegistry.register()` is idempotent-locked (`SchemaAlreadyRegisteredError`); `clear()` is test-only and guarded; CI isolates tests via `autouse` fixture | Low — lock prevents silent mutation |
| FM-102-2 | Depth-guard ceiling arithmetic allows adversarial nesting to reach validator | `_measure_depth` short-circuits at `_ceiling = max_depth + 1`; edge case at exact boundary (`depth == max_depth + 1`) not blocked before passing to `Draft202012Validator` | Deeply nested payload reaches JSON Schema validator; ReDoS or exponential validation cost | 4 | 1 | 2 | 8 | `_ceiling = max_depth + 1` short-circuits at or above ceiling; `depth > max_depth` check fires before validator; property-based test with depth == max_depth + 1 | Negligible — off-by-one validated by property test |
| FM-102-3 | Payload immutability guard bypassed when validator side-effects modify payload in-place | Third-party `jsonschema` validator implementation mutates payload during `iter_errors()` (observed in format validators with `default` injection) | Post-validation state diverges from validated state; downstream sees mutated payload that was never schema-checked in its final form | 5 | 1 | 4 | 20 | `copy.deepcopy(payload)` snapshot taken before validator runs; `payload != payload_before` raises `KernelInvariantError`; test via mock validator that injects key | Low — explicit check with non-strippable exception |

---

## 3. K2 — Permission Gates (FMEA-K103)

**Invariant:** No operation executes without a valid, non-expired,
non-revoked JWT whose granted permissions are a superset of required
permissions (Behavior Spec §1.3).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-103-1 | JWKS public-key cache serves revoked signing key after key rotation | `jwks_client` caches JWKS with long TTL; key rotated but cache not invalidated; old key still validates signatures | Tokens signed with the rotated (potentially compromised) key are accepted | 5 | 2 | 4 | 40 | Cache TTL ≤ 300 s; force JWKS refresh on first `InvalidSignatureError`; alert on rotation events; revocation cache entry per `kid` | Medium — TTL window remains |
| FM-103-2 | Redis revocation cache unavailable causes fail-open access | Network partition between K2 host and Redis; `redis.get(jti)` raises `ConnectionError`; handler catches broadly and falls through | Previously revoked tokens are accepted during Redis outage | 5 | 2 | 2 | 20 | Explicit `RevocationCacheError` on Redis failure; fail-closed policy (deny); circuit breaker for Redis; SLA 99.9% required | Low — fail-closed enforced in code |
| FM-103-3 | Permission grant race condition: role changed between token issue and validation | User's role elevated or demoted after JWT minted but before 15-minute token expiry; stale claims used | User retains former permissions for up to JWT TTL; RBAC desynchronised with IAM | 4 | 3 | 3 | 36 | Short JWT TTL (≤ 15 min); role change triggers token revocation via `jti` in Redis; K2 refreshes permissions from Authentik once per crossing | Medium — TTL window; requires revocation discipline |

---

## 4. K3 — Bounds Checking (FMEA-K104)

**Invariant:** No operation consumes resources beyond the configured budget
for its (tenant, resource_type) pair (Behavior Spec §1.4).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-104-1 | TOCTOU race in distributed usage counter | Multiple concurrent requests each read usage U, each check U + Δ ≤ budget, each increment; final usage = U + nΔ > budget | Budget exceeded by factor of concurrency degree; cost overrun; denial-of-service to other tenants | 4 | 3 | 2 | 24 | Redis atomic `INCRBY` + `GET` in Lua script (single round-trip, serialised); counter pre-decrement on failure path; property test: N concurrent requests, sum ≤ budget | Low — atomic Redis operation |
| FM-104-2 | Usage counter negative due to Redis counter corruption or decrement bug | Decrement on failure path subtracts more than was incremented; Redis flushes; data corruption | `current_usage` negative; `usage + request ≤ budget` always true; budget check passes unconditionally | 4 | 1 | 3 | 12 | `UsageTrackingError` on negative counter; minimum-floor assertion after read; Redis AOF persistence; counter schema validation on read | Low — floor guard catches immediately |
| FM-104-3 | Integer overflow in usage accumulation on extreme long-running tenants | `usage + requested` overflows Python `int` (unlikely in CPython; plausible in fixed-width FFI bindings) | Wrap-around causes check `overflow_value ≤ budget` to pass when actual accumulated usage exceeds budget | 3 | 1 | 4 | 12 | Explicit `OverflowError` handler; usage value capped at `sys.maxsize`; Redis value is string, parsed to Python `int`; CPython `int` is arbitrary precision | Low — CPython unlimited int eliminates overflow |

---

## 5. K4 — Trace Injection (FMEA-K105)

**Invariant:** Every boundary crossing carries an immutable tenant_id and
a correlation_id from the moment of K4 injection; no downstream code can
alter either field (Behavior Spec §1.5 invariant 3).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-105-1 | Correlation ID not propagated across `asyncio.Task` creation boundary | `asyncio.create_task()` creates child task without copying parent `contextvars.Context`; child crosses boundary with null or self-generated correlation ID | Distributed trace fragmented; parent and child spans cannot be correlated; HITL approval flow loses conversation thread | 3 | 3 | 3 | 27 | Use `asyncio.create_task(coro, context=copy_context())` in all spawn sites; linter rule banning bare `create_task` without context arg; test: parent correlation_id propagated to child | Medium — requires spawn-site discipline |
| FM-105-2 | Tenant ID mutated by non-kernel code after K4 injection | Context object passed by reference; downstream handler sets `context.tenant_id = "admin"` (privilege escalation) | Audit WAL records wrong tenant; tenant isolation broken; cross-tenant data leakage | 5 | 2 | 4 | 40 | `KernelContext` fields are read-only after ACTIVE; setattr raises `FrozenContextError`; property test: any post-K4 mutation attempt raises | Medium — requires frozen dataclass implementation |
| FM-105-3 | Span context desynchronised between OTEL trace and KernelContext correlation_id | OTEL SDK generates its own trace ID independent of K4-injected UUID; two trace identifiers coexist; log correlation breaks | Investigation requires manual cross-reference of two trace IDs per event; MTTR increases | 2 | 3 | 3 | 18 | K4 writes correlation_id into OTEL span baggage (`baggage.set_baggage`); OTEL span's `trace_id` recorded alongside `correlation_id` in WAL; documented mapping | Low — cosmetic after mapping documented |

---

## 6. K5 — Idempotency Key Generation (FMEA-K106)

**Invariant:** For any two logically identical operations (same payload and
context), K5 produces the same idempotency key; for any two distinct
operations the keys differ (Behavior Spec §1.6 RFC 8785 invariant).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-106-1 | RFC 8785 canonicalisation produces different bytes for logically equivalent Unicode | Python's `json.dumps(sort_keys=True)` does not apply Unicode NFC normalisation; `café` and `cafe\u0301` produce different SHA-256 hashes | Idempotent retries treated as new operations; duplicate side-effects (double charge, double goal commit) | 4 | 2 | 4 | 32 | Apply `unicodedata.normalize("NFC", …)` to all string leaves before canonicalisation; RFC 8785 §3.2.2 compliance test suite with known vectors | Low — NFC normalisation standardises inputs |
| FM-106-2 | Idempotency key computed from pre-validation payload snapshot | K5 runs before K1 in gate ordering; payload not yet validated; a mutation applied by the caller between K5 and K1 produces key for a state that was never schema-checked | Two distinct logical payloads share the same idempotency key if attacker can replay a key-matched payload | 4 | 1 | 4 | 16 | Gate ordering enforced: K1 runs first; K5 receives the same payload object as K1 (no intermediate mutation window); payload immutability guard (K1 FM-102-3) | Low — gate ordering enforced |
| FM-106-3 | Key collision probability non-negligible in very high-volume tenant | Birthday bound for SHA-256 (2^128 collision probability at 2^64 messages); in a petabyte-scale deployment | Idempotent retry incorrectly de-duplicated with different operation; data corruption | 2 | 1 | 5 | 10 | SHA-256 collision probability negligible (< 10^-18 at 10^12 messages); collision counter metric alerts at any duplicate; architecture review required if volume approaches 10^15 | Low — SHA-256 is collision-resistant at operational scale |

---

## 7. K6 — Durability / WAL (FMEA-K107)

**Invariant:** Every boundary crossing that reaches EXITING state produces
exactly one append-only WAL entry with non-null correlation_id, tenant_id,
and timestamp before the context returns to IDLE (Behavior Spec §1.7).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-107-1 | WAL entry written for operation that subsequently fails atomically | WAL write occurs before operation commit; Postgres transaction for the operation rolls back; WAL entry remains | Audit log shows operation as executed when it was never committed; forensic investigation misleads responders | 4 | 2 | 3 | 24 | WAL write and operation write wrapped in same Postgres transaction; on rollback both undone; or WAL uses explicit status field (`COMMITTED`/`ROLLED_BACK`) updated post-commit | Low — transaction coupling or two-phase WAL |
| FM-107-2 | PII redaction regex fails to match new field added to operation schema | Schema evolves; new field `user_email_secondary` added; redaction pattern only matches `user_email`; new field logged in plain text | PII leak in audit log; GDPR Article 83 fine exposure; data subject rights violation | 5 | 3 | 4 | 60 | Schema-driven redaction (list derived from ICD field annotations, not regex); CI test that adds new field and asserts redaction; redaction coverage metric | Medium — schema-driven redaction eliminates pattern-maintenance |
| FM-107-3 | WAL partition rotation makes entries inaccessible before legal retention period | DBA rotates partition or archives to cold storage after 90 days; retention requirement is 7 years (financial audit trail) | Historical boundary crossings unrecoverable; compliance failure | 3 | 2 | 3 | 18 | Retention policy codified in Postgres partition policy (7 years minimum); IaC enforces policy; quarterly compliance check in CI | Low — IaC enforcement |

---

## 8. K7 — HITL Gates (FMEA-K108)

**Invariant:** Any operation whose confidence score is below the
configured threshold is blocked until a human reviewer issues an approval
within the timeout window (Behavior Spec §1.8).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-108-1 | Confidence evaluator returns stale cached score for changed operation context | Result cache keyed on operation type only; same type, different payload; cache hit returns score from prior distinct operation | High-risk payload treated as low-risk (score inherited from benign prior call); HITL gate bypassed for operation that requires human review | 5 | 2 | 4 | 40 | Cache key includes K5 idempotency key (payload hash); cache TTL ≤ operation TTL; invalidate on context change; test: two distinct payloads never share cache entry | Low — payload-keyed cache |
| FM-108-2 | Human approval WebSocket partition causes indefinite blocking | Network partition between approval service and reviewer client; approval sent but never received; no replay or ACK mechanism | Operation blocked permanently; system livelock on critical path; timeout not triggered if WebSocket connection appears alive | 4 | 2 | 3 | 24 | Heartbeat on WebSocket (30 s interval); missing heartbeat = connection dead = restart; `ApprovalTimeout` fires after 24 h regardless; at-least-once delivery via persistent approval queue (Postgres) | Low — persistent queue + timeout backstop |
| FM-108-3 | Adversarial payload engineered to score marginally above confidence threshold | Attacker crafts operation that minimises semantic similarity to high-risk patterns while achieving desired harmful effect; confidence score = threshold + ε | HITL gate not triggered for operation that should require human oversight; potentially harmful operation executes autonomously | 5 | 2 | 5 | 50 | Threshold set conservatively (e.g., 0.95 vs 0.85 lower bound); periodic red-team evaluation of threshold boundary; K8 eval gate provides independent second check; no single gate bypasses system | Medium — requires ongoing red-team discipline |

---

## 9. K8 — Eval Gates (FMEA-K109)

**Invariant:** No operation output is returned to the caller unless the
registered eval predicate for that output type evaluates to True within
the timeout window (Behavior Spec §1.9).

| FM-ID | Mode | Cause | Effect | S | O | D | RPN | Mitigation | Residual |
|-------|------|-------|--------|---|---|---|-----|------------|---------|
| FM-109-1 | Predicate registry loaded at import time; stale after schema migration | `PredicateRegistry` is a process-global singleton populated at startup; predicate updated in DB but process not restarted; old predicate enforced | Outputs evaluated against outdated constraint; violating output passes (if predicate was tightened) or valid output blocked (if loosened) | 4 | 2 | 3 | 24 | Predicates versioned and immutable once registered (same pattern as `SchemaRegistry`); schema migrations bump predicate version; rolling restart on predicate change; `PredicateAlreadyRegisteredError` guards hot-swap | Low — immutability guard same as K1 |
| FM-109-2 | Predicate evaluation timeout leaves gate in partially-evaluated state | Predicate invokes external service; timeout fires mid-evaluation; cleanup code mutates shared output object before `TimeoutError` propagates | Output object modified by partial evaluation; caller receives corrupted output if timeout caught too broadly upstream | 4 | 1 | 3 | 12 | Predicate receives deep-copy of output (analogous to K1 payload snapshot); output passed by value; timeout raises `TimeoutError` before modified copy returned; `KernelInvariantError` if output modified post-evaluation | Low — copy-on-evaluate pattern |
| FM-109-3 | Output hash computed from different object instance than what predicate evaluates | Predicate receives `output` reference; serialisation for hashing uses `json.dumps(output)`; output is mutable dict; predicate mutates output between hash capture and predicate call | `output_hash` in `EvalGateFailure` does not correspond to the object that was actually evaluated; forensic trail broken | 3 | 2 | 4 | 24 | Hash captured from deep-copy before predicate called; predicate receives same deep-copy; hash and predicate operate on identical object; post-predicate equality check analogous to K1 | Low — copy-first pattern |

---

## Summary Table

| Gate | FMEA-ID | Highest RPN | Mode | Action Required |
|------|---------|-------------|------|-----------------|
| KernelContext | FMEA-K001 | 40 | FM-001-2: silent FAULTED→IDLE | Enforce exception propagation in `__aexit__` |
| K1 Schema | FMEA-K102 | 24 | FM-102-1: stale registry | Existing `SchemaAlreadyRegisteredError` lock |
| K2 Permissions | FMEA-K103 | 40 | FM-103-1: stale JWKS key | Short cache TTL + forced refresh on signature error |
| K3 Bounds | FMEA-K104 | 24 | FM-104-1: TOCTOU counter race | Atomic Redis Lua script |
| K4 Trace | FMEA-K105 | 40 | FM-105-2: tenant ID mutation | Frozen KernelContext fields after ACTIVE |
| K5 Idempotency | FMEA-K106 | 32 | FM-106-1: Unicode normalisation | NFC normalisation before canonicalisation |
| K6 WAL | FMEA-K107 | 60 | FM-107-2: PII redaction gap | Schema-driven redaction (not regex) |
| K7 HITL | FMEA-K108 | 50 | FM-108-3: adversarial threshold bypass | Conservative threshold + K8 independent second check |
| K8 Eval | FMEA-K109 | 24 | FM-109-1: stale predicate | Predicate versioning + immutability guard |

**Open high-RPN items (RPN ≥ 40):**

| FM-ID | RPN | Owner | Due |
|-------|-----|-------|-----|
| FM-001-2 | 40 | Kernel team | Slice 3 |
| FM-103-1 | 40 | Auth team | Slice 3 |
| FM-105-2 | 40 | Kernel team | Slice 3 |
| FM-107-2 | 60 | Data team | Slice 3 |
| FM-108-3 | 50 | Safety team | Slice 4 (red-team) |

---

## Acceptance Verification

| Criterion | Status |
|-----------|--------|
| All 8 kernel invariant gates (K1–K8) analysed | ✓ (sections 2–9) |
| KernelContext state machine analysed | ✓ (section 1) |
| Each gate has ≥ 2 failure modes | ✓ (all gates have 3 modes) |
| Each mode has severity, occurrence, detectability | ✓ |
| Each mode has mitigations | ✓ |
| RPN computed for all modes | ✓ |
| High-RPN actions identified | ✓ (summary table) |
