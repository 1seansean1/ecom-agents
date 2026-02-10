"""Security test fixtures.

Responsibilities (per plan conftest.py split):
- Creates the FastAPI `app` fixture (with TESTING=1)
- Wraps in client/authenticated_client/admin_client/operator_client/invalid_auth_client
- Provides make_auth_header, malicious_payloads, frozen_time
- Scoped to tests/security/ only -- invisible to non-security tests

The global tests/conftest.py handles env vars and basic fixtures (llm_settings, etc).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from src.security.auth import TokenMetadata, create_token


@pytest.fixture(scope="module")
def app():
    """Create a FastAPI app with TESTING=1 (skips lifespan side effects).

    Active: Full route table, auth middleware, CORS middleware, rate-limit middleware.
    Skipped: APScheduler, APS tables, Postgres, registry seeding, Ollama, HollyEventCallbackHandler.
    """
    os.environ["TESTING"] = "1"
    try:
        # Patch heavy imports that connect to services at import time
        with (
            patch("src.serve.LLMSettings"),
            patch("src.serve.LLMRouter"),
            patch("src.serve.build_graph") as mock_graph,
            patch("src.serve.HollyEventCallbackHandler"),
            patch("src.serve.WebSocketLogHandler"),
            patch("src.serve.AutonomousScheduler"),
        ):
            mock_compiled = MagicMock()
            mock_compiled.get_graph.return_value = MagicMock(nodes={}, edges=[])
            mock_graph.return_value.compile.return_value = mock_compiled

            # Force reimport to pick up TESTING=1
            import importlib

            import src.serve

            importlib.reload(src.serve)
            yield src.serve.app
    finally:
        os.environ.pop("TESTING", None)


@pytest.fixture
def client(app):
    """Unauthenticated TestClient (attacker perspective)."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def make_auth_header():
    """Factory for auth headers.

    Returns (headers_dict, TokenMetadata) where:
    - headers_dict = {"Authorization": "Bearer <token>"}
    - TokenMetadata.expires_at is the absolute expiry time (for freezegun tests)

    Per Auth Contract: optional expires_in (seconds) controls TTL.
    """

    def _make(role: str = "viewer", expires_in: int = 3600) -> tuple[dict[str, str], TokenMetadata]:
        meta = create_token(role=role, expires_in=expires_in)
        headers = {"Authorization": f"Bearer {meta.token}"}
        return headers, meta

    return _make


@pytest.fixture
def viewer_headers(make_auth_header):
    """Viewer-level auth headers."""
    headers, _ = make_auth_header("viewer")
    return headers


@pytest.fixture
def operator_headers(make_auth_header):
    """Operator-level auth headers."""
    headers, _ = make_auth_header("operator")
    return headers


@pytest.fixture
def admin_headers(make_auth_header):
    """Admin-level auth headers."""
    headers, _ = make_auth_header("admin")
    return headers


@pytest.fixture
def authenticated_client(app, viewer_headers):
    """TestClient with viewer-level auth (default authenticated)."""
    with TestClient(app, raise_server_exceptions=False, headers=viewer_headers) as c:
        yield c


@pytest.fixture
def admin_client(app, admin_headers):
    """TestClient with admin-level auth."""
    with TestClient(app, raise_server_exceptions=False, headers=admin_headers) as c:
        yield c


@pytest.fixture
def operator_client(app, operator_headers):
    """TestClient with operator-level auth."""
    with TestClient(app, raise_server_exceptions=False, headers=operator_headers) as c:
        yield c


@pytest.fixture
def invalid_auth_client(app):
    """TestClient with invalid/malformed auth token."""
    with TestClient(
        app,
        raise_server_exceptions=False,
        headers={"Authorization": "Bearer invalid-not-a-jwt-token"},
    ) as c:
        yield c


@pytest.fixture
def malicious_payloads():
    """Collection of injection strings for fuzz testing."""
    return [
        # SQL injection
        "'; DROP TABLE agents; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM pg_catalog.pg_tables --",
        "1; UPDATE agents SET system_prompt='pwned'",
        # XSS
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(document.cookie)",
        # Path traversal
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        # Command injection
        "; rm -rf /",
        "$(whoami)",
        "`id`",
        # Template injection
        "{{7*7}}",
        "${7*7}",
        "#{7*7}",
        # Null bytes
        "test\x00admin",
        # Unicode tricks
        "admin\u200b",  # Zero-width space
        # Oversized
        "A" * 100000,
    ]
