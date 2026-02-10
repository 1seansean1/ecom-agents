"""P1 CRITICAL: Webhook handler integration tests.

Verifies the full HTTP request flow through webhook handlers:
- Signature verification at HTTP level
- Idempotency (duplicate rejection)
- Response codes (202 for accepted, 401 for bad signature)
- No information disclosure in error responses
- GET /webhooks/status requires auth
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest


class TestShopifyWebhookHandler:
    """Full HTTP flow for Shopify webhooks."""

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "test-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_valid_shopify_webhook_returns_202(self, mock_redis_fn, client):
        """Valid Shopify webhook -> 202 Accepted."""
        mock_r = MagicMock()
        mock_r.set.return_value = True  # Not a duplicate
        mock_redis_fn.return_value = mock_r

        body = json.dumps({"id": 123, "total_price": "29.99"}).encode()
        sig = base64.b64encode(
            hmac.new(b"test-secret", body, hashlib.sha256).digest()
        ).decode()

        resp = client.post(
            "/webhooks/shopify",
            content=body,
            headers={
                "X-Shopify-Hmac-SHA256": sig,
                "X-Shopify-Topic": "orders/create",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 202

    def test_invalid_signature_returns_401(self, client):
        """Invalid signature -> 401."""
        resp = client.post(
            "/webhooks/shopify",
            content=b'{"id": 1}',
            headers={
                "X-Shopify-Hmac-SHA256": "invalid",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_no_signature_returns_401(self, client):
        """Missing signature header -> 401 (fail-closed)."""
        resp = client.post(
            "/webhooks/shopify",
            content=b'{"id": 1}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "test-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_duplicate_returns_200(self, mock_redis_fn, client):
        """Duplicate webhook ID -> 200 (accepted, not reprocessed)."""
        mock_r = MagicMock()
        mock_r.set.return_value = False  # Duplicate (SETNX failed)
        mock_redis_fn.return_value = mock_r

        body = json.dumps({"id": 456, "total_price": "10.00"}).encode()
        sig = base64.b64encode(
            hmac.new(b"test-secret", body, hashlib.sha256).digest()
        ).decode()

        resp = client.post(
            "/webhooks/shopify",
            content=body,
            headers={
                "X-Shopify-Hmac-SHA256": sig,
                "X-Shopify-Topic": "orders/create",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "test-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_unrecognized_event_still_202(self, mock_redis_fn, client):
        """Unrecognized event type -> 202 (don't leak event support map)."""
        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_redis_fn.return_value = mock_r

        body = json.dumps({"id": 789}).encode()
        sig = base64.b64encode(
            hmac.new(b"test-secret", body, hashlib.sha256).digest()
        ).decode()

        resp = client.post(
            "/webhooks/shopify",
            content=body,
            headers={
                "X-Shopify-Hmac-SHA256": sig,
                "X-Shopify-Topic": "carts/update",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 202


class TestStripeWebhookHandler:
    """Full HTTP flow for Stripe webhooks."""

    @patch("src.webhooks.verification._STRIPE_WEBHOOK_SECRET", "stripe-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_valid_stripe_webhook_returns_202(self, mock_redis_fn, client):
        """Valid Stripe webhook -> 202."""
        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_redis_fn.return_value = mock_r

        body = json.dumps({
            "id": "evt_test",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_1", "amount": 1000, "currency": "usd"}},
        }).encode()
        ts = int(time.time())
        sig = hmac.new(
            b"stripe-secret",
            f"{ts}.".encode() + body,
            hashlib.sha256,
        ).hexdigest()

        resp = client.post(
            "/webhooks/stripe",
            content=body,
            headers={
                "Stripe-Signature": f"t={ts},v1={sig}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 202


class TestPrintfulWebhookHandler:
    """Full HTTP flow for Printful webhooks."""

    @patch("src.webhooks.verification._PRINTFUL_WEBHOOK_SECRET", "pf-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_valid_printful_webhook_returns_202(self, mock_redis_fn, client):
        """Valid Printful webhook -> 202."""
        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_redis_fn.return_value = mock_r

        body = json.dumps({
            "type": "package_shipped",
            "data": {
                "shipment": {
                    "order": {"id": 100},
                    "tracking_number": "1Z999",
                    "carrier": "UPS",
                },
            },
        }).encode()
        sig = hmac.new(b"pf-secret", body, hashlib.sha256).hexdigest()

        resp = client.post(
            "/webhooks/printful",
            content=body,
            headers={
                "X-Printful-Signature": sig,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 202


class TestWebhookSecurityProperties:
    """Security properties of webhook handlers."""

    def test_401_response_no_details(self, client):
        """401 response doesn't leak verification details."""
        resp = client.post(
            "/webhooks/shopify",
            content=b'{"id": 1}',
            headers={"X-Shopify-Hmac-SHA256": "bad"},
        )
        body = resp.json()
        body_str = json.dumps(body).lower()
        assert "hmac" not in body_str
        assert "secret" not in body_str
        assert "key" not in body_str

    def test_webhook_status_requires_auth(self, client):
        """GET /webhooks/status requires JWT authentication."""
        resp = client.get("/webhooks/status")
        assert resp.status_code == 401

    def test_webhook_status_accessible_with_auth(self, authenticated_client):
        """GET /webhooks/status works with valid auth."""
        resp = authenticated_client.get("/webhooks/status")
        assert resp.status_code != 401
        assert "counts" in resp.json()

    @patch("src.webhooks.verification._SHOPIFY_WEBHOOK_SECRET", "test-secret")
    @patch("src.webhooks.idempotency._get_redis")
    def test_invalid_json_returns_202(self, mock_redis_fn, client):
        """Invalid JSON body with valid signature -> 202 (no info leak)."""
        mock_r = MagicMock()
        mock_r.set.return_value = True
        mock_redis_fn.return_value = mock_r

        body = b"not valid json at all"
        sig = base64.b64encode(
            hmac.new(b"test-secret", body, hashlib.sha256).digest()
        ).decode()

        resp = client.post(
            "/webhooks/shopify",
            content=body,
            headers={
                "X-Shopify-Hmac-SHA256": sig,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 202
