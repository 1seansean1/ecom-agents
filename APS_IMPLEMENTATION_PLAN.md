# Adaptive Partition Selection (APS) Implementation Plan

## Implementing Informational Monism's Core Experimental Protocol in a Live Agentic System

**Author**: Sean P. Allen
**Date**: February 6, 2026
**Target System**: ecom-agents (live at localhost:8050)
**Status**: Draft — Pre-Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Theoretical Foundation](#2-theoretical-foundation)
   - 2.1 [The Induced Macro-Channel](#21-the-induced-macro-channel)
   - 2.2 [Informational Efficiency](#22-informational-efficiency)
   - 2.3 [The Composition Bound (Theorem 1)](#23-the-composition-bound-theorem-1)
   - 2.4 [Epsilon-Triggered Partition Switching](#24-epsilon-triggered-partition-switching)
3. [System Under Test: ecom-agents](#3-system-under-test-ecom-agents)
   - 3.1 [Architecture Overview](#31-architecture-overview)
   - 3.2 [Agent Inventory and Models](#32-agent-inventory-and-models)
   - 3.3 [Existing Infrastructure We Build On](#33-existing-infrastructure-we-build-on)
   - 3.4 [Message Flow and State Schema](#34-message-flow-and-state-schema)
4. [Channel Identification: 7 Induced Macro-Channels](#4-channel-identification-7-induced-macro-channels)
   - 4.1 [K1: Orchestrator Routing Channel](#41-k1-orchestrator-routing-channel)
   - 4.2 [K2: Sales & Marketing Execution Channel](#42-k2-sales--marketing-execution-channel)
   - 4.3 [K3: Operations Execution Channel](#43-k3-operations-execution-channel)
   - 4.4 [K4: Revenue Analytics Execution Channel](#44-k4-revenue-analytics-execution-channel)
   - 4.5 [K5: Content Writer Sub-Agent Channel](#45-k5-content-writer-sub-agent-channel)
   - 4.6 [K6: Campaign Analyzer Sub-Agent Channel](#46-k6-campaign-analyzer-sub-agent-channel)
   - 4.7 [K7: Tool Call Channel](#47-k7-tool-call-channel)
5. [Partition Definitions: Fine and Coarse Schemes](#5-partition-definitions-fine-and-coarse-schemes)
   - 5.1 [Design Principles](#51-design-principles)
   - 5.2 [Complete Partition Table](#52-complete-partition-table)
   - 5.3 [Classification Functions](#53-classification-functions)
6. [Goal Specifications](#6-goal-specifications)
   - 6.1 [Goal Data Structure: G = (F_G, epsilon_G, T)](#61-goal-data-structure)
   - 6.2 [Six Concrete Goals](#62-six-concrete-goals)
7. [Information-Theoretic Computations](#7-information-theoretic-computations)
   - 7.1 [Confusion Matrix Construction](#71-confusion-matrix-construction)
   - 7.2 [Mutual Information](#72-mutual-information)
   - 7.3 [Channel Capacity via Blahut-Arimoto](#73-channel-capacity-via-blahut-arimoto)
   - 7.4 [Informational Efficiency eta](#74-informational-efficiency-eta)
   - 7.5 [Chain Capacity and Bottleneck Identification](#75-chain-capacity-and-bottleneck-identification)
8. [APS Controller Design](#8-aps-controller-design)
   - 8.1 [Rolling Failure Estimation](#81-rolling-failure-estimation)
   - 8.2 [Switch Decision Logic with Hysteresis](#82-switch-decision-logic-with-hysteresis)
   - 8.3 [Evaluation Cycle](#83-evaluation-cycle)
   - 8.4 [W_total Accounting](#84-w_total-accounting)
9. [Instrumentation Strategy](#9-instrumentation-strategy)
   - 9.1 [The Wrapper Pattern](#91-the-wrapper-pattern)
   - 9.2 [Node-Level Instrumentation](#92-node-level-instrumentation)
   - 9.3 [Tool-Call Instrumentation](#93-tool-call-instrumentation)
   - 9.4 [Error Safety](#94-error-safety)
10. [Database Schema](#10-database-schema)
    - 10.1 [Table: aps_observations](#101-table-aps_observations)
    - 10.2 [Table: aps_metrics](#102-table-aps_metrics)
    - 10.3 [Table: aps_partition_switches](#103-table-aps_partition_switches)
11. [API Endpoints and WebSocket Events](#11-api-endpoints-and-websocket-events)
    - 11.1 [REST Endpoints](#111-rest-endpoints)
    - 11.2 [WebSocket Event Types](#112-websocket-event-types)
12. [New File Structure](#12-new-file-structure)
13. [Modifications to Existing Files](#13-modifications-to-existing-files)
14. [Implementation Phases](#14-implementation-phases)
15. [Testing Strategy](#15-testing-strategy)
    - 15.1 [Unit Tests](#151-unit-tests)
    - 15.2 [Integration Tests](#152-integration-tests)
    - 15.3 [Live Validation Protocol](#153-live-validation-protocol)
16. [Paper Predictions Under Test](#16-paper-predictions-under-test)
17. [Dependencies](#17-dependencies)
18. [Key Design Decisions and Rationale](#18-key-design-decisions-and-rationale)

---

## 1. Executive Summary

### Purpose

This document specifies the implementation of an **Adaptive Partition Selection (APS)** system for the ecom-agents multi-agent e-commerce platform. The APS system is the first live experimental instantiation of the theoretical framework described in the paper *"Informational Monism: Computation, Communication, and Conduction as Unified Phenomena"* (Allen, 2026).

### What We Are Building

The paper argues that every interface between communicating agents can be modeled as an **induced macro-channel** — a stochastic map from input symbols to output symbols, where "symbols" are defined by coarse-graining (partitioning) the high-dimensional state space at each boundary. The paper further proposes that when goal failure rates exceed a tolerance threshold, systems should adaptively switch between finer and coarser partition schemes to maintain recoverability.

We are building an instrumentation and control layer that:

1. **Identifies and instruments 7 agent-to-agent interfaces** as induced macro-channels (K1 through K7), covering the orchestrator, all three specialist agents, two sub-agents, and all external tool calls.

2. **Defines 14 partition schemes** (2 per channel: fine and coarse), each with explicit symbol alphabets and deterministic classification functions that map the high-dimensional AgentState into discrete symbols.

3. **Logs every interface crossing** as a (sigma_in, sigma_out) observation tuple, with timestamps, latency, and cost metadata, into PostgreSQL.

4. **Computes information-theoretic metrics** in real time: empirical confusion matrices P_hat(sigma_out | sigma_in), mutual information I(X;Y), channel capacity C(P) via the Blahut-Arimoto algorithm, and informational efficiency eta = C(P) / W.

5. **Validates the composition bound** (Theorem 1: C(P_chain) <= min_k C(P_k)) across the full agent chain, identifying the bottleneck channel.

6. **Implements an APS controller** that monitors rolling goal-failure rates p_hat_fail(t) against 6 business goals, and triggers partition coarsening when p_fail > epsilon_G or refinement when conditions improve — with hysteresis to prevent oscillation.

7. **Exposes all metrics** via REST API endpoints and WebSocket events for observation and analysis.

### What This Validates

When running live, this system directly tests the following predictions from the paper:

- **P1 (Rate ceiling)**: Agent interfaces have measurable channel capacities that constrain information throughput.
- **P3 (Noise collapses alphabets)**: Under degraded conditions (API failures, model errors), the effective stable symbol set shrinks — the APS controller responds by switching to coarser partitions.
- **P5 (Medium constraints reshape partitions)**: Different operational conditions favor different partition granularities.
- **P7 (Epsilon-triggered switching)**: When goal failure exceeds tolerance, discrete partition transitions occur, and when conditions improve, richer alphabets return.
- **Theorem 1 (Composition bound)**: The end-to-end chain capacity is bounded by the weakest link.

### Why This Matters

If the APS system behaves as predicted — if confusion matrices are measurable, if mutual information and channel capacity are nonzero and meaningful, if the composition bound holds empirically, and if epsilon-triggered switching demonstrably maintains recoverability — then we have a live demonstration that the informational monism framework applies to software agent systems, not just physical substrates. This is the paper's Appendix A protocol, instrumented and running.

---

## 2. Theoretical Foundation

### 2.1 The Induced Macro-Channel

The paper's central construction: given a system with microstate space X that evolves under dynamics K_T with control u, and given an input partition pi_in: X -> Sigma_in and an output partition pi_out: X -> Sigma_out, the microdynamics induce a stochastic channel on symbols:

```
P(sigma_out | sigma_in, u) = integral mu(dx_i | sigma_in) integral_{pi_out^{-1}(sigma_out)} K_T(dx_out | x_i, u)
```

In our system:
- **X** (microstate space) = the full AgentState dictionary — messages, task_type, trigger_payload, all result fields, memory_context, error state, etc. This is a high-dimensional, mixed-type space.
- **K_T** (dynamics) = the LLM inference + tool execution within each agent node. The stochasticity comes from LLM sampling, API response variability, and timing.
- **pi_in, pi_out** (partitions) = our classification functions that map AgentState fields to discrete symbols.
- **u** (control) = the system prompts, model selection, temperature settings, and tool configurations.

The induced macro-channel P(sigma_out | sigma_in, u) is empirically estimated as a confusion matrix from logged observations.

### 2.2 Informational Efficiency

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

### 2.3 The Composition Bound (Theorem 1)

For a chain of n compatible links, the composed macro-channel capacity satisfies:

```
C(P_chain) <= min_k C(P_k)
```

This follows from the data processing inequality. In ecom-agents, the chain is:

```
Orchestrator (K1) -> Specialist Agent (K2/K3/K4) -> [Sub-agents (K5,K6)] -> Tool Calls (K7)
```

The APS system computes per-channel capacities and identifies which channel is the bottleneck. This is a directly falsifiable prediction: the end-to-end measured capacity should not exceed the minimum per-link capacity.

### 2.4 Epsilon-Triggered Partition Switching

The APS controller implements the paper's Section 9.3 mechanism:

1. Maintain a rolling estimate of goal failure: p_hat_fail(t) = (failures in window T) / (total observations in window T)
2. When p_hat_fail(t) > epsilon_G: the effective symbol set has degraded. Switch to a coarser partition (fewer, more separated macrostates) to preserve recoverability.
3. When p_hat_fail(t) < epsilon_G * 0.5 (hysteresis factor): conditions have improved. Switch to a finer partition (more symbols, higher information throughput).
4. W_total = W_operate + W_search: the cost of adaptation is charged against the total work budget.

---

## 3. System Under Test: ecom-agents

### 3.1 Architecture Overview

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

### 3.2 Agent Inventory and Models

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

### 3.3 Existing Infrastructure We Build On

The following existing subsystems are directly leveraged by the APS implementation:

**EventBroadcaster** (`src/events.py`): Singleton that broadcasts structured JSON events to all connected WebSocket clients. The APS system adds three new event types (`aps_observation`, `aps_evaluation`, `aps_partition_switch`) through this existing mechanism.

**ForgeEventCallbackHandler** (`src/events.py`): LangChain callback handler that already hooks into `on_chain_start`, `on_chain_end`, `on_tool_start`, `on_tool_end`, `on_llm_start`, `on_llm_end`. We extend `on_tool_start`/`on_tool_end` to log K7 (tool call) observations.

**Circuit Breaker** (`src/resilience/circuit_breaker.py`): Per-service circuit breakers with CLOSED -> OPEN -> HALF_OPEN state machine. The APS controller mirrors this pattern conceptually (threshold-triggered state transitions with cooldowns) but operates on information-theoretic metrics rather than binary failure counts.

**MODEL_REGISTRY** (`src/llm/config.py`): Contains per-model cost rates (input_cost_per_1k, output_cost_per_1k). Used by the APS instrumentation layer to estimate W (resource cost) per invocation without needing to correlate individual token counts.

**APScheduler** (`src/scheduler/autonomous.py`): Background scheduler with 6 existing jobs. We add a 7th job (`aps_evaluation`) that runs the APS controller every 5 minutes.

**PostgreSQL** (port 5434): Already running for LangGraph checkpoint storage. We add 3 new tables for APS data.

**Redis** (port 6381): Used for medium-term session memory. Not used by APS (we need SQL aggregation queries that Redis doesn't support well).

### 3.4 Message Flow and State Schema

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

## 4. Channel Identification: 7 Induced Macro-Channels

Each channel represents an agent interface where a high-dimensional input state is processed and produces an output. The "microstate" at each boundary is a subset of AgentState fields; the partition maps these to discrete symbols.

### 4.1 K1: Orchestrator Routing Channel

**What it does**: The orchestrator receives a task description (from scheduler or API) and classifies it into a task_type and route_to destination.

**Physical analogy**: This is the "encoder" of the system — it takes a raw signal (natural language task description) and produces a discrete symbol (routing decision) that determines the downstream path.

**Microstate (X)**: The full text of `messages[-1].content` plus `trigger_payload`.

**Input partition (pi_in)**: Classifies the raw task description into a task category based on keyword features.

**Output partition (pi_out)**: The orchestrator's actual (task_type, route_to) classification.

**Why it matters**: Misclassification here propagates errors through the entire chain. If the orchestrator routes an order-check task to the sales agent, the downstream confusion matrix will show it as noise.

### 4.2 K2: Sales & Marketing Execution Channel

**What it does**: The sales agent receives a classified sales task and produces content (Instagram post, campaign plan, or product launch materials).

**Microstate (X)**: task_type + task_complexity + trigger_payload + messages.

**Input partition**: What kind of sales task was requested and whether it requires sub-agent delegation.

**Output partition**: The quality/structure of the sales_result — whether it produced valid structured output, raw text, delegated to sub-agents, or errored.

### 4.3 K3: Operations Execution Channel

**What it does**: The operations agent handles order checks, inventory syncs, and fulfillment via Shopify and Printful APIs.

**Microstate (X)**: task_type + trigger_payload + available tool state.

**Input partition**: What operational action was requested.

**Output partition**: Whether the action completed successfully, requires follow-up, errored, or produced malformed output.

**Why it matters**: This is the most frequently invoked channel (order_check runs every 30 minutes), so it accumulates observations fastest and will be the first to produce statistically meaningful confusion matrices.

### 4.4 K4: Revenue Analytics Execution Channel

**What it does**: The revenue agent (Claude Opus 4.6) analyzes financial data from Stripe and produces reports with recommendations.

**Microstate (X)**: task_type + memory_context + Stripe data.

**Input partition**: Type of analysis requested.

**Output partition**: Report type combined with confidence level and whether actionable recommendations were produced.

**Why it matters**: This is the most expensive channel ($15+$75 per 1K tokens). The eta metric here will be low in absolute terms, making it a natural target for efficiency optimization.

### 4.5 K5: Content Writer Sub-Agent Channel

**What it does**: Generates Instagram post captions and content as part of the campaign sub-agent pipeline.

**Microstate (X)**: Campaign brief from parent agent.

**Input partition**: Type of brief (campaign vs. product).

**Output partition**: Quality of the generated content — whether it produced parseable JSON with a valid caption.

### 4.6 K6: Campaign Analyzer Sub-Agent Channel

**What it does**: The campaign analyzer (Claude Opus 4.6) evaluates all sub-agent outputs and predicts engagement.

**Microstate (X)**: Aggregated results from content_writer, image_selector, and hashtag_optimizer.

**Input partition**: Completeness of upstream sub-agent results.

**Output partition**: Engagement prediction level or analysis failure.

### 4.7 K7: Tool Call Channel

**What it does**: All external API calls — Shopify, Stripe, Printful, Instagram.

**Microstate (X)**: Tool name + arguments + API state.

**Input partition**: Which tool was invoked (fine: 13 individual tools, coarse: 4 service groups).

**Output partition**: Success/failure categorization of the API response.

**Why it matters**: Tool calls are the system's interface with the external world. API failures, rate limits, and auth errors are the primary source of noise in the system. The circuit breaker already tracks this at the service level; APS adds information-theoretic measurement.

---

## 5. Partition Definitions: Fine and Coarse Schemes

### 5.1 Design Principles

Each channel gets exactly two partition schemes:

1. **Fine partition**: More symbols, higher resolution, more sensitive to noise. Used when the system is operating well and we want maximum information throughput.

2. **Coarse partition**: Fewer symbols, wider separation between macrostates, more robust to noise. Used when error rates are elevated and we need to maintain recoverability at the cost of resolution.

The APS controller switches between these based on measured goal failure rates.

All classification functions are **pure, deterministic functions** of AgentState fields. They inspect only the observable interface state (satisfying the paper's admissibility constraint C1: interface-boundedness). They do not require access to internal LLM activations or other microscopic degrees of freedom.

The classification functions are also **counterfactually robust** (constraint C2): different inputs would produce different classifications under the same mapping, and these differences are achievable via the system's normal control interface (different task descriptions, different API states).

### 5.2 Complete Partition Table

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

### 5.3 Classification Functions

Each classification function is a pure function that inspects specific AgentState fields and returns a symbol string. Here is the logic for each channel:

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

## 6. Goal Specifications

### 6.1 Goal Data Structure

Each goal follows the paper's specification G = (F_G, epsilon_G, T):

- **F_G** (failure event): A boolean function that takes a single observation dict and returns True if it represents a failure.
- **epsilon_G** (tolerance): The maximum acceptable failure probability. When p_hat_fail > epsilon_G, the APS controller considers intervention.
- **T** (evaluation window): The time window in seconds over which p_hat_fail is computed as a rolling average.
- **channels**: Which channels this goal applies to.

### 6.2 Six Concrete Goals

**Goal 1: Routing Accuracy (K1)**
- F_G: The orchestrator routed to error_handler, or the task triggered a retry (retry_count > 0).
- epsilon_G: 0.10 (10% misrouting tolerance)
- T: 3600 seconds (1 hour)
- Rationale: The orchestrator uses a small local model (Qwen 3B). Misclassification is the primary risk. 10% tolerance allows for occasional ambiguous tasks.

**Goal 2: Task Completion (K2, K3, K4)**
- F_G: The output sigma_out is in {error, malformed_response, failure} — the agent failed to produce a usable result.
- epsilon_G: 0.05 (5% failure tolerance)
- T: 7200 seconds (2 hours)
- Rationale: Specialist agents use capable models (GPT-4o, GPT-4o-mini, Opus 4.6). Failure rates should be very low. 5% catches systemic issues while tolerating occasional hiccups.

**Goal 3: Tool Reliability (K7)**
- F_G: The tool call sigma_out is in {http_error, timeout, auth_error, rate_limited} — the external API call failed.
- epsilon_G: 0.15 (15% tool failure tolerance)
- T: 1800 seconds (30 minutes)
- Rationale: External APIs are inherently less reliable than LLM calls. Rate limits, network issues, and transient errors are expected. 15% tolerance with a short window catches sustained outages.

**Goal 4: Campaign Quality (K5, K6)**
- F_G: Sub-agent output sigma_out is in {unusable, analysis_failed, error} — the campaign pipeline produced unusable content.
- epsilon_G: 0.10 (10% quality tolerance)
- T: 86400 seconds (24 hours)
- Rationale: Campaigns run infrequently (2x daily for Instagram, 1x weekly for full campaigns). A 24-hour window accumulates enough observations for meaningful statistics.

**Goal 5: Response Latency (K1, K2, K3, K4)**
- F_G: latency_ms > 30000 — the agent took more than 30 seconds to respond.
- epsilon_G: 0.05 (5% latency tolerance)
- T: 3600 seconds (1 hour)
- Rationale: Slow responses indicate model overload, API timeouts, or resource contention. The 30-second threshold is generous; most operations should complete in under 15 seconds.

**Goal 6: Cost Efficiency (K2, K4, K6)**
- F_G: cost_usd > 0.50 — a single invocation cost more than $0.50.
- epsilon_G: 0.10 (10% cost tolerance)
- T: 3600 seconds (1 hour)
- Rationale: Only applies to channels using expensive models (GPT-4o and Opus 4.6). The $0.50 threshold flags unusually expensive runs (e.g., very long conversations, excessive tool calls).

---

## 7. Information-Theoretic Computations

### 7.1 Confusion Matrix Construction

Given a set of observations {(sigma_in_i, sigma_out_i)} for a channel with partition theta, construct the confusion matrix:

```
counts[i][j] = number of observations where sigma_in = alphabet_in[i] AND sigma_out = alphabet_out[j]
```

The row-normalized form gives the empirical conditional distribution:

```
P_hat(sigma_out | sigma_in) = counts[i][j] / sum_j(counts[i][j])
```

Rows with zero observations get a uniform distribution (maximum entropy prior).

### 7.2 Mutual Information

Computed from the empirical joint distribution:

```
I(X;Y) = sum_{x,y} p(x,y) * log2(p(x,y) / (p(x) * p(y)))
```

With the convention 0 * log(0) = 0.

Properties:
- I(X;Y) = 0 when input and output are statistically independent (no information transmitted).
- I(X;Y) = H(X) when the channel is deterministic (perfect information transmission).
- 0 <= I(X;Y) <= min(H(X), H(Y)).

For our system, I(X;Y) measures how many bits of the input classification are recoverable from the output. A well-functioning agent should have high mutual information (most of the input information survives processing).

### 7.3 Channel Capacity via Blahut-Arimoto

The Shannon channel capacity is:

```
C(P) = max_{p(x)} I(X;Y)
```

The maximum is over all possible input distributions. We compute this using the Blahut-Arimoto algorithm, which iteratively alternates between optimizing the input distribution and computing the resulting mutual information. The algorithm converges geometrically for finite alphabets.

For our small alphabets (max 13 symbols for K7 fine), Blahut-Arimoto converges in under 100 iterations with tolerance 1e-6.

**Why capacity and not just mutual information?** The empirical mutual information depends on the input distribution (which tasks the scheduler happens to generate). Capacity is the maximum over all input distributions, giving a substrate property — the inherent information-carrying capability of the channel regardless of how it's being used. This is the paper's C(P).

### 7.4 Informational Efficiency eta

```
eta = C(P) / W
```

Where W is the total cost in USD accumulated over the evaluation window. Units: bits per dollar.

When W is very small (e.g., the orchestrator uses free Ollama), eta approaches infinity. In these cases, we report eta as "uncapped" and focus on the absolute capacity value.

We also compute:
- **eta_token** = C(P) / W_tokens (bits per token) — useful for comparing models
- **eta_time** = C(P) / T_seconds (bits per second) — useful for latency analysis

### 7.5 Chain Capacity and Bottleneck Identification

For each directed path through the agent graph, compute:

```
C(P_chain) <= min_k C(P_k)
```

The three primary paths are:
1. K1 -> K2 -> K5 -> K6 (orchestrator -> sales -> content_writer -> campaign_analyzer)
2. K1 -> K3 -> K7 (orchestrator -> operations -> tool calls)
3. K1 -> K4 -> K7 (orchestrator -> revenue -> tool calls)

The bottleneck channel is the one with minimum capacity on each path. This is directly reported via the `/aps/chain-capacity` endpoint.

---

## 8. APS Controller Design

### 8.1 Rolling Failure Estimation

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

### 8.2 Switch Decision Logic with Hysteresis

The controller uses asymmetric cooldowns to prevent oscillation:

```
IF p_fail > epsilon_G
   AND current partition is FINE
   AND time since last switch > COARSEN_COOLDOWN (60 seconds)
   AND observation count >= MIN_OBSERVATIONS (20)
THEN:
   Switch to COARSE partition
   Record: direction = "coarsened"

IF p_fail < epsilon_G * 0.5   (hysteresis factor)
   AND current partition is COARSE
   AND time since last switch > REFINE_COOLDOWN (300 seconds)
   AND observation count >= MIN_OBSERVATIONS (20)
THEN:
   Switch to FINE partition
   Record: direction = "refined"
```

**Why asymmetric cooldowns?** Coarsening is a safety mechanism — when things are going wrong, we want to respond quickly (60s). Refinement is an optimization — when things are going well, we can afford to wait (300s) and be confident the improvement is sustained.

**Why MIN_OBSERVATIONS = 20?** With fewer observations, the failure rate estimate has high variance. 20 observations gives a standard error of ~0.11 for a true rate of 0.5, sufficient to distinguish signal from noise at our tolerance levels.

**The hysteresis factor (0.5)** prevents cycling: coarsening triggers at epsilon_G but refinement requires p_fail to drop to epsilon_G/2. This creates a dead zone where the current partition is maintained.

### 8.3 Evaluation Cycle

The APSController.evaluate_all() method runs every 5 minutes:

1. For each goal in GOALS:
   a. For each channel in goal.channels:
      - Query recent observations within window T
      - Compute p_fail
      - Build confusion matrix
      - Compute mutual information, channel capacity, eta
      - Store metrics in aps_metrics table
      - Evaluate switch decision
   b. Aggregate goal-level p_fail across all channels
2. Broadcast `aps_evaluation` event via WebSocket
3. Return summary dict with all metrics, goal statuses, and any switches triggered

### 8.4 W_total Accounting

The paper specifies W_total = W_operate + W_search:

**W_operate**: The LLM inference cost per invocation. Estimated from MODEL_REGISTRY:
- Each agent uses a known model (orchestrator = OLLAMA_QWEN at $0, sales = GPT4O at $2.50/$10.00, etc.)
- We estimate tokens from message length (rough: 1 token per 4 characters for input, use average output length per agent from historical data)
- Cost = (input_tokens / 1000) * input_cost + (output_tokens / 1000) * output_cost

**W_search**: The overhead of APS itself — database queries, Blahut-Arimoto computation, partition switching logic. This is negligible compared to LLM costs (microseconds of CPU vs. seconds of API calls and dollars of tokens), but we log the APS evaluation wall-clock time for completeness.

---

## 9. Instrumentation Strategy

### 9.1 The Wrapper Pattern

The core design principle is **zero modification to existing agent code**. All instrumentation is applied by wrapping the agent node functions at graph construction time. If the APS system crashes, the original node function still executes normally.

```python
def instrument_node(channel_id: str, model_id: ModelID, node_fn: Callable) -> Callable:
    """Transparent wrapper that logs APS observations around node execution."""
    def wrapped(state: dict) -> dict:
        partition = get_active_partition(channel_id)
        sigma_in = partition.classify_input(state)

        t0 = time.time()
        result = node_fn(state)  # Original function runs unchanged
        latency_ms = (time.time() - t0) * 1000

        sigma_out = partition.classify_output(result)
        cost = estimate_cost(model_id, state, result)

        log_observation(channel_id, partition.theta_id, sigma_in, sigma_out,
                       time.time(), latency_ms, cost)

        return result  # Original result returned unchanged
    return wrapped
```

### 9.2 Node-Level Instrumentation

Applied in `src/graph.py` where nodes are registered:

```python
# Before (existing code, lines 88-91):
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

### 9.3 Tool-Call Instrumentation

Tool calls (K7) are instrumented via the existing ForgeEventCallbackHandler in `src/events.py`. We add tracking dicts for tool start times and names, then log observations in `on_tool_end`:

```python
# In on_tool_start: record start time and tool name
self._aps_tool_starts[str(run_id)] = (time.time(), serialized.get("name", "unknown"))

# In on_tool_end: compute latency, classify, log
start_time, tool_name = self._aps_tool_starts.pop(str(run_id), (time.time(), "unknown"))
latency_ms = (time.time() - start_time) * 1000
sigma_in = classify_tool_input(tool_name)
sigma_out = classify_tool_output(output)
log_observation("K7", ..., sigma_in, sigma_out, latency_ms=latency_ms)
```

### 9.4 Error Safety

The instrumentation wrapper must never break the agent. All APS operations are wrapped in try/except:

```python
def wrapped(state: dict) -> dict:
    try:
        partition = get_active_partition(channel_id)
        sigma_in = partition.classify_input(state)
    except Exception:
        sigma_in = "unknown"

    result = node_fn(state)  # This ALWAYS runs, even if APS fails

    try:
        sigma_out = partition.classify_output(result)
        log_observation(...)
    except Exception:
        logger.warning("APS instrumentation failed for %s", channel_id, exc_info=True)

    return result
```

---

## 10. Database Schema

### 10.1 Table: aps_observations

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

Expected volume: ~50 observations/day at current scheduler rates (order_check every 30 min + Instagram 2x/day + revenue daily + weekly campaign). Low storage burden.

### 10.2 Table: aps_metrics

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

Expected volume: 7 channels * 288 evaluations/day (every 5 min) = ~2000 rows/day. Can add retention policy later if needed.

### 10.3 Table: aps_partition_switches

Audit log of every partition switch. Essential for validating prediction P7 (epsilon-triggered switching).

```sql
CREATE TABLE IF NOT EXISTS aps_partition_switches (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      VARCHAR(16) NOT NULL,
    from_theta      VARCHAR(64) NOT NULL,
    to_theta        VARCHAR(64) NOT NULL,
    direction       VARCHAR(16) NOT NULL,
    trigger_p_fail  REAL NOT NULL,
    trigger_epsilon REAL NOT NULL,
    goal_id         VARCHAR(64) NOT NULL,
    switched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_aps_switches_channel ON aps_partition_switches (channel_id, switched_at DESC);
```

Expected volume: very low — switches should be infrequent (the system is generally stable).

---

## 11. API Endpoints and WebSocket Events

### 11.1 REST Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | /aps/metrics | Latest metrics for all 7 channels | `{metrics: [{channel_id, theta_id, p_fail, mutual_info, capacity, eta, n_observations, ...}]}` |
| GET | /aps/metrics/{channel_id} | Metric history for one channel | `{channel_id, metrics: [...]}` |
| GET | /aps/partitions | Current partition state | `{partitions: {K1: {channel_name, active_theta, available_schemes}, ...}}` |
| POST | /aps/switch/{channel_id}/{theta_id} | Manual partition switch | `{status: "switched", channel_id, theta_id}` |
| GET | /aps/chain-capacity | Bottleneck analysis | `{chain_capacity, per_channel: {K1: 1.42, ...}, bottleneck: "K3"}` |
| POST | /aps/evaluate | Trigger immediate evaluation cycle | Full evaluation summary with metrics, goals, switches |

### 11.2 WebSocket Event Types

All events broadcast through the existing `ws://localhost:8050/ws/events` endpoint:

**aps_observation** (every node invocation):
```json
{
    "type": "aps_observation",
    "channel_id": "K3",
    "theta_id": "theta_K3_fine",
    "sigma_in": "order_check",
    "sigma_out": "completed",
    "latency_ms": 4521.3,
    "cost_usd": 0.012,
    "timestamp": 1738857600.0
}
```

**aps_evaluation** (every 5 minutes):
```json
{
    "type": "aps_evaluation",
    "timestamp": 1738857600.0,
    "channels": {
        "K1": {"p_fail": 0.03, "mutual_information_bits": 1.42, "channel_capacity_bits": 1.58, "eta_bits_per_usd": "inf", "n_observations": 48, "active_partition": "theta_K1_fine"},
        "K3": {"p_fail": 0.08, "mutual_information_bits": 1.12, "channel_capacity_bits": 1.35, "eta_bits_per_usd": 112.5, "n_observations": 48, "active_partition": "theta_K3_fine"}
    },
    "goals": {
        "routing_accuracy": {"p_fail": 0.03, "epsilon_G": 0.10, "violated": false},
        "task_completion": {"p_fail": 0.08, "epsilon_G": 0.05, "violated": true}
    },
    "switches": [
        {"channel_id": "K3", "from_theta": "theta_K3_fine", "to_theta": "theta_K3_coarse", "direction": "coarsened", "trigger_p_fail": 0.08, "goal_id": "task_completion"}
    ]
}
```

**aps_partition_switch** (when a partition changes):
```json
{
    "type": "aps_partition_switch",
    "channel_id": "K3",
    "from_theta": "theta_K3_fine",
    "to_theta": "theta_K3_coarse",
    "direction": "coarsened",
    "trigger_p_fail": 0.08,
    "trigger_epsilon": 0.05,
    "goal_id": "task_completion"
}
```

---

## 12. New File Structure

```
src/aps/
    __init__.py              # Package init, init_aps() startup function
    partitions.py            # PartitionScheme, ChannelPartitions, CHANNEL_REGISTRY
                             #   14 partition schemes (7 channels x 2 granularities)
                             #   All classify_input/classify_output functions
                             #   register_channel(), get_active_partition(), switch_partition()
    channel.py               # ConfusionMatrix dataclass
                             #   mutual_information()
                             #   channel_capacity_blahut_arimoto()
                             #   informational_efficiency()
                             #   chain_capacity()
    controller.py            # APSController class
                             #   evaluate_all() - main evaluation loop
                             #   _evaluate_switch() - hysteresis logic
                             #   _build_confusion_matrix() - from observations
                             #   aps_controller singleton
    goals.py                 # GoalID enum, Goal dataclass, GOALS dict (6 goals)
    instrument.py            # instrument_node() wrapper
                             #   estimate_cost() helper
                             #   classify_tool_input/output for K7
    store.py                 # init_aps_tables() - CREATE TABLE IF NOT EXISTS
                             #   log_observation()
                             #   get_recent_observations()
                             #   store_aps_metrics()
                             #   store_partition_switch_event()
                             #   get_latest_metrics()
    scheduler_jobs.py        # aps_evaluation_job() for APScheduler integration

tests/
    test_aps_partitions.py   # ~120 lines
    test_aps_channel.py      # ~120 lines
    test_aps_controller.py   # ~150 lines
    test_aps_instrument.py   # ~80 lines
    test_aps_integration.py  # ~100 lines
```

---

## 13. Modifications to Existing Files

| File | What Changes | Lines Added/Changed | Risk |
|------|-------------|---------------------|------|
| `src/graph.py` | Import instrument_node; wrap 4 node registrations with instrument_node() | ~8 lines | Low — wrapper is transparent |
| `src/agents/sub_agents.py` | Import instrument_node; wrap content_writer and campaign_analyzer nodes | ~4 lines | Low — same wrapper pattern |
| `src/events.py` | Add _aps_tool_starts dict to ForgeEventCallbackHandler; add APS logging to on_tool_start/on_tool_end | ~20 lines | Low — additive, try/except guarded |
| `src/serve.py` | Import APS init; call init_aps_tables() and init_all_partitions() in lifespan; add 6 new API endpoints | ~70 lines | Low — new endpoints, no changes to existing ones |
| `src/scheduler/autonomous.py` | Import aps_evaluation_job; add aps_evaluation IntervalTrigger(minutes=5) to start() | ~10 lines | Low — additive job |
| `pyproject.toml` | Add `numpy>=1.24.0,<3.0.0` to dependencies | ~1 line | Low — numpy is standard |

**Total existing code touched**: ~113 lines across 6 files. All changes are additive. No existing behavior is modified.

---

## 14. Implementation Phases

### Phase 1: Core Data Structures (no runtime impact)

Create the foundational modules that define partitions, compute information-theoretic metrics, and specify goals. These have no dependencies on the running system and can be fully unit-tested in isolation.

**Files created**: `src/aps/__init__.py`, `src/aps/partitions.py`, `src/aps/channel.py`, `src/aps/goals.py`
**Tests created**: `tests/test_aps_partitions.py`, `tests/test_aps_channel.py`
**Dependency added**: numpy in `pyproject.toml`

### Phase 2: Storage Layer

Create the database persistence module and initialize the 3 PostgreSQL tables. Test against the live database.

**Files created**: `src/aps/store.py`
**Tables created**: aps_observations, aps_metrics, aps_partition_switches

### Phase 3: Instrumentation (minimal runtime impact — logging only)

Create the instrumentation wrapper and apply it to all 7 channels. After this phase, every agent invocation logs an APS observation to PostgreSQL. No switching logic yet — just measurement.

**Files created**: `src/aps/instrument.py`
**Files modified**: `src/graph.py`, `src/agents/sub_agents.py`, `src/events.py`
**Tests created**: `tests/test_aps_instrument.py`

### Phase 4: APS Controller (the adaptive logic)

Create the controller with rolling failure estimation, confusion matrix computation, capacity calculation, and epsilon-triggered switching. Wire it into the scheduler.

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

## 15. Testing Strategy

### 15.1 Unit Tests

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

**test_aps_controller.py** (~150 lines):
- Mock observations where p_fail = 0.20 > epsilon_G = 0.10 with FINE partition: verify switch to COARSE.
- Mock observations where p_fail = 0.02 < epsilon_G * 0.5 = 0.05 with COARSE partition: verify switch to FINE.
- Mock observations where p_fail = 0.07 (between epsilon_G/2 and epsilon_G): verify NO switch (hysteresis dead zone).
- Test cooldown: trigger a switch, immediately re-evaluate, verify no second switch within cooldown.
- Test MIN_OBSERVATIONS guard: only 10 observations, p_fail = 0.30, verify no switch.
- Test evaluate_all returns correct structure with channels, goals, switches keys.

**test_aps_instrument.py** (~80 lines):
- Wrap a simple function, verify it returns the original result unchanged.
- Verify log_observation is called with correct channel_id and sigma values (mock the store).
- Verify that if classify_input raises, the wrapped function still runs and returns its result.
- Verify that if log_observation raises, the wrapped function still returns its result.
- Verify cost estimation uses correct MODEL_REGISTRY rates.

### 15.2 Integration Tests

**test_aps_integration.py** (~100 lines):
- Build the instrumented graph, invoke with a sample state (mocking LLM calls), verify an observation row appears in the database.
- Run aps_controller.evaluate_all() against mock observations, verify metrics row appears in database.
- Test the /aps/metrics endpoint returns valid JSON.
- Test the /aps/evaluate endpoint triggers a cycle and returns summary.
- Test the /aps/switch endpoint changes the active partition.

### 15.3 Live Validation Protocol

After deployment, validate with the running system:

1. **Start the system**: `PYTHONUTF8=1 uvicorn src.serve:app --host 0.0.0.0 --port 8050`
2. **Wait for scheduled tasks** or trigger manually: `curl -X POST localhost:8050/scheduler/trigger/order_check`
3. **After 2+ invocations**, trigger evaluation: `curl -X POST localhost:8050/aps/evaluate | python -m json.tool`
4. **Check per-channel metrics**: `curl localhost:8050/aps/metrics | python -m json.tool`
   - Verify: p_fail, mutual_info, capacity, eta are all numeric and non-null
   - Verify: n_observations matches expected invocation count
5. **Check chain capacity**: `curl localhost:8050/aps/chain-capacity | python -m json.tool`
   - Verify: bottleneck channel is identified
   - Verify: chain_capacity <= min(per_channel capacities)
6. **Check partition state**: `curl localhost:8050/aps/partitions | python -m json.tool`
   - Verify: all 7 channels listed with active_theta
7. **Test manual switching**: `curl -X POST localhost:8050/aps/switch/K1/theta_K1_coarse`
   - Verify: next invocation logs observations under the new theta_id
8. **Accumulate 24 hours of data**, then query for partition switch events and verify Theorem 1 holds on empirical data.

---

## 16. Paper Predictions Under Test

| Prediction | What We Measure | Expected Outcome | How We Verify |
|------------|----------------|-------------------|---------------|
| P1: Rate ceiling | Channel capacity C(P) per interface | Finite, measurable capacity values that constrain throughput | /aps/metrics shows C(P) > 0 and < log2(\|Sigma\|) |
| P3: Noise collapses alphabets | p_fail and active partition over time | When API errors spike (tool failures), K7 switches to coarse 2-symbol partition | /aps/partition_switches shows coarsening events correlated with elevated p_fail |
| P5: Medium reshapes partitions | Active partition under different conditions | Different channels stabilize on different granularities based on their noise profiles | /aps/partitions shows heterogeneous theta_ids across channels |
| P7: Epsilon-triggered switching | Partition switch events in audit log | Discrete transitions between fine/coarse, with hysteresis | aps_partition_switches table shows direction, trigger_p_fail, goal_id |
| Theorem 1: Composition bound | Chain capacity vs per-channel capacities | C(P_chain) <= min_k C(P_k) holds empirically | /aps/chain-capacity shows chain_capacity <= min(per_channel) |
| eta comparison | Informational efficiency across channels | Channels using expensive models (K4: Opus) have lower eta; channels using free models (K1: Ollama) have higher eta | /aps/metrics shows eta inversely correlated with model cost |

---

## 17. Dependencies

**New dependency**: `numpy>=1.24.0,<3.0.0` (for confusion matrix operations, Blahut-Arimoto)

**Existing dependencies leveraged** (no new installs):
- `psycopg` (via langgraph-checkpoint-postgres) — PostgreSQL access
- `apscheduler` — scheduler integration
- `fastapi` — API endpoints
- `langchain-core` — callback handler extension

---

## 18. Key Design Decisions and Rationale

**1. Wrapper pattern over agent modification.**
Agent code remains untouched. APS is a purely additive instrumentation layer. If APS fails at any point (classification error, database down, numpy exception), the original agent function still executes and returns its result. This is critical for a live production system.

**2. PostgreSQL over Redis for APS storage.**
APS needs time-range queries with aggregation (GROUP BY channel_id, COUNT, window functions). PostgreSQL supports this natively. Redis is optimized for key-value access patterns and would require application-level aggregation. The existing PostgreSQL instance (already running for LangGraph checkpoints) has ample capacity.

**3. Blahut-Arimoto for channel capacity, not just mutual information.**
The paper's theory requires C(P) = max_{p(x)} I(X;Y), not just the empirical mutual information under the observed input distribution. Blahut-Arimoto is the standard algorithm, converges quickly for our small alphabets, and gives the true substrate property rather than a usage-dependent estimate.

**4. Exactly two partition granularities (fine/coarse) per channel.**
The paper supports arbitrary partition sets {theta_i}. Starting with exactly two keeps the switching logic simple (binary: coarsen or refine) while fully demonstrating the epsilon-triggered mechanism. Additional intermediate granularities can be added later without architectural changes.

**5. Five-minute evaluation interval.**
The system generates ~2 invocations per hour on the scheduler (plus manual triggers). A 5-minute cycle ensures fresh metrics without excessive database load. The evaluation itself is lightweight (a few SQL queries + small matrix operations).

**6. Asymmetric hysteresis cooldowns (60s coarsen, 300s refine).**
Coarsening is a protective response to degradation — it should happen quickly. Refinement is an opportunistic optimization — it should happen cautiously to avoid premature re-expansion. The 0.5 hysteresis factor on epsilon_G creates a dead zone that further dampens oscillation.

**7. Cost estimation via MODEL_REGISTRY rather than per-invocation token counting.**
Correlating individual token counts from LangChain callbacks to specific APS observations would require complex run_id tracking across the callback system. Instead, each agent uses a known model, and we estimate cost from per-token rates with average token counts. The accuracy is sufficient for eta comparison across channels.

**8. 20-observation minimum before switching.**
Statistical significance requires sufficient data. With fewer than 20 observations, the failure rate estimate has standard error > 0.11, making it unreliable for decisions against tolerances in the 0.05-0.15 range.
