"""Idempotency store: prevents duplicate tool executions via Redis.

Uses SHA256 hash of (tool_name + sorted params) as the idempotency key.
Results are cached with a configurable TTL (default 1 hour).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import redis

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6381/0")


@dataclass
class CachedResult:
    """A previously-cached tool result."""

    key: str
    result: dict
    ttl_remaining: int


class IdempotencyStore:
    """Redis-backed idempotency store for tool calls."""

    PREFIX = "idem:"

    def __init__(self, redis_url: str | None = None):
        self._redis = redis.from_url(redis_url or _REDIS_URL, decode_responses=True)

    @staticmethod
    def generate_key(tool_name: str, params: dict[str, Any]) -> str:
        """Generate a deterministic idempotency key from tool name + params.

        Sorts params keys for consistency, then SHA256 hashes the result.
        """
        canonical = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"{tool_name}_{digest[:16]}"

    def check(self, key: str) -> CachedResult | None:
        """Check if a result exists for this key. Returns CachedResult or None."""
        full_key = f"{self.PREFIX}{key}"
        try:
            raw = self._redis.get(full_key)
            if raw is None:
                return None
            ttl = self._redis.ttl(full_key)
            result = json.loads(raw)
            logger.info("Idempotency cache HIT for %s (TTL=%ds)", key, ttl)
            return CachedResult(key=key, result=result, ttl_remaining=max(ttl, 0))
        except Exception:
            logger.warning("Idempotency check failed for %s", key, exc_info=True)
            return None

    def store(self, key: str, result: dict, ttl: int = 3600) -> None:
        """Store a tool result with TTL (default 1 hour)."""
        full_key = f"{self.PREFIX}{key}"
        try:
            self._redis.setex(full_key, ttl, json.dumps(result, default=str))
            logger.info("Idempotency cache SET for %s (TTL=%ds)", key, ttl)
        except Exception:
            logger.warning("Idempotency store failed for %s", key, exc_info=True)

    def check_and_set(
        self, key: str, ttl: int = 3600
    ) -> CachedResult | None:
        """Check for cached result. If found, return it. If not, set a lock.

        Returns CachedResult if cached, None if this is a fresh call.
        The caller should execute the tool and then call store() with the result.
        """
        cached = self.check(key)
        if cached:
            return cached
        # Set a temporary lock to prevent concurrent duplicates
        lock_key = f"{self.PREFIX}lock:{key}"
        try:
            acquired = self._redis.set(lock_key, "1", nx=True, ex=60)
            if not acquired:
                # Another call is in progress — wait briefly and check again
                import time
                time.sleep(0.5)
                return self.check(key)
        except Exception:
            logger.warning("Lock acquisition failed for %s", key, exc_info=True)
        return None

    def invalidate(self, key: str) -> None:
        """Remove a cached result."""
        try:
            self._redis.delete(f"{self.PREFIX}{key}")
            self._redis.delete(f"{self.PREFIX}lock:{key}")
        except Exception:
            logger.warning("Idempotency invalidate failed for %s", key, exc_info=True)


# Module-level singleton
_store: IdempotencyStore | None = None


def get_idempotency_store() -> IdempotencyStore:
    """Get or create the singleton IdempotencyStore."""
    global _store
    if _store is None:
        _store = IdempotencyStore()
    return _store
