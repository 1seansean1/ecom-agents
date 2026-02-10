"""Exponential backoff with jitter for API calls.

Retries on transient HTTP errors (429, 500, 502, 503, 504) and connection errors.
Respects Retry-After headers. Logs each retry attempt.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# HTTP status codes that trigger a retry
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 0.3,
) -> Callable:
    """Decorator: retry a function with exponential backoff + jitter.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        jitter: Jitter factor (0.0-1.0). Adds randomness to prevent thundering herd.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    if status not in RETRYABLE_STATUS_CODES or attempt == max_retries:
                        raise
                    last_exception = e
                    delay = _compute_delay(
                        attempt, base_delay, max_delay, jitter, e.response
                    )
                    logger.warning(
                        "Retry %d/%d for %s (HTTP %d), waiting %.1fs",
                        attempt + 1,
                        max_retries,
                        fn.__name__,
                        status,
                        delay,
                    )
                    time.sleep(delay)
                except (httpx.ConnectError, httpx.ReadTimeout, ConnectionError, OSError) as e:
                    if attempt == max_retries:
                        raise
                    last_exception = e
                    delay = _compute_delay(attempt, base_delay, max_delay, jitter)
                    logger.warning(
                        "Retry %d/%d for %s (connection error: %s), waiting %.1fs",
                        attempt + 1,
                        max_retries,
                        fn.__name__,
                        type(e).__name__,
                        delay,
                    )
                    time.sleep(delay)
            # Should not reach here, but just in case
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


def _compute_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: float,
    response: httpx.Response | None = None,
) -> float:
    """Compute delay with exponential backoff + jitter, respecting Retry-After."""
    # Check Retry-After header
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), max_delay)
            except ValueError:
                pass

    # Exponential backoff: base * 2^attempt
    delay = base_delay * (2**attempt)
    delay = min(delay, max_delay)

    # Add jitter
    jitter_amount = delay * jitter
    delay += random.uniform(-jitter_amount, jitter_amount)

    return max(0.1, delay)
