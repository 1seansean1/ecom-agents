"""Webhook idempotency — Redis-based deduplication.

Security contract:
- Tracks webhook IDs in Redis with 24h TTL
- Duplicate webhooks are rejected with 200 (not error — provider retries on errors)
- Key pattern: webhook:seen:{provider}:{webhook_id}
- If Redis is down, falls back to allowing (fail-open for availability)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEDUP_TTL_SECONDS = 86400  # 24 hours

# Key prefix for webhook dedup
_KEY_PREFIX = "webhook:seen"


def _get_redis():
    """Get Redis client (reuses medium-term memory client)."""
    import redis as redis_lib

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6381/0")
    return redis_lib.from_url(redis_url, decode_responses=True)


def is_duplicate(provider: str, webhook_id: str) -> bool:
    """Check if this webhook has already been processed.

    Uses Redis SETNX (set-if-not-exists) for atomic check-and-mark.

    Args:
        provider: Webhook provider (shopify, stripe, printful)
        webhook_id: Unique webhook/event ID from provider

    Returns:
        True if this webhook has already been seen (duplicate)
    """
    if not webhook_id:
        return False  # No ID = can't dedup, allow through

    key = f"{_KEY_PREFIX}:{provider}:{webhook_id}"

    try:
        r = _get_redis()
        # SETNX returns True if key was set (new), False if key already existed (dup)
        was_set = r.set(key, "1", nx=True, ex=_DEDUP_TTL_SECONDS)
        if not was_set:
            logger.info("Duplicate webhook rejected: %s/%s", provider, webhook_id)
            return True
        return False
    except Exception:
        # Redis down — fail open for availability (allow webhook through)
        logger.warning(
            "Redis unavailable for webhook dedup — allowing %s/%s",
            provider,
            webhook_id,
            exc_info=True,
        )
        return False


def mark_seen(provider: str, webhook_id: str) -> None:
    """Explicitly mark a webhook as seen (used after successful processing).

    This is a fallback for cases where is_duplicate wasn't called first.
    """
    if not webhook_id:
        return

    key = f"{_KEY_PREFIX}:{provider}:{webhook_id}"
    try:
        r = _get_redis()
        r.set(key, "1", ex=_DEDUP_TTL_SECONDS)
    except Exception:
        logger.warning("Failed to mark webhook as seen: %s/%s", provider, webhook_id)
