# Adaptive Partition Selection (APS) Implementation Plan — v3

## Implementing Informational Monism's Core Experimental Protocol in a Live Agentic System

**Author**: Sean P. Allen
**Date**: February 6, 2026
**Target System**: ecom-agents (live at localhost:8050)
**Version**: 3.0 — UCB confidence bounds, actual token accounting, workflow tracing, partition audits, theta caching, eta variants
**Status**: Draft — Pre-Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What Changed from v2 to v3](#2-what-changed-from-v2-to-v3)
3. [Theoretical Foundation](#3-theoretical-foundation)
   - 3.1 [The Induced Macro-Channel](#31-the-induced-macro-channel)
   - 3.2 [Informational Efficiency](#32-informational-efficiency)
   - 3.3 [The Composition Bound (Theorem 1)](#33-the-composition-bound-theorem-1)
   - 3.4 [Epsilon-Triggered Partition Switching](#34-epsilon-triggered-partition-switching)
   - 3.5 [Passive Transport vs Active Regeneration](#35-passive-transport-vs-active-regeneration)
   - 3.6 [Admissibility Constraints (C1-C3)](#36-admissibility-constraints-c1-c3)
4. [System Under Test: ecom-agents](#4-system-under-test-ecom-agents)
   - 4.1 [Architecture Overview](#41-architecture-overview)
   - 4.2 [Agent Inventory and Models](#42-agent-inventory-and-models)
   - 4.3 [Existing Infrastructure We Build On](#43-existing-infrastructure-we-build-on)
   - 4.4 [Message Flow and State Schema](#44-message-flow-and-state-schema)
5. [Channel Identification: 7 Induced Macro-Channels](#5-channel-identification-7-induced-macro-channels)
   - 5.1 [K1: Orchestrator Routing Channel](#51-k1-orchestrator-routing-channel)
   - 5.2 [K2: Sales & Marketing Execution Channel](#52-k2-sales--marketing-execution-channel)
   - 5.3 [K3: Operations Execution Channel](#53-k3-operations-execution-channel)
   - 5.4 [K4: Revenue Analytics Execution Channel](#54-k4-revenue-analytics-execution-channel)
   - 5.5 [K5: Content Writer Sub-Agent Channel](#55-k5-content-writer-sub-agent-channel)
   - 5.6 [K6: Campaign Analyzer Sub-Agent Channel](#56-k6-campaign-analyzer-sub-agent-channel)
   - 5.7 [K7: Tool Call Channel](#57-k7-tool-call-channel)
6. [Partition Definitions: Fine and Coarse Schemes](#6-partition-definitions-fine-and-coarse-schemes)
   - 6.1 [Design Principles](#61-design-principles)
   - 6.2 [Complete Partition Table](#62-complete-partition-table)
   - 6.3 [Classification Functions](#63-classification-functions)
   - 6.4 [Partition Audit Metadata (C1-C3)](#64-partition-audit-metadata-c1-c3)
7. [Theta Configurations: The Expanded Control Tuple](#7-theta-configurations-the-expanded-control-tuple)
   - 7.1 [Why Theta is More Than a Partition](#71-why-theta-is-more-than-a-partition)
   - 7.2 [ThetaConfig Data Structure](#72-thetaconfig-data-structure)
   - 7.3 [Protocol Levels](#73-protocol-levels)
   - 7.4 [Three-Level Escalation Tiers](#74-three-level-escalation-tiers)
   - 7.5 [Complete Theta Table: All 7 Channels x 3 Levels](#75-complete-theta-table-all-7-channels-x-3-levels)
8. [Regeneration Protocols](#8-regeneration-protocols)
   - 8.1 [Why Coarsening Alone Is Insufficient](#81-why-coarsening-alone-is-insufficient)
   - 8.2 [ConfirmProtocol: Retry with Clarification](#82-confirmprotocol-retry-with-clarification)
   - 8.3 [CrosscheckProtocol: Deterministic Validation](#83-crosscheckprotocol-deterministic-validation)
   - 8.4 [Per-Channel Validator Definitions](#84-per-channel-validator-definitions)
   - 8.5 [Regeneration Cost Accounting](#85-regeneration-cost-accounting)
   - 8.6 [Future Regeneration Patterns](#86-future-regeneration-patterns)
9. [Goal Specifications](#9-goal-specifications)
   - 9.1 [Two-Tier Goal Architecture](#91-two-tier-goal-architecture)
   - 9.2 [Tier 1: Mission-Critical Goals (Hard Floors)](#92-tier-1-mission-critical-goals-hard-floors)
   - 9.3 [Tier 2: Operational Goals (Epsilon-Triggered)](#93-tier-2-operational-goals-epsilon-triggered)
   - 9.4 [Goal-to-Channel Mapping](#94-goal-to-channel-mapping)
10. [Information-Theoretic Computations](#10-information-theoretic-computations)
    - 10.1 [Confusion Matrix Construction](#101-confusion-matrix-construction)
    - 10.2 [Mutual Information](#102-mutual-information)
    - 10.3 [Channel Capacity via Blahut-Arimoto](#103-channel-capacity-via-blahut-arimoto)
    - 10.4 [Informational Efficiency eta (Three Variants)](#104-informational-efficiency-eta-three-variants)
    - 10.5 [Chain Capacity and Bottleneck Identification (Realized Paths)](#105-chain-capacity-and-bottleneck-identification-realized-paths)
11. [APS Controller Design](#11-aps-controller-design)
    - 11.1 [Rolling Failure Estimation with UCB Confidence Bounds](#111-rolling-failure-estimation-with-ucb-confidence-bounds)
    - 11.2 [Three-Level Escalation Logic with Hysteresis](#112-three-level-escalation-logic-with-hysteresis)
    - 11.3 [Theta Caching with Staleness Detection](#113-theta-caching-with-staleness-detection)
    - 11.4 [Evaluation Cycle](#114-evaluation-cycle)
    - 11.5 [W_total Accounting (Actual Token Costs)](#115-w_total-accounting-actual-token-costs)
12. [Instrumentation Strategy](#12-instrumentation-strategy)
    - 12.1 [The Wrapper Pattern](#121-the-wrapper-pattern)
    - 12.2 [Node-Level Instrumentation](#122-node-level-instrumentation)
    - 12.3 [Token Accumulator Pattern](#123-token-accumulator-pattern)
    - 12.4 [Trace ID and Path ID Injection](#124-trace-id-and-path-id-injection)
    - 12.5 [Regeneration Integration in the Wrapper](#125-regeneration-integration-in-the-wrapper)
    - 12.6 [Tool-Call Instrumentation](#126-tool-call-instrumentation)
    - 12.7 [Error Safety](#127-error-safety)
13. [Database Schema](#13-database-schema)
    - 13.1 [Table: aps_observations (Extended)](#131-table-aps_observations-extended)
    - 13.2 [Table: aps_metrics (Extended)](#132-table-aps_metrics-extended)
    - 13.3 [Table: aps_theta_switches](#133-table-aps_theta_switches)
    - 13.4 [Table: aps_theta_cache (New)](#134-table-aps_theta_cache-new)
14. [API Endpoints and WebSocket Events](#14-api-endpoints-and-websocket-events)
    - 14.1 [REST Endpoints](#141-rest-endpoints)
    - 14.2 [WebSocket Event Types](#142-websocket-event-types)
15. [New File Structure](#15-new-file-structure)
16. [Modifications to Existing Files](#16-modifications-to-existing-files)
17. [Implementation Phases](#17-implementation-phases)
18. [Testing Strategy](#18-testing-strategy)
    - 18.1 [Unit Tests](#181-unit-tests)
    - 18.2 [Integration Tests](#182-integration-tests)
    - 18.3 [Live Validation Protocol](#183-live-validation-protocol)
19. [Paper Predictions Under Test](#19-paper-predictions-under-test)
20. [Dependencies](#20-dependencies)
21. [Key Design Decisions and Rationale](#21-key-design-decisions-and-rationale)
22. [Roadmap: What Comes After v3](#22-roadmap-what-comes-after-v3)

---

## 1. Executive Summary

### Purpose

This document specifies the implementation of an **Adaptive Partition Selection (APS)** system for the ecom-agents multi-agent e-commerce platform. The APS system is the first live experimental instantiation of the theoretical framework described in the paper *"Informational Monism: Computation, Communication, and Conduction as Unified Phenomena"* (Allen, 2026).

### What We Are Building

The paper argues that every interface between communicating agents can be modeled as an **induced macro-channel** — a stochastic map from input symbols to output symbols, where "symbols" are defined by coarse-graining (partitioning) the high-dimensional state space at each boundary. The paper further proposes that when goal failure rates exceed a tolerance threshold, systems should adaptively switch between finer and coarser partition schemes to maintain recoverability.

We are building an instrumentation and control layer that:

1. **Identifies and instruments 7 agent-to-agent interfaces** as induced macro-channels (K1 through K7), covering the orchestrator, all three specialist agents, two sub-agents, and all external tool calls.

2. **Defines 14 partition schemes** (2 per channel: fine and coarse), each with explicit symbol alphabets, deterministic classification functions, and **C1-C3 admissibility audit metadata** proving each partition is interface-bounded, counterfactually robust, and compositionally local.

3. **Defines 21 theta configurations** (3 per channel: nominal, degraded, critical), each bundling a partition scheme with a model override and a regeneration protocol level. Theta is a tuple θ = (π, model, protocol).

4. **Logs every interface crossing** as a (sigma_in, sigma_out) observation tuple, with timestamps, latency, **actual token counts from LLM callbacks**, cost metadata, **workflow trace_id**, and **routing path_id** into PostgreSQL.

5. **Computes information-theoretic metrics** in real time: empirical confusion matrices P_hat(sigma_out | sigma_in), mutual information I(X;Y), channel capacity C(P) via the Blahut-Arimoto algorithm, and **three variants of informational efficiency**: eta_usd (bits per dollar), eta_token (bits per token), and eta_time (bits per second).

6. **Validates the composition bound** (Theorem 1: C(P_chain) <= min_k C(P_k)) across **actually realized workflow paths** using path_id tagging, not just predefined hypothetical chains.

7. **Implements a three-level APS controller** that monitors rolling goal-failure rates using **UCB confidence bounds** (Beta-Binomial posterior) for mission-critical goals and raw p_hat_fail for operational goals, triggering proportional escalation with hysteresis.

8. **Caches successful theta configurations** keyed by context fingerprint (circuit breaker states, time-of-day, error regime), with staleness detection to prevent applying stale solutions when conditions change.

9. **Implements two regeneration protocols** (ConfirmProtocol and CrosscheckProtocol) that embody the paper's Section 4 distinction between passive transport and active regeneration.

10. **Exposes all metrics** via REST API endpoints (including workflow trace and theta cache inspection) and WebSocket events for observation and analysis.

### What This Validates

When running live, this system directly tests the following predictions from the paper:

- **P1 (Rate ceiling)**: Agent interfaces have measurable channel capacities that constrain information throughput — now with eta_token and eta_time for richer comparison.
- **P3 (Noise collapses alphabets)**: Under degraded conditions, the effective stable symbol set shrinks — UCB catches degradation earlier with small samples.
- **P5 (Medium constraints reshape partitions)**: Different operational conditions favor different partition granularities.
- **P7 (Epsilon-triggered switching)**: Discrete partition transitions occur with hysteresis — theta caching accelerates re-stabilization.
- **Theorem 1 (Composition bound)**: Validated on realized workflow paths via path_id, not just predefined chains.
- **Section 4 (Regeneration)**: Active regeneration restores recoverability at a measurable energy cost — now with actual token/dollar costs, not estimates.
- **NEW: eta improves under APS**: With three eta variants, we can measure whether APS adaptation actually improves efficiency vs a fixed baseline.
- **NEW: Caching reduces switching latency**: Measure time-to-stabilize with vs without cache hits.

---

## 2. What Changed from v2 to v3

v2 extended v1 with expanded theta configurations, regeneration protocols, and mission-critical goals. A second alternative architecture proposed a broader "CommerceOS" vision. v3 evaluates that alternative and adopts 7 concrete improvements while maintaining v2's scope discipline.

### Seven Improvements Adopted

**1. UCB confidence bounds for critical goal triggers**

v2 uses raw p_hat_fail for all switching decisions. With only 20 observations, p_hat = 0/20 = 0.0 gives false confidence that nothing is wrong. v3 replaces this with a Beta-Binomial upper confidence bound for mission-critical goals: UCB(0.95) with Jeffreys prior Beta(0.5, 0.5). Even with 0 failures in 20 observations, UCB = 0.036, keeping APS alert. Applied only to Tier 1 goals; Tier 2 continues using raw p_hat with min-observation guard.

**2. Actual token accounting via LangChain callbacks**

v2 uses `estimate_cost()` from MODEL_REGISTRY rates and estimated token counts. But the ForgeEventCallbackHandler already captures `response.llm_output.get("token_usage")` in `on_llm_end` with actual prompt_tokens and completion_tokens. v3 plumbs these through to observations via a thread-local token accumulator, making eta meaningful in real dollars rather than estimates.

**3. trace_id for workflow correlation**

LangChain provides per-call run_id, but there's no persistent ID linking all observations within one workflow execution. v3 generates a trace_id UUID at graph invocation (in serve.py) and threads it through observations. Enables querying "show me all channel crossings for this specific order_check run."

**4. path_id for empirical Theorem 1 validation**

v2 computes chain_capacity over predefined paths (K1->K3->K7). But observations aren't tagged with which path they belong to. v3 adds path_id (e.g., "K1>K3>K7") built incrementally as the workflow progresses. This makes Theorem 1 validation empirically grounded on realized paths, not hypothetical ones.

**5. Partition audit metadata (C1-C3 admissibility)**

The paper's admissibility constraints (C1: interface-boundedness, C2: counterfactual robustness, C3: compositional locality) are not just theory. v3 requires each partition scheme to include three metadata fields (`field_rule`, `intervention_story`, `locality_owner`) proving admissibility at registration time. This prevents meaningless partitions from entering the system.

**6. Theta caching with staleness detection**

When the controller finds a theta configuration that restores p_fail <= epsilon_G, it caches it keyed by a context fingerprint (circuit breaker states + time-of-day bucket + recent error regime). On future degradation with matching context, it tries the cached theta first before standard escalation. Cached thetas are rejected if older than 1 hour or if context has diverged.

**7. eta variants as first-class stored metrics**

v2 mentions eta_token and eta_time in passing but only stores a single eta (bits/$). v3 stores all three variants in aps_metrics: eta_usd (bits/dollar), eta_token (bits/token), eta_time (bits/second). K1 (free Ollama) has infinite eta_usd but finite eta_time — a single number hides this.

### What v3 Does NOT Adopt (and Why)

| Proposal | Reason for rejection |
|----------|---------------------|
| K8-K12 channels | No agents exist for merchandising, pricing, support, governance, experimentation. Can't instrument what doesn't exist. |
| CommerceOS rebrand / Executive Allocator | Renaming doesn't improve measurement. Orchestrator works. |
| ChangeSet pattern | Requires rearchitecting all agent return types. Roadmap. |
| Governance Gate as K11 agent | v2's Tier 1 goals with block-and-alert already cover this. A dedicated agent is overkill when a validator function suffices. |
| Topology changes (Tier 3 mutations) | Parallel agents, rerouting, validator agents. Requires new infrastructure that doesn't exist. |
| "Commerce CI/CD" / staging / canary | No staging Shopify store. Requires dev store setup. Roadmap. |
| Context embeddings in ChromaDB | Overkill. Simple hash-based fingerprinting (circuit breaker states + error counts) is sufficient. |
| PII scrub / privacy-aware logging | Overengineered for current scale (~50 obs/day). |
| Shared context K versioning (K_version, K_hash) | No formal "shared context K" object exists in the system. Roadmap after ChromaDB collections are formalized. |
| reasoning_effort as a theta knob | System doesn't use variable reasoning effort. Models are called with fixed settings. Future knob. |
| Majority vote / two-phase commit regeneration | Already noted as future patterns in v2 Section 8.6. Not needed for initial validation. |

---

## 3. Theoretical Foundation

### 3.1 The Induced Macro-Channel

The paper's central construction: given a system with microstate space X that evolves under dynamics K_T with control u, and given an input partition pi_in: X -> Sigma_in and an output partition pi_out: X -> Sigma_out, the microdynamics induce a stochastic channel on symbols:

```
P(sigma_out | sigma_in, u) = integral mu(dx_i | sigma_in) integral_{pi_out^{-1}(sigma_out)} K_T(dx_out | x_i, u)
```

In our system:
- **X** (microstate space) = the full AgentState dictionary — messages, task_type, trigger_payload, all result fields, memory_context, error state, etc. This is a high-dimensional, mixed-type space.
- **K_T** (dynamics) = the LLM inference + tool execution within each agent node. The stochasticity comes from LLM sampling, API response variability, and timing.
- **pi_in, pi_out** (partitions) = our classification functions that map AgentState fields to discrete symbols.
- **u** (control) = the system prompts, model selection, temperature settings, tool configurations, and the theta configuration (partition + model override + protocol level).

The induced macro-channel P(sigma_out | sigma_in, u) is empirically estimated as a confusion matrix from logged observations.

### 3.2 Informational Efficiency

The paper defines:

```
eta(pi, T, u) = C(P) / W
```

Where C(P) is the Shannon capacity of the induced macro-channel (bits per use) and W is the work/resource expenditure. v3 reports three variants:

- **eta_usd** = C(P) / W_dollars — bits per dollar. Primary efficiency metric.
- **eta_token** = C(P) / W_tokens — bits per token. Useful for comparing models independent of pricing.
- **eta_time** = C(P) / W_seconds — bits per second. Useful for latency-sensitive workflows.

When W is very small (e.g., the orchestrator uses free Ollama), eta_usd approaches infinity. In these cases, eta_token and eta_time remain finite and informative.

We also compute the empirical estimator:

```
eta_hat = log2(|Sigma_stable|) / W
```

Where Sigma_stable is the set of symbols that achieve (T, epsilon)-recoverability.

### 3.3 The Composition Bound (Theorem 1)

For a chain of n compatible links, the composed macro-channel capacity satisfies:

```
C(P_chain) <= min_k C(P_k)
```

This follows from the data processing inequality. In ecom-agents, the chain is:

```
Orchestrator (K1) -> Specialist Agent (K2/K3/K4) -> [Sub-agents (K5,K6)] -> Tool Calls (K7)
```

v3 computes per-channel capacities and identifies the bottleneck on **actually realized workflow paths** (tagged with path_id), not just predefined hypothetical chains. This makes Theorem 1 validation empirically grounded.

### 3.4 Epsilon-Triggered Partition Switching

The APS controller implements the paper's Section 9.3 mechanism:

1. Maintain a rolling estimate of goal failure: p_hat_fail(t) = (failures in window T) / (total observations in window T)
2. For mission-critical goals, compute **UCB(p_fail)** using Beta-Binomial posterior (v3 addition)
3. When p_hat_fail(t) > epsilon_G (or UCB > epsilon_G for critical goals): escalate theta level
4. When p_hat_fail(t) < epsilon_G * 0.5: de-escalate theta level (with cooldown)
5. W_total = W_operate + W_search: the cost of adaptation is charged against the total work budget

### 3.5 Passive Transport vs Active Regeneration

This is the paper's Section 4.

**Passive transport**: A chain link operates without injecting additional work to restore the partition. The agent runs, produces output, and the result is logged. If noise degrades the output, the degradation propagates downstream. This is level 0 (nominal) in the theta configuration.

**Active regeneration**: A chain link spends work to re-establish a stable symbol set with bounded error. In our agentic system:

- **ConfirmProtocol** (level 1): On failure, retry the agent with a clarified prompt. Analogous to a repeater that re-amplifies a degraded signal.
- **CrosscheckProtocol** (level 2): After LLM output, run a deterministic validator. Analogous to error-correcting codes that detect and flag corruption.

### 3.6 Admissibility Constraints (C1-C3)

The paper specifies three constraints that partitions must satisfy to be non-trivially informative:

**C1 — Interface-boundedness**: The classification function depends only on observable interface state (AgentState fields), not on internal LLM activations or other microscopic degrees of freedom.

**C2 — Counterfactual robustness**: Different inputs would produce different classifications under the same mapping, and these differences are achievable via the system's normal control interface (different task descriptions, different API states).

**C3 — Compositional locality**: The partition aligns with the modular substructure of the system — each symbol is "owned" by one module.

v3 enforces these by requiring explicit metadata on every partition scheme. Partitions that cannot provide audit metadata are inadmissible and cannot be registered.

---

## 4. System Under Test: ecom-agents

### 4.1 Architecture Overview

ecom-agents is an autonomous e-commerce platform built with LangChain + LangGraph. It operates a Shopify storefront (liberty-forge-2.myshopify.com) selling patriotic apparel via Printful print-on-demand, with Stripe payments, Instagram marketing, and AI-driven analytics.

The system runs 24/7 with 6 scheduled jobs and processes tasks through a multi-agent graph:

```
                        +----------------------+
                        |   APScheduler Jobs    |
                        |  (order_check/30min,  |
                        |   instagram/9am+3pm,  |
                        |   campaign/Mon 9am,   |
                        |   revenue/8am daily)  |
                        +----------+-----------+
                                   |
                                   v
                        +----------------------+
                        |  Master Orchestrator  |
                        |   (Ollama Qwen 2.5)  |
                        |                      |
                        |  Classifies task ->  |
                        |  routes to specialist |
                        +----------+-----------+
                                   |
              +--------------------+--------------------+
              v                    v                    v
   +----------------+   +----------------+   +----------------+
   | Sales/Marketing|   |   Operations   |   |    Revenue     |
   |   (GPT-4o)     |   |  (GPT-4o-mini) |   |  (Opus 4.6)   |
   |                |   |                |   |                |
   | Instagram,     |   | Orders, fulfil,|   | Reports,       |
   | campaigns      |   | inventory      |   | pricing,       |
   +-------+--------+   +-------+--------+   | chargebacks    |
           |                    |             +-------+--------+
           | (if complex)       |                     |
           v                    |                     |
   +----------------+          |                     |
   |  Sub-Agent     |          |                     |
   |  Subgraph      |          |                     |
   |                |          |                     |
   | Writer (GPT-4o)|          |                     |
   | Image (mini)   |          |                     |
   | Hashtag (Qwen) |          |                     |
   | Analyzer(Opus) |          |                     |
   +-------+--------+          |                     |
           |                   |                     |
           +-------------------+---------------------+
                               |
                        +------v------+
                        |  Tool Calls |
                        |  Shopify    |
                        |  Stripe     |
                        |  Printful   |
                        |  Instagram  |
                        +-------------+
```

### 4.2 Agent Inventory and Models

| Agent | Model | Provider | Cost (input/output per 1K tokens) | File |
|-------|-------|----------|-----------------------------------|------|
| Orchestrator | qwen2.5:3b | Ollama (local) | $0 / $0 | src/agents/orchestrator.py |
| Sales/Marketing | GPT-4o | OpenAI | $2.50 / $10.00 | src/agents/sales_marketing.py |
| Operations | GPT-4o-mini | OpenAI | $0.15 / $0.60 | src/agents/operations.py |
| Revenue Analytics | Claude Opus 4.6 | Anthropic | $15.00 / $75.00 | src/agents/revenue.py |
| Content Writer | GPT-4o | OpenAI | $2.50 / $10.00 | src/agents/sub_agents.py |
| Image Selector | GPT-4o-mini | OpenAI | $0.15 / $0.60 | src/agents/sub_agents.py |
| Hashtag Optimizer | qwen2.5:3b | Ollama (local) | $0 / $0 | src/agents/sub_agents.py |
| Campaign Analyzer | Claude Opus 4.6 | Anthropic | $15.00 / $75.00 | src/agents/sub_agents.py |

### 4.3 Existing Infrastructure We Build On

**EventBroadcaster** (`src/events.py`): Singleton that broadcasts structured JSON events to all connected WebSocket clients. APS adds three event types. The `on_llm_end` handler already extracts `response.llm_output.get("token_usage")` — v3 feeds this into the token accumulator for actual cost tracking.

**ForgeEventCallbackHandler** (`src/events.py`): LangChain callback handler that hooks into `on_chain_start`, `on_chain_end`, `on_tool_start`, `on_tool_end`, `on_llm_start`, `on_llm_end`. v3 extends `on_llm_end` to populate the token accumulator and extends `on_tool_start`/`on_tool_end` for K7 observations.

**Circuit Breaker** (`src/resilience/circuit_breaker.py`): Per-service circuit breakers with CLOSED -> OPEN -> HALF_OPEN state machine. v3 uses circuit breaker states as inputs to the **context fingerprint** for theta caching.

**MODEL_REGISTRY** (`src/llm/config.py`): Contains per-model cost rates (cost_per_1k_input, cost_per_1k_output). Used as fallback when actual token counts are unavailable (e.g., Ollama which may not report token usage).

**FALLBACK_CHAINS** (`src/llm/fallback.py`): Existing model fallback chains. The theta model_override field aligns with these chains.

**APScheduler** (`src/scheduler/autonomous.py`): Background scheduler with 6 existing jobs. We add a 7th job (`aps_evaluation`) that runs every 5 minutes.

**PostgreSQL** (port 5434): Already running. We add 4 tables for APS data (3 from v2 + 1 new cache table).

### 4.4 Message Flow and State Schema

All agent communication flows through a shared `AgentState` TypedDict defined in `src/state.py`:

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    task_type: NotRequired[str]
    task_complexity: NotRequired[str]
    current_agent: NotRequired[str]
    route_to: NotRequired[str]
    trigger_source: NotRequired[str]
    trigger_payload: NotRequired[dict]
    should_spawn_sub_agents: NotRequired[bool]
    sub_agents_spawned: NotRequired[list[str]]
    memory_context: NotRequired[str]
    sales_result: NotRequired[dict]
    operations_result: NotRequired[dict]
    revenue_result: NotRequired[dict]
    sub_agent_results: NotRequired[dict]
    error: NotRequired[str]
    retry_count: NotRequired[int]
```

v3 adds one internal field to the state during instrumentation: `_aps_path_id` (str) — the incrementally-built routing path for Theorem 1 validation.

---

## 5. Channel Identification: 7 Induced Macro-Channels

*(Sections 5.1 through 5.7 are unchanged from v2. See APS_IMPLEMENTATION_PLAN_v2.md for the full channel descriptions.)*

### 5.1 K1: Orchestrator Routing Channel

The orchestrator receives a task description and classifies it into a task_type and route_to destination. This is the "encoder" of the system. Misclassification here propagates errors through the entire chain.

### 5.2 K2: Sales & Marketing Execution Channel

The sales agent receives a classified sales task and produces content (Instagram post, campaign plan, or product launch materials).

### 5.3 K3: Operations Execution Channel

The operations agent handles order checks, inventory syncs, and fulfillment via Shopify and Printful APIs. Most frequently invoked channel (~48 invocations/day from order_check alone).

### 5.4 K4: Revenue Analytics Execution Channel

The revenue agent (Claude Opus 4.6) analyzes financial data from Stripe. Most expensive channel ($15+$75 per 1K tokens). Natural target for efficiency optimization.

### 5.5 K5: Content Writer Sub-Agent Channel

Generates Instagram post captions and content.

### 5.6 K6: Campaign Analyzer Sub-Agent Channel

Evaluates sub-agent outputs and predicts engagement.

### 5.7 K7: Tool Call Channel

All external API calls — Shopify, Stripe, Printful, Instagram. Primary source of noise.

---

## 6. Partition Definitions: Fine and Coarse Schemes

### 6.1 Design Principles

Each channel gets exactly two partition schemes (fine and coarse). All classification functions are **pure, deterministic functions** of AgentState fields, satisfying C1 (interface-boundedness). They are **counterfactually robust** (C2) and **compositionally local** (C3).

### 6.2 Complete Partition Table

| Channel | Theta ID | Granularity | Sigma_in Alphabet | |Sigma_in| | Sigma_out Alphabet | |Sigma_out| |
|---------|----------|-------------|-------------------|-----------|--------------------|------------|
| K1 | theta_K1_fine | FINE | content_post, full_campaign, product_launch, order_check, inventory_sync, revenue_report, pricing_review | 7 | (task_type, route_to) joint labels | 7 |
| K1 | theta_K1_coarse | COARSE | sales_task, ops_task, analytics_task | 3 | sales_marketing, operations, revenue_analytics | 3 |
| K2 | theta_K2_fine | FINE | simple_post, campaign_delegated, product_launch_delegated | 3 | completed_json, completed_raw, delegated, error | 4 |
| K2 | theta_K2_coarse | COARSE | direct_task, delegated_task | 2 | success, failure | 2 |
| K3 | theta_K3_fine | FINE | order_check, inventory_sync, fulfill_order, order_status | 4 | completed, needs_action, error, malformed | 4 |
| K3 | theta_K3_coarse | COARSE | read_operation, write_operation | 2 | success, failure | 2 |
| K4 | theta_K4_fine | FINE | revenue_report, pricing_review | 2 | daily_rev_high, daily_rev_med, daily_rev_low, pricing_high, pricing_med, pricing_low | 6 |
| K4 | theta_K4_coarse | COARSE | analytics_task | 1 | actionable, informational | 2 |
| K5 | theta_K5_fine | FINE | campaign_brief, product_brief | 2 | json_with_caption, json_no_caption, raw_text, error | 4 |
| K5 | theta_K5_coarse | COARSE | brief | 1 | usable, unusable | 2 |
| K6 | theta_K6_fine | FINE | full_results, partial_results | 2 | high_engagement, medium_engagement, low_engagement, analysis_failed | 4 |
| K6 | theta_K6_coarse | COARSE | analysis_input | 1 | pass, fail | 2 |
| K7 | theta_K7_fine | FINE | shopify_query_products, shopify_create_product, shopify_query_orders, stripe_create_product, stripe_payment_link, stripe_revenue_query, stripe_list_products, printful_catalog, printful_products, printful_store, printful_order_status, instagram_publish, instagram_insights | 13 | success_data, success_empty, http_error, timeout, auth_error, rate_limited, parse_error | 7 |
| K7 | theta_K7_coarse | COARSE | shopify, stripe, printful, instagram | 4 | success, failure | 2 |

### 6.3 Classification Functions

*(Same as v2 — see APS_IMPLEMENTATION_PLAN_v2.md Section 6.3 for full descriptions of each classify_input/classify_output function.)*

### 6.4 Partition Audit Metadata (C1-C3)

**New in v3.** Each PartitionScheme dataclass includes three required metadata fields:

```python
@dataclass
class PartitionScheme:
    partition_id: str
    channel_id: str
    granularity: str  # "fine" or "coarse"
    sigma_in_alphabet: list[str]
    sigma_out_alphabet: list[str]
    classify_input: Callable[[dict], str]
    classify_output: Callable[[dict], str]
    # v3: Admissibility audit metadata
    field_rule: str           # C1: which AgentState fields are inspected
    intervention_story: str   # C2: how sigma changes under feasible control
    locality_owner: str       # C3: which module "owns" the symbol
```

**Example for K1 Fine:**
- `field_rule`: "inspects state['messages'][-1].content and state['trigger_payload'] via keyword matching"
- `intervention_story`: "different task descriptions (e.g., 'check orders' vs 'post to instagram') produce different sigma_in values; achievable via scheduler job configuration"
- `locality_owner`: "owned by orchestrator module (src/agents/orchestrator.py)"

**Example for K7 Fine:**
- `field_rule`: "inspects serialized['name'] from LangChain on_tool_start callback"
- `intervention_story`: "different tool invocations (shopify_query_products vs stripe_revenue_query) produce different sigma_in values; achievable via agent tool selection"
- `locality_owner`: "owned by tool implementations (src/tools/*.py)"

---

## 7. Theta Configurations: The Expanded Control Tuple

*(Sections 7.1 through 7.5 are unchanged from v2.)*

### 7.1 Why Theta is More Than a Partition

The paper's formal object is θ = (π_in, π_out, D, u, ...) — the full configuration tuple. v2+ makes a practical subset explicit: partition granularity, model selection, and protocol level.

### 7.2 ThetaConfig Data Structure

```python
@dataclass
class ThetaConfig:
    theta_id: str
    channel_id: str
    level: int                             # 0=nominal, 1=degraded, 2=critical
    partition_id: str
    model_override: ModelID | None
    protocol_level: ProtocolLevel
    description: str = ""
```

### 7.3 Protocol Levels

```python
class ProtocolLevel(str, Enum):
    PASSIVE = "passive"
    CONFIRM = "confirm"
    CROSSCHECK = "crosscheck"
```

### 7.4 Three-Level Escalation Tiers

| Level | Name | Partition | Model | Protocol | Trigger |
|-------|------|-----------|-------|----------|---------|
| 0 | nominal | FINE | default | PASSIVE | p_fail < epsilon_G |
| 1 | degraded | COARSE | default | CONFIRM | p_fail > epsilon_G |
| 2 | critical | COARSE | escalated | CROSSCHECK | p_fail > 2 * epsilon_G |

### 7.5 Complete Theta Table: All 7 Channels x 3 Levels

*(Same as v2 Section 7.5 — see APS_IMPLEMENTATION_PLAN_v2.md for full 7-channel theta table.)*

---

## 8. Regeneration Protocols

*(Sections 8.1 through 8.6 are unchanged from v2. See APS_IMPLEMENTATION_PLAN_v2.md for full regeneration protocol details including ConfirmProtocol code, CrosscheckProtocol code, per-channel validators, and cost accounting.)*

---

## 9. Goal Specifications

*(Sections 9.1 through 9.4 are unchanged from v2. See APS_IMPLEMENTATION_PLAN_v2.md for full goal specifications including Tier 1 mission-critical goals, Tier 2 operational goals, and goal-to-channel mapping.)*

---

## 10. Information-Theoretic Computations

### 10.1 Confusion Matrix Construction

*(Unchanged from v2.)*

### 10.2 Mutual Information

*(Unchanged from v2.)*

### 10.3 Channel Capacity via Blahut-Arimoto

*(Unchanged from v2.)*

### 10.4 Informational Efficiency eta (Three Variants)

**Changed in v3.** Instead of a single eta = C(P) / W_dollars, v3 computes and stores three variants:

```python
def compute_eta_variants(capacity: float, total_cost_usd: float,
                         total_tokens: int, total_time_s: float) -> dict:
    """Compute all three informational efficiency variants.

    - eta_usd: bits per dollar (primary, from paper)
    - eta_token: bits per token (model-comparison metric)
    - eta_time: bits per second (latency-sensitive metric)
    """
    return {
        "eta_usd": capacity / total_cost_usd if total_cost_usd > 0 else float("inf"),
        "eta_token": capacity / total_tokens if total_tokens > 0 else float("inf"),
        "eta_time": capacity / total_time_s if total_time_s > 0 else float("inf"),
    }
```

**Why three variants?** A single eta number hides important tradeoffs:
- K1 (free Ollama): eta_usd = infinity, but eta_time might be low if latency is high
- K4 (Opus at $75/1K output): eta_usd is very low, but eta_token might be reasonable if the model is efficient
- K7 (tool calls): eta_usd depends on API costs, but eta_time is the binding constraint

v3 addition: When regeneration is active, all three W values increase. The net effect on each eta variant is empirically measurable. This is the paper's W_total = W_operate + W_search.

### 10.5 Chain Capacity and Bottleneck Identification (Realized Paths)

**Changed in v3.** Instead of computing bottleneck on predefined paths, v3 uses path_id tags on observations to identify actually realized workflow paths:

```python
def compute_realized_bottlenecks(window_seconds: float) -> list[dict]:
    """Compute chain capacity on actually realized paths.

    Groups observations by path_id, computes per-channel capacity
    within each path, applies Theorem 1.
    """
    paths = get_distinct_paths(window_seconds)
    results = []
    for path_id in paths:
        channels = path_id.split(">")
        per_channel = {}
        for ch in channels:
            obs = get_observations_by_path_and_channel(path_id, ch, window_seconds)
            if len(obs) >= MIN_OBSERVATIONS:
                cm = build_confusion_matrix(obs, ch)
                per_channel[ch] = channel_capacity_blahut_arimoto(cm)
        if per_channel:
            bottleneck = min(per_channel, key=per_channel.get)
            results.append({
                "path_id": path_id,
                "chain_capacity": min(per_channel.values()),
                "bottleneck": bottleneck,
                "per_channel": per_channel,
            })
    return results
```

The three primary realized paths will be:
1. `K1>K2>K5>K6` (orchestrator -> sales -> content_writer -> campaign_analyzer)
2. `K1>K3>K7` (orchestrator -> operations -> tool calls)
3. `K1>K4>K7` (orchestrator -> revenue -> tool calls)

But additional paths may emerge from sub-agent delegation or error handling routes.

---

## 11. APS Controller Design

### 11.1 Rolling Failure Estimation with UCB Confidence Bounds

**Changed in v3.** For each (goal, channel) pair, the controller queries recent observations:

```sql
SELECT * FROM aps_observations
WHERE channel_id = ? AND observed_at > NOW() - INTERVAL '? seconds'
ORDER BY observed_at DESC
```

It applies the goal's failure detector F_G and computes:

```
p_hat_fail = count(F_G(obs) = True) / count(obs)
```

**v3 addition:** For mission-critical goals (Tier 1, epsilon_G = 0.0), also compute the upper confidence bound:

```python
def compute_p_fail_ucb(failures: int, total: int, confidence: float = 0.95) -> float:
    """Beta-Binomial upper confidence bound with Jeffreys prior.

    Uses Beta(failures + 0.5, successes + 0.5) posterior.
    Returns the confidence-th quantile via bisection on the
    regularized incomplete beta function.
    """
    alpha = failures + 0.5
    beta_param = (total - failures) + 0.5
    return _beta_ppf(confidence, alpha, beta_param)

def _beta_ppf(q, a, b):
    """Inverse regularized incomplete beta via bisection. Pure numpy."""
    lo, hi = 0.0, 1.0
    for _ in range(64):  # 64 iterations gives ~1e-19 precision
        mid = (lo + hi) / 2
        if _regularized_incomplete_beta(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
```

**Why UCB?** With ~50 observations/day, sample sizes are small. For critical goals (epsilon_G = 0.0):
- 0 failures in 20 observations: raw p_hat = 0.0 (looks fine), but UCB(0.95) = 0.036 (APS stays alert)
- 1 failure in 20 observations: raw p_hat = 0.05, UCB(0.95) = 0.127 (clear signal)

For operational goals (epsilon_G = 0.05-0.15), the existing min-observation guard and hysteresis are sufficient. UCB adds complexity without proportional benefit for these softer thresholds.

### 11.2 Three-Level Escalation Logic with Hysteresis

*(Unchanged from v2.)*

```
For each (goal, channel):
    compute p_fail from recent observations
    current_level = get_current_theta_level(channel)

    IF goal.tier == MISSION_CRITICAL:
        effective_p = compute_p_fail_ucb(failures, total, 0.95)   # v3
    ELSE:
        effective_p = p_fail

    IF effective_p > 2 * epsilon_G AND current_level < 2:
        escalate to level 2 (critical)
        cooldown: 60s

    ELIF effective_p > epsilon_G AND current_level < 1:
        escalate to level 1 (degraded)
        cooldown: 60s

    ELIF effective_p < epsilon_G * 0.5 AND current_level > 0:
        de-escalate one level
        cooldown: 300s

    Min observations: 20 before any switch allowed
```

### 11.3 Theta Caching with Staleness Detection

**New in v3.** When the controller successfully stabilizes a channel (p_fail drops back below epsilon_G after escalation), it caches the successful theta configuration keyed by a context fingerprint.

```python
def get_context_fingerprint(channel_id: str) -> str:
    """Hash of current operational context.

    Inputs:
    - Circuit breaker states: {shopify: CLOSED, stripe: OPEN, ...}
    - Time-of-day bucket: morning (6-12), afternoon (12-18), night (18-6)
    - Error regime: low (<5% errors), medium (5-15%), high (>15%)
    """
    from src.resilience.circuit_breaker import get_all_breaker_states
    breaker_states = sorted(get_all_breaker_states().items())
    time_bucket = _get_time_bucket()
    error_regime = _get_error_regime(channel_id)
    fingerprint_str = f"{breaker_states}|{time_bucket}|{error_regime}"
    return hashlib.md5(fingerprint_str.encode()).hexdigest()
```

Integrated into escalation logic:

```
On trigger (p_fail > epsilon_G):
    cached_theta = try_cached_theta(channel_id)
    IF cached_theta AND cached_theta.level > current_level:
        apply cached_theta (skip exploration, increment hit_count)
    ELSE:
        apply standard 3-level escalation

On successful stabilization (p_fail drops below epsilon_G after escalation):
    cache_theta(channel_id, current_theta, context_fingerprint)

Cache eviction:
    Reject if (now - last_validated) > 3600 seconds (1 hour staleness)
    Reject if context_hash != current context_hash (context diverged)
```

### 11.4 Evaluation Cycle

The APSController.evaluate_all() method runs every 5 minutes:

1. For each goal in GOALS:
   a. For each channel in goal.channels:
      - Query recent observations within window T
      - Compute p_fail (and UCB for Tier 1 goals)
      - Build confusion matrix
      - Compute mutual information, channel capacity
      - Compute eta_usd, eta_token, eta_time (v3: from actual token counts where available)
      - Store metrics in aps_metrics table
      - Evaluate escalation/de-escalation decision (with cache check)
   b. Aggregate goal-level p_fail across all channels
2. Compute realized bottlenecks from path_id-tagged observations (v3)
3. Broadcast `aps_evaluation` event via WebSocket
4. Return summary dict

### 11.5 W_total Accounting (Actual Token Costs)

**Changed in v3.** The paper specifies W_total = W_operate + W_search.

**W_operate**: The LLM inference cost per invocation. v3 uses **actual token counts** where available:
- OpenAI and Anthropic models report token_usage in `on_llm_end` callback
- Cost = (prompt_tokens / 1000) * cost_per_1k_input + (completion_tokens / 1000) * cost_per_1k_output
- Fallback to estimation from MODEL_REGISTRY when token_usage is unavailable (e.g., Ollama)

**W_search**: The overhead of APS itself plus regeneration costs:
- APS evaluation: negligible
- ConfirmProtocol: approximately 1x the original invocation cost (one retry) — now tracked with actual tokens
- CrosscheckProtocol: approximately 0.01-0.05x the original cost (one validation API call)

---

## 12. Instrumentation Strategy

### 12.1 The Wrapper Pattern

*(Unchanged from v2.)* Zero modification to existing agent code.

### 12.2 Node-Level Instrumentation

Applied in `src/graph.py` where nodes are registered:

```python
# Before (existing code):
graph.add_node("orchestrator", build_orchestrator_node(router))
graph.add_node("sales_marketing", build_sales_marketing_node(router))
graph.add_node("operations", build_operations_node(router))
graph.add_node("revenue_analytics", build_revenue_node(router))

# After (instrumented):
graph.add_node("orchestrator", instrument_node("K1", ModelID.OLLAMA_QWEN, build_orchestrator_node(router)))
graph.add_node("sales_marketing", instrument_node("K2", ModelID.GPT4O, build_sales_marketing_node(router)))
graph.add_node("operations", instrument_node("K3", ModelID.GPT4O_MINI, build_operations_node(router)))
graph.add_node("revenue_analytics", instrument_node("K4", ModelID.CLAUDE_OPUS, build_revenue_node(router)))
```

### 12.3 Token Accumulator Pattern

**New in v3.** A thread-local object that the ForgeEventCallbackHandler populates in `on_llm_end`. The instrument wrapper resets it before each node invocation and reads it after.

```python
import threading

class TokenAccumulator:
    """Thread-local accumulator for actual LLM token counts.

    The ForgeEventCallbackHandler calls accumulate() in on_llm_end.
    The instrument_node wrapper calls reset() before the node runs
    and get() after the node returns.
    """
    def __init__(self):
        self._local = threading.local()

    def reset(self):
        self._local.tokens = {}

    def accumulate(self, token_usage: dict):
        current = getattr(self._local, "tokens", {})
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            current[key] = current.get(key, 0) + token_usage.get(key, 0)
        self._local.tokens = current

    def get(self) -> dict | None:
        tokens = getattr(self._local, "tokens", {})
        return tokens if tokens else None

_token_accumulator = TokenAccumulator()
```

**Why thread-local?** LangGraph may process multiple requests concurrently. Thread-local storage ensures token counts from one request don't leak into another.

### 12.4 Trace ID and Path ID Injection

**New in v3.**

**trace_id**: Generated as a UUID at graph invocation in `src/serve.py`, injected via `config["configurable"]["aps_trace_id"]`:

```python
def _per_req_config_modifier(config: dict, request) -> dict:
    callbacks = config.get("callbacks", []) or []
    callbacks.append(forge_callback)
    config["callbacks"] = callbacks
    # v3: inject APS trace_id for workflow correlation
    configurable = config.get("configurable", {})
    configurable["aps_trace_id"] = str(uuid.uuid4())
    config["configurable"] = configurable
    return config
```

**path_id**: Built incrementally as the workflow progresses through nodes. Each wrapper reads `state.get("_aps_path_id", "")` and appends its channel_id:

- K1 wrapper: path_id = "K1"
- K3 wrapper (after K1): path_id = "K1>K3"
- K7 wrapper (after K1>K3): path_id = "K1>K3>K7"

The path_id is propagated via `result["_aps_path_id"] = path_id`.

### 12.5 Regeneration Integration in the Wrapper

The complete v3 wrapper:

```python
def instrument_node(channel_id, model_id, node_fn):
    def wrapped(state, config=None):
        theta = get_active_theta(channel_id)
        partition = get_partition(theta.partition_id)
        sigma_in = partition.classify_input(state)

        effective_model = theta.model_override or model_id

        # v3: trace_id from config
        trace_id = None
        if config and "configurable" in config:
            trace_id = config["configurable"].get("aps_trace_id")

        # v3: build path_id incrementally
        parent_path = state.get("_aps_path_id", "")
        path_id = f"{parent_path}>{channel_id}" if parent_path else channel_id

        # v3: reset token accumulator before node runs
        _token_accumulator.reset()

        t0 = time.time()
        result = node_fn(state)  # Original function, always runs
        latency_ms = (time.time() - t0) * 1000
        sigma_out = partition.classify_output(result)

        # Regeneration (from v2)
        if theta.protocol_level == ProtocolLevel.CONFIRM:
            if is_failure(sigma_out, channel_id):
                result, sigma_out = confirm_protocol.execute(
                    channel_id, state, result, node_fn
                )
        elif theta.protocol_level == ProtocolLevel.CROSSCHECK:
            result, override = crosscheck_protocol.execute(channel_id, result)
            if override is not None:
                sigma_out = override

        # v3: read actual token counts from accumulator
        tokens = _token_accumulator.get()
        if tokens:
            cost = compute_actual_cost(effective_model, tokens)
        else:
            cost = estimate_cost(effective_model, state, result)

        log_observation(
            channel_id=channel_id,
            theta_id=theta.theta_id,
            sigma_in=sigma_in,
            sigma_out=sigma_out,
            timestamp=time.time(),
            latency_ms=latency_ms,
            cost_usd=cost,
            prompt_tokens=tokens.get("prompt_tokens") if tokens else None,
            completion_tokens=tokens.get("completion_tokens") if tokens else None,
            total_tokens=tokens.get("total_tokens") if tokens else None,
            model_id=str(effective_model),
            trace_id=trace_id,
            path_id=path_id,
        )

        # v3: propagate path_id to downstream nodes
        if isinstance(result, dict):
            result["_aps_path_id"] = path_id

        return result
    return wrapped
```

**Note on model_override**: Same as v2 — it is a **recommendation signal**, not an actuator. It is logged in observations and surfaced via the API, but does not change which LLM the agent internally calls. Wiring in the actuator is a roadmap item.

### 12.6 Tool-Call Instrumentation

*(Unchanged from v2.)* Tool calls (K7) are instrumented via the ForgeEventCallbackHandler.

### 12.7 Error Safety

*(Unchanged from v2.)* All APS operations are wrapped in try/except. The original node_fn always executes and returns its result.

---

## 13. Database Schema

### 13.1 Table: aps_observations (Extended)

```sql
CREATE TABLE IF NOT EXISTS aps_observations (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    theta_id        VARCHAR(64) NOT NULL,
    sigma_in        VARCHAR(128) NOT NULL,
    sigma_out       VARCHAR(128) NOT NULL,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latency_ms      REAL,
    cost_usd        REAL DEFAULT 0.0,
    -- v3: actual token accounting
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    total_tokens    INTEGER,
    model_id        VARCHAR(64),
    -- v3: workflow correlation
    trace_id        UUID,
    path_id         VARCHAR(128),
    -- metadata
    run_metadata    JSONB DEFAULT '{}'::JSONB
);

CREATE INDEX idx_aps_obs_channel_time ON aps_observations (channel_id, observed_at DESC);
CREATE INDEX idx_aps_obs_theta_time ON aps_observations (theta_id, observed_at DESC);
CREATE INDEX idx_aps_obs_trace ON aps_observations (trace_id);
```

### 13.2 Table: aps_metrics (Extended)

```sql
CREATE TABLE IF NOT EXISTS aps_metrics (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    theta_id        VARCHAR(64) NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    p_fail          REAL NOT NULL,
    p_fail_ucb      REAL,               -- v3: upper confidence bound (Tier 1 only)
    mutual_info     REAL NOT NULL,
    capacity        REAL NOT NULL,
    eta_usd         REAL NOT NULL,       -- v3: renamed from eta
    eta_token       REAL,                -- v3
    eta_time        REAL,                -- v3
    n_observations  INTEGER NOT NULL,
    total_cost_usd  REAL DEFAULT 0.0,
    total_tokens    INTEGER DEFAULT 0,   -- v3
    total_time_s    REAL DEFAULT 0.0,    -- v3
    confusion_matrix JSONB,
    window_seconds  REAL
);

CREATE INDEX idx_aps_metrics_channel_time ON aps_metrics (channel_id, computed_at DESC);
```

### 13.3 Table: aps_theta_switches

*(Unchanged from v2.)*

```sql
CREATE TABLE IF NOT EXISTS aps_theta_switches (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    from_theta      VARCHAR(64) NOT NULL,
    to_theta        VARCHAR(64) NOT NULL,
    direction       VARCHAR(16) NOT NULL,
    from_level      INTEGER NOT NULL,
    to_level        INTEGER NOT NULL,
    model_changed   BOOLEAN DEFAULT FALSE,
    protocol_changed BOOLEAN DEFAULT FALSE,
    trigger_p_fail  REAL NOT NULL,
    trigger_epsilon REAL NOT NULL,
    goal_id         VARCHAR(64) NOT NULL,
    switched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_aps_switches_channel ON aps_theta_switches (channel_id, switched_at DESC);
```

### 13.4 Table: aps_theta_cache (New)

**New in v3.** Caches successful theta configurations by context fingerprint.

```sql
CREATE TABLE IF NOT EXISTS aps_theta_cache (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    context_hash    VARCHAR(128) NOT NULL,
    theta_id        VARCHAR(64) NOT NULL,
    p_fail_at_cache REAL NOT NULL,
    cached_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_validated  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count       INTEGER DEFAULT 0,
    UNIQUE(channel_id, context_hash)
);
```

Expected volume: very low — at most 7 channels x ~10 context regimes = ~70 rows.

---

## 14. API Endpoints and WebSocket Events

### 14.1 REST Endpoints

| Method | Path | Version | Description | Response |
|--------|------|---------|-------------|----------|
| GET | /aps/metrics | v2 | Latest metrics for all 7 channels | Now includes eta_usd, eta_token, eta_time, p_fail_ucb |
| GET | /aps/metrics/{channel_id} | v2 | Metric history for one channel | Extended fields |
| GET | /aps/partitions | v2 | Current theta state for all channels | Now includes audit metadata |
| POST | /aps/switch/{channel_id}/{theta_id} | v2 | Manual theta switch (testing) | Status + new level/model/protocol |
| GET | /aps/chain-capacity | v2 | Bottleneck capacity + path analysis | Now uses realized paths via path_id |
| POST | /aps/evaluate | v2 | Trigger immediate evaluation cycle | Full evaluation summary |
| GET | /aps/trace/{trace_id} | **v3** | All observations for one workflow | Ordered list of observations |
| GET | /aps/cache | **v3** | Current theta cache state | All cached entries with staleness |

### 14.2 WebSocket Event Types

All events broadcast through `ws://localhost:8050/ws/events`:

**aps_observation** (every node invocation):
```json
{
    "type": "aps_observation",
    "channel_id": "K3",
    "theta_id": "theta_K3_degraded",
    "sigma_in": "order_check",
    "sigma_out": "completed",
    "latency_ms": 4521.3,
    "cost_usd": 0.024,
    "prompt_tokens": 1250,
    "completion_tokens": 340,
    "model_id": "gpt4o_mini",
    "trace_id": "a1b2c3d4-...",
    "path_id": "K1>K3",
    "level": 1,
    "protocol_active": "confirm",
    "timestamp": 1738857600.0
}
```

**aps_evaluation** (every 5 minutes):
```json
{
    "type": "aps_evaluation",
    "timestamp": 1738857600.0,
    "channels": {
        "K3": {
            "p_fail": 0.12,
            "p_fail_ucb": null,
            "mutual_information_bits": 0.85,
            "channel_capacity_bits": 1.00,
            "eta_usd": 83.3,
            "eta_token": 0.0006,
            "eta_time": 0.22,
            "n_observations": 48,
            "total_tokens": 76200,
            "active_theta": "theta_K3_degraded",
            "level": 1
        }
    },
    "goals": { ... },
    "switches": [ ... ],
    "realized_bottlenecks": [
        {
            "path_id": "K1>K3>K7",
            "chain_capacity": 0.85,
            "bottleneck": "K7",
            "per_channel": {"K1": 1.58, "K3": 1.00, "K7": 0.85}
        }
    ]
}
```

**aps_theta_switch** (when a theta configuration changes):
*(Same structure as v2.)*

---

## 15. New File Structure

```
src/aps/
    __init__.py              # Package init, init_aps() startup function
    partitions.py            # PartitionScheme (with C1-C3 audit metadata)
                             #   14 partition schemes (7 channels x 2 granularities)
                             #   All classify_input/classify_output functions
    theta.py                 # ThetaConfig, ProtocolLevel, THETA_REGISTRY
                             #   21 theta configs (7 channels x 3 levels)
    channel.py               # ConfusionMatrix, mutual_information()
                             #   channel_capacity_blahut_arimoto()
                             #   compute_eta_variants() (v3: 3 eta types)
    controller.py            # APSController class
                             #   evaluate_all(), _evaluate_escalation()
                             #   compute_p_fail_ucb() (v3: UCB bounds)
                             #   get_context_fingerprint(), try_cached_theta() (v3: caching)
                             #   compute_realized_bottlenecks() (v3: path-based)
    goals.py                 # GoalTier, GoalID, Goal dataclass
                             #   MISSION_CRITICAL_GOALS, OPERATIONAL_GOALS
    regeneration.py          # ConfirmProtocol, CrosscheckProtocol
                             #   VALIDATORS, FAILURE_SYMBOLS
    instrument.py            # instrument_node() wrapper
                             #   TokenAccumulator (v3: actual token accounting)
                             #   trace_id/path_id injection (v3)
                             #   compute_actual_cost() (v3)
    store.py                 # init_aps_tables() - CREATE TABLE IF NOT EXISTS (4 tables)
                             #   log_observation() (v3: extended fields)
                             #   get_recent_observations()
                             #   store_aps_metrics() (v3: extended fields)
                             #   store_theta_switch_event()
                             #   cache_theta(), query_theta_cache() (v3: new)
                             #   get_observations_by_trace() (v3: new)
    scheduler_jobs.py        # aps_evaluation_job() for APScheduler

tests/
    test_aps_partitions.py   # ~140 lines (v3: +C1-C3 metadata tests)
    test_aps_channel.py      # ~130 lines (v3: +eta_variants tests)
    test_aps_controller.py   # ~220 lines (v3: +UCB, caching, realized bottleneck tests)
    test_aps_instrument.py   # ~140 lines (v3: +token accounting, trace_id, path_id tests)
    test_aps_regeneration.py # ~80 lines
    test_aps_integration.py  # ~120 lines (v3: +trace endpoint, cache endpoint tests)
```

---

## 16. Modifications to Existing Files

| File | What Changes | Lines Added/Changed | Risk |
|------|-------------|---------------------|------|
| `src/graph.py` | Import instrument_node; wrap 4 node registrations | ~8 lines | Low |
| `src/agents/sub_agents.py` | Import instrument_node; wrap content_writer and campaign_analyzer | ~4 lines | Low |
| `src/events.py` | K7 tool-call instrumentation + token accumulator call in on_llm_end | ~25 lines | Low |
| `src/serve.py` | APS init, trace_id injection, 8 API endpoints (6 from v2 + 2 new) | ~100 lines | Low |
| `src/scheduler/autonomous.py` | Import aps_evaluation_job; add IntervalTrigger(minutes=5) | ~10 lines | Low |
| `pyproject.toml` | Add `numpy>=1.24.0,<3.0.0` | ~1 line | Low |

**Total existing code touched**: ~148 lines across 6 files. All changes are additive.

---

## 17. Implementation Phases

### Phase 1: Core Data Structures (no runtime impact)

Create foundational modules. Fully unit-testable in isolation.

**Files created**: `src/aps/__init__.py`, `src/aps/partitions.py` (with C1-C3 audit metadata), `src/aps/theta.py`, `src/aps/channel.py` (with compute_eta_variants), `src/aps/goals.py`, `src/aps/regeneration.py`
**Tests created**: `tests/test_aps_partitions.py`, `tests/test_aps_channel.py`, `tests/test_aps_regeneration.py`
**Dependency added**: numpy in `pyproject.toml`

### Phase 2: Storage Layer

Create database persistence module. Initialize 4 PostgreSQL tables (3 from v2 + aps_theta_cache).

**Files created**: `src/aps/store.py`
**Tables created**: aps_observations, aps_metrics, aps_theta_switches, aps_theta_cache

### Phase 3: Instrumentation (logging + regeneration + token accounting)

Create the instrumentation wrapper with v3 enhancements (token accumulator, trace_id, path_id) and apply to all 7 channels.

**Files created**: `src/aps/instrument.py`
**Files modified**: `src/graph.py`, `src/agents/sub_agents.py`, `src/events.py`
**Tests created**: `tests/test_aps_instrument.py`

### Phase 4: APS Controller (adaptive logic + UCB + caching)

Create the controller with UCB confidence bounds, theta caching, and realized-path bottleneck analysis. Wire into scheduler.

**Files created**: `src/aps/controller.py`, `src/aps/scheduler_jobs.py`
**Files modified**: `src/scheduler/autonomous.py`
**Tests created**: `tests/test_aps_controller.py`

### Phase 5: API and Observability

Add REST endpoints (including v3 trace and cache endpoints) and startup initialization.

**Files modified**: `src/serve.py`
**Tests created**: `tests/test_aps_integration.py`

### Phase 6: Validation

Run full test suite (existing + new), start system, trigger tasks, verify metrics via API.

---

## 18. Testing Strategy

### 18.1 Unit Tests

**test_aps_partitions.py** (~140 lines):
- All 14 partition schemes tested with known inputs/outputs
- Unknown/malformed inputs return a default symbol (never raise)
- Partition switching: register, get_active, switch, get_active again
- Fine and coarse partitions have different alphabet sizes
- **v3**: Every partition has non-empty field_rule, intervention_story, locality_owner

**test_aps_channel.py** (~130 lines):
- ConfusionMatrix with known counts
- Mutual information of independent/deterministic channels
- Blahut-Arimoto on binary symmetric channel
- **v3**: compute_eta_variants returns correct values for known inputs
- **v3**: eta_usd = inf when cost = 0, eta_token = inf when tokens = 0

**test_aps_controller.py** (~220 lines):
- Standard escalation/de-escalation with hysteresis
- Min-observations guard
- **v3**: UCB(0/20) > 0, UCB(20/20) = 1.0, UCB monotonically increases with failures
- **v3**: UCB only applied to MISSION_CRITICAL goals, not operational
- **v3**: Theta caching: trigger escalation, verify cache populated; change context, verify cache miss; same context, verify cache hit
- **v3**: compute_realized_bottlenecks returns correct paths and bottleneck identification

**test_aps_instrument.py** (~140 lines):
- Wrapper returns original result unchanged
- log_observation called with correct values (mock store)
- Error safety: classify_input/log_observation failures don't break wrapper
- **v3**: Mock on_llm_end with token_usage, verify observation has actual tokens
- **v3**: When token_usage unavailable, falls back to estimate_cost
- **v3**: trace_id propagated from config to observation
- **v3**: path_id builds incrementally: K1 -> K1>K3 -> K1>K3>K7

**test_aps_regeneration.py** (~80 lines):
*(Unchanged from v2.)*

### 18.2 Integration Tests

**test_aps_integration.py** (~120 lines):
- Build instrumented graph, invoke with sample state, verify observation in DB
- Run evaluate_all against mock observations, verify metrics in DB
- /aps/metrics returns valid JSON with eta_usd, eta_token, eta_time, p_fail_ucb
- /aps/evaluate triggers cycle and returns summary
- /aps/switch changes active theta
- /aps/chain-capacity returns realized paths with bottleneck
- **v3**: /aps/trace/{trace_id} returns all observations for that workflow
- **v3**: /aps/cache returns current theta cache state

### 18.3 Live Validation Protocol

1. `pip install numpy` (only new dependency)
2. Run existing 60 tests — should pass unchanged
3. Run new APS tests: `pytest tests/test_aps_*.py -v`
4. Start system: `PYTHONUTF8=1 uvicorn src.serve:app --host 0.0.0.0 --port 8050`
5. Trigger tasks: `curl -X POST localhost:8050/scheduler/trigger/order_check`
6. After 2+ invocations: `curl -X POST localhost:8050/aps/evaluate | python -m json.tool`
7. Check metrics: `curl localhost:8050/aps/metrics`
   - Verify: eta_usd, eta_token, eta_time all present
   - Verify: prompt_tokens, completion_tokens in observations (for LLM-backed channels)
   - Verify: p_fail_ucb present for mission-critical goals
8. Check trace: `curl localhost:8050/aps/trace/{trace_id}` — verify all observations linked
9. Check paths: `curl localhost:8050/aps/chain-capacity` — verify realized paths appear
10. Check cache: `curl localhost:8050/aps/cache` — verify theta cache state
11. Test manual escalation: `curl -X POST localhost:8050/aps/switch/K3/theta_K3_critical`
12. After 24h: verify theta cache has entries, realized bottleneck matches predefined paths

---

## 19. Paper Predictions Under Test

| Prediction | What We Measure | v3 Enhancement | How We Verify |
|------------|----------------|----------------|---------------|
| P1: Rate ceiling | C(P) per interface | eta_token and eta_time for richer comparison | /aps/metrics shows C(P) > 0 with all three eta variants |
| P3: Noise collapses alphabets | p_fail and theta over time | UCB catches degradation earlier with small samples | aps_theta_switches correlated with elevated p_fail_ucb |
| P5: Medium reshapes partitions | Active theta under different conditions | Unchanged | /aps/partitions shows heterogeneous levels |
| P7: Epsilon-triggered switching | Theta switch events | Theta cache accelerates re-stabilization | aps_theta_switches + cache hit_count |
| Theorem 1: Composition bound | Chain capacity vs per-channel | Validated on realized paths via path_id | /aps/chain-capacity shows chain_capacity <= min(per_channel) on actual paths |
| Section 4: Regeneration | eta at different protocol levels | Actual token/$ costs, not estimates | Compare eta_usd/token/time across levels |
| eta comparison | Efficiency across channels | Three variants reveal different tradeoffs | eta_usd vs eta_token vs eta_time diverge for K1 vs K4 |
| **NEW**: eta improves under APS | Time series of eta | Measurable with actual costs | eta trend after APS adaptation vs fixed baseline |
| **NEW**: Caching reduces switching latency | Time-to-stabilize | Compare with vs without cache hits | Cache hit_count + stabilization timestamps |

---

## 20. Dependencies

**New dependency**: `numpy>=1.24.0,<3.0.0` (for confusion matrix operations, Blahut-Arimoto, Beta-Binomial UCB)

Beta-Binomial UCB is implemented using a pure-numpy bisection method on the regularized incomplete beta function. No scipy required:

```python
def _beta_ppf(q, a, b):
    """Inverse regularized incomplete beta via bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = (lo + hi) / 2
        if _regularized_incomplete_beta(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
```

**Existing dependencies leveraged** (no new installs):
- `psycopg` (via langgraph-checkpoint-postgres) — PostgreSQL access
- `apscheduler` — scheduler integration
- `fastapi` — API endpoints
- `langchain-core` — callback handler extension

---

## 21. Key Design Decisions and Rationale

**v2 decisions (retained):**

1. **Wrapper pattern over agent modification.** Agent code untouched. APS is additive.
2. **PostgreSQL over Redis for APS storage.** Need time-range queries with aggregation.
3. **Blahut-Arimoto for channel capacity.** Standard algorithm, converges quickly for small alphabets.
4. **Theta as a tuple (partition + model + protocol).** Richer action space than binary partition switching.
5. **Three-level escalation (nominal/degraded/critical).** Proportional response.
6. **Regeneration as first-class concept.** Paper's Section 4 made operational.
7. **Mission-critical goal tier.** Hard floors that block actions, not just switch partitions.
8. **Model override as signal first, actuator later.** Validate routing logic with data before wiring.
9. **Asymmetric hysteresis cooldowns (60s/300s).** Escalate fast, de-escalate cautiously.
10. **20-observation minimum before switching.** Statistical significance.
11. **Five-minute evaluation interval.** Fresh metrics without excessive DB load.

**v3 additions:**

12. **UCB for critical goals.** Small samples require honest uncertainty. Beta-Binomial posterior with Jeffreys prior gives conservative bounds that prevent false confidence from sparse data. With 0 failures in 20 observations, raw p_hat = 0.0 says "everything is fine" while UCB = 0.036 says "we can't be sure yet."

13. **Actual token accounting.** Estimated costs are approximations. The LangChain callback infrastructure already provides real token counts via `response.llm_output.get("token_usage")` — v3 plumbs them through via a thread-local accumulator. This makes eta a measurement, not a guess.

14. **trace_id + path_id.** Without these, observations are isolated data points. With trace_id, we can reconstruct complete workflow executions. With path_id, we can validate Theorem 1 on paths that actually happened, not hypothetical chains.

15. **C1-C3 partition audit metadata.** The paper's admissibility constraints aren't optional decorations — they're what separates meaningful partitions from arbitrary ones. Requiring metadata at registration time enforces discipline and provides documentation.

16. **Theta caching with staleness.** The controller shouldn't rediscover solutions it already found when the same conditions recur. But cached solutions must expire when context changes. A simple context fingerprint (circuit breaker states + time bucket + error regime) with 1-hour staleness achieves both.

17. **eta variants ($/token/time).** A single eta number hides important tradeoffs. K1 has infinite eta_usd (free model) but finite eta_time (latency matters). K4 has terrible eta_usd ($75/1K output tokens) but reasonable eta_token. Reporting all three lets operators and the controller make informed decisions.

---

## 22. Roadmap: What Comes After v3

### Near-term (after v3 validates)

1. **Dynamic model routing actuator** — Wire model_override into agent builders so APS can actually swap models at runtime. Highest-leverage follow-up.

2. **Shared context K as compression engine** — Formalize ChromaDB collections + schemas as the shared prior K. Add K_version to observations. Measure H(I|K) vs H(I) to quantify compression benefit.

3. **Governance gate agent** — If Tier 1 blocking proves too coarse, evolve into a dedicated pre-execution review agent.

### Medium-term

4. **Extended channels K8-K12** — Merchandising, Pricing, Customer Support, Governance, Experimentation agents.

5. **Staging/canary infrastructure** — Staging Shopify store for dry-run regeneration patterns.

6. **Majority vote regeneration** — For high-risk decisions, run through 2-3 models and take consensus.

7. **reasoning_effort as theta knob** — When models support variable effort levels natively.

### Long-term

8. **ChangeSet pattern** — Versioned agent outputs with rollback capability.

9. **Reasoning-native executive** — Planning orchestrator that emits multi-step workflows with explicit budgets.

10. **Full CommerceOS** — Complete autonomous commerce organization with APS governing the full autonomy stack.
