# Monograph Glossary Extract

**Source**: "Informational Monism, Morphogenetic Agency, and Goal-Specification Engineering" v2.0, Sean P. Allen, 2026-02-10
**Holly Version**: 3.0 (Holly Grace)
**Document Version**: 0.1.0
**Purpose**: Bidirectional mapping between monograph formal terms and Holly implementation constructs. Every Holly component should trace to at least one monograph concept; every monograph concept used in Holly should appear here.

---

## 1  Notation Reference

The monograph defines a formal notation table (pp. 1–2). Key symbols used throughout Holly's architecture:

| Symbol | Monograph Meaning | Holly Usage |
|--------|-------------------|-------------|
| `X`, `X_phys` | Microstate space (effective / underlying physical) | Raw sensor/API state before partitioning |
| `m` | Measurement map `y = m(x)` | Data ingestion transforms in MCP tools |
| `π` | Partition / coarse-graining map `π : X → Σ` | Event classification in observability layer |
| `π_G` | Goal-conditioned partition | Goal decomposer's predicate-to-symbol mapping |
| `σ` | Symbol (macrostate) produced by `π` | Discrete state tokens in inter-agent messages |
| `Σ` | Symbol alphabet | Enum types in message contracts |
| `Σ_stable` | `(T, ε)`-stable symbol set | Validated symbol sets after stability assessment |
| `K_T` | Stochastic kernel (microdynamics over horizon `T` under control `u`) | LLM inference as stochastic map |
| `P(σ_out\|σ_in, u)` | Induced macro-channel | Agent-to-agent information flow matrix |
| `C(P)` | Shannon capacity of induced macro-channel | Channel health metric in observability |
| `W` | Work/energy per channel use (joules, or domain resource `W_R`) | Token cost, API cost, compute budget |
| `η` | Informational efficiency `η := C(P)/W` | Efficiency metric in budget tracking |
| `ε` | Error tolerance | Goal failure thresholds `ε_G` |
| `T` | Evaluation horizon | Monitoring window in APS controller |
| `G⁰` | Preference (pre-observational ordering) | Constitutional anchor (celestial.py) |
| `G¹` | Goal specification tuple `(F_G, ε_G, T, m_G)` | Persona specification / agent_registry.yaml |
| `G²` | Implementation (realized policy under `θ` and `m`) | Runtime configuration (model, tools, guardrails) |
| `F_G` | Failure predicate | `failure_predicate` field in goal contracts |
| `ε_G` | Tolerated failure probability | Threshold in goal hierarchy (L0–L6) |
| `m_G` | Goal measurement map | Evaluation metric extraction |
| `θ` | Agent configuration (architecture + parameters + caches) | Agent config in registry + runtime state |
| `x` | External states | Environment observations |
| `μ` | Internal states (belief/latent states) | Agent memory / belief state |
| `s` | Sensory states | Inbound event stream |
| `a` | Active states | Agent actions / tool invocations |
| `b = (s, a)` | Markov blanket separating `μ` from `x` | Agent boundary in topology contracts |
| `F` | Variational free energy | — (theoretical grounding, not directly implemented) |
| `E[F]` | Expected free energy (EFE) | Explore/exploit decision in APS controller |
| `AI(θ)` | Assembly index (structural construction cost with reuse) | Team topology complexity metric |
| `CLC(θ)` | Cognitive light cone (goal reach—spatiotemporal extent) | Agent capability horizon |
| `J_F` | Feedback Jacobian / sensitivity matrix | Sensitivity analysis in goal monitoring |
| `k` | Agency rank `k := rank_τ(J_F)` | Dimensionality of agent's effective control |
| `{f_i}` | Goal predicate set (measurable pass/fail constraints) | Goal predicates in hierarchy spec |
| `g = (g_1, …, g_m)` | Predicate pass indicator vector | Goal status vector in dashboard |
| `ν` | Reference distribution over macro-states/trajectories | Baseline for goal coupling estimation |
| `M` | Goal coupling matrix `M := Cov_ν(g)` | Goal interdependency matrix |
| `cod_π(G)` | Goal codimension `cod_π(G) := rank_τ(M)` | Number of independent failure directions |
| `α` | Assignment of predicates to agents | Agent-to-goal mapping in topology |
| `J_a` | Agent predicate steering operator (first-order) | Per-agent control Jacobian |
| `J_α` | Block-diagonal steering operator | Combined agent steering matrix |
| `J_O` | Orchestrator steering operator | Cross-agent coupling control |
| `J_total` | Total steering operator `[J_α  J_O]` | Full system controllability |
| `Π` | Orthogonal projector onto `im(J_total)` | Reachable goal subspace |
| `Δ` | Infeasibility residual `Δ := (I − Π)M(I − Π)^T` | Uncontrollable goal variance |
| `ς_i` | Per-axis steering power (capacity × resolution × depth surrogate) | Per-predicate control strength |
| `ς` | Steering power spectrum vector (sorted) | Sorted control capabilities |
| `S` | Total steering power `S := Σ_i ς_i` | Aggregate system control budget |
| `C` | Cross-agent coupling rank | Inter-agent dependency dimensionality |
| `γ` | Governance margin `γ := R − C` | Orchestrator headroom |
| `ε_dist` | Distinguishability frontier | Minimum resolvable goal difference |
| `ε_dmg` | Damage tolerance | Maximum tolerable goal divergence |
| `ε_eff` | Latency-adjusted effective tolerance | Operational error bound |
| `τ` | Threshold / tolerance parameter | Numerical rank cutoff |
| `η_R`, `η_token`, `η_$` | Resource-normalized efficiency variants | Token-efficiency, dollar-efficiency metrics |
| `η_alignment` | Normative throughput per unit resource | Alignment efficiency measure |
| `K` | Shared context / codebook | Redis-backed shared state store |
| `n_i` | Reuse count of cached subassembly `i` | Cache hit metrics |
| `p̂_fail` | Empirical failure rate estimate | UCB-monitored goal failure rate |
| `κ` | Hysteresis parameter | Debounce for APS tier transitions |
| `F` | Feedback map from internal state to control selection | APS explore/exploit policy |
| `P_feasible(θ)` | Set of feasible partitions | Valid agent configurations |
| `S_eff(θ)` | Operative scale set | Active monitoring scales |
| `G(θ)` | Feasible goal set | Achievable goals given config |
| `dim*(G)` | Intrinsic goal complexity | Effective dimensionality of goal contract |
| `CP(l)` | Causal power profile across scales `l` | Multi-scale causal analysis |

---

## 2  Core Theoretical Concepts → Holly Mapping

### 2.1  Part I: Channel Theory (Ch 1–3, pp. 3–50)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Informational Monism** | Ch 1, p. 4 | Thesis that conduction, communication, and computation are specializations of a single formalism: the induced macro-channel | Foundational design principle; all agent interactions modeled as information channels | — (architectural axiom) |
| **Induced Macro-Channel** | Ch 1, p. 4; Def 1 | Given microdynamics `K_T` and partitions `(π_in, π_out)`, the stochastic map `P(σ_out \| σ_in, u)` on symbols | Agent-to-agent message passing; measured via confusion matrices in observability | L4 Observability |
| **Informational Efficiency** | Ch 1, p. 4 | `η := C(P)/W` — Shannon capacity per unit work | `η_token`, `η_$` metrics in budget tracking | L2 Core / LLM Router |
| **Coarse-Graining / Partition** | Ch 1–2 | Map `π : X → Σ` that collapses microstate space to symbol alphabet | Event classification, state discretization in MCP tools | L3 Engine / MCP |
| **Shannon Capacity** | Ch 2 | `C(P)` — maximum mutual information over input distributions | Channel health KPI; computed via Blahut-Arimoto | L4 Observability |
| **Data Processing Inequality** | Thm 2 | `C(P_chain) ≤ min_i C(P_i)` for cascaded channels | Bottleneck analysis for multi-agent pipelines | L2 Core / Topology |
| **Digital Branching** | Ch 3 | Discrete decision points where partition choice determines information flow | Agent decision nodes in workflow DAGs | L3 Engine / Workflow |
| **Channel Composition** | Ch 2–3 | Cascade: `P_chain = P_1 · P_2`; parallel; feedback compositions | Team topology composition rules | L2 Core / Topology |
| **Stable Symbol Set** | Def (pp. 1–2) | `Σ_stable` — symbols whose empirical frequency is stable over `(T, ε)` window | Validated enum types after burn-in period | L4 Observability |

### 2.2  Part II: Agency & Active Inference (Ch 4–5, pp. 51–90)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Feedback Jacobian** | Ch 4 | `J_F` — matrix of partial derivatives of control selection w.r.t. internal state | Sensitivity matrix for goal monitoring | L2 Core / Goals |
| **Agency Rank** | Ch 4 | `k := rank_τ(J_F)` — dimensionality of effective agent control | Agent capability dimensionality in topology contracts | L2 Core / Topology |
| **Markov Blanket** | Ch 4–5 | `b = (s, a)` separating internal states `μ` from external `x` | Agent isolation boundary; enforced by kernel permission gates | L1 Kernel (K2) |
| **Active Inference** | Ch 5 | Policy selection by minimizing expected free energy `E[F]` | APS controller explore/exploit mechanism | L2 Core / APS |
| **Cognitive Light Cone** | Ch 5 | `CLC(θ)` — spatiotemporal reach of an agent's goal influence | Agent scope constraints in topology contracts | L2 Core / Topology |
| **Variational Free Energy** | Ch 5 | `F` — divergence between agent's generative model and observations | Theoretical basis for APS tier selection (not directly computed) | — |
| **Expected Free Energy (EFE)** | Ch 5 | `E[F]` — expected surprise under policy; balances epistemic/pragmatic value | UCB-like decision in APS explore vs. exploit | L2 Core / APS |

### 2.3  Part III: Goal-Specification Engineering (Ch 6–9, pp. 91–150)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Three-Layer GMF Stack** | §4 | `G⁰` (constitutional) → `G¹` (persona spec) → `G²` (runtime config) | Celestial (G⁰) → Agent Registry (G¹) → Runtime (G²) | L2 Core / Agents |
| **G⁰ Gap** | §4.3 | Constitutional anchor violated by agent | Celestial.py constraint violation | L2 Core / Constitution |
| **G⁰–G¹ Gap** | §4.3 | Persona spec inconsistent with constitution | Static analysis: persona vs. constitution conflicts | L2 Core / Constitution |
| **G¹–G² Gap** | §4.3 | Runtime config doesn't faithfully implement persona | Config drift detection; CI schema validation | L2 Core / Config |
| **G² Gap** | §4.3 | Runtime behaves outside G² specification | Model drift, adversarial inputs, tool misuse | L3 Engine / Safety |
| **Goal Predicate Set** | §4, Def | `{f_i}` — measurable pass/fail constraints under partition `π` | Goal hierarchy predicates (L0–L6) | L2 Core / Goals |
| **Goal Coupling Matrix** | §4 | `M := Cov_ν(g)` — covariance of predicate pass indicators | Goal interdependency analysis | L2 Core / Goals |
| **Goal Codimension** | §4 | `cod_π(G) := rank_τ(M)` — independent failure directions | Eigenspectrum analysis in topology manager | L2 Core / Topology |
| **Lexicographic Ordering** | §4 | Priority ordering: higher-level goals strictly dominate lower | Celestial L0 > L1 > L2 > L3 > L4 > Terrestrial L5 > L6 | L2 Core / Goals |
| **Celestial Goals (L0–L4)** | Ch 7 | Safety (L0), Legal (L1), Ethical (L2), Permissions (L3), Constitutional (L4) | `holly/agents/constitution/celestial.py` | L2 Core / Constitution |
| **Terrestrial Goals (L5–L6)** | Ch 7 | Primary (L5), Derived (L6) operational goals | Goal decomposer output; workflow objectives | L2 Core / Goals |
| **Failure Predicate** | §4 | `F_G` — observable condition indicating goal breach | `failure_predicate` field in goal contracts | L2 Core / Goals |
| **Tolerated Failure Probability** | §4 | `ε_G` — maximum acceptable `P(F_G = true)` | Threshold per goal level; drives APS triggers | L2 Core / APS |
| **Evaluation Horizon** | §4 | `T` — time window for empirical failure estimation | Monitoring window (configurable per goal) | L2 Core / APS |

### 2.4  Part IV: Steering & Feasibility (Ch 9–11, pp. 151–200)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Steering Power** | Ch 9 | `ς_i` — per-axis capacity × resolution × depth surrogate | Per-predicate control strength metric | L2 Core / Topology |
| **Total Steering Power** | Ch 9 | `S := Σ_i ς_i` | System-wide controllability budget | L2 Core / Topology |
| **Governance Margin** | Ch 9 | `γ := R − C` where `R` = orchestrator rank, `C` = coupling rank | Orchestrator headroom; must be > 0 for feasibility | L2 Core / Topology |
| **Rank Coverage Inequality** | Ch 9, Eq 14 | `R + Σ r_a ≥ cod_π(G)` | Feasibility check in topology manager | L2 Core / Topology |
| **Coupling Coverage** | Ch 9, Eq 15 | `R ≥ C` | Orchestrator must cover cross-agent coupling | L2 Core / Topology |
| **Power Coverage** | Ch 9, Eq 17 | `∀f_i: ς(assigned agent on f_i) ≥ ς_min,i` | Per-predicate power sufficiency check | L2 Core / Topology |
| **Infeasibility Residual** | Ch 9 | `Δ := (I − Π)M(I − Π)^T` | Uncontrollable variance; must be zero for feasibility | L2 Core / Topology |
| **Damage Tolerance** | Ch 9 | `ε_dmg` — maximum tolerable goal divergence | SLA thresholds per goal predicate | L2 Core / Goals |
| **Distinguishability Frontier** | Ch 9 | `ε_dist` — minimum resolvable goal difference | Monitoring resolution floor | L4 Observability |

### 2.5  Part V: Morphogenetic Agency (Ch 10–13, pp. 151–220)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Morphogenetic Field Theory** | Ch 10–11 | Biological development metaphor: agents differentiate from undifferentiated templates via field gradients | Team topology assembly from templates | L2 Core / Topology |
| **Morphogenetic Potential** | Ch 10 | Field potential governing agent differentiation trajectories | Template selection criteria in APS T3 tier | L2 Core / APS |
| **Basin of Attraction** | Ch 10 | Stable equilibrium regions in configuration state space | Stable team configurations; hysteresis `κ` prevents oscillation | L2 Core / Topology |
| **Assembly Index** | Ch 12 | `AI(θ)` — structural construction cost with subassembly reuse | Team complexity metric; cached subassembly reuse count `n_i` | L2 Core / Topology |
| **K-scope (Kaleidoscopic Composition)** | Ch 12 | Pattern-based composition: small set of primitives → large set of valid assemblies | Template library + composition rules in topology manager | L2 Core / Topology |
| **Reflexive Governance** | Ch 13 | Self-monitoring governance loops where system observes and adjusts its own governance | Config control plane with hot reload + audit + rollback | L2 Core / Config |

### 2.6  Part VI: APS Controller & Cascade (Algorithm 1, §4, Appendix C)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **APS Controller** | Alg 1 | Adaptive Persona Steering: `ε`-triggered cascade through governance tiers | `holly/core/aps/controller.py` | L2 Core / APS |
| **APS Tier T0 (Reflexive)** | §4, Alg 1 | Auto-approved prompt adjustments | Prompt template hot-swap | L2 Core / APS |
| **APS Tier T1 (Deliberative)** | §4, Alg 1 | Tool reconfiguration, guardrail adjustment | MCP permission changes, safety threshold updates | L2 Core / APS |
| **APS Tier T2 (Collaborative)** | §4, Alg 1 | Persona revision requiring HITL approval | Agent persona rewrite → human gate | L2 Core / APS |
| **APS Tier T3 (Morphogenetic)** | §4, Alg 1 | Full team topology restructuring | Team disassembly/reassembly from templates | L2 Core / APS |
| **UCB Trigger** | §4, Appendix C | Hoeffding-bound upper confidence bound on `p̂_fail`; triggers cascade when UCB > `ε_G` | APS explore/exploit decision | L2 Core / APS |
| **Hysteresis Parameter** | §4 | `κ` — debounce for tier transitions; requires `n` consecutive windows | Prevents oscillation between APS tiers | L2 Core / APS |
| **Explore/Exploit** | §4, Appendix C | APS stays in *exploit* when goals met; enters *explore* when UCB crosses `ε_G` | APS mode selection | L2 Core / APS |

### 2.7  Part VII–VIII: Engineering Bridge & Implementation (Ch 14–15, pp. 200–240)

| Monograph Concept | Section | Formal Definition | Holly Component | SAD Layer |
|-------------------|---------|-------------------|-----------------|-----------|
| **Engineering Bridge** | Ch 14 | Systematic mapping from formal theory to implementation artifacts | This glossary document + architecture-as-code pipeline | — (process) |
| **Compositional Semantics** | Ch 14 | Meaning preservation through composition: if components satisfy spec, composed system satisfies composed spec | Interface contracts in ICD; verified at SIL boundaries | L1 Kernel |
| **Invariant Preservation** | Ch 14 | Properties maintained across transformations: kernel invariants K1–K8 | KernelContext async context manager wrapping every boundary crossing | L1 Kernel |
| **Effectively-Once Semantics** | Ch 14 | Idempotent execution: side effects occur exactly once despite retries | Workflow engine: idempotency keys (RFC 8785) + dedupe + compensating actions | L3 Engine / Workflow |

### 2.8  Appendices: Worked Examples & Configuration Artifacts

| Monograph Concept | Section | Holly Relevance |
|-------------------|---------|-----------------|
| **AWS Configuration Template** | Appendix A (v1.1) | Reference YAML schema for agent deployment; informs `architecture.yaml` parser |
| **Agent Configuration Artifacts** | Appendix B | `agent_registry.yaml`, `constitution.md`, dashboard YAML specs |
| **Agentic E-Commerce Case Study** | Appendix C | Validates channel capacity, APS cascade, efficiency metrics on production data |
| **Research Programme Integration** | Appendix D | 9-month phased research plan: Phase 1 (taxonomy), Phase 2A/2B (toolkit + constitution), Phase 3 (monitoring + cascade) |
| **Space Domain Awareness Ops Center** | Appendix E | 12-predicate worked example demonstrating full governance procedure |
| **Autonomous E-Commerce Platform** | Appendix F | 14-predicate, 8-agent, 2-level hierarchy worked example with eigenspectrum analysis |

---

## 3  Holly-Specific Terms → Monograph Grounding

| Holly Term | Implementation Location | Monograph Grounding | Monograph Section |
|------------|------------------------|---------------------|-------------------|
| **KernelContext** | `holly/kernel/context.py` | Invariant enforcement wrapper; implements compositional semantics guarantee | Ch 14 (Engineering Bridge) |
| **K1: Schema Validation** | `holly/kernel/` | Ensures `π` produces valid `σ ∈ Σ` | Partition validity (Ch 2) |
| **K2: Permission Gates** | `holly/kernel/` | Enforces Markov blanket boundaries | Markov blanket (Ch 5) |
| **K3: Bounds Checking** | `holly/kernel/` | Validates `ε_eff < ε_dmg` | Damage tolerance (Ch 9) |
| **K4: Trace Injection** | `holly/kernel/` | Correlation IDs for channel capacity measurement | Channel instrumentation (Appendix C) |
| **K5: Idempotency Key Gen** | `holly/kernel/` | RFC 8785 canonical JSON → deterministic keys | Effectively-once (Ch 14) |
| **K6: Durability WAL** | `holly/kernel/` | Audit-only write-ahead log (not replay source) | Audit trail (Appendix E, predicate 12) |
| **K7: HITL Gates** | `holly/kernel/` | Human-in-the-loop for APS T2+ transitions | APS cascade HITL requirement (Alg 1) |
| **K8: Eval Gates** | `holly/kernel/` | Evaluation checkpoints for goal monitoring | UCB trigger evaluation (§4) |
| **Goal Decomposer** | `holly/core/goals/` | Implements `G⁰ → G¹` decomposition with lexicographic gating | Goal-Specification Engineering (§4, Ch 7) |
| **Topology Manager** | `holly/core/topology/` | Manages team composition; checks rank/coupling/power coverage | Feasibility verification (Ch 9, Eqs 14–17) |
| **Eigenspectrum** | `holly/core/topology/eigenspectrum.py` | `rank_τ(M)` computation for codimension estimation | Codimension / eigenspectrum (Ch 9, Appendix E–F) |
| **APS Controller** | `holly/core/aps/controller.py` | T0–T3 tiered cascade with UCB trigger | APS Algorithm 1 (§4) |
| **Lane Policy** | `holly/engine/lanes/policy.py` | Dynamic concurrency limits, per-tenant quotas | Resource budgets `W` (Ch 1) |
| **Workflow Engine** | `holly/engine/workflow/` | Durable task graphs with effectively-once semantics | Effectively-once (Ch 14); checkpoint/resume |
| **MCP Registry** | `holly/engine/mcp/` | Introspectable tool catalog with per-agent permissions | Agent configuration `θ` (Ch 5); tool credential store |
| **Event Bus** | `holly/observability/event_bus.py` | Unified ingest with PII redaction and tenant-scoped fanout | Channel instrumentation; `P̂` estimation (Appendix C) |
| **Redaction Library** | `holly/safety/redaction.py` | Canonical redaction; all redactors import this | Redact-before-persist / redact-before-egress |
| **Egress Control** | `holly/infra/egress.py` | L7 domain allowlist + redaction; L3 NAT routing | Controlled information flow; prevents unpartitioned leakage |
| **Secrets Manager** | `holly/infra/secrets.py` | KMS/Vault client, key rotation, credential store | `θ` security; Authentik client secret management |
| **Celestial Constitution** | `holly/agents/constitution/celestial.py` | L0–L4 non-negotiable constraints | `G⁰` (Ch 7) |
| **Terrestrial Goals** | `holly/agents/constitution/terrestrial.py` | L5–L6 operational goals | `G¹` derived goals (Ch 7) |
| **Memory System** | `holly/core/memory/` | Short (Redis) / Medium (PG) / Long (Chroma) | Agent internal states `μ`; shared context `K` |
| **Config Control Plane** | `holly/config/` | Hot reload + audit + rollback + HITL for dangerous keys | Reflexive governance (Ch 13) |
| **JWT Middleware** | `holly/api/middleware/jwt.py` | JWKS public key verification, short-lived tokens | Authentication boundary (not in monograph scope; infra concern) |
| **Sandbox** | `sandbox/` | gVisor/Firecracker isolated code execution | Security boundary; no network egress enforces Markov blanket for code exec |

---

## 4  Theorems & Key Results Referenced in Holly Design

| Theorem | Statement (abbreviated) | Holly Design Implication |
|---------|------------------------|------------------------|
| **Theorem 1** (Induced Macro-Channel) | Every communicating agent pair induces a measurable macro-channel `P(σ_out\|σ_in, u)` | All inter-agent interfaces must be instrumentable for `P̂` estimation |
| **Theorem 2** (Data Processing Inequality) | `C(P_chain) ≤ min_i C(P_i)` for cascaded channels | Multi-agent pipeline capacity bounded by weakest link; topology manager must identify bottlenecks |
| **Theorem 3** (Capacity-Stability) | If `Σ_stable = Σ` and CV of `Ĉ(P)` < threshold, channel attribution is non-trivial | Stability assessment required before channel metrics are trusted |
| **Algorithm 1** (APS Cascade) | `ε`-triggered tiered response: T0 (prompt) → T1 (tool) → T2 (persona, HITL) → T3 (topology, HITL) | Direct implementation in `holly/core/aps/controller.py` |
| **Feasibility Inequalities** (Eqs 14–17) | Rank coverage, coupling coverage, governance margin, power coverage | Topology manager pre-flight checks before team deployment |

---

## 5  Monograph Structure Overview

| Part | Chapters | Pages | Topic | Primary Holly Relevance |
|------|----------|-------|-------|------------------------|
| **I** | 1–3 | 3–50 | Channel Theory | Information-theoretic foundation; channel metrics |
| **II** | 4–5 | 51–90 | Agency & Active Inference | Agent model; Markov blankets; cognitive light cones |
| **III** | 6–9 | 91–150 | Goal-Specification Engineering | G⁰/G¹/G² stack; goal predicates; lexicographic ordering |
| **IV** | 9–11 | 151–200 | Steering & Feasibility | Steering power; governance margin; feasibility checks |
| **V** | 10–13 | 151–220 | Morphogenetic Agency | Team assembly; basin of attraction; K-scope |
| **VI** | — | — | APS Controller | Algorithm 1; UCB trigger; tiered cascade |
| **VII–VIII** | 14–15 | 200–240 | Engineering Bridge | Theory-to-implementation mapping; invariant preservation |
| **Appendices** | A–F | 241–266 | Configuration, Case Studies, Worked Examples | YAML templates; e-commerce validation; SDA ops center; e-commerce platform |
| **Bibliography** | — | 267–269 | 62 references | Landauer, Bennett, Zurek, Baez, Friston, Anthropic, etc. |
| **Change Log** | — | 269 | v0.1–v2.0 (2026-02-05 to 2026-02-10) | Monograph evolution history |

---

## 6  Cross-Reference: SAD Layers → Monograph Chapters

| SAD Layer | Primary Monograph Grounding |
|-----------|-----------------------------|
| L0: Cloud/VPC | Infrastructure (not in monograph scope) |
| L1: Kernel | Compositional semantics (Ch 14), invariant preservation, Markov blanket enforcement (Ch 5) |
| L2: Core | Goal-Specification Engineering (Ch 6–9), APS (Alg 1), morphogenetic assembly (Ch 10–13), steering/feasibility (Ch 9) |
| L3: Engine | Effectively-once semantics (Ch 14), channel composition (Ch 2–3), digital branching (Ch 3) |
| L4: Observability | Channel capacity measurement (Ch 1–2, Appendix C), `Σ_stable` assessment, PII redaction |
| L5: Console | Visualization of goal trees, topology, traces (engineering bridge, Ch 14) |
| Data Stores | Persistence for `μ` (memory), `M` (coupling), task state, audit WAL |
| Sandbox | Security boundary; enforces Markov blanket for code execution |
| Egress | Controlled information flow; prevents unpartitioned state leakage |

---

## 7  Terms NOT in Monograph (Holly-Originated)

These Holly terms have no direct monograph counterpart. They arise from implementation engineering decisions:

| Holly Term | Origin | Notes |
|------------|--------|-------|
| Row-Level Security (RLS) | PostgreSQL multi-tenancy | Infra isolation; monograph assumes single-tenant |
| Sentinel/Cluster (Redis) | HA deployment | Operational concern |
| gVisor / Firecracker | Sandbox isolation tech | Specific technology choice |
| Authentik / OIDC | Identity provider | AuthN/AuthZ infrastructure |
| JWKS verification | JWT standard | API security |
| WAF Rules | Web application firewall | Perimeter defense |
| ChromaDB | Vector store choice | Specific technology for long-term memory |
| Ollama | Local inference runtime | Cost optimization for `W` |
| MCP (Model Context Protocol) | Tool interface standard | Standardized tool registry protocol |
| EDDOps | Eval-Driven Development Operations | Holly-specific development methodology |

---

*Document generated from complete monograph reading (289 pages). Notation table sourced from pp. 1–2. Chapter mapping based on Part I–VIII structure plus Appendices A–F.*
