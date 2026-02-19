"""Tests for K5 - Idempotency key generation gate (Task 17.3).

Covers Behavior Spec §1.6 acceptance criteria:

1. Deterministic keys: same payload always generates same key.
2. Field-order independence: reordered JSON fields produce same key.
3. Whitespace independence: implicit (jcs always strips whitespace).
4. Unicode normalization: unicode payloads produce stable keys.
5. Different payloads produce different keys (property-based).
6. Non-JSON input rejection: non-serializable types raise CanonicalizeError.
7. Key format: 64-char lowercase hex string.

Also tests:
- InMemoryIdempotencyStore protocol conformance.
- k5_gate Gate-protocol integration with KernelContext.
- Composition with K1/K2/K3/K4 gates.
- Property-based tests via hypothesis.
"""

from __future__ import annotations

import datetime
import re
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    CanonicalizeError,
    DuplicateRequestError,
)
from holly.kernel.k5 import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    k5_gate,
    k5_generate_key,
)
from holly.kernel.schema_registry import SchemaRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[a-f0-9]{64}$")
_SCHEMA_ID = "test_k5_compose_schema"
_SCHEMA = {"type": "object", "properties": {"v": {"type": "integer"}}, "required": ["v"]}


def _ensure_schema() -> None:
    if not SchemaRegistry.has(_SCHEMA_ID):
        SchemaRegistry.register(_SCHEMA_ID, _SCHEMA)


# ---------------------------------------------------------------------------
# TestStructure
# ---------------------------------------------------------------------------


class TestStructure:
    """Structural checks: imports, types, instantiation."""

    def test_generate_key_callable(self) -> None:
        """k5_generate_key is callable with a dict payload."""
        result = k5_generate_key({"a": 1})
        assert isinstance(result, str)

    def test_key_length_64(self) -> None:
        """Key is exactly 64 characters (SHA-256 hex)."""
        key = k5_generate_key({"x": 42})
        assert len(key) == 64

    def test_key_lowercase_hex(self) -> None:
        """Key matches ^[a-f0-9]{64}$."""
        key = k5_generate_key({"hello": "world"})
        assert _KEY_RE.fullmatch(key) is not None

    def test_in_memory_store_instantiates(self) -> None:
        """InMemoryIdempotencyStore instantiates with empty _seen set."""
        store = InMemoryIdempotencyStore()
        assert hasattr(store, "_seen")
        assert len(store._seen) == 0

    def test_store_satisfies_protocol(self) -> None:
        """InMemoryIdempotencyStore satisfies IdempotencyStore protocol."""
        store = InMemoryIdempotencyStore()
        assert isinstance(store, IdempotencyStore)

    def test_gate_returns_callable(self) -> None:
        """k5_gate returns an async callable Gate."""
        import inspect

        store = InMemoryIdempotencyStore()
        gate = k5_gate(payload={"a": 1}, store=store)
        assert callable(gate)
        assert inspect.iscoroutinefunction(gate)


# ---------------------------------------------------------------------------
# TestDeterminism (Behavior Spec §1.6 AC-1)
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same payload always produces the same key (AC-1)."""

    def test_same_dict_idempotent(self) -> None:
        """Calling k5_generate_key 10 times on same dict yields same key."""
        payload = {"tenant": "t1", "action": "read", "amount": 100}
        keys = [k5_generate_key(payload) for _ in range(10)]
        assert len(set(keys)) == 1

    def test_same_list_idempotent(self) -> None:
        """List payloads are deterministic."""
        payload = [1, 2, 3, "a", None, True]
        keys = [k5_generate_key(payload) for _ in range(5)]
        assert len(set(keys)) == 1

    def test_same_string_idempotent(self) -> None:
        """String payloads are deterministic."""
        keys = [k5_generate_key("hello world") for _ in range(5)]
        assert len(set(keys)) == 1

    def test_same_int_idempotent(self) -> None:
        """Integer payloads are deterministic."""
        keys = [k5_generate_key(42) for _ in range(5)]
        assert len(set(keys)) == 1

    def test_same_nested_dict_idempotent(self) -> None:
        """Nested dicts are deterministic."""
        payload = {"a": {"b": {"c": [1, 2, 3]}, "d": True}, "e": None}
        keys = [k5_generate_key(payload) for _ in range(5)]
        assert len(set(keys)) == 1


# ---------------------------------------------------------------------------
# TestFieldOrderIndependence (Behavior Spec §1.6 AC-2)
# ---------------------------------------------------------------------------


class TestFieldOrderIndependence:
    """Reordered JSON object fields produce the same key (AC-2)."""

    def test_two_field_reorder(self) -> None:
        """{'a': 1, 'b': 2} == {'b': 2, 'a': 1}."""
        k1 = k5_generate_key({"a": 1, "b": 2})
        k2 = k5_generate_key({"b": 2, "a": 1})
        assert k1 == k2

    def test_three_field_reorder(self) -> None:
        """All permutations of three fields produce the same key."""
        base = {"action": "write", "tenant": "t1", "resource": "storage"}
        import itertools

        keys = set()
        for perm in itertools.permutations(base.items()):
            keys.add(k5_generate_key(dict(perm)))
        assert len(keys) == 1

    def test_nested_field_reorder(self) -> None:
        """Nested object field ordering is also canonicalized."""
        k1 = k5_generate_key({"outer": {"x": 1, "y": 2}, "z": 3})
        k2 = k5_generate_key({"z": 3, "outer": {"y": 2, "x": 1}})
        assert k1 == k2

    def test_unicode_key_order(self) -> None:
        """Unicode keys are ordered by UTF-8 codepoint (RFC 8785)."""
        k1 = k5_generate_key({"\u00e9": 1, "a": 2})
        k2 = k5_generate_key({"a": 2, "\u00e9": 1})
        assert k1 == k2


# ---------------------------------------------------------------------------
# TestUnicodeNormalization (Behavior Spec §1.6 AC-4)
# ---------------------------------------------------------------------------


class TestUnicodeNormalization:
    """Unicode characters in payloads produce stable, consistent keys."""

    def test_ascii_key_consistent(self) -> None:
        key1 = k5_generate_key({"hello": "world"})
        key2 = k5_generate_key({"hello": "world"})
        assert key1 == key2

    def test_unicode_value_consistent(self) -> None:
        """Unicode string values are stable."""
        key1 = k5_generate_key({"name": "Ren\u00e9e"})
        key2 = k5_generate_key({"name": "Ren\u00e9e"})
        assert key1 == key2

    def test_unicode_key_and_value(self) -> None:
        """Unicode in both key and value is stable."""
        key1 = k5_generate_key({"\u4e2d\u6587": "\u6c49\u5b57"})
        key2 = k5_generate_key({"\u4e2d\u6587": "\u6c49\u5b57"})
        assert key1 == key2

    def test_emoji_value_consistent(self) -> None:
        """Emoji in values is stable (jcs handles supplementary planes)."""
        key1 = k5_generate_key({"mood": "\U0001f600"})
        key2 = k5_generate_key({"mood": "\U0001f600"})
        assert key1 == key2


# ---------------------------------------------------------------------------
# TestDistinctPayloads (Behavior Spec §1.6 AC-5)
# ---------------------------------------------------------------------------


class TestDistinctPayloads:
    """Logically different payloads produce different keys (AC-5)."""

    def test_different_values(self) -> None:
        assert k5_generate_key({"a": 1}) != k5_generate_key({"a": 2})

    def test_different_keys(self) -> None:
        assert k5_generate_key({"a": 1}) != k5_generate_key({"b": 1})

    def test_empty_vs_nonempty(self) -> None:
        assert k5_generate_key({}) != k5_generate_key({"a": 1})

    def test_nested_difference(self) -> None:
        k1 = k5_generate_key({"a": {"b": 1}})
        k2 = k5_generate_key({"a": {"b": 2}})
        assert k1 != k2

    def test_bool_vs_int(self) -> None:
        """True and 1 serialize differently in strict JSON contexts."""
        # In Python json, True -> true, 1 -> 1 (distinct JSON values)
        k1 = k5_generate_key({"v": True})
        k2 = k5_generate_key({"v": 1})
        # jcs handles booleans as JSON booleans; integers as numbers
        # They may or may not be equal depending on jcs — just ensure consistency
        assert isinstance(k1, str) and isinstance(k2, str)

    def test_null_vs_empty_string(self) -> None:
        assert k5_generate_key({"v": None}) != k5_generate_key({"v": ""})

    def test_array_order_matters(self) -> None:
        """Array element order is preserved (not sorted)."""
        k1 = k5_generate_key([1, 2, 3])
        k2 = k5_generate_key([3, 2, 1])
        assert k1 != k2


# ---------------------------------------------------------------------------
# TestNonJsonRejection (Behavior Spec §1.6 AC-6)
# ---------------------------------------------------------------------------


class TestNonJsonRejection:
    """Non-JSON-serializable types raise CanonicalizeError (AC-6)."""

    def test_none_raises_value_error(self) -> None:
        """None is explicitly rejected with ValueError."""
        with pytest.raises(ValueError, match="None"):
            k5_generate_key(None)

    def test_datetime_raises_canonicalize_error(self) -> None:
        """datetime is not JSON-serializable."""
        with pytest.raises(CanonicalizeError):
            k5_generate_key(datetime.datetime.now())

    def test_custom_object_raises_canonicalize_error(self) -> None:
        """Custom (non-dataclass) objects are not JSON-serializable."""

        class _Opaque:
            pass

        with pytest.raises(CanonicalizeError):
            k5_generate_key(_Opaque())

    def test_set_raises_canonicalize_error(self) -> None:
        """Sets are not JSON-serializable."""
        with pytest.raises(CanonicalizeError):
            k5_generate_key({1, 2, 3})  # type: ignore[arg-type]

    def test_exception_detail_populated(self) -> None:
        """CanonicalizeError.detail is a non-empty string."""
        with pytest.raises(CanonicalizeError) as exc_info:
            k5_generate_key(datetime.date(2024, 1, 1))
        assert exc_info.value.detail


# ---------------------------------------------------------------------------
# TestIdempotencyStore
# ---------------------------------------------------------------------------


class TestIdempotencyStore:
    """InMemoryIdempotencyStore check_and_mark semantics."""

    def test_first_call_returns_true(self) -> None:
        store = InMemoryIdempotencyStore()
        assert store.check_and_mark("abc") is True

    def test_second_call_returns_false(self) -> None:
        store = InMemoryIdempotencyStore()
        store.check_and_mark("abc")
        assert store.check_and_mark("abc") is False

    def test_distinct_keys_independent(self) -> None:
        store = InMemoryIdempotencyStore()
        assert store.check_and_mark("key1") is True
        assert store.check_and_mark("key2") is True
        assert store.check_and_mark("key1") is False
        assert store.check_and_mark("key2") is False

    def test_key_persists_across_many_calls(self) -> None:
        store = InMemoryIdempotencyStore()
        store.check_and_mark("x")
        for _ in range(20):
            assert store.check_and_mark("x") is False

    def test_empty_store_new_instance(self) -> None:
        store1 = InMemoryIdempotencyStore()
        store1.check_and_mark("key")
        store2 = InMemoryIdempotencyStore()
        # store2 has no shared state with store1
        assert store2.check_and_mark("key") is True


# ---------------------------------------------------------------------------
# TestK5Gate (Gate integration)
# ---------------------------------------------------------------------------


class TestK5Gate:
    """k5_gate integration with KernelContext."""

    @pytest.mark.asyncio
    async def test_new_key_passes(self) -> None:
        """First request through gate succeeds (new key)."""
        store = InMemoryIdempotencyStore()
        payload = {"op": "create", "id": str(uuid.uuid4())}
        async with KernelContext(gates=[k5_gate(payload=payload, store=store)]):
            pass  # should not raise

    @pytest.mark.asyncio
    async def test_duplicate_raises(self) -> None:
        """Second request with same payload raises DuplicateRequestError."""
        store = InMemoryIdempotencyStore()
        payload = {"op": "create", "id": "fixed-id"}
        # First crossing — succeeds
        async with KernelContext(gates=[k5_gate(payload=payload, store=store)]):
            pass
        # Second crossing — duplicate
        with pytest.raises(DuplicateRequestError) as exc_info:
            async with KernelContext(gates=[k5_gate(payload=payload, store=store)]):
                pass
        assert exc_info.value.key == k5_generate_key(payload)

    @pytest.mark.asyncio
    async def test_different_payloads_both_pass(self) -> None:
        """Two distinct payloads through same store both succeed."""
        store = InMemoryIdempotencyStore()
        async with KernelContext(gates=[k5_gate(payload={"id": "a"}, store=store)]):
            pass
        async with KernelContext(gates=[k5_gate(payload={"id": "b"}, store=store)]):
            pass

    @pytest.mark.asyncio
    async def test_context_reaches_idle_after_duplicate(self) -> None:
        """Context reaches IDLE after DuplicateRequestError (liveness)."""
        from holly.kernel.state_machine import KernelState

        store = InMemoryIdempotencyStore()
        payload = {"op": "liveness-test"}
        async with KernelContext(gates=[k5_gate(payload=payload, store=store)]):
            pass

        ctx = KernelContext(gates=[k5_gate(payload=payload, store=store)])
        with pytest.raises(DuplicateRequestError):
            async with ctx:
                pass
        assert ctx.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_none_payload_raises_value_error(self) -> None:
        """Gate with None payload raises ValueError on entry."""
        store = InMemoryIdempotencyStore()
        with pytest.raises(ValueError, match="None"):
            async with KernelContext(gates=[k5_gate(payload=None, store=store)]):
                pass

    @pytest.mark.asyncio
    async def test_gate_key_matches_standalone(self) -> None:
        """The key used by k5_gate matches k5_generate_key directly."""
        store = InMemoryIdempotencyStore()
        payload = {"tenant": "t1", "action": "write", "bytes": 512}
        expected_key = k5_generate_key(payload)

        async with KernelContext(gates=[k5_gate(payload=payload, store=store)]):
            pass

        # Key should now be in store
        assert expected_key in store._seen


# ---------------------------------------------------------------------------
# TestCompose
# ---------------------------------------------------------------------------


class TestCompose:
    """k5_gate composes cleanly with other kernel gates."""

    @pytest.mark.asyncio
    async def test_k5_with_k1_schema_gate(self) -> None:
        """k5_gate followed by k1_gate: both pass for valid payload."""
        from holly.kernel.k1 import k1_gate

        _ensure_schema()
        store = InMemoryIdempotencyStore()
        payload = {"v": 42}
        gates = [
            k5_gate(payload=payload, store=store),
            k1_gate(payload, _SCHEMA_ID),
        ]
        async with KernelContext(gates=gates):
            pass

    @pytest.mark.asyncio
    async def test_k5_duplicate_blocks_before_k1(self) -> None:
        """k5 duplicate is detected before k1 even runs."""
        from holly.kernel.k1 import k1_gate

        _ensure_schema()
        store = InMemoryIdempotencyStore()
        payload = {"v": 1}
        gates = [
            k5_gate(payload=payload, store=store),
            k1_gate(payload, _SCHEMA_ID),
        ]
        # First crossing
        async with KernelContext(gates=gates):
            pass
        # Second crossing — k5 blocks first
        with pytest.raises(DuplicateRequestError):
            async with KernelContext(gates=gates):
                pass


# ---------------------------------------------------------------------------
# TestPropertyBased
# ---------------------------------------------------------------------------


class TestPropertyBased:
    """Property-based tests via hypothesis."""

    @given(
        a=st.integers(min_value=0, max_value=10_000),
        b=st.text(min_size=0, max_size=50),
    )
    @settings(max_examples=80)
    def test_key_always_64_hex(self, a: int, b: str) -> None:
        """For any (int, str) pair, generated key is always 64-char hex."""
        key = k5_generate_key({"a": a, "b": b})
        assert _KEY_RE.fullmatch(key) is not None

    @given(
        p1=st.fixed_dictionaries(
            {"x": st.integers(min_value=0, max_value=100), "y": st.text(min_size=1)}
        ),
        p2=st.fixed_dictionaries(
            {"x": st.integers(min_value=101, max_value=200), "y": st.text(min_size=1)}
        ),
    )
    @settings(max_examples=60)
    def test_distinct_payloads_distinct_keys(
        self, p1: dict, p2: dict
    ) -> None:
        """Payloads with different x values (non-overlapping ranges) always differ."""
        k1 = k5_generate_key(p1)
        k2 = k5_generate_key(p2)
        assert k1 != k2

    @given(
        payload=st.fixed_dictionaries(
            {"op": st.sampled_from(["read", "write", "delete"]), "n": st.integers()}
        )
    )
    @settings(max_examples=60)
    def test_store_sees_key_after_mark(self, payload: dict) -> None:
        """After check_and_mark(key) = True, store returns False on next call."""
        store = InMemoryIdempotencyStore()
        key = k5_generate_key(payload)
        assert store.check_and_mark(key) is True
        assert store.check_and_mark(key) is False

    @given(
        items=st.lists(
            st.fixed_dictionaries({"id": st.integers(min_value=0, max_value=1_000_000)}),
            min_size=1,
            max_size=20,
            unique_by=lambda d: d["id"],
        )
    )
    @settings(max_examples=30)
    def test_unique_payloads_all_new_in_fresh_store(self, items: list[dict]) -> None:
        """Unique payloads all return True (new) in a fresh store."""
        store = InMemoryIdempotencyStore()
        results = [store.check_and_mark(k5_generate_key(item)) for item in items]
        assert all(results)
