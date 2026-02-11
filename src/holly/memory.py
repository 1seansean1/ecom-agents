"""Three-tier memory system for Holly Grace autonomous operation.

Short-term:  Recent conversation messages (Postgres holly_sessions — existing)
Medium-term: Episode summaries from completed tasks (Postgres holly_memory_episodes)
Long-term:   Key facts and learned patterns (Postgres holly_memory_facts)

Context assembly pulls from all three tiers to build an optimal
API call context within token budget.  The short-term tier is
managed by the existing session.py; this module adds medium and
long-term layers plus a unified context builder.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://holly:holly_dev_password@localhost:5434/holly_grace",
)

# ── Budget knobs ──────────────────────────────────────────────────────────
EPISODE_CONTEXT_LIMIT = 12   # Max recent episodes to include
FACT_CONTEXT_LIMIT = 40      # Max facts to include
SHORT_TERM_COMPACT_AT = 30   # Trigger compaction to episode when this many msgs


# ── DB helpers ────────────────────────────────────────────────────────────

def _get_conn() -> psycopg.Connection:
    return psycopg.connect(_DB_URL, autocommit=True, row_factory=dict_row)


def init_memory_tables() -> None:
    """Create memory tables if they don't exist.  Idempotent."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS holly_memory_episodes (
                id            SERIAL PRIMARY KEY,
                session_id    TEXT NOT NULL DEFAULT 'autonomous',
                summary       TEXT NOT NULL,
                key_decisions JSONB DEFAULT '[]',
                tools_used    JSONB DEFAULT '[]',
                outcome       TEXT,
                objective     TEXT,
                token_estimate INT DEFAULT 0,
                created_at    TIMESTAMPTZ DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS holly_memory_facts (
                id            SERIAL PRIMARY KEY,
                category      TEXT NOT NULL,
                content       TEXT NOT NULL,
                source        TEXT,
                confidence    REAL DEFAULT 1.0,
                last_accessed TIMESTAMPTZ DEFAULT now(),
                access_count  INT DEFAULT 0,
                created_at    TIMESTAMPTZ DEFAULT now(),
                UNIQUE (category, content)
            )
        """)
    logger.info("Holly memory tables initialized")


# ── Medium-term: Episode store ────────────────────────────────────────────

def store_episode(
    summary: str,
    *,
    key_decisions: list[str] | None = None,
    tools_used: list[str] | None = None,
    outcome: str | None = None,
    objective: str | None = None,
    session_id: str = "autonomous",
) -> int:
    """Store a completed-task episode in medium-term memory.  Returns episode id."""
    token_est = len(summary) // 4
    with _get_conn() as conn:
        row = conn.execute(
            """INSERT INTO holly_memory_episodes
               (session_id, summary, key_decisions, tools_used, outcome, objective, token_estimate)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                session_id,
                summary,
                json.dumps(key_decisions or []),
                json.dumps(tools_used or []),
                outcome,
                objective,
                token_est,
            ),
        ).fetchone()
    return row["id"] if row else 0


def get_recent_episodes(
    limit: int = EPISODE_CONTEXT_LIMIT,
    session_id: str | None = None,
) -> list[dict]:
    """Retrieve recent episode summaries for context assembly."""
    with _get_conn() as conn:
        if session_id:
            rows = conn.execute(
                """SELECT id, summary, key_decisions, tools_used, outcome, objective, created_at
                   FROM holly_memory_episodes
                   WHERE session_id = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, summary, key_decisions, tools_used, outcome, objective, created_at
                   FROM holly_memory_episodes
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            ).fetchall()
    return [
        {
            "id": r["id"],
            "summary": r["summary"],
            "key_decisions": r["key_decisions"] or [],
            "tools_used": r["tools_used"] or [],
            "outcome": r["outcome"],
            "objective": r["objective"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


# ── Long-term: Fact store ─────────────────────────────────────────────────

def store_fact(
    category: str,
    content: str,
    source: str | None = None,
    confidence: float = 1.0,
) -> int:
    """Upsert a key fact.  Returns fact id (0 on conflict)."""
    with _get_conn() as conn:
        row = conn.execute(
            """INSERT INTO holly_memory_facts (category, content, source, confidence)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (category, content)
               DO UPDATE SET confidence = EXCLUDED.confidence,
                             last_accessed = now(),
                             access_count = holly_memory_facts.access_count + 1
               RETURNING id""",
            (category, content, source, confidence),
        ).fetchone()
    return row["id"] if row else 0


def get_facts(
    category: str | None = None,
    limit: int = FACT_CONTEXT_LIMIT,
) -> list[dict]:
    """Retrieve facts, optionally filtered by category."""
    with _get_conn() as conn:
        if category:
            rows = conn.execute(
                """SELECT id, category, content, source, confidence, access_count, created_at
                   FROM holly_memory_facts
                   WHERE category = %s
                   ORDER BY confidence DESC, access_count DESC
                   LIMIT %s""",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, category, content, source, confidence, access_count, created_at
                   FROM holly_memory_facts
                   ORDER BY confidence DESC, access_count DESC
                   LIMIT %s""",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


# ── Context builder ───────────────────────────────────────────────────────

def build_memory_context(session_id: str = "autonomous") -> str:
    """Assemble a memory-context block for Holly's next API call.

    Returns a Markdown string that gets injected into the system prompt
    or prepended as a system context message.  Short-term messages are
    handled by session.py directly.
    """
    parts: list[str] = []

    # Medium-term: recent episodes
    episodes = get_recent_episodes(limit=EPISODE_CONTEXT_LIMIT, session_id=session_id)
    if episodes:
        parts.append("## Recent Task History")
        for ep in reversed(episodes):  # oldest first for narrative flow
            ts = ep["created_at"][:16]
            parts.append(f"- [{ts}] {ep['summary']}")
            if ep.get("outcome"):
                parts.append(f"  Outcome: {ep['outcome']}")

    # Long-term: key facts grouped by category
    facts = get_facts(limit=FACT_CONTEXT_LIMIT)
    if facts:
        parts.append("\n## Key Facts")
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            by_cat.setdefault(f["category"], []).append(f["content"])
        for cat, items in by_cat.items():
            parts.append(f"**{cat}:**")
            for item in items:
                parts.append(f"- {item}")

    return "\n".join(parts) if parts else ""


# ── Compaction: short-term → episode ──────────────────────────────────────

def compact_session_to_episode(
    messages: list[dict],
    keep_recent: int = 15,
    session_id: str = "autonomous",
) -> tuple[list[dict], int]:
    """Summarize old messages into an episode and return kept messages.

    Returns (kept_messages, episode_id).  If there aren't enough messages
    to compact, returns (messages, 0).
    """
    if len(messages) <= keep_recent:
        return messages, 0

    old = messages[:-keep_recent]
    recent = messages[-keep_recent:]

    # Build a lightweight summary from Holly's responses
    holly_turns: list[str] = []
    tools_seen: set[str] = set()
    for m in old:
        role = m.get("role", "")
        content = m.get("content", "")[:300]
        if role == "holly":
            holly_turns.append(content)
        if "tool" in content.lower():
            for word in content.split():
                if word.startswith("query_") or word.startswith("start_") or word.startswith("dispatch_"):
                    tools_seen.add(word)

    summary = (
        f"Processed {len(old)} messages. "
        + " | ".join(holly_turns[:5])
    )[:800]

    ep_id = store_episode(
        summary=summary,
        tools_used=list(tools_seen),
        outcome="compacted",
        session_id=session_id,
    )

    return recent, ep_id
