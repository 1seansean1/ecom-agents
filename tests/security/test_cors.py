"""P3 MEDIUM: CORS middleware tests.

Verifies CORS middleware rejects disallowed origins and doesn't use wildcard.
"""

from __future__ import annotations

import pytest


class TestCORSPolicy:
    """CORS middleware enforces origin allowlist."""

    def test_cors_allows_configured_origin(self, client):
        """Allowed origin gets CORS headers."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_rejects_unknown_origin(self, client):
        """Unknown origin doesn't get CORS allow header."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "https://evil-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Either no CORS header or not matching the evil origin
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        assert allow_origin != "https://evil-site.com"
        assert allow_origin != "*"

    def test_cors_no_wildcard(self, client):
        """CORS doesn't use wildcard (*) origin."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        assert allow_origin != "*", "CORS should not use wildcard origin"

    def test_cors_credentials_supported(self, client):
        """CORS allows credentials (for Bearer auth)."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_cors_allows_auth_header(self, client):
        """CORS allows Authorization header in requests."""
        resp = client.options(
            "/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allow_headers or "*" in allow_headers
