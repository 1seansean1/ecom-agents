"""Tests for webhook inbound system — Phase 19b.

Tests:
- Signature verification for Shopify, Stripe, Printful (constant-time HMAC)
- Idempotency (Redis-based dedup)
- Event parsing and dispatch
- Handler integration (full request flow)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.webhooks.dispatcher import (
    WebhookEvent,
    _sanitize_field,
    dispatch_event,
    parse_event,
)
from src.webhooks.verification import (
    verify_printful,
    verify_shopify,
    verify_stripe,
    verify_webhook,
)


# ── Signature Verification ────────────────────────────────────────────────


class TestShopifyVerification:
    """Shopify HMAC-SHA256 verification (base64-encoded)."""

    SECRET = "shopify-test-secret"

    def _sign(self, body: bytes) -> str:
        """Compute valid Shopify signature."""
        digest = hmac.new(self.SECRET.encode(), body, hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "shopify-test-secret")
    def test_valid_signature(self):
        body = b'{"id": 123, "topic": "orders/create"}'
        sig = self._sign(body)
        assert verify_shopify(body, sig) is True

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "shopify-test-secret")
    def test_invalid_signature(self):
        body = b'{"id": 123}'
        assert verify_shopify(body, "invalid-signature") is False

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "shopify-test-secret")
    def test_tampered_body(self):
        body = b'{"id": 123}'
        sig = self._sign(body)
        tampered = b'{"id": 456}'
        assert verify_shopify(tampered, sig) is False

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "shopify-test-secret")
    def test_missing_signature(self):
        assert verify_shopify(b"body", None) is False

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "")
    def test_missing_secret_rejects(self):
        """No secret configured -> always reject (fail-closed)."""
        body = b'{"id": 123}'
        assert verify_shopify(body, "anything") is False


class TestStripeVerification:
    """Stripe signature verification with timestamp tolerance."""

    SECRET = "stripe-test-secret"

    def _sign(self, body: bytes, timestamp: int | None = None) -> str:
        """Compute valid Stripe-Signature header."""
        ts = timestamp or int(time.time())
        signed_payload = f"{ts}.".encode() + body
        sig = hmac.new(self.SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_valid_signature(self):
        body = b'{"type": "payment_intent.succeeded"}'
        header = self._sign(body)
        assert verify_stripe(body, header) is True

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_invalid_signature(self):
        body = b'{"type": "payment_intent.succeeded"}'
        assert verify_stripe(body, "t=123,v1=invalid") is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_expired_timestamp_rejects(self):
        """Timestamps older than 5 minutes are rejected."""
        body = b'{"type": "test"}'
        old_ts = int(time.time()) - 600  # 10 minutes ago
        header = self._sign(body, timestamp=old_ts)
        assert verify_stripe(body, header) is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_future_timestamp_rejects(self):
        """Timestamps far in the future are rejected."""
        body = b'{"type": "test"}'
        future_ts = int(time.time()) + 600  # 10 minutes from now
        header = self._sign(body, timestamp=future_ts)
        assert verify_stripe(body, header) is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_missing_timestamp(self):
        assert verify_stripe(b"body", "v1=sig") is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_missing_v1(self):
        assert verify_stripe(b"body", f"t={int(time.time())}") is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_missing_header(self):
        assert verify_stripe(b"body", None) is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "")
    def test_missing_secret_rejects(self):
        assert verify_stripe(b"body", "t=1,v1=sig") is False

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-test-secret")
    def test_multiple_v1_signatures(self):
        """Stripe may send multiple v1 signatures (key rotation)."""
        body = b'{"type": "test"}'
        ts = int(time.time())
        signed_payload = f"{ts}.".encode() + body
        valid_sig = hmac.new(self.SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
        header = f"t={ts},v1=invalid_first,v1={valid_sig}"
        assert verify_stripe(body, header) is True


class TestPrintfulVerification:
    """Printful HMAC-SHA256 verification (hex digest)."""

    SECRET = "printful-test-secret"

    def _sign(self, body: bytes) -> str:
        return hmac.new(self.SECRET.encode(), body, hashlib.sha256).hexdigest()

    @patch("src.webhooks.verification._PRINTFUL_WEBHOOK_SECRET", "printful-test-secret")
    def test_valid_signature(self):
        body = b'{"type": "package_shipped"}'
        sig = self._sign(body)
        assert verify_printful(body, sig) is True

    @patch("src.webhooks.verification._PRINTFUL_WEBHOOK_SECRET", "printful-test-secret")
    def test_invalid_signature(self):
        assert verify_printful(b"body", "invalid") is False

    @patch("src.webhooks.verification._PRINTFUL_WEBHOOK_SECRET", "printful-test-secret")
    def test_missing_signature(self):
        assert verify_printful(b"body", None) is False

    @patch("src.webhooks.verification._PRINTFUL_WEBHOOK_SECRET", "")
    def test_missing_secret_rejects(self):
        assert verify_printful(b"body", "anything") is False


class TestVerifyWebhookDispatch:
    """verify_webhook dispatches to the right provider verifier."""

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "test")
    def test_shopify_dispatch(self):
        body = b"test"
        sig = base64.b64encode(
            hmac.new(b"test", body, hashlib.sha256).digest()
        ).decode()
        headers = {"x-shopify-hmac-sha256": sig}
        assert verify_webhook("shopify", body, headers) is True

    def test_unknown_provider(self):
        assert verify_webhook("unknown", b"body", {}) is False


# ── Idempotency ───────────────────────────────────────────────────────────


class TestIdempotency:
    """Webhook deduplication via Redis."""

    @patch("src.webhooks.idempotency._get_redis")
    def test_new_webhook_not_duplicate(self, mock_redis_fn):
        from src.webhooks.idempotency import is_duplicate

        mock_r = MagicMock()
        mock_r.set.return_value = True  # SETNX succeeded (new key)
        mock_redis_fn.return_value = mock_r

        assert is_duplicate("shopify", "wh_123") is False
        mock_r.set.assert_called_once()

    @patch("src.webhooks.idempotency._get_redis")
    def test_seen_webhook_is_duplicate(self, mock_redis_fn):
        from src.webhooks.idempotency import is_duplicate

        mock_r = MagicMock()
        mock_r.set.return_value = False  # SETNX failed (key exists)
        mock_redis_fn.return_value = mock_r

        assert is_duplicate("shopify", "wh_123") is True

    @patch("src.webhooks.idempotency._get_redis")
    def test_redis_down_allows_through(self, mock_redis_fn):
        """Redis failure -> fail open (allow webhook)."""
        from src.webhooks.idempotency import is_duplicate

        mock_redis_fn.side_effect = Exception("Redis connection refused")
        assert is_duplicate("shopify", "wh_123") is False

    def test_empty_webhook_id_not_duplicate(self):
        from src.webhooks.idempotency import is_duplicate

        assert is_duplicate("shopify", "") is False

    @patch("src.webhooks.idempotency._get_redis")
    def test_mark_seen(self, mock_redis_fn):
        from src.webhooks.idempotency import mark_seen

        mock_r = MagicMock()
        mock_redis_fn.return_value = mock_r

        mark_seen("stripe", "evt_123")
        mock_r.set.assert_called_once()
        # Verify TTL is set
        call_kwargs = mock_r.set.call_args
        assert call_kwargs[1]["ex"] == 86400  # 24h TTL


# ── Event Parsing ─────────────────────────────────────────────────────────


class TestSanitizeField:
    """Field sanitization strips HTML and truncates."""

    def test_strips_html(self):
        assert _sanitize_field("<script>alert('xss')</script>") == "alert('xss')"

    def test_unescapes_entities(self):
        assert _sanitize_field("Tom &amp; Jerry") == "Tom & Jerry"

    def test_truncates_long_values(self):
        result = _sanitize_field("A" * 1000)
        assert len(result) <= 503  # 500 + "..."

    def test_none_returns_empty(self):
        assert _sanitize_field(None) == ""

    def test_collapses_whitespace(self):
        assert _sanitize_field("hello    world") == "hello world"


class TestParseShopifyEvent:
    """Shopify webhook event parsing."""

    def test_orders_create(self):
        payload = {
            "_topic": "orders/create",
            "id": 12345,
            "order_number": 1001,
            "total_price": "29.99",
            "currency": "USD",
            "line_items": [{"title": "Classic Tee"}],
        }
        event = parse_event("shopify", payload)
        assert event is not None
        assert event.provider == "shopify"
        assert event.event_type == "orders/create"
        assert event.webhook_id == "12345"
        assert "12345" in event.task_description or "1001" in event.task_description
        assert "29.99" in event.task_description
        assert "fulfillment" in event.task_description.lower()

    def test_orders_cancelled_is_high_priority(self):
        payload = {
            "_topic": "orders/cancelled",
            "id": 99,
            "total_price": "10.00",
        }
        event = parse_event("shopify", payload)
        assert event is not None
        assert event.priority == "high"

    def test_unrecognized_event_returns_none(self):
        payload = {"_topic": "carts/update", "id": 1}
        event = parse_event("shopify", payload)
        assert event is None

    def test_products_create(self):
        payload = {"_topic": "products/create", "id": 42, "title": "Test Product"}
        event = parse_event("shopify", payload)
        assert event is not None
        assert "Test Product" in event.task_description

    def test_customer_email_redacted(self):
        """Customer email should be partially redacted."""
        payload = {
            "_topic": "customers/create",
            "id": 1,
            "email": "john@example.com",
        }
        event = parse_event("shopify", payload)
        assert event is not None
        assert "john@example.com" not in event.task_description
        assert "***@example.com" in event.task_description


class TestParseStripeEvent:
    """Stripe webhook event parsing."""

    def test_payment_succeeded(self):
        payload = {
            "id": "evt_123",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_abc",
                    "amount": 2999,
                    "currency": "usd",
                }
            },
        }
        event = parse_event("stripe", payload)
        assert event is not None
        assert event.event_type == "payment_intent.succeeded"
        assert event.webhook_id == "evt_123"
        assert "$29.99" in event.task_description

    def test_dispute_is_high_priority(self):
        payload = {
            "id": "evt_456",
            "type": "charge.dispute.created",
            "data": {"object": {"id": "dp_xyz", "amount": 5000}},
        }
        event = parse_event("stripe", payload)
        assert event is not None
        assert event.priority == "high"

    def test_unrecognized_stripe_event(self):
        payload = {"id": "evt_789", "type": "not.a.real.event"}
        event = parse_event("stripe", payload)
        assert event is None


class TestParsePrintfulEvent:
    """Printful webhook event parsing."""

    def test_package_shipped(self):
        payload = {
            "type": "package_shipped",
            "data": {
                "shipment": {
                    "order": {"id": 100, "external_id": "ext_100"},
                    "tracking_number": "1Z999AA",
                    "carrier": "UPS",
                },
            },
        }
        event = parse_event("printful", payload)
        assert event is not None
        assert event.event_type == "package_shipped"
        assert "1Z999AA" in event.task_description
        assert "UPS" in event.task_description

    def test_order_failed_is_high_priority(self):
        payload = {
            "type": "order_failed",
            "data": {"order": {"id": 200}},
        }
        event = parse_event("printful", payload)
        assert event is not None
        assert event.priority == "high"


class TestDispatchEvent:
    """dispatch_event broadcasts events."""

    @patch("src.webhooks.dispatcher.broadcaster")
    def test_broadcasts_event(self, mock_broadcaster):
        event = WebhookEvent(
            provider="shopify",
            event_type="orders/create",
            webhook_id="wh_1",
            payload={},
            task_description="New order",
        )
        dispatch_event(event)
        mock_broadcaster.broadcast.assert_called_once()
        call_args = mock_broadcaster.broadcast.call_args[0][0]
        assert call_args["type"] == "webhook_received"
        assert call_args["provider"] == "shopify"


