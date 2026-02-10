"""P3 MEDIUM: Information disclosure tests.

Verifies sensitive internals are not exposed through API responses.
System prompts, graph internals, model IDs, error details.
"""

from __future__ import annotations

import pytest


class TestSystemPromptExposure:
    """System prompts should not be exposed to low-privilege users."""

    def test_viewer_cannot_see_system_prompts(self, authenticated_client):
        """REMEDIATED: GET /agents strips system_prompt for non-admin users."""
        resp = authenticated_client.get("/agents")
        if resp.status_code == 200:
            body = resp.json()
            agents = body.get("agents", [])
            for agent in agents:
                assert "system_prompt" not in agent, (
                    f"Agent '{agent.get('agent_id')}' leaks system_prompt to viewer"
                )

    def test_admin_can_see_system_prompts(self, admin_client):
        """Admin users CAN see system_prompt in agent responses."""
        resp = admin_client.get("/agents")
        if resp.status_code == 200:
            body = resp.json()
            agents = body.get("agents", [])
            if agents:
                # Admin should have system_prompt in the response
                assert "system_prompt" in agents[0]


class TestErrorResponseSafety:
    """Error responses should not leak internals."""

    def test_404_error_no_stack_trace(self, admin_client):
        """404 responses don't contain stack traces."""
        resp = admin_client.get("/agents/definitely-not-a-real-agent")
        assert "Traceback" not in resp.text
        assert "File \"" not in resp.text

    def test_invalid_json_error_safe(self, admin_client):
        """REMEDIATED: Invalid JSON body returns 400 with clean error message."""
        resp = admin_client.post(
            "/agents",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400, (
            f"Invalid JSON returned {resp.status_code}, expected 400"
        )
        assert "Traceback" not in resp.text
        assert "Invalid JSON" in resp.text

    def test_method_not_allowed_clean(self, admin_client):
        """Method not allowed returns clean error."""
        resp = admin_client.patch("/agents")  # PATCH not defined
        assert resp.status_code == 405


class TestFastAPIDocsGated:
    """FastAPI auto-generated docs should require auth in production."""

    def test_docs_require_auth(self, client):
        """GET /docs requires authentication."""
        resp = client.get("/docs")
        assert resp.status_code == 401, (
            f"/docs returned {resp.status_code}, should require auth"
        )

    def test_redoc_requires_auth(self, client):
        """GET /redoc requires authentication."""
        resp = client.get("/redoc")
        assert resp.status_code == 401, (
            f"/redoc returned {resp.status_code}, should require auth"
        )

    def test_openapi_json_requires_auth(self, client):
        """GET /openapi.json requires authentication."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 401, (
            f"/openapi.json returned {resp.status_code}, should require auth"
        )
