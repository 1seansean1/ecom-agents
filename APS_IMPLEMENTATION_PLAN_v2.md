# Adaptive Partition Selection (APS) Implementation Plan — v2

## Implementing Informational Monism's Core Experimental Protocol in a Live Agentic System

**Author**: Sean P. Allen
**Date**: February 6, 2026
**Target System**: ecom-agents (live at localhost:8050)
**Version**: 2.0 — Expanded with theta configurations, regeneration protocols, and mission-critical goal tier
**Status**: Draft — Pre-Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What Changed from v1 to v2](#2-what-changed-from-v1-to-v2)
3. [Theoretical Foundation](#3-theoretical-foundation)
   - 3.1 [The Induced Macro-Channel](#31-the-induced-macro-channel)
   - 3.2 [Informational Efficiency](#32-informational-efficiency)
   - 3.3 [The Composition Bound (Theorem 1)](#33-the-composition-bound-theorem-1)
   - 3.4 [Epsilon-Triggered Partition Switching](#34-epsilon-triggered-partition-switching)
   - 3.5 [Passive Transport vs Active Regeneration](#35-passive-transport-vs-active-regeneration)
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
    - 10.4 [Informational Efficiency eta](#104-informational-efficiency-eta)
    - 10.5 [Chain Capacity and Bottleneck Identification](#105-chain-capacity-and-bottleneck-identification)
11. [APS Controller Design](#11-aps-controller-design)
    - 11.1 [Rolling Failure Estimation](#111-rolling-failure-estimation)
    - 11.2 [Three-Level Escalation Logic with Hysteresis](#112-three-level-escalation-logic-with-hysteresis)
    - 11.3 [Evaluation Cycle](#113-evaluation-cycle)
    - 11.4 [W_total Accounting](#114-w_total-accounting)
12. [Instrumentation Strategy](#12-instrumentation-strategy)
    - 12.1 [The Wrapper Pattern](#121-the-wrapper-pattern)
    - 12.2 [Node-Level Instrumentation](#122-node-level-instrumentation)
    - 12.3 [Regeneration Integration in the Wrapper](#123-regeneration-integration-in-the-wrapper)
    - 12.4 [Tool-Call Instrumentation](#124-tool-call-instrumentation)
    - 12.5 [Error Safety](#125-error-safety)
13. [Database Schema](#13-database-schema)
    - 13.1 [Table: aps_observations](#131-table-aps_observations)
    - 13.2 [Table: aps_metrics](#132-table-aps_metrics)
    - 13.3 [Table: aps_theta_switches](#133-table-aps_theta_switches)
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
22. [Roadmap: What Comes After v2](#22-roadmap-what-comes-after-v2)

---

## 1. Executive Summary

### Purpose

This document specifies the implementation of an **Adaptive Partition Selection (APS)** system for the ecom-agents multi-agent e-commerce platform. The APS system is the first live experimental instantiation of the theoretical framework described in the paper *"Informational Monism: Computation, Communication, and Conduction as Unified Phenomena"* (Allen, 2026).

### What We Are Building

The paper argues that every interface between communicating agents can be modeled as an **induced macro-channel** — a stochastic map from input symbols to output symbols, where "symbols" are defined by coarse-graining (partitioning) the high-dimensional state space at each boundary. The paper further proposes that when goal failure rates exceed a tolerance threshold, systems should adaptively switch between finer and coarser partition schemes to maintain recoverability.

We are building an instrumentation and control layer that:

1. **Identifies and instruments 7 agent-to-agent interfaces** as induced macro-channels (K1 through K7), covering the orchestrator, all three specialist agents, two sub-agents, and all external tool calls.

2. **Defines 14 partition schemes** (2 per channel: fine and coarse), each with explicit symbol alphabets and deterministic classification functions that map the high-dimensional AgentState into discrete symbols.

3. **Defines 21 theta configurations** (3 per channel: nominal, degraded, critical), each bundling a partition scheme with a model override and a regeneration protocol level. This is the key v2 expansion: theta is a tuple θ = (π, model, protocol), not just a partition.

4. **Logs every interface crossing** as a (sigma_in, sigma_out) observation tuple, with timestamps, latency, and cost metadata, into PostgreSQL.

5. **Computes information-theoretic metrics** in real time: empirical confusion matrices P_hat(sigma_out | sigma_in), mutual information I(X;Y), channel capacity C(P) via the Blahut-Arimoto algorithm, and informational efficiency eta = C(P) / W.

6. **Validates the composition bound** (Theorem 1: C(P_chain) <= min_k C(P_k)) across the full agent chain, identifying the bottleneck channel.

7. **Implements a three-level APS controller** that monitors rolling goal-failure rates p_hat_fail(t) against both mission-critical hard floors and operational goals, triggering proportional escalation: partition coarsening at level 1, model escalation and regeneration protocols at level 2 — with hysteresis to prevent oscillation.

8. **Implements two regeneration protocols** (ConfirmProtocol and CrosscheckProtocol) that embody the paper's Section 4 distinction between passive transport and active regeneration.

9. **Exposes all metrics** via REST API endpoints and WebSocket events for observation and analysis.

### What This Validates

When running live, this system directly tests the following predictions from the paper:

- **P1 (Rate ceiling)**: Agent interfaces have measurable channel capacities that constrain information throughput.
- **P3 (Noise collapses alphabets)**: Under degraded conditions (API failures, model errors), the effective stable symbol set shrinks — the APS controller responds by switching to coarser partitions.
- **P5 (Medium constraints reshape partitions)**: Different operational conditions favor different partition granularities.
- **P7 (Epsilon-triggered switching)**: When goal failure exceeds tolerance, discrete partition transitions occur, and when conditions improve, richer alphabets return.
- **Theorem 1 (Composition bound)**: The end-to-end chain capacity is bounded by the weakest link.
- **Section 4 (Regeneration)**: Active regeneration (confirmation, crosscheck) restores recoverability at a measurable energy cost, validating the passive-vs-regenerative axis.

### Why This Matters

If the APS system behaves as predicted — if confusion matrices are measurable, if mutual information and channel capacity are nonzero and meaningful, if the composition bound holds empirically, if epsilon-triggered switching demonstrably maintains recoverability, and if regeneration protocols restore channel quality at a measurable cost — then we have a live demonstration that the informational monism framework applies to software agent systems, not just physical substrates. This is the paper's Appendix A protocol, instrumented and running.

---

## 2. What Changed from v1 to v2

v1 defined APS as a measurement + binary partition-switching layer. An alternative architecture proposal ("APS-governed, reasoning-native CommerceOS") identified three gaps. v2 folds in the valid insights while staying implementable on the current ecom-agents system.

### Three Insights Adopted

**1. Expanded theta (θ = partition + model + protocol)**

v1 only switched between fine and coarse partitions. The alternative correctly identified that partition granularity is only one control knob. Model selection (cheap → expensive) and protocol level (passive → regenerative) are equally important. v2 bundles these into a ThetaConfig tuple, giving the controller a richer action space with three escalation levels instead of two.

**2. Regeneration as a concrete response (paper Section 4)**

v1 had no implementation of the paper's passive-vs-regenerative axis. When coarsening alone isn't enough, the system needs to spend work to restore the symbol set. v2 adds two regeneration protocols: ConfirmProtocol (retry with clarified prompt on failure) and CrosscheckProtocol (run deterministic validator after LLM output). These are the commerce analogs of digital repeaters and error-correcting codes.

**3. Mission-critical goal tier (hard floors)**

v1 treated all goals as operational (epsilon-triggered switching). The alternative proposed that some failures are not "noise to adapt to" but "failures to prevent." v2 adds Tier 1 mission-critical goals (policy violations = 0, negative margin = 0) that block actions rather than switch partitions.

### What We Did NOT Adopt (and Why)

- **New agents K8-K12** (Merchandising, Pricing, Support, Governance, Experimentation): The system has 4 agents + sub-agents, not 7 departments. Building new agents is a separate project. Noted as roadmap.
- **Staging/canary infrastructure**: No staging Shopify store exists. Requires dev store setup. Noted as roadmap.
- **ChangeSet versioning**: Requires rearchitecting all agent return types. Noted as roadmap.
- **Reasoning-native executive rewrite**: The orchestrator works. We measure first, then decide if it needs replacement. Noted as roadmap.

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
- **u** (control) = the system prompts, model selection, temperature settings, tool configurations, and now also the theta configuration (partition + model override + protocol level).

The induced macro-channel P(sigma_out | sigma_in, u) is empirically estimated as a confusion matrix from logged observations.

### 3.2 Informational Efficiency

The paper defines:

```
eta(pi, T, u) = C(P) / W
```

Where C(P) is the Shannon capacity of the induced macro-channel (bits per use) and W is the work/resource expenditure. In our system, W is measured in US dollars (token costs from the MODEL_REGISTRY), giving eta in bits per dollar. The same structure applies: higher eta means more recoverable distinctions per unit resource.

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

The APS system computes per-channel capacities and identifies which channel is the bottleneck. This is a directly falsifiable prediction: the end-to-end measured capacity should not exceed the minimum per-link capacity.

### 3.4 Epsilon-Triggered Partition Switching

The APS controller implements the paper's Section 9.3 mechanism:

1. Maintain a rolling estimate of goal failure: p_hat_fail(t) = (failures in window T) / (total observations in window T)
2. When p_hat_fail(t) > epsilon_G: the effective symbol set has degraded. Switch to a coarser partition (fewer, more separated macrostates) to preserve recoverability.
3. When p_hat_fail(t) < epsilon_G * 0.5 (hysteresis factor): conditions have improved. Switch to a finer partition (more symbols, higher information throughput).
4. W_total = W_operate + W_search: the cost of adaptation is charged against the total work budget.

v2 extends this with a second threshold at 2 * epsilon_G that triggers model escalation and regeneration in addition to coarsening.

### 3.5 Passive Transport vs Active Regeneration

This is the paper's Section 4, which v1 acknowledged theoretically but did not implement. v2 makes it operational.

**Passive transport**: A chain link operates without injecting additional work to restore the partition. The agent runs, produces output, and the result is logged. If noise degrades the output, the degradation propagates downstream. This is level 0 (nominal) in the theta configuration.

**Active regeneration**: A chain link spends work to re-establish a stable symbol set with bounded error. In physical systems, this means digital repeaters, CMOS gates refreshing voltage levels, or neural spikes with active ion pumps. In our agentic system, this means:

- **ConfirmProtocol** (level 1): On failure, retry the agent with a clarified prompt. This is analogous to a repeater that re-amplifies a degraded signal.
- **CrosscheckProtocol** (level 2): After LLM output, run a deterministic validator. This is analogous to error-correcting codes that detect and flag corruption.

The key insight: regeneration costs work (W_search increases), but it restores recoverability. The APS controller decides when the cost is justified by comparing p_fail against epsilon_G.

---

## 4. System Under Test: ecom-agents

### 4.1 Architecture Overview

ecom-agents is an autonomous e-commerce platform built with LangChain + LangGraph. It operates a Shopify storefront (liberty-forge-2.myshopify.com) selling patriotic apparel via Printful print-on-demand, with Stripe payments, Instagram marketing, and AI-driven analytics.

The system runs 24/7 with 6 scheduled jobs and processes tasks through a multi-agent graph:

```
                        ┌──────────────────────┐
                        │   APScheduler Jobs    │
                        │  (order_check/30min,  │
                        │   instagram/9am+3pm,  │
                        │   campaign/Mon 9am,   │
                        │   revenue/8am daily)  │
                        └──────────┬───────────┘
                                   │
                                   v
                        ┌──────────────────────┐
                        │  Master Orchestrator  │
                        │   (Ollama Qwen 2.5)  │
                        │                      │
                        │  Classifies task →   │
                        │  routes to specialist │
                        └──────────┬───────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              v                    v                    v
   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │ Sales/Marketing│   │   Operations   │   │    Revenue     │
   │   (GPT-4o)     │   │  (GPT-4o-mini) │   │  (Opus 4.6)   │
   │                │   │                │   │                │
   │ Instagram,     │   │ Orders, fulfil,│   │ Reports,       │
   │ campaigns      │   │ inventory      │   │ pricing,       │
   └───────┬────────┘   └───────┬────────┘   │ chargebacks    │
           │                    │             └───────┬────────┘
           │ (if complex)       │                     │
           v                    │                     │
   ┌────────────────┐          │                     │
   │  Sub-Agent     │          │                     │
   │  Subgraph      │          │                     │
   │                │          │                     │
   │ Writer (GPT-4o)│          │                     │
   │ Image (mini)   │          │                     │
   │ Hashtag (Qwen) │          │                     │
   │ Analyzer(Opus) │          │                     │
   └───────┬────────┘          │                     │
           │                   │                     │
           └───────────────────┴─────────────────────┘
                               │
                        ┌──────v──────┐
                        │  Tool Calls │
                        │  Shopify    │
                        │  Stripe     │
                        │  Printful   │
                        │  Instagram  │
                        └─────────────┘
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

The following existing subsystems are directly leveraged by the APS implementation:

**EventBroadcaster** (`src/events.py`): Singleton that broadcasts structured JSON events to all connected WebSocket clients. The APS system adds three new event types (`aps_observation`, `aps_evaluation`, `aps_theta_switch`) through this existing mechanism.

**ForgeEventCallbackHandler** (`src/events.py`): LangChain callback handler that already hooks into `on_chain_start`, `on_chain_end`, `on_tool_start`, `on_tool_end`, `on_llm_start`, `on_llm_end`. We extend `on_tool_start`/`on_tool_end` to log K7 (tool call) observations.

**Circuit Breaker** (`src/resilience/circuit_breaker.py`): Per-service circuit breakers with CLOSED -> OPEN -> HALF_OPEN state machine. The APS controller mirrors this pattern conceptually (threshold-triggered state transitions with cooldowns) but operates on information-theoretic metrics rather than binary failure counts.

**MODEL_REGISTRY** (`src/llm/config.py`): Contains per-model cost rates (input_cost_per_1k, output_cost_per_1k). Used by the APS instrumentation layer to estimate W (resource cost) per invocation without needing to correlate individual token counts.

**FALLBACK_CHAINS** (`src/llm/fallback.py`): Existing model fallback chains (e.g., OLLAMA_QWEN -> GPT4O_MINI -> GPT4O). The v2 theta configuration's model_override field aligns with these chains — when APS escalates a model, it recommends the next model in the existing fallback chain.

**APScheduler** (`src/scheduler/autonomous.py`): Background scheduler with 6 existing jobs. We add a 7th job (`aps_evaluation`) that runs the APS controller every 5 minutes.

**PostgreSQL** (port 5434): Already running for LangGraph checkpoint storage. We add 3 new tables for APS data.

**Redis** (port 6381): Used for medium-term session memory. Not used by APS (we need SQL aggregation queries that Redis doesn't support well).

### 4.4 Message Flow and State Schema

All agent communication flows through a shared `AgentState` TypedDict defined in `src/state.py`:

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # LangChain message history
    task_type: NotRequired[str]           # Orchestrator classification
    task_complexity: NotRequired[str]     # trivial/simple/moderate/complex
    current_agent: NotRequired[str]       # Active agent name
    route_to: NotRequired[str]            # Next agent destination
    trigger_source: NotRequired[str]      # 'scheduler' or 'api'
    trigger_payload: NotRequired[dict]    # Task parameters
    should_spawn_sub_agents: NotRequired[bool]
    sub_agents_spawned: NotRequired[list[str]]
    memory_context: NotRequired[str]      # ChromaDB retrieval
    sales_result: NotRequired[dict]
    operations_result: NotRequired[dict]
    revenue_result: NotRequired[dict]
    sub_agent_results: NotRequired[dict]
    error: NotRequired[str]
    retry_count: NotRequired[int]
```

Each agent node is a function `(state: AgentState) -> dict` that reads from state and returns a partial update dict. The LangGraph runtime merges the update into the state. This is the interface we instrument.

---

## 5. Channel Identification: 7 Induced Macro-Channels

Each channel represents an agent interface where a high-dimensional input state is processed and produces an output. The "microstate" at each boundary is a subset of AgentState fields; the partition maps these to discrete symbols.

### 5.1 K1: Orchestrator Routing Channel

**What it does**: The orchestrator receives a task description (from scheduler or API) and classifies it into a task_type and route_to destination.

**Physical analogy**: This is the "encoder" of the system — it takes a raw signal (natural language task description) and produces a discrete symbol (routing decision) that determines the downstream path.

**Microstate (X)**: The full text of `messages[-1].content` plus `trigger_payload`.

**Input partition (pi_in)**: Classifies the raw task description into a task category based on keyword features.

**Output partition (pi_out)**: The orchestrator's actual (task_type, route_to) classification.

**Why it matters**: Misclassification here propagates errors through the entire chain. If the orchestrator routes an order-check task to the sales agent, the downstream confusion matrix will show it as noise. This is frequently the bottleneck channel.

### 5.2 K2: Sales & Marketing Execution Channel

**What it does**: The sales agent receives a classified sales task and produces content (Instagram post, campaign plan, or product launch materials).

**Microstate (X)**: task_type + task_complexity + trigger_payload + messages.

**Input partition**: What kind of sales task was requested and whether it requires sub-agent delegation.

**Output partition**: The quality/structure of the sales_result — whether it produced valid structured output, raw text, delegated to sub-agents, or errored.

### 5.3 K3: Operations Execution Channel

**What it does**: The operations agent handles order checks, inventory syncs, and fulfillment via Shopify and Printful APIs.

**Microstate (X)**: task_type + trigger_payload + available tool state.

**Input partition**: What operational action was requested.

**Output partition**: Whether the action completed successfully, requires follow-up, errored, or produced malformed output.

**Why it matters**: This is the most frequently invoked channel (order_check runs every 30 minutes), so it accumulates observations fastest and will be the first to produce statistically meaningful confusion matrices.

### 5.4 K4: Revenue Analytics Execution Channel

**What it does**: The revenue agent (Claude Opus 4.6) analyzes financial data from Stripe and produces reports with recommendations.

**Microstate (X)**: task_type + memory_context + Stripe data.

**Input partition**: Type of analysis requested.

**Output partition**: Report type combined with confidence level and whether actionable recommendations were produced.

**Why it matters**: This is the most expensive channel ($15+$75 per 1K tokens). The eta metric here will be low in absolute terms, making it a natural target for efficiency optimization and model escalation decisions.

### 5.5 K5: Content Writer Sub-Agent Channel

**What it does**: Generates Instagram post captions and content as part of the campaign sub-agent pipeline.

**Microstate (X)**: Campaign brief from parent agent.

**Input partition**: Type of brief (campaign vs. product).

**Output partition**: Quality of the generated content — whether it produced parseable JSON with a valid caption.

### 5.6 K6: Campaign Analyzer Sub-Agent Channel

**What it does**: The campaign analyzer (Claude Opus 4.6) evaluates all sub-agent outputs and predicts engagement.

**Microstate (X)**: Aggregated results from content_writer, image_selector, and hashtag_optimizer.

**Input partition**: Completeness of upstream sub-agent results.

**Output partition**: Engagement prediction level or analysis failure.

### 5.7 K7: Tool Call Channel

**What it does**: All external API calls — Shopify, Stripe, Printful, Instagram.

**Microstate (X)**: Tool name + arguments + API state.

**Input partition**: Which tool was invoked (fine: 13 individual tools, coarse: 4 service groups).

**Output partition**: Success/failure categorization of the API response.

**Why it matters**: Tool calls are the system's interface with the external world. API failures, rate limits, and auth errors are the primary source of noise in the system. The circuit breaker already tracks this at the service level; APS adds information-theoretic measurement. This channel is the most natural target for regeneration (retries, cross-checks).

---

## 6. Partition Definitions: Fine and Coarse Schemes

### 6.1 Design Principles

Each channel gets exactly two partition schemes:

1. **Fine partition**: More symbols, higher resolution, more sensitive to noise. Used when the system is operating well and we want maximum information throughput.

2. **Coarse partition**: Fewer symbols, wider separation between macrostates, more robust to noise. Used when error rates are elevated and we need to maintain recoverability at the cost of resolution.

All classification functions are **pure, deterministic functions** of AgentState fields. They inspect only the observable interface state (satisfying the paper's admissibility constraint C1: interface-boundedness). They do not require access to internal LLM activations or other microscopic degrees of freedom.

The classification functions are also **counterfactually robust** (constraint C2): different inputs would produce different classifications under the same mapping, and these differences are achievable via the system's normal control interface (different task descriptions, different API states).

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

Each classification function is a pure function that inspects specific AgentState fields and returns a symbol string.

**K1 Fine — classify_input**: Parse the last message content and trigger_payload. Match against keyword sets for each of the 7 VALID_TASK_TYPES defined in `src/agents/orchestrator.py`. Fall back to "content_post" if no keywords match.

**K1 Fine — classify_output**: Read `result["task_type"]` directly — the orchestrator already produces this classification. If task_type is not in the valid set or route_to is "error_handler", classify as the error symbol.

**K1 Coarse — classify_input**: Map the 7 task types into 3 groups: {content_post, full_campaign, product_launch} -> "sales_task", {order_check, inventory_sync} -> "ops_task", {revenue_report, pricing_review} -> "analytics_task".

**K1 Coarse — classify_output**: Read `result["route_to"]` directly — already one of 3 values.

**K3 Fine — classify_input**: Read `state["task_type"]` and map to the operations subcategory. "order_check" and "inventory_sync" map directly; "fulfill_order" and "order_status" are inferred from trigger_payload keywords.

**K3 Fine — classify_output**: Inspect `result["operations_result"]`. If it contains an "error" key or the status field indicates failure -> "error". If the response doesn't parse as expected structure -> "malformed". If it contains action items -> "needs_action". Otherwise -> "completed".

**K7 Fine — classify_input**: The tool function name, extracted from the LangChain callback `on_tool_start` event's `serialized["name"]` field.

**K7 Fine — classify_output**: Inspect the tool result. If the result is an exception -> categorize by exception type (HTTP status codes for http_error, TimeoutError for timeout, authentication messages for auth_error, rate limit headers for rate_limited). If the result parses but is empty -> "success_empty". If it contains data -> "success_data". If it fails to parse -> "parse_error".

**K7 Coarse — classify_input**: Map tool names to service groups: any function starting with "shopify_" -> "shopify", "stripe_" -> "stripe", "printful_" -> "printful", "instagram_" -> "instagram".

**K7 Coarse — classify_output**: Binary: any non-error result -> "success", any error -> "failure".

---

## 7. Theta Configurations: The Expanded Control Tuple

### 7.1 Why Theta is More Than a Partition

v1 treated the APS controller's action space as a binary: fine or coarse partition. The alternative architecture correctly identified that this is too narrow. When a channel degrades, the system has three independent knobs:

1. **Partition granularity**: Reduce the number of symbols (coarsen) to increase separation between macrostates.
2. **Model capability**: Escalate from a cheap/fast model to a more capable/expensive one.
3. **Protocol level**: Add regeneration (retries, validation) to actively restore the symbol set.

These correspond to different physical mechanisms. Coarsening is like reducing the alphabet size in a noisy communication system. Model escalation is like increasing transmit power. Regeneration is like adding error-correcting codes or repeaters.

The paper's formal object is θ = (π_in, π_out, D, u, ...) — the full configuration tuple. v2 makes a practical subset of this explicit.

### 7.2 ThetaConfig Data Structure

```python
@dataclass
class ThetaConfig:
    """Complete control configuration for one channel under APS.

    This is the paper's theta = (pi, D, u) made concrete:
    - partition_id selects the coarse-graining (pi)
    - model_override selects the dynamics (part of u)
    - protocol_level selects the regeneration strategy (part of u)
    """
    theta_id: str                          # e.g., "theta_K3_degraded"
    channel_id: str                        # e.g., "K3"
    level: int                             # 0=nominal, 1=degraded, 2=critical
    partition_id: str                      # references a PartitionScheme theta_id
    model_override: ModelID | None         # None = use default; set = override
    protocol_level: ProtocolLevel          # PASSIVE, CONFIRM, CROSSCHECK
    description: str = ""
```

### 7.3 Protocol Levels

```python
class ProtocolLevel(str, Enum):
    PASSIVE = "passive"       # No regeneration. Run and log. Default.
    CONFIRM = "confirm"       # On failure, retry once with clarified prompt.
    CROSSCHECK = "crosscheck" # After LLM output, run deterministic validator.
```

**PASSIVE**: The agent runs normally. Output is classified and logged. No additional work is spent. This is passive transport in the paper's terminology.

**CONFIRM**: If the output is classified as a failure symbol, the wrapper retries the agent once with an augmented prompt that includes the failure context ("Previous attempt produced an error. Please re-examine..."). Both attempts are logged as observations. This doubles the cost but often recovers from transient LLM failures.

**CROSSCHECK**: After the agent produces output, a deterministic validator checks the result against known invariants (e.g., "do the Shopify order IDs in the result actually exist?", "does the Stripe revenue figure match the raw API data?"). If validation fails, the output is flagged as "crosscheck_failed" in sigma_out. This adds a small fixed cost (one API call for validation) but catches hallucinated or malformed data.

### 7.4 Three-Level Escalation Tiers

| Level | Name | Partition | Model | Protocol | Trigger |
|-------|------|-----------|-------|----------|---------|
| 0 | nominal | FINE | default | PASSIVE | p_fail < epsilon_G |
| 1 | degraded | COARSE | default | CONFIRM | p_fail > epsilon_G |
| 2 | critical | COARSE | escalated | CROSSCHECK | p_fail > 2 * epsilon_G |

Level 0 → 1 is equivalent to v1's coarsening, plus adds confirmation retries.
Level 1 → 2 adds model escalation and deterministic validation — the key v2 contribution.
De-escalation (2 → 1 → 0) happens when p_fail drops below epsilon_G * 0.5, with a 300s cooldown.

### 7.5 Complete Theta Table: All 7 Channels x 3 Levels

**K1 — Orchestrator Routing**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K1_nominal | theta_K1_fine | Ollama Qwen (default) | PASSIVE |
| 1 | theta_K1_degraded | theta_K1_coarse | Ollama Qwen (default) | CONFIRM — re-classify ambiguous tasks |
| 2 | theta_K1_critical | theta_K1_coarse | GPT-4o-mini (escalated) | PASSIVE — stronger model doesn't need retry |

**K2 — Sales/Marketing**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K2_nominal | theta_K2_fine | GPT-4o (default) | PASSIVE |
| 1 | theta_K2_degraded | theta_K2_coarse | GPT-4o (default) | CONFIRM — retry failed content generation |
| 2 | theta_K2_critical | theta_K2_coarse | GPT-4o (no escalation available) | CROSSCHECK — validate output JSON structure |

**K3 — Operations**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K3_nominal | theta_K3_fine | GPT-4o-mini (default) | PASSIVE |
| 1 | theta_K3_degraded | theta_K3_coarse | GPT-4o-mini (default) | CONFIRM — retry failed operations |
| 2 | theta_K3_critical | theta_K3_coarse | GPT-4o (escalated) | CROSSCHECK — validate Shopify order IDs exist |

**K4 — Revenue Analytics**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K4_nominal | theta_K4_fine | Claude Opus 4.6 (default) | PASSIVE |
| 1 | theta_K4_degraded | theta_K4_coarse | Claude Opus 4.6 (default) | CONFIRM — retry failed analyses |
| 2 | theta_K4_critical | theta_K4_coarse | Claude Opus 4.6 (no escalation) | CROSSCHECK — validate Stripe revenue figures |

**K5 — Content Writer**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K5_nominal | theta_K5_fine | GPT-4o (default) | PASSIVE |
| 1 | theta_K5_degraded | theta_K5_coarse | GPT-4o (default) | CONFIRM — retry with explicit JSON schema |
| 2 | theta_K5_critical | theta_K5_coarse | GPT-4o (default) | CROSSCHECK — validate caption length + hashtag count |

**K6 — Campaign Analyzer**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K6_nominal | theta_K6_fine | Claude Opus 4.6 (default) | PASSIVE |
| 1 | theta_K6_degraded | theta_K6_coarse | Claude Opus 4.6 (default) | CONFIRM — retry with explicit scoring rubric |
| 2 | theta_K6_critical | theta_K6_coarse | Claude Opus 4.6 (default) | CROSSCHECK — validate engagement score ranges |

**K7 — Tool Calls**:
| Level | theta_id | Partition | Model | Protocol |
|-------|----------|-----------|-------|----------|
| 0 | theta_K7_nominal | theta_K7_fine | N/A (tools, not LLM) | PASSIVE |
| 1 | theta_K7_degraded | theta_K7_coarse | N/A | CONFIRM — retry failed API calls once |
| 2 | theta_K7_critical | theta_K7_coarse | N/A | CROSSCHECK — validate response schema + idempotency |

Note: For K7 (tool calls), model_override is always None because tools don't use LLMs. Regeneration for tools means retries (CONFIRM) and response validation (CROSSCHECK).

---

## 8. Regeneration Protocols

### 8.1 Why Coarsening Alone Is Insufficient

The data processing inequality tells us that cascading noisy channels degrades information. Coarsening the partition helps by reducing the number of symbols that need to be distinguished — but it doesn't reduce the underlying error rate. If a Shopify API is returning 500 errors, coarsening from 13 tool names to 4 service groups doesn't fix the 500 errors.

Regeneration addresses this by spending additional work to restore the symbol set. In the paper's terms: regeneration is what distinguishes a passive transmission line (which degrades with distance) from a digital repeater chain (which maintains signal quality by re-establishing voltage levels at each stage).

### 8.2 ConfirmProtocol: Retry with Clarification

```python
class ConfirmProtocol:
    """On failure, retry once with a clarified/rephrased prompt.

    This is the simplest form of active regeneration: re-amplify
    the signal by giving the agent a second chance with more context.
    """

    def should_activate(self, sigma_out: str, channel_id: str) -> bool:
        """Only activate on failure symbols."""
        return sigma_out in FAILURE_SYMBOLS.get(channel_id, set())

    def execute(self, channel_id: str, state: dict, original_result: dict,
                node_fn: Callable) -> tuple[dict, str]:
        """Retry the node with augmented prompt.

        Returns (new_result, new_sigma_out).
        Both the original and retry are logged as separate observations.
        """
        # Augment the last message with failure context
        retry_state = state.copy()
        original_messages = list(state.get("messages", []))
        retry_prompt = (
            f"Previous attempt produced an error or incomplete result. "
            f"Please re-examine the task carefully and try again. "
            f"Original error context: {_extract_error(original_result)}"
        )
        original_messages.append(HumanMessage(content=retry_prompt))
        retry_state["messages"] = original_messages

        # Re-invoke the node function
        retry_result = node_fn(retry_state)

        # Re-classify the output
        partition = get_active_partition(channel_id)
        new_sigma_out = partition.classify_output(retry_result)

        return retry_result, new_sigma_out
```

### 8.3 CrosscheckProtocol: Deterministic Validation

```python
class CrosscheckProtocol:
    """After LLM output, run a deterministic validator.

    This is error-detection coding: we can't fix the output, but we can
    detect when it's wrong and flag it, preventing bad data from propagating
    downstream.
    """

    def execute(self, channel_id: str, result: dict) -> tuple[dict, str | None]:
        """Validate the result against known invariants.

        Returns (result, override_sigma_out).
        If override_sigma_out is not None, it replaces the LLM-derived sigma_out.
        """
        validator = VALIDATORS.get(channel_id)
        if validator is None:
            return result, None

        validation_result = validator(result)
        if validation_result.passed:
            return result, None
        else:
            # Flag the result as crosscheck-failed
            result["_crosscheck_failed"] = True
            result["_crosscheck_reason"] = validation_result.reason
            return result, "crosscheck_failed"
```

### 8.4 Per-Channel Validator Definitions

| Channel | Validator | What It Checks |
|---------|-----------|----------------|
| K3 | validate_operations_result | If result mentions Shopify order IDs, verify they exist via shopify_query_orders. If result claims "no orders", verify against Shopify API. |
| K4 | validate_revenue_numbers | If result contains revenue figures, verify against raw stripe_revenue_query. Flag if discrepancy > 10%. |
| K5 | validate_content_output | Check JSON structure has "caption" field with len > 10 and "hashtags" field with 3-30 items. |
| K6 | validate_engagement_score | Check that predicted engagement score is a number in [0, 100] range. |
| K7 | validate_tool_response | Check that API response matches expected schema (e.g., Shopify product has "id", "title", "variants"). |

Validators are deterministic functions that make at most one API call (for data verification) and return a pass/fail with reason string.

### 8.5 Regeneration Cost Accounting

Regeneration costs are tracked as part of W_total:

- **ConfirmProtocol**: Approximately doubles the LLM cost for that invocation (one retry). The retry's token cost is estimated from MODEL_REGISTRY the same way as the original.
- **CrosscheckProtocol**: Adds a small fixed cost per validation API call. For tool-based validators (Shopify/Stripe re-query), the cost is approximately one tool invocation.

Both costs are included in the `cost_usd` field of the observation record, ensuring that eta = C(P) / W correctly accounts for regeneration overhead.

### 8.6 Future Regeneration Patterns

Not implemented in v2, but noted for future work:

- **Majority vote**: Run the same task through 2-3 different models, take the consensus. High cost, high reliability.
- **Two-phase commit**: For irreversible actions (price changes, refunds), create a "proposed change" first, then validate and commit separately.
- **Acknowledgement protocols**: Explicit ACK messages between agents to prevent silent drift.
- **Canary deployment**: Test changes on a small subset before full rollout.

---

## 9. Goal Specifications

### 9.1 Two-Tier Goal Architecture

v2 introduces a two-tier goal system:

**Tier 1 — Mission-Critical (Hard Floors)**: Goals with epsilon_G = 0. Failure here is not "noise to adapt to" — it's a failure to prevent. These trigger immediate action (block the action, log an alert) rather than partition switching.

**Tier 2 — Operational (Epsilon-Triggered)**: Goals with epsilon_G > 0. Failure rates are expected to fluctuate; the APS controller adapts theta configurations to keep p_fail within tolerance.

### 9.2 Tier 1: Mission-Critical Goals (Hard Floors)

| Goal | F_G (failure event) | epsilon_G | Response | Channels |
|------|---------------------|-----------|----------|----------|
| policy_violation | Action violates Shopify ToS, Instagram community guidelines, Stripe acceptable use, or ad platform policies | 0.0 | Block action before execution, log alert, increment violation counter | All |
| negative_margin | Order would result in contribution margin < 0 (cost exceeds revenue after COGS, shipping, fees) | 0.0 | Block action, log alert, flag for human review | K3, K4 |

**Implementation**: These are checked as pre-execution validators in the instrument wrapper, not as post-hoc analysis. The wrapper inspects the agent's proposed action before allowing it to proceed. If a Tier 1 goal would be violated, the action is blocked and sigma_out is recorded as "blocked_policy" or "blocked_margin".

**Why these are not epsilon-triggered**: You don't adapt to policy violations by coarsening partitions. You prevent them. The alternative architecture correctly identified this distinction.

### 9.3 Tier 2: Operational Goals (Epsilon-Triggered)

| Goal | F_G (failure event) | epsilon_G | T (window) | Channels |
|------|---------------------|-----------|------------|----------|
| routing_accuracy | route_to = error_handler or retry triggered | 0.10 | 3600s (1 hour) | K1 |
| task_completion | sigma_out in {error, malformed, failure} | 0.05 | 7200s (2 hours) | K2, K3, K4 |
| tool_reliability | sigma_out in {http_error, timeout, auth_error, rate_limited} | 0.15 | 1800s (30 min) | K7 |
| campaign_quality | sigma_out in {unusable, analysis_failed, error} | 0.10 | 86400s (24 hours) | K5, K6 |
| response_latency | latency_ms > 30000 | 0.05 | 3600s (1 hour) | K1, K2, K3, K4 |
| cost_efficiency | cost_usd > 0.50 per invocation | 0.10 | 3600s (1 hour) | K2, K4, K6 |

**Escalation thresholds for v2**:
- p_fail > epsilon_G → escalate to level 1 (degraded)
- p_fail > 2 * epsilon_G → escalate to level 2 (critical)
- p_fail < epsilon_G * 0.5 → de-escalate one level (with cooldown)

### 9.4 Goal-to-Channel Mapping

```
                    K1    K2    K3    K4    K5    K6    K7
policy_violation     x     x     x     x     x     x     x
negative_margin      -     -     x     x     -     -     -
routing_accuracy     x     -     -     -     -     -     -
task_completion      -     x     x     x     -     -     -
tool_reliability     -     -     -     -     -     -     x
campaign_quality     -     -     -     -     x     x     -
response_latency     x     x     x     x     -     -     -
cost_efficiency      -     x     -     x     -     x     -
```

---

## 10. Information-Theoretic Computations

### 10.1 Confusion Matrix Construction

Given a set of observations {(sigma_in_i, sigma_out_i)} for a channel with partition theta, construct the confusion matrix:

```
counts[i][j] = number of observations where sigma_in = alphabet_in[i] AND sigma_out = alphabet_out[j]
```

The row-normalized form gives the empirical conditional distribution:

```
P_hat(sigma_out | sigma_in) = counts[i][j] / sum_j(counts[i][j])
```

Rows with zero observations get a uniform distribution (maximum entropy prior).

### 10.2 Mutual Information

Computed from the empirical joint distribution:

```
I(X;Y) = sum_{x,y} p(x,y) * log2(p(x,y) / (p(x) * p(y)))
```

With the convention 0 * log(0) = 0.

Properties:
- I(X;Y) = 0 when input and output are statistically independent (no information transmitted).
- I(X;Y) = H(X) when the channel is deterministic (perfect information transmission).
- 0 <= I(X;Y) <= min(H(X), H(Y)).

### 10.3 Channel Capacity via Blahut-Arimoto

The Shannon channel capacity is:

```
C(P) = max_{p(x)} I(X;Y)
```

The maximum is over all possible input distributions. We compute this using the Blahut-Arimoto algorithm, which iteratively alternates between optimizing the input distribution and computing the resulting mutual information. The algorithm converges geometrically for finite alphabets.

For our small alphabets (max 13 symbols for K7 fine), Blahut-Arimoto converges in under 100 iterations with tolerance 1e-6.

**Why capacity and not just mutual information?** The empirical mutual information depends on the input distribution (which tasks the scheduler happens to generate). Capacity is the maximum over all input distributions, giving a substrate property — the inherent information-carrying capability of the channel regardless of how it's being used.

### 10.4 Informational Efficiency eta

```
eta = C(P) / W
```

Where W is the total cost in USD accumulated over the evaluation window. Units: bits per dollar.

When W is very small (e.g., the orchestrator uses free Ollama), eta approaches infinity. In these cases, we report eta as "uncapped" and focus on the absolute capacity value.

We also compute:
- **eta_token** = C(P) / W_tokens (bits per token) — useful for comparing models
- **eta_time** = C(P) / T_seconds (bits per second) — useful for latency analysis

v2 addition: When regeneration is active, W increases (confirm doubles LLM cost, crosscheck adds validator cost). eta may temporarily decrease during regeneration, but if regeneration restores capacity (C(P) increases), the net effect on eta is empirically measurable. This is the paper's W_total = W_operate + W_search.

### 10.5 Chain Capacity and Bottleneck Identification

For each directed path through the agent graph, compute:

```
C(P_chain) <= min_k C(P_k)
```

The three primary paths are:
1. K1 -> K2 -> K5 -> K6 (orchestrator -> sales -> content_writer -> campaign_analyzer)
2. K1 -> K3 -> K7 (orchestrator -> operations -> tool calls)
3. K1 -> K4 -> K7 (orchestrator -> revenue -> tool calls)

The bottleneck channel is the one with minimum capacity on each path.

---

## 11. APS Controller Design

### 11.1 Rolling Failure Estimation

For each (goal, channel) pair, the controller queries recent observations from PostgreSQL:

```sql
SELECT * FROM aps_observations
WHERE channel_id = ? AND observed_at > NOW() - INTERVAL '? seconds'
ORDER BY observed_at DESC
```

It applies the goal's failure detector F_G to each observation and computes:

```
p_hat_fail = count(F_G(obs) = True) / count(obs)
```

### 11.2 Three-Level Escalation Logic with Hysteresis

```
For each (goal, channel):
    compute p_fail from recent observations
    current_level = get_current_theta_level(channel)

    IF p_fail > 2 * epsilon_G AND current_level < 2:
        escalate to level 2 (critical): coarse + model escalation + crosscheck
        cooldown: 60s before further escalation allowed

    ELIF p_fail > epsilon_G AND current_level < 1:
        escalate to level 1 (degraded): coarse + confirm protocol
        cooldown: 60s before further escalation allowed

    ELIF p_fail < epsilon_G * 0.5 AND current_level > 0:
        de-escalate one level
        cooldown: 300s before further de-escalation allowed

    Min observations: 20 before any switch allowed
```

**Why three levels instead of two?** v1's binary (fine/coarse) treated all degradation the same. But there's a meaningful difference between "error rate is slightly elevated" (10% when tolerance is 5%) and "error rate is severely elevated" (30% when tolerance is 15%). The three-level system provides proportional response:

- Level 0 → 1: Light noise → coarsen + retry. Low additional cost.
- Level 1 → 2: Severe noise → coarsen + escalate model + validate. Higher cost, but necessary.

**Hysteresis parameters**:
- Escalation cooldown: 60s (respond quickly to degradation)
- De-escalation cooldown: 300s (wait for stable improvement before relaxing)
- Hysteresis factor: 0.5 (de-escalate when p_fail < epsilon_G / 2)
- Min observations: 20 (sufficient for standard error < 0.11 at p = 0.5)

### 11.3 Evaluation Cycle

The APSController.evaluate_all() method runs every 5 minutes:

1. For each goal in GOALS:
   a. For each channel in goal.channels:
      - Query recent observations within window T
      - Compute p_fail
      - Build confusion matrix
      - Compute mutual information, channel capacity, eta
      - Store metrics in aps_metrics table
      - Evaluate escalation/de-escalation decision
   b. Aggregate goal-level p_fail across all channels
2. Broadcast `aps_evaluation` event via WebSocket
3. Return summary dict with all metrics, goal statuses, theta levels, and any switches triggered

### 11.4 W_total Accounting

The paper specifies W_total = W_operate + W_search:

**W_operate**: The LLM inference cost per invocation. Estimated from MODEL_REGISTRY:
- Each agent uses a known model (orchestrator = OLLAMA_QWEN at $0, sales = GPT4O at $2.50/$10.00, etc.)
- Cost = (input_tokens / 1000) * input_cost + (output_tokens / 1000) * output_cost

**W_search (v2 addition)**: The overhead of APS itself plus regeneration costs:
- APS evaluation: negligible (microseconds of CPU for DB queries + matrix math)
- ConfirmProtocol: approximately 1x the original invocation cost (one retry)
- CrosscheckProtocol: approximately 0.01-0.05x the original cost (one validation API call)

All costs are logged per observation, so eta correctly accounts for regeneration overhead.

---

## 12. Instrumentation Strategy

### 12.1 The Wrapper Pattern

The core design principle is **zero modification to existing agent code**. All instrumentation is applied by wrapping the agent node functions at graph construction time. If the APS system crashes, the original node function still executes normally.

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

Similarly in `src/agents/sub_agents.py` for K5 and K6.

### 12.3 Regeneration Integration in the Wrapper

The v2 wrapper checks the active theta's protocol level after the node runs:

```python
def instrument_node(channel_id, model_id, node_fn):
    def wrapped(state):
        theta = get_active_theta(channel_id)
        partition = get_partition(theta.partition_id)
        sigma_in = partition.classify_input(state)

        # Track effective model (for cost accounting)
        effective_model = theta.model_override or model_id

        t0 = time.time()
        result = node_fn(state)  # Original function, always runs
        latency_ms = (time.time() - t0) * 1000
        sigma_out = partition.classify_output(result)

        # v2: Apply regeneration protocol if active and result is a failure
        if theta.protocol_level == ProtocolLevel.CONFIRM:
            if is_failure(sigma_out, channel_id):
                result, sigma_out = confirm_protocol.execute(
                    channel_id, state, result, node_fn
                )
                # Note: retry cost added to total
        elif theta.protocol_level == ProtocolLevel.CROSSCHECK:
            result, override = crosscheck_protocol.execute(channel_id, result)
            if override is not None:
                sigma_out = override

        cost = estimate_cost(effective_model, state, result, theta.protocol_level)
        log_observation(channel_id, theta.theta_id, sigma_in, sigma_out,
                       time.time(), latency_ms, cost)
        return result
    return wrapped
```

**Important note on model_override**: In v2, model_override is a **recommendation signal**, not an actuator. It is logged in observations and surfaced via the API, but it does not change which LLM the agent internally calls (that's hardcoded in each agent file). To actually swap models at runtime would require passing model selection through the LangGraph state or refactoring agent builders. This is deferred to the roadmap. For now, model_override provides data to validate that escalation would be beneficial, before we wire in the actuator.

### 12.4 Tool-Call Instrumentation

Tool calls (K7) are instrumented via the existing ForgeEventCallbackHandler in `src/events.py`. We add tracking dicts for tool start times and names, then log observations in `on_tool_end`.

For K7 regeneration:
- **CONFIRM**: On tool failure, retry the tool call once (respecting idempotency — only retry read operations, not writes).
- **CROSSCHECK**: After tool success, validate the response schema against expected structure.

### 12.5 Error Safety

The instrumentation wrapper must never break the agent. All APS operations are wrapped in try/except:

```python
def wrapped(state):
    try:
        theta = get_active_theta(channel_id)
        partition = get_partition(theta.partition_id)
        sigma_in = partition.classify_input(state)
    except Exception:
        sigma_in = "unknown"

    result = node_fn(state)  # This ALWAYS runs, even if APS fails

    try:
        sigma_out = partition.classify_output(result)
        # Regeneration attempt (also try/excepted)
        if theta.protocol_level != ProtocolLevel.PASSIVE and is_failure(sigma_out, channel_id):
            try:
                result, sigma_out = apply_regeneration(...)
            except Exception:
                pass  # Regeneration failed; keep original result
        log_observation(...)
    except Exception:
        logger.warning("APS instrumentation failed for %s", channel_id, exc_info=True)

    return result  # Always return the result
```

---

## 13. Database Schema

### 13.1 Table: aps_observations

Stores every (sigma_in, sigma_out) observation. This is the raw data from which confusion matrices are computed.

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
    run_metadata    JSONB DEFAULT '{}'::JSONB
);

CREATE INDEX idx_aps_obs_channel_time ON aps_observations (channel_id, observed_at DESC);
CREATE INDEX idx_aps_obs_theta_time ON aps_observations (theta_id, observed_at DESC);
```

Expected volume: ~50 observations/day at current scheduler rates. Low storage burden.

### 13.2 Table: aps_metrics

Stores aggregated metrics computed by the APS controller each evaluation cycle (every 5 minutes).

```sql
CREATE TABLE IF NOT EXISTS aps_metrics (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    theta_id        VARCHAR(64) NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    p_fail          REAL NOT NULL,
    mutual_info     REAL NOT NULL,
    capacity        REAL NOT NULL,
    eta             REAL NOT NULL,
    n_observations  INTEGER NOT NULL,
    total_cost_usd  REAL DEFAULT 0.0,
    confusion_matrix JSONB,
    window_seconds  REAL
);

CREATE INDEX idx_aps_metrics_channel_time ON aps_metrics (channel_id, computed_at DESC);
```

Expected volume: 7 channels * 288 evaluations/day = ~2000 rows/day.

### 13.3 Table: aps_theta_switches

Audit log of every theta switch. Extended from v1's partition_switches to track level, model, and protocol changes.

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

Expected volume: very low — switches should be infrequent.

---

## 14. API Endpoints and WebSocket Events

### 14.1 REST Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | /aps/metrics | Latest metrics for all 7 channels | `{metrics: [{channel_id, theta_id, p_fail, mutual_info, capacity, eta, n_observations, ...}]}` |
| GET | /aps/metrics/{channel_id} | Metric history for one channel | `{channel_id, metrics: [...]}` |
| GET | /aps/partitions | Current theta state for all channels | `{partitions: {K1: {channel_name, active_theta, level, model_override, protocol_level, available_thetas}, ...}}` |
| POST | /aps/switch/{channel_id}/{theta_id} | Manual theta switch (testing) | `{status: "switched", channel_id, theta_id, level, model, protocol}` |
| GET | /aps/chain-capacity | Bottleneck capacity + path analysis | `{paths: [{path, chain_capacity, bottleneck, per_channel}], overall_bottleneck}` |
| POST | /aps/evaluate | Trigger immediate evaluation cycle | Full evaluation summary with metrics, goals, theta levels, switches |

### 14.2 WebSocket Event Types

All events broadcast through the existing `ws://localhost:8050/ws/events` endpoint:

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
        "K1": {
            "p_fail": 0.03,
            "mutual_information_bits": 1.42,
            "channel_capacity_bits": 1.58,
            "eta_bits_per_usd": "inf",
            "n_observations": 48,
            "active_theta": "theta_K1_nominal",
            "level": 0,
            "model_override": null,
            "protocol_level": "passive"
        },
        "K3": {
            "p_fail": 0.12,
            "mutual_information_bits": 0.85,
            "channel_capacity_bits": 1.00,
            "eta_bits_per_usd": 83.3,
            "n_observations": 48,
            "active_theta": "theta_K3_degraded",
            "level": 1,
            "model_override": null,
            "protocol_level": "confirm"
        }
    },
    "goals": {
        "routing_accuracy": {"p_fail": 0.03, "epsilon_G": 0.10, "violated": false},
        "task_completion": {"p_fail": 0.12, "epsilon_G": 0.05, "violated": true}
    },
    "switches": [
        {
            "channel_id": "K3",
            "from_theta": "theta_K3_nominal",
            "to_theta": "theta_K3_degraded",
            "direction": "escalated",
            "from_level": 0,
            "to_level": 1,
            "model_changed": false,
            "protocol_changed": true,
            "trigger_p_fail": 0.12,
            "goal_id": "task_completion"
        }
    ]
}
```

**aps_theta_switch** (when a theta configuration changes):
```json
{
    "type": "aps_theta_switch",
    "channel_id": "K3",
    "from_theta": "theta_K3_nominal",
    "to_theta": "theta_K3_degraded",
    "direction": "escalated",
    "from_level": 0,
    "to_level": 1,
    "model_changed": false,
    "protocol_changed": true,
    "trigger_p_fail": 0.12,
    "trigger_epsilon": 0.05,
    "goal_id": "task_completion"
}
```

---

## 15. New File Structure

```
src/aps/
    __init__.py              # Package init, init_aps() startup function
    partitions.py            # PartitionScheme, ChannelPartitions, CHANNEL_REGISTRY
                             #   14 partition schemes (7 channels x 2 granularities)
                             #   All classify_input/classify_output functions
                             #   register_channel(), get_active_partition(), switch_partition()
    theta.py                 # ThetaConfig, ProtocolLevel, THETA_REGISTRY
                             #   21 theta configs (7 channels x 3 levels)
                             #   get_active_theta(), set_theta_level()
    channel.py               # ConfusionMatrix dataclass
                             #   mutual_information()
                             #   channel_capacity_blahut_arimoto()
                             #   informational_efficiency()
                             #   chain_capacity()
    controller.py            # APSController class
                             #   evaluate_all() - main evaluation loop
                             #   _evaluate_escalation() - 3-level logic with hysteresis
                             #   _build_confusion_matrix() - from observations
                             #   aps_controller singleton
    goals.py                 # GoalTier enum, GoalID enum, Goal dataclass
                             #   MISSION_CRITICAL_GOALS (Tier 1)
                             #   OPERATIONAL_GOALS (Tier 2)
    regeneration.py          # ConfirmProtocol, CrosscheckProtocol
                             #   VALIDATORS dict (per-channel validators)
                             #   FAILURE_SYMBOLS dict
                             #   apply_regeneration() dispatcher
    instrument.py            # instrument_node() wrapper
                             #   estimate_cost() helper (with regeneration cost)
                             #   classify_tool_input/output for K7
    store.py                 # init_aps_tables() - CREATE TABLE IF NOT EXISTS
                             #   log_observation()
                             #   get_recent_observations()
                             #   store_aps_metrics()
                             #   store_theta_switch_event()
                             #   get_latest_metrics()
    scheduler_jobs.py        # aps_evaluation_job() for APScheduler integration

tests/
    test_aps_partitions.py   # ~120 lines
    test_aps_channel.py      # ~120 lines
    test_aps_controller.py   # ~180 lines
    test_aps_instrument.py   # ~100 lines
    test_aps_regeneration.py # ~80 lines
    test_aps_integration.py  # ~100 lines
```

---

## 16. Modifications to Existing Files

| File | What Changes | Lines Added/Changed | Risk |
|------|-------------|---------------------|------|
| `src/graph.py` | Import instrument_node; wrap 4 node registrations with instrument_node() | ~8 lines | Low — wrapper is transparent |
| `src/agents/sub_agents.py` | Import instrument_node; wrap content_writer and campaign_analyzer nodes | ~4 lines | Low — same wrapper pattern |
| `src/events.py` | Add _aps_tool_starts dict to ForgeEventCallbackHandler; add APS logging to on_tool_start/on_tool_end | ~20 lines | Low — additive, try/except guarded |
| `src/serve.py` | Import APS init; call init_aps_tables() and init_all_partitions() in lifespan; add 6 new API endpoints | ~80 lines | Low — new endpoints, no changes to existing ones |
| `src/scheduler/autonomous.py` | Import aps_evaluation_job; add aps_evaluation IntervalTrigger(minutes=5) to start() | ~10 lines | Low — additive job |
| `pyproject.toml` | Add `numpy>=1.24.0,<3.0.0` to dependencies | ~1 line | Low — numpy is standard |

**Total existing code touched**: ~123 lines across 6 files. All changes are additive. No existing behavior is modified.

---

## 17. Implementation Phases

### Phase 1: Core Data Structures (no runtime impact)

Create the foundational modules. These have no dependencies on the running system and can be fully unit-tested in isolation.

**Files created**: `src/aps/__init__.py`, `src/aps/partitions.py`, `src/aps/theta.py`, `src/aps/channel.py`, `src/aps/goals.py`, `src/aps/regeneration.py`
**Tests created**: `tests/test_aps_partitions.py`, `tests/test_aps_channel.py`, `tests/test_aps_regeneration.py`
**Dependency added**: numpy in `pyproject.toml`

### Phase 2: Storage Layer

Create the database persistence module and initialize the 3 PostgreSQL tables.

**Files created**: `src/aps/store.py`
**Tables created**: aps_observations, aps_metrics, aps_theta_switches

### Phase 3: Instrumentation (logging + regeneration)

Create the instrumentation wrapper and apply it to all 7 channels. After this phase, every agent invocation logs an APS observation to PostgreSQL, and regeneration protocols activate when theta level > 0.

**Files created**: `src/aps/instrument.py`
**Files modified**: `src/graph.py`, `src/agents/sub_agents.py`, `src/events.py`
**Tests created**: `tests/test_aps_instrument.py`

### Phase 4: APS Controller (the adaptive logic)

Create the controller with rolling failure estimation, confusion matrix computation, capacity calculation, and three-level escalation. Wire it into the scheduler.

**Files created**: `src/aps/controller.py`, `src/aps/scheduler_jobs.py`
**Files modified**: `src/scheduler/autonomous.py`
**Tests created**: `tests/test_aps_controller.py`

### Phase 5: API and Observability

Add the REST endpoints and startup initialization. Wire everything together.

**Files modified**: `src/serve.py`
**Tests created**: `tests/test_aps_integration.py`

### Phase 6: Validation

Run the full test suite (existing + new), start the system, trigger tasks, and verify metrics via the API.

---

## 18. Testing Strategy

### 18.1 Unit Tests

**test_aps_partitions.py** (~120 lines):
- Each of the 14 partition schemes has its classify_input tested with at least 2 known inputs, verifying the output is in the declared sigma_in_alphabet.
- Each classify_output tested with at least 2 known outputs.
- Test that unknown/malformed inputs return a default symbol (never raise).
- Test partition switching: register, get_active, switch, get_active again.
- Test that fine and coarse partitions for the same channel have different alphabet sizes.

**test_aps_channel.py** (~120 lines):
- ConfusionMatrix with known counts: verify conditional_distribution rows sum to 1.
- Mutual information of independent channel (uniform confusion matrix) returns 0.
- Mutual information of deterministic channel (identity matrix) returns H(X).
- Blahut-Arimoto on a binary symmetric channel with known crossover probability p: verify C = 1 - H(p) within tolerance.
- Blahut-Arimoto on a noiseless channel: verify C = log2(|alphabet|).
- Informational efficiency: verify eta = C/W for known values.
- Chain capacity: verify returns minimum of input dict values.

**test_aps_controller.py** (~180 lines):
- Mock observations where p_fail = 0.12 > epsilon_G = 0.05: verify escalation to level 1.
- Mock observations where p_fail = 0.35 > 2 * epsilon_G = 0.10: verify escalation to level 2.
- Mock observations where p_fail = 0.02 < epsilon_G * 0.5 = 0.025 with level 1: verify de-escalation to level 0.
- Mock observations where p_fail = 0.07 (between epsilon_G/2 and epsilon_G): verify NO switch (hysteresis dead zone).
- Test cooldown: trigger an escalation, immediately re-evaluate, verify no second escalation within 60s cooldown.
- Test de-escalation cooldown: verify 300s cooldown between de-escalation steps.
- Test MIN_OBSERVATIONS guard: only 10 observations, p_fail = 0.30, verify no switch.
- Test evaluate_all returns correct structure with channels, goals, switches keys.
- Test that level 2 theta has model_override set and protocol_level = CROSSCHECK.

**test_aps_instrument.py** (~100 lines):
- Wrap a simple function, verify it returns the original result unchanged.
- Verify log_observation is called with correct channel_id and sigma values (mock the store).
- Verify that if classify_input raises, the wrapped function still runs and returns its result.
- Verify that if log_observation raises, the wrapped function still returns its result.
- Verify cost estimation uses correct MODEL_REGISTRY rates.
- Verify that regeneration triggers when theta level > 0 and sigma_out is a failure symbol.
- Verify that regeneration failure doesn't break the wrapper.

**test_aps_regeneration.py** (~80 lines):
- ConfirmProtocol: mock a failing node, verify it retries once with augmented prompt.
- ConfirmProtocol: mock a node that succeeds on retry, verify new sigma_out is non-failure.
- ConfirmProtocol: mock a node that fails on retry too, verify original result returned.
- CrosscheckProtocol: mock a valid result, verify validator passes and sigma_out unchanged.
- CrosscheckProtocol: mock an invalid result, verify sigma_out overridden to "crosscheck_failed".
- Test that validators exist for all channels that have level 2 theta configs.

### 18.2 Integration Tests

**test_aps_integration.py** (~100 lines):
- Build the instrumented graph, invoke with a sample state (mocking LLM calls), verify an observation row appears in the database.
- Run aps_controller.evaluate_all() against mock observations, verify metrics row appears in database.
- Test the /aps/metrics endpoint returns valid JSON with expected fields.
- Test the /aps/evaluate endpoint triggers a cycle and returns summary with theta levels.
- Test the /aps/switch endpoint changes the active theta and returns new level/model/protocol.
- Test that /aps/chain-capacity returns paths with bottleneck identification.

### 18.3 Live Validation Protocol

After deployment, validate with the running system:

1. **Start the system**: `PYTHONUTF8=1 uvicorn src.serve:app --host 0.0.0.0 --port 8050`
2. **Wait for scheduled tasks** or trigger manually: `curl -X POST localhost:8050/scheduler/trigger/order_check`
3. **After 2+ invocations**, trigger evaluation: `curl -X POST localhost:8050/aps/evaluate | python -m json.tool`
4. **Check per-channel metrics**: `curl localhost:8050/aps/metrics | python -m json.tool`
   - Verify: p_fail, mutual_info, capacity, eta are all numeric and non-null
   - Verify: n_observations matches expected invocation count
   - Verify: level, model_override, protocol_level fields present
5. **Check chain capacity**: `curl localhost:8050/aps/chain-capacity | python -m json.tool`
   - Verify: bottleneck channel is identified per path
   - Verify: chain_capacity <= min(per_channel capacities)
6. **Check theta state**: `curl localhost:8050/aps/partitions | python -m json.tool`
   - Verify: all 7 channels listed with level, model_override, protocol_level
7. **Test manual escalation**: `curl -X POST localhost:8050/aps/switch/K3/theta_K3_critical`
   - Verify: next invocation shows crosscheck protocol active
   - Verify: observation includes regeneration cost in cost_usd
8. **Test manual de-escalation**: `curl -X POST localhost:8050/aps/switch/K3/theta_K3_nominal`
   - Verify: next invocation runs with passive protocol
9. **Accumulate 24 hours of data**, then query for theta switch events and verify:
   - Theorem 1 holds on empirical data
   - Regeneration increases W but may also increase C(P)
   - eta changes are measurable across theta levels

---

## 19. Paper Predictions Under Test

| Prediction | What We Measure | Expected Outcome | How We Verify |
|------------|----------------|-------------------|---------------|
| P1: Rate ceiling | Channel capacity C(P) per interface | Finite, measurable capacity values that constrain throughput | /aps/metrics shows C(P) > 0 and < log2(\|Sigma\|) |
| P3: Noise collapses alphabets | p_fail and active theta over time | When API errors spike, K7 escalates to coarse partition | aps_theta_switches shows escalation correlated with elevated p_fail |
| P5: Medium reshapes partitions | Active theta under different conditions | Different channels stabilize on different levels based on their noise profiles | /aps/partitions shows heterogeneous levels across channels |
| P7: Epsilon-triggered switching | Theta switch events in audit log | Discrete transitions between levels, with hysteresis | aps_theta_switches shows direction, trigger_p_fail, level changes |
| Theorem 1: Composition bound | Chain capacity vs per-channel capacities | C(P_chain) <= min_k C(P_k) holds empirically | /aps/chain-capacity shows chain_capacity <= min(per_channel) |
| Section 4: Regeneration | eta at different protocol levels | Active regeneration (confirm/crosscheck) increases W but may restore C(P), changing eta | Compare eta across level 0, 1, 2 for same channel over time |
| eta comparison | Informational efficiency across channels | Expensive models (K4: Opus) have lower eta; free models (K1: Ollama) have higher eta | /aps/metrics shows eta inversely correlated with model cost |

---

## 20. Dependencies

**New dependency**: `numpy>=1.24.0,<3.0.0` (for confusion matrix operations, Blahut-Arimoto)

**Existing dependencies leveraged** (no new installs):
- `psycopg` (via langgraph-checkpoint-postgres) — PostgreSQL access
- `apscheduler` — scheduler integration
- `fastapi` — API endpoints
- `langchain-core` — callback handler extension

---

## 21. Key Design Decisions and Rationale

**1. Wrapper pattern over agent modification.**
Agent code remains untouched. APS is a purely additive instrumentation layer. If APS fails at any point (classification error, database down, numpy exception), the original agent function still executes and returns its result. This is critical for a live production system.

**2. PostgreSQL over Redis for APS storage.**
APS needs time-range queries with aggregation (GROUP BY channel_id, COUNT, window functions). PostgreSQL supports this natively. Redis is optimized for key-value access patterns and would require application-level aggregation.

**3. Blahut-Arimoto for channel capacity, not just mutual information.**
The paper's theory requires C(P) = max_{p(x)} I(X;Y), not just the empirical mutual information under the observed input distribution. Blahut-Arimoto is the standard algorithm, converges quickly for our small alphabets.

**4. Theta as a tuple, not just a partition (v2).**
The alternative correctly identified that partition granularity is only one control knob. Model selection and protocol level are equally important. Bundling them into a single theta config gives the controller a richer action space.

**5. Three-level escalation (nominal/degraded/critical) (v2).**
More nuanced than binary fine/coarse. Allows proportional response — light noise gets coarsening + retry, severe noise gets model escalation + crosscheck.

**6. Regeneration as a first-class concept (v2).**
The paper's Section 4 (passive vs active regeneration) was missing from v1. The confirm and crosscheck protocols make it concrete and measurable.

**7. Mission-critical goal tier (v2).**
Hard floors that block actions rather than just switching partitions. Policy violations and negative margins are not noise to adapt to — they're failures to prevent.

**8. Model override as signal first, actuator later (v2).**
We record what model APS would choose, but don't force-swap models in v2. This gives us data to validate the routing logic before wiring it in. The actuator is a roadmap item.

**9. Asymmetric hysteresis cooldowns (60s escalate, 300s de-escalate).**
Escalation is a protective response — respond quickly. De-escalation is opportunistic — wait for stable improvement.

**10. 20-observation minimum before switching.**
Statistical significance requires sufficient data. With fewer than 20 observations, the failure rate estimate has standard error > 0.11, making it unreliable for decisions against tolerances in the 0.05-0.15 range.

**11. Five-minute evaluation interval.**
The system generates ~2 invocations per hour on the scheduler. 5-minute cycles ensure fresh metrics without excessive database load.

---

## 22. Roadmap: What Comes After v2

These are valid ideas from the alternative architecture that require more infrastructure than currently exists. They are prioritized by value and feasibility:

### Near-term (after v2 validates)

1. **Dynamic model routing actuator** — Wire model_override into the agent builders so APS can actually swap models at runtime. Requires passing model selection through LangGraph state or refactoring agent builders to accept model as a parameter. This is the single highest-leverage follow-up.

2. **Shared context K as compression engine** — Formalize ChromaDB collections + schemas as the shared prior K. Measure H(I|K) vs H(I) to quantify the compression benefit of shared context. This validates prediction P4 (shared priors reduce required channel rate).

3. **Governance gate** — Dedicated pre-execution validator for high-risk actions (currently approximated by Tier 1 mission-critical goals). Could evolve into a dedicated agent.

### Medium-term

4. **Extended channels K8-K12** — Add Merchandising, Pricing, Customer Support, Governance, and Experimentation agents. Each new agent adds a new instrumented channel to the APS system.

5. **Staging/canary infrastructure** — Set up a staging Shopify store. Test listing changes, price changes, and campaign launches in staging before production. This is the "dry-run" regeneration pattern from the alternative.

6. **Majority vote regeneration** — For high-risk decisions, run the same task through 2-3 models and take consensus. Expensive but demonstrably higher reliability.

### Long-term

7. **ChangeSet pattern** — Structure all agent outputs as versioned diffs with rollback capability. Enables "Commerce CI/CD" with automated testing and deployment pipelines.

8. **Reasoning-native executive** — Replace the keyword-based orchestrator with a planning agent that emits multi-step workflows with explicit budgets and constraints.

9. **Full CommerceOS** — The complete vision from the alternative: 7+ department agents, staging/canary, ChangeSet CI/CD, governance gates, and APS controlling the entire autonomy stack.
