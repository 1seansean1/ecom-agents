"""P1 CRITICAL: API authorization tests.

Verifies role-based access control:
- admin: full CRUD + triggers
- operator: read + trigger jobs
- viewer: read-only

Per Auth Contract: 403 for insufficient role (distinct from 401 for missing auth).
"""

from __future__ import annotations

import pytest


class TestAdminOnlyEndpoints:
    """Endpoints that require admin role."""

    def test_aps_switch_requires_admin(self, operator_client):
        """APS partition switching restricted to admin."""
        resp = operator_client.post("/aps/switch/K1/default")
        assert resp.status_code == 403

    def test_agent_create_requires_admin(self, operator_client):
        """Agent creation restricted to admin."""
        resp = operator_client.post("/agents", json={
            "agent_id": "test",
            "channel_id": "K99",
            "display_name": "Test",
            "model_id": "gpt-4o",
            "system_prompt": "Test prompt",
        })
        assert resp.status_code == 403

    def test_agent_update_requires_admin(self, operator_client):
        """Config modification restricted to admin."""
        resp = operator_client.put("/agents/test-agent", json={
            "expected_version": 1,
            "display_name": "Updated",
        })
        assert resp.status_code == 403

    def test_agent_delete_requires_admin(self, operator_client):
        """Agent deletion restricted to admin."""
        resp = operator_client.delete("/agents/test-agent")
        assert resp.status_code == 403


class TestOperatorEndpoints:
    """Endpoints that operator can access but viewer cannot."""

    def test_scheduler_trigger_requires_operator(self, client, viewer_headers):
        """Job triggering restricted to operator+."""
        resp = client.post("/scheduler/trigger/test-job", headers=viewer_headers)
        assert resp.status_code == 403

    def test_evaluate_requires_operator(self, client, viewer_headers):
        """APS evaluation restricted to operator+."""
        resp = client.post("/aps/evaluate", headers=viewer_headers)
        assert resp.status_code == 403

    def test_eval_run_requires_operator(self, client, viewer_headers):
        """Eval suite run restricted to operator+."""
        resp = client.post("/eval/run", headers=viewer_headers)
        assert resp.status_code == 403

    def test_operator_can_trigger_job(self, operator_client):
        """Operator CAN trigger jobs."""
        resp = operator_client.post("/scheduler/trigger/test-job")
        # Should not be 403 (might be 404 if job doesn't exist, but auth passed)
        assert resp.status_code != 403


class TestViewerAccess:
    """Viewer role can read but not write."""

    def test_readonly_endpoints_allow_viewer(self, authenticated_client):
        """GET works with viewer role."""
        read_endpoints = [
            "/agents",
            "/tools",
            "/workflows",
            "/scheduler/jobs",
            "/scheduler/dlq",
            "/approvals",
            "/aps/metrics",
            "/aps/partitions",
            "/morphogenetic/goals",
            "/morphogenetic/cascade",
            "/morphogenetic/cascade/config",
        ]
        for endpoint in read_endpoints:
            resp = authenticated_client.get(endpoint)
            assert resp.status_code != 401, f"Viewer rejected from GET {endpoint}"
            assert resp.status_code != 403, f"Viewer forbidden from GET {endpoint}"

    def test_write_endpoints_reject_viewer(self, client, viewer_headers):
        """POST/PUT reject viewer role."""
        write_endpoints = [
            ("POST", "/agents", {"agent_id": "x", "channel_id": "K1",
             "display_name": "X", "model_id": "gpt-4o", "system_prompt": "X"}),
            ("PUT", "/agents/test-agent", {"expected_version": 1, "display_name": "X"}),
            ("DELETE", "/agents/test-agent", None),
        ]
        for method, path, body in write_endpoints:
            if body:
                resp = getattr(client, method.lower())(path, json=body, headers=viewer_headers)
            else:
                resp = getattr(client, method.lower())(path, headers=viewer_headers)
            assert resp.status_code == 403, (
                f"Viewer should be forbidden from {method} {path}, got {resp.status_code}"
            )
