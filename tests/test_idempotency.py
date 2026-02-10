"""Tests for the idempotency store."""

import pytest
from unittest.mock import MagicMock, patch

from src.tools.idempotency import IdempotencyStore


def test_generate_key_deterministic():
    """Same params should produce the same key."""
    key1 = IdempotencyStore.generate_key("stripe_create_product", {"name": "Tee", "price": 2999})
    key2 = IdempotencyStore.generate_key("stripe_create_product", {"name": "Tee", "price": 2999})
    assert key1 == key2


def test_generate_key_different_params():
    """Different params should produce different keys."""
    key1 = IdempotencyStore.generate_key("stripe_create_product", {"name": "Tee A", "price": 2999})
    key2 = IdempotencyStore.generate_key("stripe_create_product", {"name": "Tee B", "price": 2999})
    assert key1 != key2


def test_generate_key_order_independent():
    """Key should be the same regardless of param order."""
    key1 = IdempotencyStore.generate_key("test", {"a": 1, "b": 2})
    key2 = IdempotencyStore.generate_key("test", {"b": 2, "a": 1})
    assert key1 == key2


def test_generate_key_includes_tool_name():
    """Different tools with same params should have different keys."""
    key1 = IdempotencyStore.generate_key("tool_a", {"x": 1})
    key2 = IdempotencyStore.generate_key("tool_b", {"x": 1})
    assert key1 != key2
