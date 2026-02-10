"""Fallback chain wrapper: wraps each model with ordered fallbacks.

Phase 18b enhancements (openclaw-inspired):
- Error classification (rate_limit, auth_failure, server_error, timeout)
- Audit logging of fallback decisions
- Provider health tracking with backoff
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.llm.config import FALLBACK_CHAINS, ModelID
from src.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class ErrorClass(str, Enum):
    """Classification of LLM provider errors."""

    RATE_LIMIT = "rate_limit"       # 429 — backoff same provider
    AUTH_FAILURE = "auth_failure"    # 401/403 — skip provider until key rotated
    SERVER_ERROR = "server_error"    # 500/502/503 — try next provider
    TIMEOUT = "timeout"             # Request timeout — try next provider
    MODEL_ERROR = "model_error"     # Invalid model, bad request — skip provider
    UNKNOWN = "unknown"             # Unclassified — try next provider


@dataclass
class FallbackEvent:
    """Record of a single fallback decision."""

    timestamp: float
    primary_model: str
    fallback_model: str | None
    error_class: ErrorClass
    error_message: str
    success: bool


@dataclass
class ProviderHealth:
    """Tracks per-provider error state for backoff decisions."""

    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    last_error_class: ErrorClass | None = None
    backoff_until: float = 0.0  # Don't retry before this timestamp

    def record_failure(self, error_class: ErrorClass) -> None:
        """Record a failure and compute backoff."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        self.last_error_class = error_class

        # Exponential backoff: 2^n seconds, capped at 300s (5 min)
        backoff_seconds = min(2 ** self.consecutive_failures, 300)

        # Auth failures get longer backoff (key needs rotation)
        if error_class == ErrorClass.AUTH_FAILURE:
            backoff_seconds = max(backoff_seconds, 600)  # 10 min minimum

        self.backoff_until = time.time() + backoff_seconds

    def record_success(self) -> None:
        """Reset health on successful call."""
        self.consecutive_failures = 0
        self.backoff_until = 0.0
        self.last_error_class = None

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently available (not in backoff)."""
        return time.time() >= self.backoff_until


class FallbackAuditLog:
    """In-memory audit log of fallback events.

    Capped at 1000 entries for memory safety.
    """

    MAX_ENTRIES = 1000

    def __init__(self) -> None:
        self._events: list[FallbackEvent] = []

    def record(self, event: FallbackEvent) -> None:
        """Record a fallback event."""
        self._events.append(event)
        if len(self._events) > self.MAX_ENTRIES:
            self._events = self._events[-self.MAX_ENTRIES:]

    def recent(self, hours: int = 24) -> list[FallbackEvent]:
        """Get events from the last N hours."""
        cutoff = time.time() - (hours * 3600)
        return [e for e in self._events if e.timestamp >= cutoff]

    def summary(self, hours: int = 24) -> dict[str, Any]:
        """Get summary stats for the last N hours."""
        events = self.recent(hours)
        if not events:
            return {"total_fallbacks": 0, "success_rate": 1.0, "by_error_class": {}}

        total = len(events)
        successes = sum(1 for e in events if e.success)
        by_class: dict[str, int] = {}
        for e in events:
            by_class[e.error_class.value] = by_class.get(e.error_class.value, 0) + 1

        return {
            "total_fallbacks": total,
            "success_rate": successes / total if total else 1.0,
            "by_error_class": by_class,
        }


# Module-level singletons
_provider_health: dict[str, ProviderHealth] = {}
_audit_log = FallbackAuditLog()


def get_provider_health(provider: str) -> ProviderHealth:
    """Get or create health tracker for a provider."""
    if provider not in _provider_health:
        _provider_health[provider] = ProviderHealth()
    return _provider_health[provider]


def get_fallback_audit_log() -> FallbackAuditLog:
    """Get the module-level fallback audit log."""
    return _audit_log


def classify_error(error: Exception) -> ErrorClass:
    """Classify an LLM error into an error class.

    Inspects exception type and message to determine retry strategy.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Rate limit errors
    if "429" in error_str or "rate" in error_str and "limit" in error_str:
        return ErrorClass.RATE_LIMIT
    if "too many requests" in error_str:
        return ErrorClass.RATE_LIMIT
    if "RateLimitError" in error_type:
        return ErrorClass.RATE_LIMIT

    # Auth errors
    if "401" in error_str or "403" in error_str:
        return ErrorClass.AUTH_FAILURE
    if "authentication" in error_str or "unauthorized" in error_str:
        return ErrorClass.AUTH_FAILURE
    if "invalid api key" in error_str or "invalid_api_key" in error_str:
        return ErrorClass.AUTH_FAILURE
    if "AuthenticationError" in error_type:
        return ErrorClass.AUTH_FAILURE

    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return ErrorClass.TIMEOUT
    if "TimeoutError" in error_type or "ConnectTimeout" in error_type:
        return ErrorClass.TIMEOUT
    if "ReadTimeout" in error_type:
        return ErrorClass.TIMEOUT

    # Server errors
    if any(code in error_str for code in ("500", "502", "503", "504")):
        return ErrorClass.SERVER_ERROR
    if "server" in error_str and "error" in error_str:
        return ErrorClass.SERVER_ERROR
    if "InternalServerError" in error_type:
        return ErrorClass.SERVER_ERROR

    # Model errors (bad request, invalid model)
    if "400" in error_str or "bad request" in error_str:
        return ErrorClass.MODEL_ERROR
    if "model" in error_str and ("not found" in error_str or "invalid" in error_str):
        return ErrorClass.MODEL_ERROR

    return ErrorClass.UNKNOWN


def get_model_with_fallbacks(
    router: LLMRouter,
    model_id: ModelID,
) -> BaseChatModel:
    """Wrap a model with its fallback chain using LangChain's with_fallbacks().

    If primary model fails, automatically tries the next model in the chain.
    """
    primary = router.get_model(model_id)
    fallback_ids = FALLBACK_CHAINS.get(model_id, [])

    if not fallback_ids:
        return primary

    fallbacks = []
    for fb_id in fallback_ids:
        try:
            fallbacks.append(router.get_model(fb_id))
        except Exception:
            logger.warning("Could not create fallback model %s", fb_id)

    if not fallbacks:
        return primary

    return primary.with_fallbacks(fallbacks)


async def invoke_with_fallback(
    router: LLMRouter,
    model_id: ModelID,
    messages: list,
    **kwargs: Any,
) -> Any:
    """Invoke a model with fallback chain, error classification, and audit logging.

    Unlike get_model_with_fallbacks() which uses LangChain's built-in fallback,
    this function provides richer error handling:
    - Classifies errors to determine retry strategy
    - Tracks provider health with exponential backoff
    - Logs fallback decisions to audit trail
    - Skips providers in backoff period

    Returns the response from the first successful model.
    Raises the last error if all models fail.
    """
    from src.llm.config import MODEL_REGISTRY

    chain = [model_id] + FALLBACK_CHAINS.get(model_id, [])
    last_error: Exception | None = None

    for i, mid in enumerate(chain):
        spec = MODEL_REGISTRY.get(mid)
        if spec is None:
            continue

        health = get_provider_health(spec.provider)

        # Skip providers in backoff
        if not health.is_available:
            logger.info(
                "Skipping %s (provider %s in backoff until %.0f)",
                mid.value,
                spec.provider,
                health.backoff_until,
            )
            continue

        try:
            model = router.get_model(mid)
            result = await model.ainvoke(messages, **kwargs)

            # Record success
            health.record_success()

            # Log fallback if we're not on the primary
            if i > 0:
                _audit_log.record(FallbackEvent(
                    timestamp=time.time(),
                    primary_model=model_id.value,
                    fallback_model=mid.value,
                    error_class=classify_error(last_error) if last_error else ErrorClass.UNKNOWN,
                    error_message=str(last_error) if last_error else "",
                    success=True,
                ))
                logger.info(
                    "Fallback succeeded: %s -> %s",
                    model_id.value,
                    mid.value,
                )

            return result

        except Exception as e:
            last_error = e
            error_class = classify_error(e)
            health.record_failure(error_class)

            logger.warning(
                "Model %s (provider %s) failed: [%s] %s",
                mid.value,
                spec.provider,
                error_class.value,
                str(e)[:200],  # Truncate to avoid logging secrets
            )

            # Log the fallback attempt
            next_model = chain[i + 1].value if i + 1 < len(chain) else None
            _audit_log.record(FallbackEvent(
                timestamp=time.time(),
                primary_model=model_id.value,
                fallback_model=next_model,
                error_class=error_class,
                error_message=str(e)[:200],
                success=False,
            ))

    # All models failed
    raise last_error  # type: ignore[misc]
