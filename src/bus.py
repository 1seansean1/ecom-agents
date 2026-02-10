"""Redis Streams message bus — publish + consume utilities.

All components that emit events import ``publish()`` from this module.
Messages are added via XADD with an auto-generated stream ID (*).
The module maintains a singleton Redis connection (same pattern as
src/memory/medium_term.py and src/tools/idempotency.py).

If Redis is unreachable, publishes are silently dropped (fail-open).
The EventBroadcaster (src/events.py) remains the WebSocket fan-out
mechanism — this bus is the durable inter-component backbone.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import redis

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6381/0")

# ---------------------------------------------------------------------------
# Stream names
# ---------------------------------------------------------------------------

STREAM_TOWER_EVENTS = "holly:tower:events"
STREAM_TOWER_TICKETS = "holly:tower:tickets"
STREAM_HUMAN_INBOUND = "holly:human:inbound"
STREAM_HUMAN_OUTBOUND = "holly:human:outbound"
STREAM_SYSTEM_HEALTH = "holly:system:health"

ALL_STREAMS = [
    STREAM_TOWER_EVENTS,
    STREAM_TOWER_TICKETS,
    STREAM_HUMAN_INBOUND,
    STREAM_HUMAN_OUTBOUND,
    STREAM_SYSTEM_HEALTH,
]

# Approximate trim policies per stream
_TRIM_POLICIES: dict[str, int] = {
    STREAM_TOWER_EVENTS: 5000,
    STREAM_TOWER_TICKETS: 2000,
    STREAM_HUMAN_INBOUND: 1000,
    STREAM_HUMAN_OUTBOUND: 1000,
    STREAM_SYSTEM_HEALTH: 3000,
}

# Consumer group name for Holly Grace orchestrator
CONSUMER_GROUP = "holly-grace"

_redis_client: redis.Redis | None = None


# ---------------------------------------------------------------------------
# Redis singleton
# ---------------------------------------------------------------------------

def _get_redis() -> redis.Redis:
    """Get or create the singleton Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
    return _redis_client


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

def publish(
    stream: str,
    msg_type: str,
    payload: dict[str, Any],
    *,
    source: str = "",
    msg_id: str | None = None,
) -> str | None:
    """Publish a message to a Redis Stream.

    Fire-and-forget: never raises, never blocks the caller on failure.
    Returns the Redis stream entry ID or None on failure.
    """
    if msg_id is None:
        msg_id = uuid.uuid4().hex[:16]

    entry = {
        "msg_id": msg_id,
        "msg_type": msg_type,
        "source": source,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "payload": json.dumps(payload, default=str),
    }

    maxlen = _TRIM_POLICIES.get(stream, 5000)

    try:
        r = _get_redis()
        entry_id = r.xadd(stream, entry, maxlen=maxlen, approximate=True)
        return entry_id
    except Exception:
        logger.warning(
            "Bus publish failed: stream=%s type=%s", stream, msg_type,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Consumer group management
# ---------------------------------------------------------------------------

def ensure_consumer_groups() -> None:
    """Create consumer groups for all streams (idempotent).

    Call once during lifespan startup. Uses ``mkstream=True`` so that
    streams are created even if no messages have been published yet.
    """
    r = _get_redis()
    for stream in ALL_STREAMS:
        try:
            r.xgroup_create(stream, CONSUMER_GROUP, id="0", mkstream=True)
            logger.info("Consumer group '%s' created on %s", CONSUMER_GROUP, stream)
        except redis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # Group already exists — expected on restart
            else:
                logger.warning(
                    "Failed to create consumer group on %s: %s", stream, exc,
                )


# ---------------------------------------------------------------------------
# Consuming
# ---------------------------------------------------------------------------

def read_batch(
    stream: str,
    consumer_name: str,
    *,
    count: int = 10,
    block_ms: int = 2000,
) -> list[tuple[str, dict[str, str]]]:
    """Read a batch of new messages from a consumer group.

    Uses XREADGROUP with BLOCK for efficient polling.
    Returns list of (entry_id, fields_dict) tuples.
    """
    r = _get_redis()
    try:
        result = r.xreadgroup(
            CONSUMER_GROUP,
            consumer_name,
            {stream: ">"},
            count=count,
            block=block_ms,
        )
        if not result:
            return []
        # result is [(stream_name, [(entry_id, fields), ...])]
        return result[0][1]
    except Exception:
        logger.warning(
            "Bus read failed: stream=%s consumer=%s", stream, consumer_name,
            exc_info=True,
        )
        return []


def read_multi(
    streams: list[str],
    consumer_name: str,
    *,
    count: int = 10,
    block_ms: int = 2000,
) -> list[tuple[str, str, dict[str, str]]]:
    """Read from multiple streams at once.

    Returns list of (stream, entry_id, fields) tuples.
    """
    r = _get_redis()
    try:
        stream_ids = {s: ">" for s in streams}
        result = r.xreadgroup(
            CONSUMER_GROUP,
            consumer_name,
            stream_ids,
            count=count,
            block=block_ms,
        )
        if not result:
            return []
        entries = []
        for stream_name, messages in result:
            for entry_id, fields in messages:
                entries.append((stream_name, entry_id, fields))
        return entries
    except Exception:
        logger.warning("Bus read_multi failed", exc_info=True)
        return []


def ack(stream: str, *entry_ids: str) -> int:
    """Acknowledge processed messages in the consumer group.

    Returns the number of messages acknowledged.
    """
    if not entry_ids:
        return 0
    r = _get_redis()
    try:
        return r.xack(stream, CONSUMER_GROUP, *entry_ids)
    except Exception:
        logger.warning(
            "Bus ack failed: stream=%s ids=%s", stream, entry_ids,
            exc_info=True,
        )
        return 0


def claim_stale(
    stream: str,
    consumer_name: str,
    min_idle_ms: int = 60_000,
    count: int = 10,
) -> list[tuple[str, dict[str, str]]]:
    """Claim messages pending too long (dead letter recovery).

    Uses XAUTOCLAIM to find and reclaim messages that another consumer
    failed to acknowledge within *min_idle_ms*.
    """
    r = _get_redis()
    try:
        # XAUTOCLAIM returns (next_start_id, [(entry_id, fields), ...], deleted_ids)
        _, entries, _ = r.xautoclaim(
            stream,
            CONSUMER_GROUP,
            consumer_name,
            min_idle_time=min_idle_ms,
            count=count,
        )
        if entries:
            logger.info(
                "Claimed %d stale messages from %s (idle > %dms)",
                len(entries), stream, min_idle_ms,
            )
        return entries
    except Exception:
        logger.warning("Bus claim_stale failed: stream=%s", stream, exc_info=True)
        return []


def pending_count(stream: str) -> int:
    """Get the number of pending (unacknowledged) messages for the consumer group."""
    r = _get_redis()
    try:
        info = r.xpending(stream, CONSUMER_GROUP)
        return info.get("pending", 0) if isinstance(info, dict) else 0
    except Exception:
        return 0
