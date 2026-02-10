"""P1 CRITICAL: API authentication tests.

Verifies every non-public endpoint requires valid Bearer token auth.
Uses introspection-driven approach (app.routes) to auto-discover routes.

Per Auth Contract:
- Missing/malformed/expired credentials -> 401
- Only GET /health is public
- OPTIONS handled by CORS middleware (skipped)
"""

from __future__ import annotations

import re
import time

import pytest
from freezegun import freeze_time

from src.security.auth import PUBLIC_ALLOWLIST, SKIP_METHODS, create_token, is_webhook_path

# Minimum route count to catch import failures that silently reduce the route table
MIN_EXPECTED_ROUTES = 50


def _fill_path_params(path: str) -> str:
    """Replace FastAPI path parameters with test values."""
    replacements = {
        "{agent_id}": "test-agent",
        "{channel_id}": "K1",
        "{theta_id}": "default",
        "{job_id}": "test-job",
        "{dlq_id}": "1",
        "{approval_id}": "1",
        "{suite_id}": "test-suite",
        "{trace_id}": "test-trace",
        "{thread_id}": "test-thread",
        "{goal_id}": "test-goal",
        "{image_id}": "1",
        "{version}": "1",
        "{workflow_id}": "test-workflow",
        "{config_hash}": "abc123",
        "{file_path:path}": "index.html",
    }
    result = path
    for param, value in replacements.items():
        result = result.replace(param, value)
    return result


@pytest.fixture
def all_routes(app):
    """Introspect FastAPI app to get all registered routes (deduplicated)."""
    seen = set()
    routes = []
    for route in app.routes:
        if hasattr(route, "methods"):
            for method in route.methods:
                if method not in SKIP_METHODS:
                    key = (method, route.path)
                    if key not in seen:
                        seen.add(key)
                        routes.append(key)
    return routes


class TestRouteIntrospection:
    """Verify the introspection mechanism itself is sound."""

    def test_new_routes_covered_by_introspection(self, all_routes):
        """Route count meets expected minimum (catches import failures)."""
        assert len(all_routes) >= MIN_EXPECTED_ROUTES, (
            f"Only {len(all_routes)} routes found, expected >= {MIN_EXPECTED_ROUTES}. "
            "Check for import failures silently reducing the route table."
        )

    def test_public_allowlist_is_minimal(self):
        """PUBLIC_ALLOWLIST has exactly 2 entries (GET / and GET /health)."""
        assert PUBLIC_ALLOWLIST == {("GET", "/"), ("GET", "/health")}

    def test_skip_methods_only_options(self):
        """SKIP_METHODS contains only OPTIONS."""
        assert SKIP_METHODS == {"OPTIONS"}


class TestAllRoutesRequireAuth:
    """Every non-public route must return 401 without credentials."""

    def test_all_non_public_routes_require_auth(self, client, all_routes):
        """Introspects app.routes; every non-allowlisted route rejects unauthenticated.

        Per auth contract: missing credentials -> 401 (not 403).
        """
        failures = []
        for method, path in all_routes:
            if (method, path) in PUBLIC_ALLOWLIST:
                continue
            test_path = _fill_path_params(path)
            # Webhook paths bypass JWT (signature-verified by handler instead).
            # POST to webhook paths is public; tested separately in test_webhook_auth.py.
            if method == "POST" and is_webhook_path(test_path):
                continue
            resp = getattr(client, method.lower())(test_path)
            if resp.status_code != 401:
                failures.append(f"{method} {path} -> {resp.status_code} (expected 401)")

        assert not failures, (
            f"{len(failures)} routes don't require auth:\n" + "\n".join(failures)
        )


class TestPublicEndpoints:
    """Verify public endpoint behavior."""

    def test_health_allows_unauthenticated(self, client):
        """Health is the ONE public endpoint."""
        resp = client.get("/health")
        # May return 200 or 503 depending on service health, but NOT 401
        assert resp.status_code != 401

    def test_cors_preflight_allowed_without_auth(self, client):
        """OPTIONS requests return 200 with CORS headers, no auth required."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


class TestCredentialValidation:
    """Test various credential scenarios."""

    def test_invalid_credentials_rejected(self, client):
        """Malformed token -> 401."""
        resp = client.get(
            "/agents",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert resp.status_code == 401

    def test_missing_bearer_prefix_rejected(self, client):
        """Token without 'Bearer ' prefix -> 401."""
        token_meta = create_token(role="admin")
        resp = client.get(
            "/agents",
            headers={"Authorization": token_meta.token},  # Missing "Bearer " prefix
        )
        assert resp.status_code == 401

    def test_empty_bearer_rejected(self, client):
        """'Bearer ' with no token -> 401."""
        resp = client.get(
            "/agents",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    def test_expired_credentials_rejected(self, client, make_auth_header):
        """Expired token (via freezegun) -> 401."""
        from datetime import datetime, timedelta, timezone

        # Create token that expires in 10 seconds
        headers, meta = make_auth_header("viewer", expires_in=10)

        # Fast-forward past expiry using datetime (freezegun requires datetime, not float)
        future = datetime.now(timezone.utc) + timedelta(seconds=20)
        with freeze_time(future, tick=False):
            resp = client.get("/agents", headers=headers)
            assert resp.status_code == 401

    def test_valid_credentials_allows_access(self, authenticated_client):
        """Valid Bearer token -> not 401 on a protected endpoint."""
        resp = authenticated_client.get("/agents")
        # Should not be 401 (might be 500 if DB not available, but auth passed)
        assert resp.status_code != 401


class TestAuthMiddlewareOrdering:
    """Verify auth runs before body validation."""

    def test_auth_runs_before_validation(self, client):
        """Unauthenticated POST with invalid body returns 401, not 422."""
        resp = client.post(
            "/agents",
            json={"invalid": "body"},  # Missing required fields
        )
        assert resp.status_code == 401, (
            f"Expected 401 (auth failure) before body validation, got {resp.status_code}"
        )

    def test_auth_runs_before_validation_on_put(self, client):
        """Unauthenticated PUT with invalid body returns 401, not 422."""
        resp = client.put(
            "/agents/test-agent",
            json={},  # Missing expected_version
        )
        assert resp.status_code == 401
