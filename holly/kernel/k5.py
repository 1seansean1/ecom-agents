"""K5 - Idempotency key generation gate (Task 17.3).

Generates deterministic RFC 8785 (JSON Canonicalization Scheme) keys from
operation payloads, enabling idempotency checks and deduplication across
retries.

Algorithm (Behavior Spec §1.6):

1. **Canonicalize** payload to RFC 8785 canonical form (sorted keys,
   no whitespace, UTF-8 encoding) using the ``jcs`` library.
2. **Hash** the canonical bytes with SHA-256.
3. **Return** the 64-character lowercase hex digest as the idempotency key.

TLA+ invariant (Task 14.1):

- ``Determinism``: same payload always produces the same key.
- ``CollisionResistance``: SHA-256 collision probability < 2^-256 per pair.
- ``NoSideEffects``: key generation does not mutate any registry or store.

The idempotency store (``IdempotencyStore`` protocol) is intentionally
backend-agnostic: ``InMemoryIdempotencyStore`` serves testing and
single-process use; production deployment uses a Redis distributed set
(future slice).
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import jcs

from holly.kernel.exceptions import CanonicalizeError, DuplicateRequestError

if TYPE_CHECKING:
    from holly.kernel.context import KernelContext

Gate = Callable[["KernelContext"], Awaitable[None]]

_SHA256_HEX_LEN: int = 64  # SHA-256 digest yields 32 bytes = 64 hex chars


# ---------------------------------------------------------------------------
# IdempotencyStore protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IdempotencyStore(Protocol):
    """Protocol for idempotency key deduplication stores.

    Implementations must provide atomic ``check_and_mark`` semantics for
    their concurrency model: in-memory for single-process, Redis SETNX /
    sorted-set for distributed deployments.
    """

    def check_and_mark(self, key: str) -> bool:
        """Atomically check whether *key* is new and mark it as seen.

        Args:
            key: 64-char SHA-256 hex idempotency key.

        Returns:
            ``True`` if the key is new (first occurrence).
            ``False`` if the key has been seen before (duplicate).
        """
        ...


# ---------------------------------------------------------------------------
# InMemoryIdempotencyStore
# ---------------------------------------------------------------------------


class InMemoryIdempotencyStore:
    """In-memory idempotency store for single-process use and testing.

    Not thread-safe. For multi-threaded or distributed use, employ
    locking or replace with a Redis-backed implementation.

    Attributes
    ----------
    _seen : set[str]
        Set of idempotency keys recorded since instantiation.
    """

    __slots__ = ("_seen",)

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_and_mark(self, key: str) -> bool:
        """Return ``True`` if *key* is new; mark and return ``False`` if duplicate.

        Args:
            key: 64-char SHA-256 hex idempotency key.

        Returns:
            ``True`` on first call with this key; ``False`` on subsequent calls.
        """
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


# ---------------------------------------------------------------------------
# k5_generate_key
# ---------------------------------------------------------------------------


def k5_generate_key(payload: Any) -> str:
    """Generate a 64-char SHA-256 hex idempotency key via RFC 8785.

    The function is a pure computation with no side effects (satisfies
    Behavior Spec §1.1 INV-4 and TLA+ ``NoSideEffects``).

    RFC 8785 rules applied by ``jcs.canonicalize``:

    - Object members ordered lexicographically by key (UTF-8 codepoint order).
    - No whitespace (no spaces, newlines, or tabs).
    - All strings use double quotes; Unicode escapes normalized.
    - Numbers in decimal form.
    - Arrays preserve element order.
    - ``null``, ``true``, ``false`` rendered verbatim.

    Args:
        payload: JSON-serializable value (``dict``, ``list``, ``str``,
                 ``int``, ``float``, ``bool``). ``None`` is explicitly
                 rejected to prevent silent null-key collisions.

    Returns:
        64-character lowercase hexadecimal string (SHA-256 of RFC 8785
        canonical JSON bytes).

    Raises:
        ValueError: *payload* is ``None``.
        CanonicalizeError: *payload* contains a non-JSON-serializable type
                           (e.g., ``datetime``, custom objects) or jcs raises
                           an unexpected error.

    Examples:
        >>> k5_generate_key({"b": 2, "a": 1}) == k5_generate_key({"a": 1, "b": 2})
        True
        >>> import re
        >>> bool(re.fullmatch(r"[a-f0-9]{64}", k5_generate_key({"x": 1})))
        True
    """
    if payload is None:
        raise ValueError("Payload must not be None; got None")
    try:
        canonical: bytes = jcs.canonicalize(payload)
    except TypeError as exc:
        raise CanonicalizeError(
            f"Non-JSON-serializable type in payload: {exc}"
        ) from exc
    except Exception as exc:
        raise CanonicalizeError(f"Unexpected canonicalization error: {exc}") from exc
    digest = hashlib.sha256(canonical).hexdigest()
    assert len(digest) == _SHA256_HEX_LEN  # invariant: SHA-256 always 64 hex chars
    return digest


# ---------------------------------------------------------------------------
# k5_gate
# ---------------------------------------------------------------------------


def k5_gate(
    *,
    payload: Any,
    store: IdempotencyStore,
) -> Gate:
    """Return a Gate that enforces request idempotency.

    The gate executes the following sequence inside ``KernelContext``:

    1. Generate the idempotency key via ``k5_generate_key(payload)``.
    2. Call ``store.check_and_mark(key)`` atomically.
    3. If duplicate (returns ``False``): raise ``DuplicateRequestError``.
       ``KernelContext`` transitions ENTERING -> FAULTED -> IDLE.
    4. If new (returns ``True``): proceed; gate returns without raising.

    TLA+ liveness: all execution paths reach IDLE (via success or FAULTED).

    Args:
        payload: The operation payload to generate the idempotency key from.
                 Evaluated at gate-call time (not at factory call time),
                 so the same gate instance can be composed with others.
        store: An ``IdempotencyStore`` instance for deduplication.

    Returns:
        An async ``Gate`` callable compatible with ``KernelContext``.

    Raises:
        ValueError: *payload* is ``None`` (propagated from ``k5_generate_key``).
        CanonicalizeError: Canonicalization of *payload* fails.
        DuplicateRequestError: *key* has already been recorded in *store*.
    """

    async def _k5_gate(ctx: KernelContext) -> None:
        key = k5_generate_key(payload)
        is_new = store.check_and_mark(key)
        if not is_new:
            raise DuplicateRequestError(key)

    return _k5_gate
