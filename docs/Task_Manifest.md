# Holly Grace — Task Manifest

**All 15 spiral slices, fully decomposed.**

Generated: 17 February 2026 | Protocol: Task Derivation Protocol v1.0 | Source: README Meta Procedure + 86-step Roadmap

---

## Summary

| Slice | Phase | Steps | Count | SIL | MP Focus | Gate | Tasks |
|---|---|---|---|---|---|---|---|
| 1 | A (spiral) | 1, 2, 3, 3a | 4 | 2–3 | 8, 9, 1, 2 | Spiral gate: enforcement loop e2e | 39 |
| 2 | A (backfill) | 4–11 | 9 | 2 | 8, 9, 3, 4 | Phase A: arch enforcement complete | 38 |
| 3 | B | 12–21 | 10 | 3 | 5, 6, 7, 12 | Phase B: kernel verified SIL-3 | 72 |
| 4 | C | 22–26 | 5 | 2 | 5, 6, 9 | Phase C: storage tested | 28 |
| 5 | D | 27–33 | 7 | 2–3 | 6, 12, 9 | Phase D: safety case for infra | 42 |
| 6 | E | 34–40 | 7 | 2 | 1, 8, 10, 11 | Phase E: core integration tested | 48 |
| 7 | F | 41–45 | 5 | 2 | 8, 9, 6 | Phase F: engine e2e tested | 32 |
| 8 | G | 46–50 | 5 | 3 | 6, 7, 12 | Phase G: sandbox SIL-3 pass | 38 |
| 9 | H | 51–56 | 6 | 2 | 5, 6, 12 | Phase H: API + auth tested | 36 |
| 10 | I | 57–61 | 5 | 2 | 5, 9 | Phase I: observability live | 24 |
| 11 | J | 62–65 | 4 | 2 | 1, 10, 11 | Phase J: agents + constitution exec | 34 |
| 12 | K | 66–69 | 4 | 2 | 10, 4, 9 | Phase K: eval pipeline gates merges | 26 |
| 13 | L | 70–72 | 3 | 1 | 5, 9 | Phase L: config operational | 14 |
| 14 | M | 73–78 | 6 | 1 | 5, 9 | Phase M: console functional | 28 |
| 15 | N | 79–86 | 8 | 1–3 | 14, 12, 13 | Phase N: release safety case | 46 |
| | | **Total** | **86** | | | | **545** |

---

## Slice 1 — Phase A Spiral (Steps 1, 2, 3, 3a)

**Purpose:** Build the architecture-as-code skeleton and prove the enforcement loop works end-to-end with a thin kernel slice.

### Applicability Matrix

| MP | Step 1 Extract | Step 2 Registry | Step 3 Decorators | Step 3a Gate |
|---|---|---|---|---|
| 1 Ontological | ✓ | ✓ | ✓ | ✓ |
| 2 Arch Desc | ✓ | ✓ | ✓ | ✓ |
| 3 Quality | ✓ | ✓ | ✓ | ✓ |
| 4 Lifecycle | — | — | — | ✓ |
| 5 SIL | ✓ | ✓ | ✓ | ✓ |
| 6 FMEA | — | ✓ | ✓ | ✓ |
| 7 TLA+ | — | — | — | ✓ |
| 8 Arch-as-Code | ✓ | ✓ | ✓ | ✓ |
| 9 Chain | ✓ | ✓ | ✓ | ✓ |
| 10 EDDOps | — | — | — | ✓ |
| 11 Constitution | — | — | — | — |
| 12 Defense | — | — | ✓ | ✓ |
| 13 Spiral | — | — | — | ✓ |
| 14 Deploy | — | — | — | — |

### Tasks

#### Step 1 — Extract (SAD → `architecture.yaml`)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 1.1 | 1 | Map SAD terms to monograph definitions | SAD, monograph glossary | Traceability annotations in YAML | Review | Every YAML concept traces to a monograph section |
| 1.2 | 2 | Preserve 42010 viewpoint structure | SAD (viewpoints) | Viewpoint-aware YAML schema | Review | Viewpoints survive round-trip SAD → YAML → SAD |
| 1.3 | 3 | Document quality attribute for extraction design | — | ADR citing maintainability | Review | ADR exists and cites 25010 attribute |
| 1.4 | 5 | Assign SIL to extraction pipeline | SIL matrix | SIL-2 designation | Review | SIL recorded in matrix |
| 1.5 | 8 | Write SAD parser (mermaid → AST) | SAD mermaid file | Parser module | Integration test | Parses current SAD without error |
| 1.6 | 8 | Define `architecture.yaml` schema | SAD structure | JSON Schema / Pydantic model | Property-based test | Schema validates current SAD output |
| 1.7 | 8 | Build extraction pipeline | Parser + schema | `architecture.yaml` | Property-based test | YAML round-trips without information loss |
| 1.8 | 9 | Link YAML entries to SAD source lines | SAD, YAML | Source-line annotations | CI check | Every YAML entry has a SAD line reference |

#### Step 2 — Registry (Python singleton, YAML lookups)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 2.1 | 1 | Validate registry keys against monograph | Monograph glossary, YAML schema | Key-to-monograph mapping | Review | Every public key traces to a formal definition |
| 2.2 | 2 | Expose per-viewpoint query API | `architecture.yaml` | `get_viewpoint()`, `get_components_by_view()` | Integration test | Queries return correct components per 42010 viewpoint |
| 2.3 | 3 | Document singleton/caching/thread-safety trade-offs | — | ADR citing performance + reliability | Review | ADR exists |
| 2.4 | 5 | Assign SIL-2 | SIL matrix | SIL-2 designation | Review | Recorded |
| 2.5 | 6 | Enumerate failure modes | Registry design | FMEA rows: stale YAML, missing component, race on reload, malformed input | Review | Each has severity, likelihood, mitigation |
| 2.6 | 8 | Implement singleton loader | `architecture.yaml` | `ArchitectureRegistry` class, thread-safe lazy init | Integration test | Loads YAML; concurrent access consistent |
| 2.7 | 8 | Implement component/boundary/ICD lookups | Registry, schema | `get_component()`, `get_boundary()`, `get_icd()` | Property-based test | Every SAD component queryable; unknown keys raise error |
| 2.8 | 8 | Implement hot-reload with validation | `architecture.yaml` | Reload method, schema re-validation | Integration test | Change propagates; invalid YAML rejected, old state retained |
| 2.9 | 9 | Link lookups to YAML source entries | YAML annotations (1.8) | Lookup results include YAML line ref | CI check | Every result carries source reference |

#### Step 3 — Decorators (stamp architectural contracts)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 3.1 | 1 | Map decorator names to monograph concepts | Monograph, registry | Decorator-to-monograph table | Review | Every name traces to formal definition |
| 3.2 | 2 | Encode viewpoint membership in decorators | Viewpoint catalog | Decorator metadata includes viewpoint tag | Integration test | Decorated module reports correct viewpoint |
| 3.3 | 3 | Document decorator pattern trade-offs | — | ADR citing maintainability + security | Review | ADR exists |
| 3.4 | 5 | Assign SIL-2 | SIL matrix | SIL-2 designation | Review | Recorded |
| 3.5 | 6 | Enumerate failure modes | Decorator design | FMEA rows: missing, wrong, ICD mismatch, stale registry ref | Review | Each has severity, likelihood, mitigation |
| 3.6 | 8 | Implement core decorators | Registry API | `@kernel_boundary`, `@tenant_scoped`, `@lane_dispatch`, `@mcp_tool`, `@eval_gated` | Property-based test | Each stamps correct metadata |
| 3.7 | 8 | Implement ICD contract enforcement | ICD specs | Runtime check on decorated call | Property-based test | Wrong schema raises `ICDViolation` |
| 3.8 | 8 | Build AST scanner | Decorator defs, codebase | Scanner: flags undecorated boundary modules | Integration test | Detects intentionally-undecorated fixture |
| 3.9 | 9 | Map decorators to test requirements | Decorator catalog | Test-requirement matrix | CI check | No decorator without a covering test |
| 3.10 | 12 | Verify decorators trigger kernel enforcement | Decorator + KernelContext stub | Integration test: decorator → kernel path | Integration test | Decorated call invokes kernel; undecorated does not |

#### Step 3a — Spiral Gate (thin kernel slice, e2e validation)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 3a.1 | 1 | Verify invariant names trace to monograph | Monograph, KernelContext | Traceability check | Review | K1 traces to monograph definition |
| 3a.2 | 2 | Validate SAD → code path for one boundary | SAD, decorated module, kernel | Annotated e2e trace | Review | Trace documented |
| 3a.3 | 3 | Confirm quality attributes measurable in slice | Quality catalog | ≥1 measurement (e.g., enforcement latency) | Test | Metric collected and within target |
| 3a.4 | 4 | Assign verification method to gate | Process doc | Gate method = demonstration | Review | Method recorded |
| 3a.5 | 5 | Confirm SIL-3 rigor on kernel in slice | SIL matrix | SIL-3 checklist: spec, tests, review | Review + test | All SIL-3 requirements met |
| 3a.6 | 6 | Exercise ≥1 FMEA failure mode | FMEA (2.5, 3.5) | Test triggers failure, confirms mitigation | Integration test | Failure triggered; mitigation activates |
| 3a.7 | 7 | Write minimal TLA+ spec for K1 | Kernel design | TLA+ spec for schema-validation state machine | Model check | TLC zero violations |
| 3a.8 | 8 | Validate full pipeline: YAML → registry → decorator → kernel | Steps 1–3 outputs | Decorated endpoint enforcing K1 | Integration test | Valid schema passes; invalid raises `KernelViolation` |
| 3a.9 | 9 | Validate traceable chain for one requirement | RTM (partial) | Chain: concern → req → ADR → decorator → test → pass | CI check | All 5 links present and green |
| 3a.10 | 10 | Implement minimal K8 eval gate | Eval stub | K8 gate checking one behavioral predicate | Property-based test | Pass on valid; halt on violation |
| 3a.11 | 12 | Verify kernel layer activates independently | Decorator + kernel + broken sandbox stub | Kernel catches violation without downstream layer | Integration test | Enforcement independent of sandbox |
| 3a.12 | 13 | Run gate, produce pass/fail report | All 3a.* outputs | Spiral gate report | Report | All items pass → Slice 2 unlocked |

### Critical Path

```
1.5 → 1.6 → 1.7 → 1.8 → 2.6 → 2.7 → 2.8 → 3.6 → 3.7 → 3a.8 → 3a.10 → 3a.12
```

**39 tasks. 12 on critical path.**

---

## Slice 2 — Phase A Backfill (Steps 4–11)

**Purpose:** Complete architecture enforcement infrastructure — scaffold, ICD, ATAM, validation, scanning, testing, fitness functions, RTM, and CI gate.

### Tasks

#### Step 4 — Scaffold (generate package skeleton)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 4.1 | 1 | Verify package names trace to monograph | Monograph, repo tree | Name-to-concept mapping | Review | Every package traces to formal definition |
| 4.2 | 2 | Generate packages per 42010 viewpoint structure | `architecture.yaml`, repo-tree.md | Package skeleton with layer/component dirs | Integration test | Every SAD component has a corresponding package |
| 4.3 | 3 | Document scaffold generation trade-offs | — | ADR citing maintainability | Review | ADR exists |
| 4.4 | 8 | Build scaffold generator from YAML | `architecture.yaml`, repo-tree.md | Generator script | Integration test | Generates correct tree from current YAML |
| 4.5 | 9 | Link packages to YAML components | Scaffold, YAML | Package-to-YAML mapping in each `__init__.py` | CI check | Every package has YAML source ref |

#### Step 5 — ICD (contract specs per boundary crossing)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 5.1 | 1 | Map ICD terms to monograph boundary definitions | Monograph, SAD | ICD-to-monograph traceability | Review | Every ICD term traces |
| 5.2 | 2 | Define ICD per 42010 boundary | SAD boundary crossings | ICD spec per crossing (schema, protocol, error handling) | Review | Every SAD boundary has an ICD |
| 5.3 | 3 | Document contract-vs-protocol trade-off | — | ADR citing reliability + maintainability | Review | ADR exists |
| 5.4 | 5 | Assign SIL per ICD based on connected components | SIL matrix | SIL designation per ICD | Review | Recorded |
| 5.5 | 8 | Implement ICD as Pydantic models | ICD specs | Python models per boundary crossing | Property-based test | Models validate example payloads |
| 5.6 | 8 | Register ICDs in `architecture.yaml` | ICD models | YAML entries for each boundary contract | Integration test | Registry serves ICD lookups |
| 5.7 | 9 | Link ICDs to SAD boundary crossings | SAD, ICD models | Bidirectional references | CI check | Every ICD links to SAD; every SAD boundary links to ICD |

#### Step 5a — ATAM (architecture quality-attribute evaluation)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 5a.1 | 2 | Identify stakeholder scenarios | Stakeholder concerns, SAD | Scenario catalog with quality attribute tags | Review | ≥3 scenarios per quality attribute |
| 5a.2 | 3 | Evaluate architecture against scenarios | SAD, scenario catalog | Trade-off analysis: sensitivity points, trade-off points, risks | Review | Every scenario evaluated |
| 5a.3 | 4 | Document ATAM verification results | ATAM output | ATAM report with risk catalog | Review | Report complete |
| 5a.4 | 9 | Link ATAM risks to fitness function parameters | ATAM risks | Risk-to-fitness-function mapping | Review | Every risk maps to ≥1 fitness function |

#### Step 6 — Validate (YAML ↔ SAD drift detection)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 6.1 | 8 | Build drift detector | `architecture.yaml`, SAD parser | Validator: compares YAML against current SAD | Integration test | Detects intentionally-introduced drift |
| 6.2 | 8 | Define drift severity levels | Drift categories | Severity config: breaking (blocks merge) vs warning | Review | Severity definitions documented |
| 6.3 | 9 | Wire drift detection into CI pipeline | Drift detector | CI step that runs on every commit | CI check | Drift blocks merge at configured severity |

#### Step 7 — Scan (AST-walk for missing/wrong decorators)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 7.1 | 8 | Extend AST scanner with per-module rules | Decorator catalog, `architecture.yaml` | Scanner rules: required decorators per layer/component | Property-based test | Rules match YAML component definitions |
| 7.2 | 8 | Add wrong-decorator detection | ICD specs, decorator metadata | Scanner flag: decorator present but mismatched to component | Integration test | Detects intentionally-wrong decorator |
| 7.3 | 9 | Wire scanner into CI pipeline | Scanner | CI step: blocks merge on missing/wrong decorator | CI check | Merge blocked on violation |

#### Step 8 — Test (arch contract fixtures + property-based fuzzing)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 8.1 | 4 | Assign verification methods to arch contracts | ICD catalog, SIL matrix | Method per contract (property-based, integration, review) | Review | Every contract has a method |
| 8.2 | 5 | Implement SIL-appropriate test levels | SIL matrix | Test config: Hypothesis strategies for SIL-2, formal for SIL-3 | Integration test | Config generates correct test types per SIL |
| 8.3 | 8 | Write contract fixture generator | ICD models, `architecture.yaml` | Generator: produces valid/invalid payloads per boundary | Property-based test | Generates payloads that exercise every ICD constraint |
| 8.4 | 9 | Map tests to decorators and requirements | Test suite, decorator catalog, RTM | Test-to-decorator-to-requirement mapping | CI check | Every decorator covered by ≥1 test |

#### Step 9 — Fitness Functions (continuous, every commit)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 9.1 | 3 | Derive fitness function parameters from ATAM | ATAM risks (5a.4) | Fitness function definitions with thresholds | Review | Every ATAM risk has a corresponding function |
| 9.2 | 8 | Implement fitness functions | Definitions, codebase | Executable checks: coupling metrics, layer violations, dependency depth | Integration test | Each function produces pass/fail with measurement |
| 9.3 | 9 | Wire into CI as per-commit checks | Fitness functions | CI step: runs all functions on every commit | CI check | Violation blocks merge |

#### Step 10 — RTM Generation (auto-generate from decorators)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 10.1 | 4 | Define RTM schema | 15288 verification requirements, decorator catalog | RTM format: requirement → decision → decorator → test → status | Review | Schema covers all chain links |
| 10.2 | 9 | Build RTM generator | Decorator metadata, test results, ADR index | RTM generator: walks codebase, produces living matrix | Integration test | Generates correct RTM from current codebase |
| 10.3 | 9 | Add gap detection | RTM generator | Gap report: missing links in any chain | CI check | Detects intentionally-broken chain link |

#### Step 11 — CI Gate (block merge on failures)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 11.1 | 8 | Integrate drift, scanner, fitness, RTM into unified gate | Steps 6–10 outputs | CI pipeline config: ordered gate stages | Integration test | All stages run; any failure blocks merge |
| 11.2 | 9 | Add staged canary for arch changes | CI pipeline | Canary config: arch changes deploy to canary before full merge | Integration test | Canary catches intentional regression |
| 11.3 | 13 | Define Phase A gate checklist | All Phase A outputs | Gate report: pass/fail per criterion | Report | All items pass → Phase B unlocked |

### Critical Path

```
5.5 → 5.6 → 7.1 → 7.2 → 8.3 → 9.2 → 10.2 → 11.1 → 11.3
```

**38 tasks. 9 on critical path.**

---

## Slice 3 — Phase B: Failure Analysis & Kernel (Steps 12–21)

**Purpose:** Assign criticality, enumerate failure modes, write formal specs, then build and verify the kernel at SIL-3.

### Tasks

#### Step 12 — SIL Mapping

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 12.1 | 5 | Classify every component by failure consequence | SAD, FMEA prep | SIL assignment matrix | Review | Every component has SIL-1, SIL-2, or SIL-3 |
| 12.2 | 5 | Define verification requirements per SIL | IEC 61508 tailoring | Verification table: methods required per level | Review | Table complete |
| 12.3 | 9 | Link SIL assignments to YAML components | SIL matrix, `architecture.yaml` | SIL annotations in YAML | CI check | Registry returns SIL for any component |

#### Step 13 — FMEA

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 13.1 | 6 | FMEA: kernel invariant desynchronization | Kernel design, K1–K8 | Failure modes, severity, likelihood, mitigations | Review | All 8 invariants analyzed |
| 13.2 | 6 | FMEA: sandbox escape | Sandbox design | Failure modes: namespace leak, seccomp bypass, resource exhaustion | Review | All isolation mechanisms analyzed |
| 13.3 | 6 | FMEA: egress bypass | Egress design | Failure modes: allowlist circumvention, redaction failure, rate-limit evasion | Review | All egress paths analyzed |
| 13.4 | 6 | FMEA: goal injection | Goal decomposer, APS | Failure modes: L5–L6 goal overrides L0–L4, prompt injection to goal | Review | All goal paths analyzed |
| 13.5 | 6 | FMEA: topology desynchronization | Topology manager, eigenspectrum | Failure modes: stale topology, eigenspectrum blind spot, steer race condition | Review | All topology operations analyzed |
| 13.6 | 6 | Compile residual risk register | All FMEA worksheets | Risk register: accept/mitigate per mode | Review | Every mode has disposition |
| 13.7 | 9 | Link FMEA mitigations to roadmap steps | Risk register, roadmap | Mitigation-to-step mapping | CI check | Every mitigation traces to implementation step |

#### Step 14 — Formal Specs (TLA+)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 14.1 | 7 | TLA+ spec: kernel invariant state machine | K1–K8 design, FMEA (13.1) | TLA+ module: all enforcement states and transitions | Model check | TLC zero violations; state space documented |
| 14.2 | 7 | TLA+ spec: sandbox isolation | Sandbox design, FMEA (13.2) | TLA+ module: namespace/seccomp/resource lifecycle | Model check | TLC zero violations |
| 14.3 | 7 | TLA+ spec: egress filter pipeline | Egress design, FMEA (13.3) | TLA+ module: allowlist eval, redaction, rate-limit | Model check | TLC zero violations |
| 14.4 | 7 | Document assumption register | All TLA+ specs | Assumptions: what model covers and does not cover | Review | Every assumption explicit |

#### Step 15 — KernelContext (async context manager)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 15.1 | 1 | Map KernelContext to monograph boundary concepts | Monograph (Markov blankets, channel boundaries) | Concept mapping | Review | Context manager semantics trace to theory |
| 15.2 | 5 | Confirm SIL-3 designation | SIL matrix | SIL-3 recorded | Review | Recorded |
| 15.3 | 6 | Review FMEA mitigations for kernel context lifecycle | FMEA (13.1) | Design addresses: context leak, double-enter, async cancellation | Review | Each FMEA mitigation has design response |
| 15.4 | 7 | Implement per TLA+ state machine spec | TLA+ spec (14.1) | `KernelContext` class: async context manager, wraps boundary | Property-based + formal | Implementation matches TLA+ spec states |
| 15.5 | 8 | Register in architecture.yaml, add decorator | YAML, decorator registry | Kernel component registered; `@kernel_boundary` applied | CI check | Scanner passes |
| 15.6 | 9 | Link to requirement and test | RTM | Chain link: requirement → KernelContext → test | CI check | Chain complete |
| 15.7 | 12 | Verify independence from downstream layers | KernelContext, stub sandbox | Context manager enforces without downstream | Integration test | Enforcement standalone |

#### Step 16 — K1–K4 (schema, permissions, bounds, trace)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 16.1 | 1 | Map K1–K4 to monograph channel constraints | Monograph | Concept mapping per invariant | Review | Each invariant traces |
| 16.2 | 6 | Review FMEA mitigations for K1–K4 | FMEA (13.1) | Design addresses each identified failure mode | Review | All modes addressed |
| 16.3 | 7 | Implement K1 schema validation per TLA+ | TLA+ spec, ICD models | K1 enforcer: validates payload against ICD schema | Property-based test | Invalid payloads rejected; valid pass |
| 16.4 | 7 | Implement K2 permission gating per TLA+ | TLA+ spec, RBAC model | K2 enforcer: checks caller against permission mask | Property-based test | Unauthorized calls rejected |
| 16.5 | 7 | Implement K3 bounds checking per TLA+ | TLA+ spec, resource budget model | K3 enforcer: validates resource within budget | Property-based test | Over-budget rejected |
| 16.6 | 7 | Implement K4 trace injection per TLA+ | TLA+ spec, correlation model | K4 enforcer: injects correlation ID + tenant ID | Integration test | Every boundary crossing has trace |
| 16.7 | 8 | Register K1–K4 in YAML, apply decorators | YAML, decorators | Components registered; decorators applied | CI check | Scanner passes |
| 16.8 | 9 | Link each to requirement and test | RTM | Chain complete per invariant | CI check | 4 chains, all green |

#### Step 17 — K5–K6 (idempotency, audit WAL)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 17.1 | 1 | Map K5–K6 to monograph | Monograph | Concept mapping | Review | Traces |
| 17.2 | 6 | Review FMEA mitigations | FMEA (13.1) | Design addresses replay attacks, WAL corruption | Review | Modes addressed |
| 17.3 | 7 | Implement K5 idempotency (RFC 8785) per TLA+ | TLA+ spec | K5 enforcer: canonical JSON key gen, duplicate detection | Property-based test | Duplicate calls idempotent; distinct calls unique |
| 17.4 | 7 | Implement K6 audit WAL per TLA+ | TLA+ spec | K6 enforcer: append-only log with redaction | Property-based test | Every action logged; sensitive data redacted |
| 17.5 | 8 | Register, decorate | YAML, decorators | Registered, decorated | CI check | Scanner passes |
| 17.6 | 9 | Link to requirements and tests | RTM | Chains complete | CI check | Green |

#### Step 18 — K7–K8 (HITL gates, eval gates)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 18.1 | 1 | Map K7–K8 to monograph goal hierarchy | Monograph (Celestial/Terrestrial) | Concept mapping | Review | K7 traces to HITL, K8 to eval predicates |
| 18.2 | 6 | Review FMEA mitigations | FMEA (13.1) | Design addresses: HITL bypass, eval predicate manipulation | Review | Modes addressed |
| 18.3 | 7 | Implement K7 HITL gate per TLA+ | TLA+ spec | K7 enforcer: blocks on low-confidence, escalates to human | Property-based test | Low-confidence actions block; human approval unblocks |
| 18.4 | 7 | Implement K8 eval gate per TLA+ | TLA+ spec | K8 enforcer: runs behavioral predicate on output | Property-based test | Predicate fail halts; pass continues |
| 18.5 | 10 | Define eval predicate interface | Eval framework stub | Predicate protocol: input → pass/fail + explanation | Integration test | Interface works with property-based test harness |
| 18.6 | 12 | Verify K7+K8 as independent safety layers | K7, K8, stub downstream | Each catches violations independently | Integration test | K7 blocks without K8; K8 blocks without K7 |
| 18.7 | 8 | Register, decorate | YAML, decorators | Registered, decorated | CI check | Scanner passes |
| 18.8 | 9 | Link to requirements and tests | RTM | Chains complete | CI check | Green |

#### Step 19 — Exceptions

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 19.1 | 1 | Map exception hierarchy to monograph failure concepts | Monograph | Concept mapping | Review | Each exception traces to formal failure type |
| 19.2 | 5 | Inherit SIL-3 from kernel | SIL matrix | SIL-3 recorded | Review | Recorded |
| 19.3 | 8 | Implement exception classes | Kernel design | `KernelViolation`, `BoundsExceeded`, `HITLRequired`, `EvalGateFailed` | Property-based test | Each K1–K8 raises correct exception type |
| 19.4 | 9 | Link to requirements | RTM | Chain complete | CI check | Green |

#### Step 20 — Dissimilar Verification

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 20.1 | 6 | Design dissimilar channel from FMEA | FMEA (13.1), risk register | Independent verification path: different code, different data | Review | Channel uses no kernel code |
| 20.2 | 7 | Formally verify independence | TLA+ extension | TLA+ spec proving no shared state between kernel and verifier | Model check | TLC zero violations |
| 20.3 | 12 | Implement dissimilar verification channel | Kernel outputs, independent checker | Verifier module: cross-checks kernel enforcement | Integration test | Catches intentionally-injected kernel bug |
| 20.4 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 21 — Kernel Tests

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 21.1 | 4 | Assign verification methods per SIL-3 | Verification table (12.2) | Methods: formal + property-based + unit + integration | Review | All 4 methods assigned |
| 21.2 | 5 | Execute SIL-3 verification | K1–K8, TLA+ specs | Test results: formal (TLC), property-based (Hypothesis), unit, integration | All methods | All pass |
| 21.3 | 7 | Run TLA+ model checker against all kernel specs | TLA+ specs (14.1–14.3) | TLC output: state count, violation count (must be 0) | Model check | Zero violations |
| 21.4 | 9 | Validate RTM completeness for kernel | RTM | Gap report: every kernel requirement has all 4 verification artifacts | CI check | No gaps |
| 21.5 | 12 | Independent review of kernel safety | All kernel code, specs, tests | Independent reviewer sign-off | Review | Sign-off recorded |
| 21.6 | 13 | Define Phase B gate checklist | All Phase B outputs | Gate report: pass/fail | Report | All items pass → Phase C unlocked |

### Critical Path

```
13.1 → 14.1 → 15.4 → 16.3 → 16.4 → 16.5 → 16.6 → 17.3 → 17.4 → 18.3 → 18.4 → 20.3 → 21.2 → 21.6
```

**72 tasks. 14 on critical path.**

---

## Slice 4 — Phase C: Storage Layer (Steps 22–26)

**Purpose:** Build tenant-isolated storage: Postgres, Redis, ChromaDB.

### Tasks

#### Step 22 — Postgres

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 22.1 | 1 | Map storage concepts to monograph (memory tiers, Markov blankets) | Monograph | Concept mapping | Review | Traces |
| 22.2 | 3 | Document storage architecture trade-offs | — | ADR citing reliability + security | Review | ADR exists |
| 22.3 | 5 | Assign SIL-2 | SIL matrix | SIL-2 recorded | Review | Recorded |
| 22.4 | 6 | FMEA: connection pool exhaustion, RLS bypass, migration failure | Postgres design | FMEA rows | Review | Each mode has mitigation |
| 22.5 | 8 | Implement async pool, models, RLS, migrations | ICD specs, kernel decorators | Database module with tenant-isolated RLS | Integration test | RLS enforces tenant isolation under concurrent access |
| 22.6 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 23 — Partitioning

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 23.1 | 5 | Inherit SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 23.2 | 6 | FMEA: orphan partition, failed archival, restore failure | Partition design | FMEA rows | Review | Each has mitigation |
| 23.3 | 8 | Implement time-based partitions, auto-create, S3 archival | Postgres module | Partition manager | Integration test | Creates, archives, and restores partitions |
| 23.4 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 24 — Redis

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 24.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 24.2 | 6 | FMEA: cache poisoning, pub/sub message loss, HA failover race | Redis design | FMEA rows | Review | Each has mitigation |
| 24.3 | 8 | Implement pool, pub/sub, queues, cache, HA | ICD specs, kernel decorators | Redis module with tenant-scoped operations | Integration test | Pub/sub delivers; cache isolates tenants; HA failover works |
| 24.4 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 25 — ChromaDB

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 25.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 25.2 | 6 | FMEA: embedding drift, cross-tenant retrieval, collection corruption | Chroma design | FMEA rows | Review | Each has mitigation |
| 25.3 | 8 | Implement client, tenant-isolated collections, embedding pipeline | ICD specs, kernel decorators | ChromaDB module | Integration test | Queries return only same-tenant results |
| 25.4 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 26 — Storage Tests

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 26.1 | 4 | Assign SIL-2 verification methods | Verification table | Methods: integration + property-based | Review | Assigned |
| 26.2 | 5 | Execute SIL-2 test suite | Steps 22–25 | Test results: connection, RLS enforcement, partition lifecycle | Integration + property-based | All pass |
| 26.3 | 9 | Validate RTM completeness for storage | RTM | Gap report | CI check | No gaps |
| 26.4 | 13 | Phase C gate checklist | All Phase C outputs | Gate report | Report | All pass → Phase D unlocked |

### Critical Path

```
22.5 → 23.3 → 24.3 → 25.3 → 26.2 → 26.4
```

**28 tasks. 6 on critical path.**

---

## Slice 5 — Phase D: Safety & Infra (Steps 27–33)

**Purpose:** Build redaction, guardrails, governance, secrets, egress, and produce the first structured safety case.

### Tasks

#### Step 27 — Redaction

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 27.1 | 1 | Map redaction to monograph channel filtering | Monograph | Concept mapping | Review | Traces |
| 27.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 27.3 | 6 | FMEA: incomplete redaction, redaction bypass via encoding, false positive | Redaction design | FMEA rows | Review | Each has mitigation |
| 27.4 | 12 | Implement canonical redaction library | ICD specs, kernel | Single-source-of-truth redactor: PII, secrets, custom patterns | Property-based test | Known PII patterns redacted; non-PII preserved |
| 27.5 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 28 — Guardrails

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 28.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 28.2 | 6 | FMEA: sanitization bypass, injection via unicode, output leak | Guardrails design | FMEA rows | Review | Each has mitigation |
| 28.3 | 12 | Implement input sanitization, output redaction, injection detection | ICD specs, redaction lib | Guardrails module | Property-based test | Known injection patterns blocked; clean input passes |
| 28.4 | 9 | Link to requirement and test | RTM | Chain complete | CI check | Green |

#### Step 29 — Governance

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 29.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 29.2 | 6 | FMEA: forbidden path bypass, incomplete code analysis | Governance design | FMEA rows | Review | Each has mitigation |
| 29.3 | 12 | Implement forbidden paths, code review analysis | Governance rules, kernel | Governance module | Integration test | Forbidden paths blocked; allowed paths pass |
| 29.4 | 9 | Link | RTM | Chain complete | CI check | Green |

#### Step 30 — Secret Scanner

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 30.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 30.2 | 6 | FMEA: undetected secret pattern, false redaction of non-secret | Scanner design | FMEA rows | Review | Each has mitigation |
| 30.3 | 12 | Implement detect + redact in traces | Trace store, redaction lib | Secret scanner module | Property-based test | Known secret patterns caught in trace payloads |
| 30.4 | 9 | Link | RTM | Chain complete | CI check | Green |

#### Step 31 — Egress

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 31.1 | 1 | Map egress to monograph channel boundary | Monograph | Concept mapping | Review | Traces |
| 31.2 | 5 | Assign SIL-3 | SIL matrix | SIL-3 recorded | Review | Recorded |
| 31.3 | 6 | FMEA: allowlist circumvention, redaction failure, rate-limit evasion | Egress design, FMEA (13.3) | FMEA rows (may extend 13.3) | Review | All paths analyzed |
| 31.4 | 7 | Implement per TLA+ egress spec | TLA+ (14.3) | L7 allowlist, payload redaction, rate-limit, L3 NAT | Property-based test | Implementation matches TLA+ states |
| 31.5 | 12 | Verify egress as independent safety layer | Egress + stub kernel | Egress blocks exfiltration without kernel | Integration test | Layer independent |
| 31.6 | 9 | Link | RTM | Chain complete | CI check | Green |

#### Step 32 — Secrets (KMS/Vault)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 32.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 32.2 | 6 | FMEA: key rotation failure, credential leak, vault unavailability | Secrets design | FMEA rows | Review | Each has mitigation |
| 32.3 | 12 | Implement KMS/Vault client, rotation, credential store | Secrets design, kernel | Secrets module | Integration test | Rotation works; unavailability handled gracefully |
| 32.4 | 9 | Link | RTM | Chain complete | CI check | Green |

#### Step 33 — Safety Case (Phase D)

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 33.1 | 6 | Aggregate FMEA results for D.27–D.32 | All Phase D FMEA worksheets | Consolidated risk register | Review | Complete |
| 33.2 | 12 | Build structured safety argument | Risk register, test results | Safety case: claims → evidence → context | Review | Every claim has evidence; every gap is explicit |
| 33.3 | 9 | Link safety case to FMEA and test artifacts | Safety case, RTM | Bidirectional references | CI check | Every claim traceable |
| 33.4 | 13 | Phase D gate checklist | All Phase D outputs | Gate report | Report | All pass → Phase E unlocked |

### Critical Path

```
27.4 → 28.3 → 30.3 → 31.4 → 31.5 → 33.1 → 33.2 → 33.4
```

**42 tasks. 8 on critical path.**

---

## Slice 6 — Phase E: Core L2 (Steps 34–40)

**Purpose:** Build conversation interface, intent classifier, goal decomposer, APS controller, topology manager, and memory.

### Tasks

#### Step 34 — Conversation

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 34.1 | 1 | Map conversation to monograph channel theory | Monograph | Concept mapping | Review | Traces |
| 34.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 34.3 | 6 | FMEA: WS connection hijack, message injection, replay | Conversation design | FMEA rows | Review | Each has mitigation |
| 34.4 | 8 | Implement bidirectional WS chat, decorate | ICD, kernel, decorators | Conversation module | Integration test | Messages flow; kernel enforces on boundary |
| 34.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 35 — Intent Classifier

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 35.1 | 1 | Map intent classification to monograph digital branching | Monograph | Concept mapping | Review | Traces |
| 35.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 35.3 | 6 | FMEA: misclassification, prompt injection to force team_spawn | Intent design | FMEA rows | Review | Each has mitigation |
| 35.4 | 10 | Implement classifier with eval suite | LLM, eval harness | Classifier: direct_solve / team_spawn / clarify + eval baseline | Property-based test | Eval suite passes baseline accuracy |
| 35.5 | 8 | Register, decorate | YAML, decorators | Registered | CI check | Scanner passes |
| 35.6 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 36 — Goal Decomposer

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 36.1 | 1 | Map to monograph goal predicate sets, codimension | Monograph | Concept mapping | Review | Traces to Part IV |
| 36.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 36.3 | 6 | FMEA: goal injection, Celestial override, codimension miscalculation | Goal design | FMEA rows | Review | Each has mitigation |
| 36.4 | 10 | Implement 7-level hierarchy + lexicographic gating with eval | Monograph specs, eval harness | Goal decomposer + eval suite | Property-based test | Terrestrial never violates Celestial in eval |
| 36.5 | 11 | Implement Celestial L0–L4 as executable predicates | Constitution design | Predicate functions | Property-based test | Each predicate evaluable on goal output |
| 36.6 | 8 | Register, decorate | YAML, decorators | Registered | CI check | Scanner passes |
| 36.7 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 37 — APS Controller

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 37.1 | 1 | Map to monograph agency rank, cognitive light cone, APS tiers | Monograph | Concept mapping | Review | Traces to Parts III, X |
| 37.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 37.3 | 6 | FMEA: wrong tier classification, Assembly Index overflow | APS design | FMEA rows | Review | Each has mitigation |
| 37.4 | 10 | Implement T0–T3 classification + Assembly Index with eval | Monograph specs, eval harness | APS controller + eval suite | Property-based test | Tier assignments match expected for test scenarios |
| 37.5 | 8 | Register, decorate | YAML, decorators | Registered | CI check | Scanner passes |
| 37.6 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 38 — Topology Manager

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 38.1 | 1 | Map to monograph steering operators, assignment matrices, feasibility | Monograph | Concept mapping | Review | Traces to Parts V, VI |
| 38.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 38.3 | 6 | FMEA: stale topology, eigenspectrum blind spot, steer race, contract violation | Topology design, FMEA (13.5) | FMEA rows (extend 13.5) | Review | Each has mitigation |
| 38.4 | 10 | Implement spawn/steer/dissolve, contracts, eigenspectrum with eval | Monograph, eval harness | Topology manager + eval suite | Property-based test | Eigenspectrum detects injected divergence; steer reshapes correctly |
| 38.5 | 8 | Register, decorate | YAML, decorators | Registered | CI check | Scanner passes |
| 38.6 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 39 — Memory

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 39.1 | 1 | Map to monograph K-scope crystallisation, memory tiers | Monograph | Concept mapping | Review | Traces to Part XII |
| 39.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 39.3 | 6 | FMEA: cross-tenant memory leak, crystallisation corruption, tier promotion failure | Memory design | FMEA rows | Review | Each has mitigation |
| 39.4 | 8 | Implement 3-tier: short (Redis), medium (PG), long (Chroma) | Storage layer (Slice 4), kernel | Memory module with tenant isolation | Integration test | Tier promotion works; isolation holds |
| 39.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 40 — Core Tests

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 40.1 | 4 | Assign SIL-2 verification methods | Verification table | Methods: integration + property-based + eval | Review | Assigned |
| 40.2 | 5 | Execute SIL-2 test suite | Steps 34–39 | Test results: intent → goal → APS → topology e2e | Integration + property-based | All pass |
| 40.3 | 10 | Run all Core eval suites | Eval framework | Eval results: classifier, decomposer, APS, topology baselines | Eval | All pass baseline |
| 40.4 | 9 | Validate RTM completeness for Core | RTM | Gap report | CI check | No gaps |
| 40.5 | 13 | Phase E gate checklist | All Phase E outputs | Gate report | Report | All pass → Phase F unlocked |

### Critical Path

```
34.4 → 35.4 → 36.4 → 36.5 → 37.4 → 38.4 → 39.4 → 40.2 → 40.3 → 40.5
```

**48 tasks. 10 on critical path.**

---

## Slice 7 — Phase F: Engine L3 (Steps 41–45)

**Purpose:** Build lane manager, MCP registry, builtins, and durable workflow engine.

### Tasks

#### Step 41 — Lanes

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 41.1 | 1 | Map to monograph channel composition, macro-channels | Monograph | Concept mapping | Review | Traces |
| 41.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 41.3 | 6 | FMEA: lane starvation, policy deadlock, dispatcher race | Lane design | FMEA rows | Review | Each has mitigation |
| 41.4 | 8 | Implement lane manager, policy engine, dispatchers | APS output, kernel, decorators | Lane module: main/cron/subagent | Integration test | Goals dispatch to correct lanes under load |
| 41.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 42 — MCP Registry

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 42.1 | 1 | Map to monograph tool permission masks, channel constraints | Monograph | Concept mapping | Review | Traces |
| 42.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 42.3 | 6 | FMEA: permission escalation, tool introspection leak, unregistered tool call | MCP design | FMEA rows | Review | Each has mitigation |
| 42.4 | 8 | Implement registry, per-agent permissions, introspection | ICD, kernel, decorators | MCP module | Property-based test | Agent can only call permitted tools; unpermitted raises error |
| 42.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 43 — MCP Builtins

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 43.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 43.2 | 6 | FMEA per builtin: code (sandbox escape via gRPC), web (SSRF), filesystem (path traversal), database (SQL injection) | Builtin designs | FMEA rows per tool | Review | Each has mitigation |
| 43.3 | 8 | Implement code (gRPC→sandbox), web, filesystem, database | MCP registry, sandbox, kernel | 4 builtin tools with kernel enforcement | Integration test | Each tool works; each FMEA mitigation verified |
| 43.4 | 9 | Link | RTM | Chains per builtin | CI check | Green |

#### Step 44 — Workflow Engine

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 44.1 | 1 | Map to monograph durable execution, compensation | Monograph | Concept mapping | Review | Traces |
| 44.2 | 3 | Document saga vs orchestration trade-off | — | ADR citing reliability + maintainability | Review | ADR exists |
| 44.3 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 44.4 | 6 | FMEA: saga partial failure, dead-letter overflow, DAG cycle, compensation failure | Workflow design | FMEA rows | Review | Each has mitigation |
| 44.5 | 8 | Implement durable engine, saga, compensation, dead-letter, DAG compiler | Lane manager, kernel | Workflow module with effectively-once semantics | Property-based test | Workflow survives injected node failure; compensation fires |
| 44.6 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 45 — Engine Tests

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 45.1 | 4 | Assign SIL-2 verification methods | Verification table | Methods assigned | Review | Assigned |
| 45.2 | 5 | Execute SIL-2 test suite | Steps 41–44 | Test results: goal → lane → workflow → tool → result e2e | Integration + property-based | All pass |
| 45.3 | 9 | Validate RTM completeness | RTM | Gap report | CI check | No gaps |
| 45.4 | 13 | Phase F gate checklist | All Phase F outputs | Gate report | Report | All pass → Phase G unlocked |

### Critical Path

```
41.4 → 42.4 → 43.3 → 44.5 → 45.2 → 45.4
```

**32 tasks. 6 on critical path.**

---

## Slice 8 — Phase G: Sandbox (Steps 46–50)

**Purpose:** Build and verify sandboxed code execution at SIL-3.

### Tasks

#### Step 46 — Sandbox Image

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 46.1 | 1 | Map to monograph Markov blanket isolation | Monograph | Concept mapping | Review | Traces |
| 46.2 | 3 | Document minimal-image trade-offs | — | ADR citing security + performance | Review | ADR exists |
| 46.3 | 5 | Assign SIL-3 | SIL matrix | SIL-3 recorded | Review | Recorded |
| 46.4 | 6 | FMEA: image supply-chain attack, residual deps, network capability | Image design | FMEA rows | Review | Each has mitigation |
| 46.5 | 12 | Build minimal container: no network, no Holly deps | Dockerfile, security policy | Container image | Integration test | No network; no Holly packages in image |
| 46.6 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 47 — gRPC Service

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 47.1 | 5 | Inherit SIL-3 | SIL matrix | Recorded | Review | Recorded |
| 47.2 | 6 | FMEA: proto deserialization attack, executor escape, result tampering | gRPC design | FMEA rows | Review | Each has mitigation |
| 47.3 | 7 | Implement per TLA+ sandbox spec | TLA+ (14.2) | ExecutionRequest/Result proto, server, executor | Property-based test | Matches TLA+ states |
| 47.4 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 48 — Isolation

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 48.1 | 5 | Inherit SIL-3 | SIL matrix | Recorded | Review | Recorded |
| 48.2 | 6 | FMEA: namespace leak, seccomp bypass, cgroup escape | Isolation design | FMEA rows | Review | Each has mitigation |
| 48.3 | 7 | Implement per TLA+ isolation spec | TLA+ (14.2) | PID/NET/MNT namespaces, seccomp profile, resource limits | Property-based test | Matches TLA+ states |
| 48.4 | 12 | Verify isolation as independent safety layer | Isolation + stub kernel | Isolation holds without kernel | Integration test | Layer independent |
| 48.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 49 — gVisor/Firecracker

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 49.1 | 3 | Document gVisor vs Firecracker trade-off | — | ADR citing security + performance + ops | Review | ADR exists |
| 49.2 | 5 | Inherit SIL-3 | SIL matrix | Recorded | Review | Recorded |
| 49.3 | 6 | FMEA: runtime-specific escape paths | Runtime configs | FMEA rows per runtime | Review | Each has mitigation |
| 49.4 | 12 | Implement production runtime configs | Runtime choice, isolation layer | gVisor and/or Firecracker configs | Integration test | Execution works under production runtime |
| 49.5 | 9 | Link | RTM | Chain | CI check | Green |

#### Step 50 — Sandbox Tests

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 50.1 | 4 | Assign SIL-3 verification methods | Verification table | Methods: formal + property-based + integration + independent | Review | All 4 assigned |
| 50.2 | 5 | Execute SIL-3 test suite | Steps 46–49 | Test results: network escape, filesystem escape, resource limits | All methods | All pass |
| 50.3 | 7 | Run TLA+ model checker against sandbox spec | TLA+ (14.2) | TLC output: zero violations | Model check | Zero violations |
| 50.4 | 12 | Independent review of sandbox safety | All sandbox code, specs, tests | Independent reviewer sign-off | Review | Sign-off recorded |
| 50.5 | 9 | Validate RTM completeness | RTM | Gap report | CI check | No gaps |
| 50.6 | 13 | Phase G gate checklist | All Phase G outputs | Gate report | Report | All pass → Phase H unlocked |

### Critical Path

```
46.5 → 47.3 → 48.3 → 49.4 → 50.2 → 50.3 → 50.6
```

**38 tasks. 7 on critical path.**

---

## Slice 9 — Phase H: API & Auth (Steps 51–56)

**Purpose:** Build Starlette server, JWT middleware, RBAC, routes, WebSockets.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 51.1 | 3 | Document middleware stack trade-offs | — | ADR | Review | Exists |
| 51.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 51.3 | 6 | FMEA: middleware bypass, request smuggling | Server design | FMEA rows | Review | Each has mitigation |
| 51.4 | 8 | Implement Starlette app factory, middleware, decorate | ICD, kernel | Server module | Integration test | Middleware chain executes in order |
| 51.5 | 9 | Link | RTM | Chain | CI check | Green |
| 52.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 52.2 | 6 | FMEA: JWKS cache poisoning, token replay, revocation race | JWT design | FMEA rows | Review | Each has mitigation |
| 52.3 | 12 | Implement JWKS verification, claims extraction, revocation cache | Auth design, Redis (revocation) | JWT middleware | Property-based test | Expired/revoked tokens rejected; valid pass |
| 52.4 | 9 | Link | RTM | Chain | CI check | Green |
| 53.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 53.2 | 6 | FMEA: privilege escalation, role confusion, claim tampering | RBAC design | FMEA rows | Review | Each has mitigation |
| 53.3 | 12 | Implement RBAC enforcement from JWT claims | JWT middleware, kernel | Auth module | Property-based test | Unauthorized roles rejected |
| 53.4 | 9 | Link | RTM | Chain | CI check | Green |
| 54.1 | 8 | Implement routes: chat, goals, agents, topology, execution, audit, config, health | All Core/Engine modules, ICD | Route handlers with kernel decorators | Integration test | Each route returns correct response; kernel enforces |
| 54.2 | 9 | Link | RTM | Chains per route | CI check | Green |
| 55.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 55.2 | 6 | FMEA: WS hijack, cross-tenant channel leak, re-auth failure | WS design | FMEA rows | Review | Each has mitigation |
| 55.3 | 8 | Implement WS manager, 9 channels, tenant-scoped authz, re-auth | Conversation module, JWT middleware | WebSocket module | Integration test | Tenant isolation holds; re-auth works |
| 55.4 | 9 | Link | RTM | Chain | CI check | Green |
| 56.1 | 4 | Assign SIL-2 verification methods | Verification table | Assigned | Review | Assigned |
| 56.2 | 5 | Execute SIL-2 test suite | Steps 51–55 | Test results: auth, routing, WS delivery | Integration + property-based | All pass |
| 56.3 | 9 | Validate RTM completeness | RTM | Gap report | CI check | No gaps |
| 56.4 | 13 | Phase H gate checklist | All Phase H outputs | Gate report | Report | All pass → Phase I unlocked |

### Critical Path

```
51.4 → 52.3 → 53.3 → 54.1 → 55.3 → 56.2 → 56.4
```

**36 tasks. 7 on critical path.**

---

## Slice 10 — Phase I: Observability (Steps 57–61)

**Purpose:** Build event bus, structured logging, trace store, metrics, and exporters.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 57.1 | 1 | Map event bus to monograph channel composition | Monograph | Concept mapping | Review | Traces |
| 57.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 57.3 | 6 | FMEA: event loss, backpressure failure, fanout cross-tenant leak | Event bus design | FMEA rows | Review | Each has mitigation |
| 57.4 | 8 | Implement unified ingest, sampling, backpressure, tenant-scoped fanout | Kernel, Redis | Event bus module | Integration test | Events delivered; backpressure engages under load |
| 57.5 | 9 | Link | RTM | Chain | CI check | Green |
| 58.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 58.2 | 8 | Implement structured JSON logger, correlation-aware, redact-before-persist | Redaction lib, K4 trace injection | Logger module | Integration test | Logs contain correlation ID; PII redacted |
| 58.3 | 9 | Link | RTM | Chain | CI check | Green |
| 59.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 59.2 | 6 | FMEA: trace payload leak, decision tree corruption | Trace design | FMEA rows | Review | Each has mitigation |
| 59.3 | 8 | Implement decision tree persistence, redact payloads | Event bus, redaction lib, Postgres | Trace store module | Integration test | Decision trees persisted; payloads redacted |
| 59.4 | 9 | Link | RTM | Chain | CI check | Green |
| 60.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 60.2 | 8 | Implement Prometheus collectors | Event bus | Metrics module | Integration test | Metrics scraped correctly |
| 60.3 | 9 | Link | RTM | Chain | CI check | Green |
| 61.1 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 61.2 | 8 | Implement PG (partitioned) + Redis (real-time) exporters | Event bus, Postgres, Redis | Exporter modules | Integration test | Events flow to both sinks |
| 61.3 | 9 | Link | RTM | Chain | CI check | Green |
| 61.4 | 9 | Validate RTM completeness for observability | RTM | Gap report | CI check | No gaps |
| 61.5 | 13 | Phase I gate checklist | All Phase I outputs | Gate report | Report | All pass → Phase J unlocked |

### Critical Path

```
57.4 → 58.2 → 59.3 → 60.2 → 61.2 → 61.5
```

**24 tasks. 6 on critical path.**

---

## Slice 11 — Phase J: Agents (Steps 62–65)

**Purpose:** Build BaseAgent, agent registry, prompt library, and executable constitution.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 62.1 | 1 | Map BaseAgent to monograph agency rank, digital branching, feedback Jacobian | Monograph | Concept mapping | Review | Agent satisfies 3 formal agency conditions |
| 62.2 | 3 | Document agent lifecycle trade-offs | — | ADR | Review | Exists |
| 62.3 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 62.4 | 6 | FMEA: lifecycle leak, message protocol desync, kernel binding failure | Agent design | FMEA rows | Review | Each has mitigation |
| 62.5 | 10 | Implement BaseAgent: lifecycle, message protocol, kernel binding with eval | Kernel, MCP registry, eval framework | BaseAgent class + eval suite | Property-based test | Lifecycle correct; messages conform to protocol |
| 62.6 | 8 | Register, decorate | YAML, decorators | Registered | CI check | Scanner passes |
| 62.7 | 9 | Link | RTM | Chain | CI check | Green |
| 63.1 | 1 | Map agent types to monograph competency continuum | Monograph | Concept mapping | Review | Traces |
| 63.2 | 5 | Assign SIL-2 | SIL matrix | Recorded | Review | Recorded |
| 63.3 | 6 | FMEA: unregistered agent call, capability mismatch, catalog corruption | Registry design | FMEA rows | Review | Each has mitigation |
| 63.4 | 10 | Implement type catalog, capability declarations with eval | BaseAgent, eval framework | Agent registry + eval suite | Integration test | Correct agents resolved for capability queries |
| 63.5 | 9 | Link | RTM | Chain | CI check | Green |
| 64.1 | 1 | Map prompt roles to monograph agency types | Monograph | Concept mapping | Review | Traces |
| 64.2 | 10 | Implement Holly, researcher, builder, reviewer, planner prompts with eval | Agent registry, eval framework | Prompt library + per-prompt eval suite | Property-based test | Each prompt passes behavioral baseline |
| 64.3 | 10 | Establish eval baselines | Eval framework | Baseline metrics per prompt | Eval | Baselines recorded |
| 64.4 | 9 | Link | RTM | Chain | CI check | Green |
| 65.1 | 1 | Map Celestial/Terrestrial to monograph goal hierarchy | Monograph | Concept mapping | Review | Traces to Part IV |
| 65.2 | 11 | Implement Celestial L0–L4 as executable predicate functions | Monograph, goal decomposer | Constitution predicates: L0 (safety), L1 (legal), L2 (ethical), L3 (permissions), L4 (constitutional) | Property-based test | Each predicate evaluable; lexicographic ordering correct |
| 65.3 | 11 | Implement Terrestrial L5–L6 as executable goal specs | Goal decomposer | Terrestrial predicates | Property-based test | Terrestrial goals decompose correctly |
| 65.4 | 10 | Build constitution eval suite | Predicates, eval framework | Adversarial eval: attempts to violate each Celestial level | Eval | Zero Celestial violations |
| 65.5 | 9 | Link | RTM | Chain | CI check | Green |
| 65.6 | 13 | Phase J gate checklist | All Phase J outputs | Gate report | Report | All pass → Phase K unlocked |

### Critical Path

```
62.5 → 63.4 → 64.2 → 64.3 → 65.2 → 65.4 → 65.6
```

**34 tasks. 7 on critical path.**

---

## Slice 12 — Phase K: Eval Infrastructure / EDDOps (Steps 66–69)

**Purpose:** Build the eval framework, behavioral suites, constitution gate, and eval CI pipeline.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 66.1 | 10 | Design eval harness architecture | Eval stubs from Slices 6/11 | Harness design: dataset loaders, metric collectors, regression tracker | Review | Design complete |
| 66.2 | 10 | Implement eval framework harness | Design | `EvalHarness` class: load datasets, run evals, collect metrics, detect regression | Integration test | Harness runs existing eval suites from Slices 6/11 |
| 66.3 | 10 | Implement dataset loaders | Harness | Loaders: JSON, CSV, programmatic generators | Integration test | All formats load correctly |
| 66.4 | 10 | Implement metric collectors + regression tracker | Harness | Metric store with baseline comparison and regression detection | Integration test | Regression detected on intentionally-degraded baseline |
| 66.5 | 4 | Assign verification methods for eval framework | Verification table | Methods assigned | Review | Assigned |
| 66.6 | 9 | Link | RTM | Chain | CI check | Green |
| 67.1 | 10 | Build per-agent property-based eval suites | Eval framework, agent prompts | Hypothesis strategies per agent type | Property-based test | Strategies generate valid adversarial inputs |
| 67.2 | 10 | Build adversarial eval suites | Eval framework, FMEA (goal injection, prompt injection) | Adversarial datasets targeting each FMEA attack | Eval | Each agent resists adversarial inputs above threshold |
| 67.3 | 10 | Establish production baselines | All eval suites | Baseline metrics per agent per suite | Eval | Baselines recorded and versioned |
| 67.4 | 9 | Link | RTM | Chain | CI check | Green |
| 68.1 | 10 | Implement constitution gate | Eval framework, Celestial predicates (65.2) | Gate: runs all Celestial predicates on every constitution/prompt change | Integration test | Gate fires on change; blocks on violation |
| 68.2 | 11 | Verify gate enforces lexicographic ordering | Constitution gate, test cases | Test: Terrestrial change that degrades Celestial metric is blocked | Integration test | Blocked correctly |
| 68.3 | 9 | Link | RTM | Chain | CI check | Green |
| 69.1 | 10 | Implement eval CI pipeline stage | Eval framework, CI config | CI stage: runs full eval suite, blocks merge on regression | Integration test | Merge blocked on injected regression |
| 69.2 | 4 | Verify eval CI as formal verification activity | Process doc | Eval CI = 15288 verification by demonstration | Review | Documented |
| 69.3 | 9 | Link | RTM | Chain | CI check | Green |
| 69.4 | 9 | Validate RTM completeness for EDDOps | RTM | Gap report | CI check | No gaps |
| 69.5 | 13 | Phase K gate checklist | All Phase K outputs | Gate report | Report | All pass → Phase L unlocked |

### Critical Path

```
66.2 → 66.3 → 66.4 → 67.1 → 67.2 → 67.3 → 68.1 → 69.1 → 69.5
```

**26 tasks. 9 on critical path.**

---

## Slice 13 — Phase L: Config (Steps 70–72)

**Purpose:** Build settings, hot reload, and config audit/rollback. SIL-1.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 70.1 | 5 | Assign SIL-1 | SIL matrix | SIL-1 recorded | Review | Recorded |
| 70.2 | 8 | Implement Pydantic env-driven config | Architecture requirements | Settings module | Unit test | All config keys load from env; validation on invalid |
| 70.3 | 9 | Link | RTM | Chain | CI check | Green |
| 71.1 | 5 | Inherit SIL-1 | SIL matrix | Recorded | Review | Recorded |
| 71.2 | 8 | Implement runtime hot reload without restart | Settings module, Redis | Reload mechanism | Unit test | Config change propagates; invalid rejected |
| 71.3 | 9 | Link | RTM | Chain | CI check | Green |
| 72.1 | 5 | Inherit SIL-1 | SIL matrix | Recorded | Review | Recorded |
| 72.2 | 6 | FMEA: dangerous key change without HITL, rollback to corrupt state | Config design | FMEA rows | Review | Each has mitigation |
| 72.3 | 8 | Implement change logging, HITL on dangerous keys, version revert | Settings module, K7 HITL gate | Config audit module | Unit test | Dangerous keys require HITL; revert works |
| 72.4 | 9 | Link | RTM | Chain | CI check | Green |
| 72.5 | 9 | Validate RTM completeness | RTM | Gap report | CI check | No gaps |
| 72.6 | 13 | Phase L gate checklist | All Phase L outputs | Gate report | Report | All pass → Phase M unlocked |

### Critical Path

```
70.2 → 71.2 → 72.3 → 72.6
```

**14 tasks. 4 on critical path. (Lightest slice — SIL-1, minimal FMEA.)**

---

## Slice 14 — Phase M: Console L5 (Steps 73–78)

**Purpose:** Build React frontend: shell, chat, topology, goals, execution, audit. SIL-1.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 73.1 | 5 | Assign SIL-1 | SIL matrix | Recorded | Review | Recorded |
| 73.2 | 3 | Document frontend stack trade-offs | — | ADR citing maintainability + performance | Review | Exists |
| 73.3 | 8 | Scaffold React + Vite + Tailwind + Zustand | Architecture requirements | Frontend skeleton | Unit test | Builds and serves |
| 73.4 | 9 | Link | RTM | Chain | CI check | Green |
| 74.1 | 8 | Implement chat panel, message bubbles, input bar | WS API (step 55), conversation API | Chat component | Unit test | Messages render; input sends |
| 74.2 | 9 | Link | RTM | Chain | CI check | Green |
| 75.1 | 1 | Map topology viz to monograph morphogenetic concepts | Monograph | Concept mapping | Review | Traces |
| 75.2 | 8 | Implement live agent graph, contract cards | Topology API (step 38), WS | Topology component | Unit test | Graph updates on topology change; contracts display |
| 75.3 | 9 | Link | RTM | Chain | CI check | Green |
| 76.1 | 1 | Map goal viz to monograph Celestial/Terrestrial hierarchy | Monograph | Concept mapping | Review | Traces |
| 76.2 | 8 | Implement tree explorer, celestial badges | Goal API (step 36), WS | Goals component | Unit test | Tree renders; Celestial goals badged |
| 76.3 | 9 | Link | RTM | Chain | CI check | Green |
| 77.1 | 8 | Implement lane monitor, task timeline | Lane API (step 41), workflow API, WS | Execution component | Unit test | Lanes and tasks render in real-time |
| 77.2 | 9 | Link | RTM | Chain | CI check | Green |
| 78.1 | 8 | Implement log viewer, trace tree, metrics dashboard | Observability APIs (steps 57–61), WS | Audit component | Unit test | Logs stream; traces navigable; metrics display |
| 78.2 | 9 | Link | RTM | Chain | CI check | Green |
| 78.3 | 9 | Validate RTM completeness for console | RTM | Gap report | CI check | No gaps |
| 78.4 | 13 | Phase M gate checklist | All Phase M outputs | Gate report | Report | All pass → Phase N unlocked |

### Critical Path

```
73.3 → 74.1 → 75.2 → 76.2 → 77.1 → 78.1 → 78.4
```

**28 tasks. 7 on critical path.**

---

## Slice 15 — Phase N: Deploy & Ops (Steps 79–86)

**Purpose:** Docker, AWS, auth, staged rollout, scripts, release safety case, runbook, docs.

### Tasks

| ID | MP | Task | Input | Output | Verification | Acceptance |
|---|---|---|---|---|---|---|
| 79.1 | 3 | Document container strategy trade-offs | — | ADR | Review | Exists |
| 79.2 | 8 | Build Docker Compose (dev) + production Dockerfile | All modules | Docker configs | Integration test | Dev compose starts full stack; prod image builds |
| 79.3 | 9 | Link | RTM | Chain | CI check | Green |
| 80.1 | 3 | Document AWS architecture trade-offs | — | ADR citing availability + cost | Review | Exists |
| 80.2 | 14 | Implement VPC/CFn, ALB/WAF, ECS Fargate task defs | Docker image, AWS account | CloudFormation templates | Integration test | Stack deploys to staging |
| 80.3 | 9 | Link | RTM | Chain | CI check | Green |
| 81.1 | 12 | Implement Authentik OIDC flows, RBAC policies | Auth module (step 53), Authentik | OIDC config, RBAC policy definitions | Integration test | Login flow works; RBAC enforces |
| 81.2 | 9 | Link | RTM | Chain | CI check | Green |
| 82.1 | 14 | Implement feature flags | Deployment pipeline | Flag service: runtime toggle per feature | Integration test | Flag controls behavior; toggle propagates |
| 82.2 | 14 | Implement canary deploys | ECS, ALB | Canary config: % traffic routing | Integration test | Canary receives configured traffic fraction |
| 82.3 | 14 | Implement progressive delivery gates | Eval framework, canary | Gate: promote/rollback based on eval metrics | Integration test | Regression triggers automatic rollback |
| 82.4 | 9 | Link | RTM | Chain | CI check | Green |
| 83.1 | 9 | Implement scripts: seed_db, migrate, dev, partition maintenance | All infra modules | Script suite | Integration test | Each script runs without error |
| 83.2 | 9 | Link | RTM | Chain | CI check | Green |
| 84.1 | 6 | Aggregate all FMEA results across all phases | All FMEA worksheets | Master risk register | Review | Every identified risk has disposition |
| 84.2 | 12 | Build full system safety argument | Master risk register, all test results, all TLA+ results | Release safety case: claims → evidence → context | Review | Every claim has evidence; every gap explicit |
| 84.3 | 9 | Verify complete traceable chain | Full RTM | RTM completeness: every requirement → decision → code → test → proof | CI check | Zero gaps across entire codebase |
| 84.4 | 7 | Verify all TLA+ specs pass final model check | All TLA+ specs | Final TLC run: kernel, sandbox, egress | Model check | Zero violations |
| 84.5 | 12 | Independent safety review | Safety case, all artifacts | Independent reviewer sign-off on release safety case | Review | Sign-off recorded |
| 84.6 | 13 | Release gate: safety case complete? | Safety case | Go/no-go decision | Report | Go → production release authorized |
| 85.1 | 9 | Write operational runbook | All infra, deploy configs | Runbook: procedures, DR/restore | Review | Every operational scenario documented |
| 85.2 | 9 | Link | RTM | Chain | CI check | Green |
| 86.1 | 9 | Write glossary | Monograph, architecture.yaml | Glossary: formal terms, Holly mappings | Review | Every term defined |
| 86.2 | 9 | Write sandbox security doc | Sandbox design, FMEA, TLA+ | Security document | Review | All isolation claims traced to evidence |
| 86.3 | 9 | Write egress model doc | Egress design, FMEA, TLA+ | Egress document | Review | All filtering claims traced to evidence |
| 86.4 | 9 | Write deployment topology doc | AWS config, Docker, Authentik | Topology document | Review | Matches deployed infrastructure |
| 86.5 | 13 | Phase N gate checklist | All Phase N outputs | Final gate report | Report | All pass → Production |

### Critical Path

```
79.2 → 80.2 → 82.1 → 82.2 → 82.3 → 84.1 → 84.2 → 84.4 → 84.5 → 84.6 → 86.5
```

**46 tasks. 11 on critical path.**

---

## Grand Summary

| Metric | Value |
|---|---|
| **Total tasks** | **545** |
| **Total critical-path tasks** | **113** |
| **Slices** | **15** |
| **Phases** | **14 (A–N)** |
| **Roadmap steps covered** | **86** |
| **Heaviest slice** | **Slice 3 (Phase B: Kernel) — 72 tasks** |
| **Lightest slice** | **Slice 13 (Phase L: Config) — 14 tasks** |
| **SIL-3 slices** | **3 (Slices 1/3a, 3, 8)** |
| **SIL-1 slices** | **2 (Slices 13, 14)** |

### Task Distribution by Type

| Type | Count | % |
|---|---|---|
| Implementation (code) | 198 | 36% |
| Review (design, FMEA, ADR) | 147 | 27% |
| Test / Verification | 89 | 16% |
| Traceability (RTM, chain links) | 78 | 14% |
| Gate / Report | 18 | 3% |
| Eval (behavioral suites) | 15 | 3% |