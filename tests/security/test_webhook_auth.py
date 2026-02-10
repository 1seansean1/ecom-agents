"""P1 CRITICAL: Webhook authentication and authorization tests.

Verifies:
- Webhook paths bypass JWT auth (signature-verified by handler, not middleware)
- Webhook RBAC role is tightly restricted to /agent/invoke and /agent/batch only
- Webhook role cannot access non-whitelisted endpoints
- is_webhook_path matches only declared prefixes
- Non-POST methods on webhook paths still require JWT
- Auth module constants are correctly defined
"""

from __future__ import annotations

import pytest

from src.security.auth import (
    ALL_ROLES,
    ROLES,
    WEBHOOK_ALLOWED_PATHS,
    WEBHOOK_PUBLIC_PREFIXES,
    WEBHOOK_ROLE,
    _check_webhook_authorization,
    check_authorization,
    is_webhook_path,
)


class TestWebhookConstants:
    """Webhook auth constants are correctly defined."""

    def test_webhook_role_is_webhook(self):
        """Webhook role is 'webhook'."""
        assert WEBHOOK_ROLE == "webhook"

    def test_webhook_role_not_in_standard_roles(self):
        """Webhook role is NOT in the standard role hierarchy."""
        assert WEBHOOK_ROLE not in ROLES

    def test_webhook_role_in_all_roles(self):
        """Webhook role IS in ALL_ROLES."""
        assert WEBHOOK_ROLE in ALL_ROLES

    def test_all_roles_includes_standard_and_webhook(self):
        """ALL_ROLES = standard roles + webhook."""
        assert set(ALL_ROLES) == set(ROLES) | {WEBHOOK_ROLE}

    def test_webhook_public_prefixes_are_scoped(self):
        """Only shopify, stripe, and printful webhook prefixes are public."""
        assert len(WEBHOOK_PUBLIC_PREFIXES) == 3
        assert "/webhooks/shopify" in WEBHOOK_PUBLIC_PREFIXES
        assert "/webhooks/stripe" in WEBHOOK_PUBLIC_PREFIXES
        assert "/webhooks/printful" in WEBHOOK_PUBLIC_PREFIXES

    def test_webhook_allowed_paths_are_minimal(self):
        """Webhook role can only invoke agent endpoints."""
        assert WEBHOOK_ALLOWED_PATHS == {"/agent/invoke", "/agent/batch"}


class TestIsWebhookPath:
    """is_webhook_path matches only declared webhook prefixes."""

    def test_shopify_webhook_path(self):
        assert is_webhook_path("/webhooks/shopify") is True

    def test_shopify_webhook_subpath(self):
        assert is_webhook_path("/webhooks/shopify/orders/create") is True

    def test_stripe_webhook_path(self):
        assert is_webhook_path("/webhooks/stripe") is True

    def test_printful_webhook_path(self):
        assert is_webhook_path("/webhooks/printful") is True

    def test_non_webhook_path(self):
        assert is_webhook_path("/agents") is False

    def test_health_not_webhook(self):
        assert is_webhook_path("/health") is False

    def test_partial_prefix_no_match(self):
        """'/webhooks/shop' should NOT match '/webhooks/shopify'."""
        assert is_webhook_path("/webhooks/shop") is False

    def test_webhook_base_not_match(self):
        """'/webhooks' alone is not a valid webhook path."""
        assert is_webhook_path("/webhooks") is False

    def test_unknown_provider_not_match(self):
        """'/webhooks/paypal' is not a declared provider."""
        assert is_webhook_path("/webhooks/paypal") is False

    def test_case_sensitive(self):
        """Webhook paths are case-sensitive — '/webhooks/Shopify' != '/webhooks/shopify'."""
        assert is_webhook_path("/webhooks/Shopify") is False


class TestWebhookAuthorization:
    """Webhook role authorization is tightly restricted."""

    def test_webhook_can_post_agent_invoke(self):
        """Webhook role can POST /agent/invoke."""
        result = _check_webhook_authorization("POST", "/agent/invoke")
        assert result is None  # authorized

    def test_webhook_can_post_agent_batch(self):
        """Webhook role can POST /agent/batch."""
        result = _check_webhook_authorization("POST", "/agent/batch")
        assert result is None

    def test_webhook_cannot_get_agents(self):
        """Webhook role cannot GET /agents."""
        result = _check_webhook_authorization("GET", "/agents")
        assert result is not None  # denied

    def test_webhook_cannot_post_agents(self):
        """Webhook role cannot POST /agents (create)."""
        result = _check_webhook_authorization("POST", "/agents")
        assert result is not None

    def test_webhook_cannot_post_scheduler_trigger(self):
        """Webhook role cannot trigger scheduler jobs."""
        result = _check_webhook_authorization("POST", "/scheduler/trigger/{job_id}")
        assert result is not None

    def test_webhook_cannot_get_health(self):
        """Webhook role cannot GET /health (it's public, not webhook-authorized)."""
        result = _check_webhook_authorization("GET", "/health")
        assert result is not None

    def test_webhook_cannot_delete_anything(self):
        """Webhook role cannot DELETE."""
        result = _check_webhook_authorization("DELETE", "/agents/test")
        assert result is not None

    def test_webhook_cannot_put_anything(self):
        """Webhook role cannot PUT."""
        result = _check_webhook_authorization("PUT", "/agents/test")
        assert result is not None

    def test_webhook_denied_message_includes_method_and_path(self):
        """Denial message includes context for debugging."""
        result = _check_webhook_authorization("GET", "/agents")
        assert "GET" in result
        assert "/agents" in result
        assert "Webhook" in result


class TestCheckAuthorizationWithWebhookRole:
    """check_authorization dispatches webhook role correctly."""

    def test_webhook_dispatches_to_webhook_handler(self):
        """Webhook role is handled by _check_webhook_authorization, not standard logic."""
        # Webhook can POST /agent/invoke
        assert check_authorization("webhook", "POST", "/agent/invoke") is None
        # But cannot do things standard roles can
        assert check_authorization("webhook", "GET", "/agents") is not None

    def test_webhook_does_not_affect_standard_roles(self):
        """Standard roles still work as before."""
        # Admin can POST /agents
        assert check_authorization("admin", "POST", "/agents") is None
        # Viewer cannot
        assert check_authorization("viewer", "POST", "/agents") is not None
        # Operator can POST /scheduler/trigger/{job_id}
        assert check_authorization("operator", "POST", "/scheduler/trigger/{job_id}") is None

    def test_webhook_role_isolated_from_hierarchy(self):
        """Webhook role doesn't get viewer/operator/admin privileges."""
        # Webhook can't read (viewer privilege)
        assert check_authorization("webhook", "GET", "/agents") is not None
        # Webhook can't trigger (operator privilege)
        assert check_authorization("webhook", "POST", "/scheduler/trigger/{job_id}") is not None
        # Webhook can't admin (admin privilege)
        assert check_authorization("webhook", "POST", "/agents") is not None


class TestWebhookMiddlewareIntegration:
    """Webhook paths bypass JWT in middleware but are otherwise restricted."""

    def test_webhook_path_bypasses_jwt_middleware(self, client):
        """POST to webhook path bypasses JWT middleware.

        The handler may still return 401 (signature verification), but NOT
        the middleware's 401 (which includes WWW-Authenticate: Bearer and
        {"error": "Authentication required"}).
        """
        resp = client.post("/webhooks/shopify")
        # Middleware 401 has WWW-Authenticate header; handler 401 does not.
        if resp.status_code == 401:
            assert "WWW-Authenticate" not in resp.headers, (
                "POST /webhooks/shopify was blocked by JWT middleware, not handler"
            )

    def test_webhook_path_get_still_requires_auth(self, client):
        """GET on webhook path still requires JWT (only POST is public)."""
        resp = client.get("/webhooks/shopify")
        # GET is not bypassed — should hit JWT check
        # But since there's no GET route for webhooks, middleware may let it
        # through to 404. The key is it's not explicitly allowed.
        # Actually, middleware only bypasses POST + is_webhook_path.
        # GET will not match that condition, so it falls through to JWT check.
        # If no auth header → 401.
        assert resp.status_code == 401

    def test_webhook_stripe_bypasses_jwt_middleware(self, client):
        """POST to stripe webhook path bypasses JWT middleware."""
        resp = client.post("/webhooks/stripe")
        if resp.status_code == 401:
            assert "WWW-Authenticate" not in resp.headers, (
                "POST /webhooks/stripe was blocked by JWT middleware, not handler"
            )

    def test_webhook_printful_bypasses_jwt_middleware(self, client):
        """POST to printful webhook path bypasses JWT middleware."""
        resp = client.post("/webhooks/printful")
        if resp.status_code == 401:
            assert "WWW-Authenticate" not in resp.headers, (
                "POST /webhooks/printful was blocked by JWT middleware, not handler"
            )

    def test_non_webhook_post_still_requires_auth(self, client):
        """POST to non-webhook paths still requires JWT."""
        resp = client.post("/agents", json={"agent_id": "test"})
        assert resp.status_code == 401

    def test_fake_webhook_path_requires_auth(self, client):
        """POST to non-declared webhook provider still requires JWT."""
        resp = client.post("/webhooks/paypal")
        assert resp.status_code == 401
