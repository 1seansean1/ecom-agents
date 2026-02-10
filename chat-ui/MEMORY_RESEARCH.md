# Memory Management for Agentic AI Systems
## Research Report — Feb 2026

Comprehensive research into memory architectures, tier promotion, synthesis, compaction, and retrieval patterns for LLM-based agent systems. Synthesized from 30+ papers, frameworks, and production implementations.

---

## Table of Contents
1. [Multi-Tier Memory Architectures](#1-multi-tier-memory-architectures)
2. [Key Implementations](#2-key-implementations)
3. [Promotion Mechanisms](#3-promotion-mechanisms)
4. [Synthesis During Promotion](#4-synthesis-during-promotion)
5. [Compaction Strategies](#5-compaction-strategies)
6. [Retrieval Patterns](#6-retrieval-patterns)
7. [Context Window Packing](#7-context-window-packing)
8. [Long Session Management](#8-long-session-management)
9. [Design Recommendations for Chat UI](#9-design-recommendations-for-chat-ui)

---

## 1. Multi-Tier Memory Architectures

Nearly all modern systems converge on a 3-5 tier hierarchy inspired by cognitive psychology:

### The Universal Pattern

| Tier | Cognitive Analog | Technical Implementation | Lifecycle |
|------|-----------------|-------------------------|-----------|
| **Working Memory** | Executive workspace | LLM context window | Per-turn, always present |
| **Short-Term / Episodic** | Recent experience | Message buffer, event log | Session-scoped or sliding window |
| **Long-Term / Semantic** | Facts & knowledge | Vector DB + entity graph | Persistent, updated via extraction |
| **Crystallized / Strategic** | Wisdom & principles | Distilled rules, learned strategies | Persistent, rarely changes |

### Notable Architectures

**MemGPT/Letta** (2023, foundational):
- **Main Context** = system instructions + core memory blocks (persona, human) + FIFO message queue
- **Recall Storage** = complete raw conversation history in PostgreSQL (auto-populated on eviction)
- **Archival Storage** = vector DB (pgvector) for agent-curated long-term knowledge
- Key insight: the LLM itself is the "OS kernel" — decides when to move data between tiers via tool calls

**EverMemOS** (Jan 2026, current SOTA — 93% on LoCoMo):
- Episodic traces → MemCells → consolidated into thematic MemScenes
- +19.7% on multi-hop reasoning, +16.1% on temporal tasks

**MAGMA** (Jan 2026):
- Four orthogonal graphs over the same memory: Temporal, Causal, Entity, Semantic
- Policy-guided traversal selects which graph(s) to query per question type

**Zep/Graphiti** (Jan 2025):
- Three subgraph tiers: Episodes → Entities → Communities
- Bi-temporal model: 4 timestamps per edge (`t_created`, `t_expired`, `t_valid`, `t_invalid`)
- Never deletes — marks facts invalid, preserving complete history

---

## 2. Key Implementations

### Framework Memory Systems

| Framework | Short-Term | Long-Term | Eviction | Semantic Search | Temporal Awareness |
|-----------|-----------|-----------|----------|----------------|-------------------|
| **LangGraph** | Checkpointer (thread-scoped) | Store (cross-thread, namespaced) | App-defined | Yes (with embeddings) | No |
| **LlamaIndex** | Chat history (token ratio) | Memory blocks (priority-based) | Priority truncation | VectorMemoryBlock | No |
| **CrewAI** | ChromaDB (RAG) | SQLite3 + ChromaDB | Per-type | Yes | No |
| **AutoGen** | ListMemory | External (Mem0, Zep) | Manual | Via integration | Via integration |
| **Mem0** | Rolling summary + last m msgs | Vector + graph (Neo4j) | LLM-judged ADD/UPDATE/DELETE | Yes | Partial |
| **Zep** | Session messages | Temporal knowledge graph | Edge invalidation | Cosine + BM25 + graph | Full bi-temporal |

### LangChain Legacy Memory Types (deprecated but patterns still relevant)

| Type | Mechanism | LLM Cost/Turn | Best For |
|------|-----------|--------------|----------|
| `ConversationBufferMemory` | Store all messages verbatim | 0 | Short conversations (<20 turns) |
| `ConversationBufferWindowMemory` | Sliding window of last k turns | 0 | Support bots, simple Q&A |
| `ConversationTokenBufferMemory` | Drop oldest when over token limit | 0 | Precise token budget control |
| `ConversationSummaryMemory` | Running LLM summary after each turn | 1 per turn | Long conversations, cost-sensitive |
| `ConversationSummaryBufferMemory` | Hybrid: recent verbatim + older summarized | 0 until overflow, then 1 | **Best general-purpose** |
| `ConversationKGMemory` | Extract triples → NetworkX graph | 2+ per turn | Entity-rich conversations |
| `ConversationEntityMemory` | Per-entity running summaries | 1+N per turn | Personal assistants, CRM |
| `VectorStoreRetrieverMemory` | Embed each turn, retrieve by similarity | 0 (embedding only) | Long-lived cross-session agents |

### LlamaIndex Memory Block System

Priority-based truncation with composable blocks:
```
StaticMemoryBlock       (priority=0, NEVER truncated)  — system rules, persona
FactExtractionMemoryBlock (priority=1)                 — LLM-extracted facts, max_facts limit
VectorMemoryBlock       (priority=2, first truncated)  — archived messages via embeddings
```

Token budget: `token_limit * chat_history_token_ratio` for messages, remainder for blocks.

### MemGPT/Letta Memory Operations

| Function | Direction | Description |
|----------|-----------|-------------|
| `core_memory_append(block, content)` | → Working | Add facts to always-visible core memory |
| `core_memory_replace(block, old, new)` | ↔ Working | Update/correct facts in core memory |
| `memory_rethink(block, new_content)` | → Working | Complete rewrite of a memory block |
| `archival_memory_insert(content)` | → Long-term | Persist curated knowledge to vector DB |
| `archival_memory_search(query, page)` | ← Long-term | Semantic search with pagination |
| `conversation_search(query, page)` | ← Episodic | Text search over full history |
| `conversation_search_date(start, end)` | ← Episodic | Date-range retrieval |

**Two-threshold eviction**: Warning at ~70% capacity (agent triages), forced eviction at ~100% (50% oldest messages flushed, recursively summarized).

**Sleep-time agents** (Letta evolution): Primary agent handles conversation (no memory tools), sleep-time agent runs every N steps in background to update shared memory blocks. Lower latency, better quality, higher total cost.

---

## 3. Promotion Mechanisms

### 3a. Composite Scoring (Stanford Generative Agents, foundational)

```
score = alpha * recency + beta * importance + gamma * relevance

recency    = 0.995 ^ hours_since_last_access  (exponential decay)
importance = LLM-assigned 1-10 score at creation ("eating breakfast"=1, "a breakup"=9)
relevance  = cosine_similarity(query_embedding, memory_embedding)
```

### 3b. ACT-R Base-Level Activation (cognitive architecture)

```
A_i = ln( SUM(t_j^-0.5) ) + SUM(W_k * S_ki) + noise

t_j   = time since j-th access (power-law decay)
W_k   = spreading activation weight from context
S_ki  = association strength
```

Memory retrieval follows logistic function of activation. Below-threshold = effectively "forgotten."

### 3c. LLM-as-Judge (Mem0)

Extract candidate facts → retrieve top-10 similar existing memories → LLM decides:
- **ADD**: genuinely new information
- **UPDATE**: augments existing memory
- **DELETE**: contradicts existing memory
- **NOOP**: no change needed

### 3d. Frequency + Importance Threshold

When a fact/entity appears in N separate episodes AND cumulative importance exceeds threshold → promote from episodic to semantic tier.

### 3e. Zettelkasten Dynamic Indexing (A-MEM, NeurIPS 2025)

Every memory = structured note with description, keywords, tags, cross-links. New memories retroactively update existing notes' context. 85-93% token reduction, sub-10μs retrieval at 1M notes.

### 3f. RL-Trained Gating (BudgetMem)

Feature-based salience scorer (entity density, TF-IDF, discourse markers, position bias) + reinforcement learning decides what to store under strict token budgets. 1% F1 loss with 72% memory savings.

---

## 4. Synthesis During Promotion

### Fact/Triple Extraction (Zep 8-step pipeline)
1. Entity extraction (with 4-message context + reflection)
2. Entity embedding (1024D vectors)
3. Entity resolution (cosine + BM25 + LLM dedup)
4. Relationship extraction (subject-predicate-object)
5. Edge deduplication
6. Temporal annotation (4 timestamps)
7. Edge invalidation (contradiction detection)
8. Community detection (label propagation + LLM summaries)

### Recursive Summarization (MemGPT)
```
new_summary = LLM(existing_summary + evicted_messages)
```
Each eviction cycle produces progressively more compressed representation. Older content has diminishing influence — natural temporal decay.

### Reflection Chains (Stanford Generative Agents)
1. Accumulated importance scores exceed threshold → trigger reflection
2. LLM generates 5 high-level questions from recent memories
3. Per question: retrieve relevant memories → LLM generates higher-level inference
4. Reflections stored as new memories (can be reflected upon recursively)

### Contradiction Resolution
- **Mem0**: LLM chooses DELETE or UPDATE. Old memories marked INVALID for audit trail.
- **Zep**: `t_invalid` timestamp + `invalidated_by` link. Complete temporal history preserved.
- **Current limitation**: Multi-hop conflict resolution accuracy ≤6% even in best systems.

### Entropy-Aware Filtering (SimpleMem)
Measure information entropy per memory unit at write time. High-entropy (high information density) → retain. Low-entropy (repetitive, boilerplate) → discard immediately. 26.4% F1 improvement, 30x token reduction.

---

## 5. Compaction Strategies

### Sliding Window + Summary (ConversationSummaryBufferMemory pattern)
Keep recent N messages verbatim. When buffer overflows `max_token_limit`:
1. Pop oldest messages
2. LLM generates summary from `existing_summary + popped_messages`
3. Summary replaces evicted messages as SystemMessage at position 0

### Ebbinghaus Forgetting Curve (FadeMem)
```
retention = e^(-t/S)     where S = strength (incremented on each access)
```
Dual layers: Long-term (slow decay) + Short-term (fast decay). 45% storage reduction, 85.9% factual consistency.

### Hierarchical Consolidation (EverMemOS)
MemCells → grouped by semantic similarity → consolidated into MemScenes → MemScenes further consolidated over time. Multi-level compression.

### Observation Masking (JetBrains Research, Dec 2025)
Replace older tool outputs with placeholders, preserve full action/reasoning history. **Beat LLM summarization in 4/5 settings**: simpler, cheaper, avoids smoothing over stopping signals. Halves costs vs doing nothing.

### Token Budget Tiers
```
Priority 1: Keep raw content (if it fits)
Priority 2: Context compaction (strip redundant info, keep references)
Priority 3: LLM summarization (irreversible, triggered at capacity)
```

---

## 6. Retrieval Patterns

### Hybrid Search (BM25 + Vector)
Combine dense semantic retrieval with sparse keyword retrieval:
- **Linear blending**: `H = (1-α) * keyword_score + α * vector_score`
- **Reciprocal Rank Fusion**: `RRF(d) = SUM(1 / (k + rank(d)))`
- BM25 catches what embeddings miss: abbreviations, proper names, code, exact matches

### Two-Stage Retrieval + Reranking
1. **Recall**: Broad vector search → 20-100 candidates (fast, bi-encoder)
2. **Precision**: Cross-encoder reranker scores each (query, doc) pair → top 3-5 results
- 15-30% accuracy improvement over embeddings alone

### MMR (Maximal Marginal Relevance)
```
MMR = argmax_d [ λ * Sim(d, Q) - (1-λ) * max_d'(Sim(d, d')) ]
```
Balances relevance with diversity — avoids injecting redundant memories.

### Graph-Based Retrieval
Entity-centric: identify entities in query → traverse graph → return connected subgraph
Semantic triplet: embed query → match against (subject, predicate, object) encodings

### Query Rewriting / HyDE
1. LLM generates hypothetical answer document (5x)
2. Embed each hypothetical, compute mean
3. Use averaged embedding to search real corpus
Bridges query-document phrasing mismatch.

### Composite Scoring for Retrieval
```python
score = (w1 * semantic_similarity
       + w2 * topic_overlap
       + w3 * exp(-decay * age_days)
       + w4 * access_frequency
       + w5 * importance_label)
```

---

## 7. Context Window Packing

### Structured Injection Pattern
```xml
<system_instructions>
Base persona and behavior rules (priority 0, never evicted)
</system_instructions>

<user_profile>
Structured facts as YAML frontmatter
</user_profile>

<memories>
GLOBAL: durable preferences/facts (top 6 by recency)
SESSION: current session context (after trim events)
</memories>

<conversation>
Recent messages (sliding window, token-budgeted)
</conversation>
```

### Token Budget Allocation
```
System instructions + tools:   15-25%
Retrieved memories:             10-30% (dynamic, by relevance)
Conversation history:           30-50% (sliding window)
Generation reserve:             15-20%
```

### Lost-in-the-Middle Mitigation
LLMs attend strongly to beginning and end, degrade 30%+ for middle content.
- Place highest-priority content at start and end
- Use MMR to limit total injected content
- Two-stage retrieval to keep only 3-5 most relevant items

---

## 8. Long Session Management

### Observation Masking (recommended, JetBrains)
Replace older tool outputs with `[result stored at <path>]` placeholders. Keep full action/reasoning chain intact. Retrievable on demand via tools.

### Rolling Summarization
At 80% context capacity: summarize everything older than N messages, keep recent N verbatim. Triggered per-turn only when threshold exceeded.

### Context Offloading (Manus pattern)
Store full tool results in filesystem. Keep compact references in context. Agent uses `grep`/`cat` to pull back details when needed. Dramatically reduces context consumption.

### Checkpoint + Resume
Write key decisions, progress, context to external file (NOTES.md). On context reset, reload file to restore working state. Manual but reliable.

---

## 9. Design Recommendations for Chat UI

Based on all research, here's the recommended architecture for the chat-ui shared memory system:

### Tier Architecture
```
Tier 0: System Prompt (always in context, never evicted)
Tier 1: Working Context — last 10-20 messages verbatim (sliding window)
Tier 2: Session Summary — rolling LLM summary of older messages
Tier 3: Extracted Facts — key entities/facts from conversation (vector-indexed)
Tier 4: Crystallized — cross-session lessons, user preferences (persistent)
```

### Compaction Pipeline
```
1. MEASURE: Count tokens across all tiers
2. IF total < 75% of context window → do nothing
3. IF total > 75% → trigger compaction:
   a. Identify messages outside the sliding window
   b. Extract key facts/entities via LLM (→ Tier 3)
   c. Generate summary from old_summary + evicted_messages (→ Tier 2)
   d. Drop raw messages from context
4. IF total > 90% after compaction → aggressive mode:
   a. Summarize Tier 3 facts into bullet points
   b. Truncate Tier 2 summary to 500 tokens
```

### Promotion Rules
```
Episodic → Semantic: fact appears in 3+ messages OR LLM importance ≥ 7/10
Semantic → Crystallized: fact persists across 3+ sessions AND is generalizable
```

### Retrieval Strategy
```
1. Always inject: Tier 0 (system) + Tier 1 (recent messages)
2. Conditionally inject: Tier 2 summary (if > 0 evicted messages)
3. Similarity search: Tier 3 facts (top 5 by cosine similarity to current query)
4. Persistent load: Tier 4 crystallized (always prepended, token-budgeted)
```

### Implementation Priority
1. **Sliding window + token counting** (cheapest, biggest impact)
2. **Rolling summarization on overflow** (one LLM call per compaction)
3. **Fact extraction to vector store** (uses existing ChromaDB knowledge)
4. **Cross-session persistence** (localStorage or server-side DB)

---

## Sources

### Papers
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) (Oct 2023)
- [Generative Agents: Interactive Simulacra](https://arxiv.org/abs/2304.03442) (Apr 2023)
- [Zep: Temporal Knowledge Graph Architecture](https://arxiv.org/abs/2501.13956) (Jan 2025)
- [Mem0: Production-Ready Agent Memory](https://arxiv.org/abs/2504.19413) (Apr 2025)
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) (NeurIPS 2025)
- [EverMemOS](https://arxiv.org/abs/2601.02163) (Jan 2026)
- [MAGMA: Multi-Graph Agentic Memory](https://arxiv.org/abs/2601.03236) (Jan 2026)
- [Synapse: Spreading Activation for LLM Agents](https://arxiv.org/abs/2601.02744) (Jan 2026)
- [SimpleMem: Efficient Lifelong Memory](https://arxiv.org/abs/2601.02553) (Jan 2026)
- [FadeMem: Biologically-Inspired Forgetting](https://arxiv.org/abs/2601.18642) (Jan 2026)
- [BudgetMem: Learned Selective Memory](https://arxiv.org/abs/2511.04919) (Nov 2025)
- [MMAG: Mixed Memory-Augmented Generation](https://arxiv.org/abs/2512.01710) (Dec 2025)
- [Memory in the Age of AI Agents (Survey)](https://arxiv.org/abs/2512.13564) (Dec 2025)
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) (Jul 2023)
- [HyDE: Hypothetical Document Embeddings](https://arxiv.org/abs/2212.10496) (Dec 2022)

### Documentation
- [Letta/MemGPT Docs](https://docs.letta.com/)
- [LangGraph Memory](https://langchain-ai.github.io/langgraph/)
- [LlamaIndex Memory](https://docs.llamaindex.ai/)
- [Zep/Graphiti GitHub](https://github.com/getzep/graphiti)
- [CrewAI Memory Docs](https://docs.crewai.com/en/concepts/memory)
- [AutoGen Memory Docs](https://microsoft.github.io/autogen/)
- [Semantic Kernel Memory](https://deepwiki.com/microsoft/semantic-kernel/3.3-memory-system)
- [OpenAI Agents SDK Context Engineering](https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization)
- [JetBrains Context Management Research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/)
- [Agent Memory Paper List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
