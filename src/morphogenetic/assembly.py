"""Assembly Cache: reusable competency storage with competency taxonomy.

Successful adaptations are cached as reusable subassemblies.
Repeated reuse is the engineered analogue of biological "copy number."

Competency taxonomy (ordered by assembly cost):
- Sensitization:  lower threshold for known failure → faster response
- Habituation:    raise threshold for benign fluctuation → less noise
- Associative:    context→response binding (this fingerprint → this config)
- Homeostatic:    new permanent capability with dedicated monitoring
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Competency types ordered by assembly cost
SENSITIZATION = "sensitization"
HABITUATION = "habituation"
ASSOCIATIVE = "associative"
HOMEOSTATIC = "homeostatic"

COMPETENCY_TYPES = [SENSITIZATION, HABITUATION, ASSOCIATIVE, HOMEOSTATIC]
COMPETENCY_COST = {SENSITIZATION: 1, HABITUATION: 1, ASSOCIATIVE: 2, HOMEOSTATIC: 3}


@dataclass
class CachedCompetency:
    """A cached adaptation that can be reused when a matching context recurs."""

    competency_id: str
    tier: int                            # which APS tier created this (0-3)
    competency_type: str                 # sensitization/habituation/associative/homeostatic
    channel_id: str                      # which channel this applies to
    goal_id: str                         # which goal triggered the cascade
    adaptation: dict[str, Any]           # what was changed
    context_fingerprint: str             # when to reuse this (context hash)
    reuse_count: int = 0
    success_rate: float = 1.0
    assembly_index: float = 0.0          # structural complexity proxy
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def classify_competency(tier: int, adaptation: dict) -> str:
    """Classify a cached adaptation into the competency taxonomy.

    Rules:
    - Tier 0 + threshold lowered → sensitization
    - Tier 0 + threshold raised → habituation
    - Tier 1 (context→config binding) → associative
    - Tier 2-3 (new capability) → homeostatic
    """
    if tier == 0:
        # Check if adaptation lowered or raised a threshold
        direction = adaptation.get("direction", "")
        if direction == "escalated":
            return SENSITIZATION  # More aggressive response
        return HABITUATION  # More tolerant

    if tier == 1:
        return ASSOCIATIVE  # Context→response binding

    return HOMEOSTATIC  # New permanent capability (Tier 2-3)


def compute_assembly_index(adaptation: dict, tier: int) -> float:
    """Compute a structural complexity proxy (AI) for an adaptation.

    Higher values indicate more structural modification.
    This is an ordinal measure, not cardinal.
    """
    base = COMPETENCY_COST.get(classify_competency(tier, adaptation), 1)

    # Add complexity based on what was changed
    n_fields = len(adaptation)
    if "tools_added" in adaptation:
        base += len(adaptation["tools_added"])
    if "prompt_delta" in adaptation:
        base += 1
    if "model_changed" in adaptation and adaptation["model_changed"]:
        base += 2
    if "agent_added" in adaptation:
        base += 5  # Adding an agent is structurally expensive

    return float(base + n_fields * 0.1)


def generate_competency_id(channel_id: str, goal_id: str, adaptation: dict) -> str:
    """Generate a deterministic ID for a competency."""
    key = json.dumps({"c": channel_id, "g": goal_id, "a": sorted(adaptation.keys())}, sort_keys=True)
    return f"comp_{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def generate_context_fingerprint(channel_id: str, metrics: dict) -> str:
    """Generate a context fingerprint for cache lookup.

    Matches the existing APS theta_cache context fingerprinting approach:
    time bucket + error regime + channel.
    """
    hour = datetime.now(timezone.utc).hour
    if hour < 12:
        time_bucket = "morning"
    elif hour < 18:
        time_bucket = "afternoon"
    else:
        time_bucket = "night"

    p_fail = metrics.get("p_fail", 0.0)
    if p_fail < 0.05:
        error_regime = "low"
    elif p_fail < 0.15:
        error_regime = "medium"
    else:
        error_regime = "high"

    parts = [channel_id, time_bucket, error_regime]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# DB operations (delegates to store.py functions)
# ---------------------------------------------------------------------------


def store_competency(comp: CachedCompetency) -> None:
    """Store a cached competency in the assembly cache."""
    from src.aps.store import _get_conn

    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO assembly_cache
            (competency_id, tier, competency_type, channel_id, goal_id,
             adaptation, context_fingerprint, reuse_count, success_rate,
             assembly_index, created_at, last_used_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (competency_id) DO UPDATE SET
                reuse_count = assembly_cache.reuse_count + 1,
                last_used_at = NOW()
            """,
            (
                comp.competency_id, comp.tier, comp.competency_type,
                comp.channel_id, comp.goal_id,
                json.dumps(comp.adaptation), comp.context_fingerprint,
                comp.reuse_count, comp.success_rate, comp.assembly_index,
                comp.created_at, comp.last_used_at,
            ),
        )
    logger.info(
        "Stored competency %s (type=%s, tier=%d, channel=%s)",
        comp.competency_id, comp.competency_type, comp.tier, comp.channel_id,
    )


def lookup_competency(channel_id: str, context_fingerprint: str) -> CachedCompetency | None:
    """Look up a cached competency by context fingerprint."""
    from src.aps.store import _get_conn

    with _get_conn() as conn:
        row = conn.execute(
            """SELECT competency_id, tier, competency_type, channel_id, goal_id,
                      adaptation, context_fingerprint, reuse_count, success_rate,
                      assembly_index, created_at, last_used_at
            FROM assembly_cache
            WHERE channel_id = %s AND context_fingerprint = %s
            ORDER BY reuse_count DESC, success_rate DESC
            LIMIT 1""",
            (channel_id, context_fingerprint),
        ).fetchone()

    if not row:
        return None

    return CachedCompetency(
        competency_id=row[0], tier=row[1], competency_type=row[2],
        channel_id=row[3], goal_id=row[4],
        adaptation=row[5] if isinstance(row[5], dict) else json.loads(row[5]),
        context_fingerprint=row[6], reuse_count=row[7], success_rate=row[8],
        assembly_index=row[9], created_at=row[10], last_used_at=row[11],
    )


def increment_reuse(competency_id: str, success: bool) -> None:
    """Increment reuse count and update success rate."""
    from src.aps.store import _get_conn

    with _get_conn() as conn:
        conn.execute(
            """UPDATE assembly_cache SET
                reuse_count = reuse_count + 1,
                last_used_at = NOW(),
                success_rate = CASE WHEN %s THEN
                    (success_rate * reuse_count + 1.0) / (reuse_count + 1)
                ELSE
                    (success_rate * reuse_count) / (reuse_count + 1)
                END
            WHERE competency_id = %s""",
            (success, competency_id),
        )


def get_all_competencies() -> list[dict]:
    """Get all cached competencies."""
    from src.aps.store import _get_conn

    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT competency_id, tier, competency_type, channel_id, goal_id,
                      adaptation, context_fingerprint, reuse_count, success_rate,
                      assembly_index, created_at, last_used_at
            FROM assembly_cache ORDER BY reuse_count DESC"""
        ).fetchall()

    return [
        {
            "competency_id": r[0], "tier": r[1], "competency_type": r[2],
            "channel_id": r[3], "goal_id": r[4],
            "adaptation": r[5] if isinstance(r[5], dict) else json.loads(r[5]),
            "context_fingerprint": r[6], "reuse_count": r[7],
            "success_rate": round(r[8], 3) if r[8] else 0.0,
            "assembly_index": round(r[9], 2) if r[9] else 0.0,
            "created_at": str(r[10]), "last_used_at": str(r[11]),
        }
        for r in rows
    ]


def get_competency_distribution() -> dict[str, int]:
    """Get count of competencies per type."""
    from src.aps.store import _get_conn

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT competency_type, COUNT(*) FROM assembly_cache GROUP BY competency_type"
        ).fetchall()

    dist = {t: 0 for t in COMPETENCY_TYPES}
    for row in rows:
        dist[row[0]] = row[1]
    return dist
