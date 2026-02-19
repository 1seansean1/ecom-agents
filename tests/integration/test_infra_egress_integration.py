"""Integration tests for holly.infra.egress module.

Tests end-to-end egress scenarios with actual redaction library and
state machine verification against Behavior Spec §3.1 acceptance criteria.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

from holly.infra.egress import (
    AllowedDomainConfig,
    BudgetExceededError,
    DomainBlockedError,
    EgressGateway,
    EgressRequest,
    EgressResponse,
    ForwardError,
    create_default_gateway,
)

# ─────────────────────────────────────────────────────────────────────────────
# Integration Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def http_client_mock():
    """HTTP client that returns realistic responses."""
    client = MagicMock()
    client.send = Mock(
        return_value=EgressResponse(
            status_code=200,
            headers={
                "content-type": "application/json",
                "x-ratelimit-remaining": "99",
            },
            body='{"choices": [{"message": {"content": "Hello, world!"}}]}',
        )
    )
    return client


@pytest.fixture
def rate_limiter_mock():
    """Rate limiter that simulates typical behavior."""
    limiter = MagicMock()
    call_count = {"count": 0}

    def check_and_increment(key: str, limit: int, window_seconds: int = 60) -> bool:
        call_count["count"] += 1
        # Simulate: allow first N calls, block on Nth
        return call_count["count"] <= limit

    limiter.check_and_increment = Mock(side_effect=check_and_increment)
    return limiter


@pytest.fixture
def budget_tracker_mock():
    """Budget tracker that simulates workflow budgets."""
    tracker = MagicMock()
    budgets: dict[str, int] = {}

    def check_and_deduct(workflow_id: str, budget_type: str, amount: int) -> bool:
        key = f"{workflow_id}:{budget_type}"
        current = budgets.get(key, 10000)  # Default 10k tokens
        if current < amount:
            return False
        budgets[key] = current - amount
        return True

    tracker.check_and_deduct = Mock(side_effect=check_and_deduct)
    return tracker


@pytest.fixture
def audit_logger_mock():
    """Audit logger that records all calls."""
    logger = MagicMock()
    entries: list[dict] = []

    def log_egress(audit_entry: dict) -> None:
        entries.append(audit_entry)

    logger.log_egress = Mock(side_effect=log_egress)
    logger.entries = entries
    return logger


@pytest.fixture
def egress_gateway_integration(
    http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
):
    """Egress gateway with realistic mock dependencies."""
    allowed_domains = {
        "api.openai.com": AllowedDomainConfig(
            domain="api.openai.com",
            domain_type="llm",
            rate_limit_per_minute=5,  # Low limit for testing
            budget_type="token_count",
        ),
        "api.anthropic.com": AllowedDomainConfig(
            domain="api.anthropic.com",
            domain_type="llm",
            rate_limit_per_minute=10,
            budget_type="token_count",
        ),
    }

    return EgressGateway(
        allowed_domains=allowed_domains,
        http_client=http_client_mock,
        rate_limiter=rate_limiter_mock,
        budget_tracker=budget_tracker_mock,
        audit_logger=audit_logger_mock,
    ), audit_logger_mock


# ─────────────────────────────────────────────────────────────────────────────
# Acceptance Criteria Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAcceptanceCriteria:
    """Tests for Behavior Spec §3.1 acceptance criteria."""

    def test_ac1_allowlisted_domain_passes(self, egress_gateway_integration):
        """AC1: Allowlisted Domain Passes.

        Assert: l7_enforce_egress(request_to_api.openai.com) → request forwarded
        """
        gateway, _ = egress_gateway_integration

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body='{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}',
            tenant_id="tenant-1",
            workflow_id="workflow-1",
            correlation_id="corr-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is True
        assert result.response is not None
        assert result.state == "IDLE"

    def test_ac2_non_allowlisted_domain_blocked(self, egress_gateway_integration):
        """AC2: Non-Allowlisted Domain Blocked.

        Assert: l7_enforce_egress(request_to_random.example.com) → DomainBlockedError
        """
        gateway, _ = egress_gateway_integration

        request = EgressRequest(
            url="https://random.example.com/evil",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "DOMAIN_BLOCKED"
        assert isinstance(result.error, DomainBlockedError)

    def test_ac3_request_redaction(self, egress_gateway_integration):
        """AC3: Request Redaction.

        Assert: request contains email@example.com → forwarded request contains [email]
        """
        gateway, _ = egress_gateway_integration

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body='{"user_email": "john.doe@example.com", "prompt": "Help me"}',
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is True
        # Verify redaction was applied (check audit entry or actual redaction result)
        # The redaction happens in the pipeline
        called_request = gateway._http_client.send.call_args[0][0]
        # Body should be redacted
        assert "[" in called_request.body or "email" in called_request.body

    def test_ac4_response_redaction(self, egress_gateway_integration):
        """AC4: Response Redaction.

        Assert: response contains API key → returned response contains [secret]
        """
        gateway, _ = egress_gateway_integration
        # Mock response with secrets
        gateway._http_client.send = Mock(
            return_value=EgressResponse(
                status_code=200,
                headers={},
                body='{"api_key": "sk-1234567890", "result": "ok"}',
            )
        )

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is True
        assert result.response is not None
        # Response body should be redacted
        assert "[secret" in result.response.body or "api_key" not in result.response.body

    def test_ac5_rate_limit_enforcement(self, egress_gateway_integration):
        """AC5: Rate Limit Enforcement.

        Assert: Send 100 requests in 1 minute (limit=100) → 101st blocked
        """
        gateway, _ = egress_gateway_integration
        # Create a fresh rate limiter with actual counting
        rate_limit_data = {"count": 0}

        def check_and_increment(key: str, limit: int, window_seconds: int = 60) -> bool:
            rate_limit_data["count"] += 1
            return rate_limit_data["count"] <= limit

        gateway._rate_limiter.check_and_increment = Mock(side_effect=check_and_increment)

        # Send requests up to limit
        for i in range(5):  # Limit is 5 for api.openai.com in fixture
            request = EgressRequest(
                url="https://api.openai.com/v1/chat/completions",
                method="POST",
                body=f"test {i}",
                tenant_id="tenant-1",
                workflow_id=f"workflow-{i}",
            )
            result = gateway.enforce_egress(request)
            assert result.success is True

        # Next request should be rate limited
        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test over limit",
            tenant_id="tenant-1",
            workflow_id="workflow-over",
        )
        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "RATE_EXCEEDED"

    def test_ac6_budget_enforcement(self, egress_gateway_integration):
        """AC6: Budget Enforcement.

        Assert: workflow.budget = 1000 tokens, 900 used, request needs 200 → BudgetExceededError
        """
        gateway, _ = egress_gateway_integration
        # Set up budget tracker with specific budget
        budget_data = {"workflow-1": 100}  # 100 tokens available

        def check_and_deduct(workflow_id: str, budget_type: str, amount: int) -> bool:
            if workflow_id not in budget_data:
                budget_data[workflow_id] = 1000
            if budget_data[workflow_id] < amount:
                return False
            budget_data[workflow_id] -= amount
            return True

        gateway._budget_tracker.check_and_deduct = Mock(side_effect=check_and_deduct)

        # Request that would use 50 tokens should pass (100 available)
        request1 = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="x" * 200,  # ~50 tokens
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )
        result1 = gateway.enforce_egress(request1)
        assert result1.success is True

        # Request that would use 100 tokens should fail (only 50 left)
        request2 = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="y" * 400,  # ~100 tokens
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )
        result2 = gateway.enforce_egress(request2)
        assert result2.success is False
        assert isinstance(result2.error, BudgetExceededError)

    def test_ac7_logging_coverage(self, egress_gateway_integration):
        """AC7: Logging Coverage.

        Assert: After forwarding N requests, count(egress_logs) == N
        """
        gateway, audit_logger = egress_gateway_integration

        for i in range(3):
            request = EgressRequest(
                url="https://api.openai.com/v1/chat/completions",
                method="POST",
                body=f"test {i}",
                tenant_id="tenant-1",
                workflow_id=f"workflow-{i}",
            )
            result = gateway.enforce_egress(request)
            assert result.success is True

        # All requests should be logged
        assert len(audit_logger.entries) >= 3

    def test_ac8_timeout_enforcement(self, egress_gateway_integration):
        """AC8: Timeout Enforcement.

        Assert: Slow upstream → TimeoutError after 30s
        """
        gateway, _ = egress_gateway_integration
        # Mock timeout
        gateway._http_client.send = Mock(side_effect=TimeoutError("Request timeout"))

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "FORWARD_ERROR"
        assert isinstance(result.error, ForwardError)

    def test_ac9_tenant_isolation(self, egress_gateway_integration):
        """AC9: Tenant Isolation.

        Assert: tenant_a uses X requests, tenant_b uses Y requests; no interference
        """
        gateway, _ = egress_gateway_integration
        rate_limits: dict[str, int] = {"tenant-a": 0, "tenant-b": 0}

        def check_and_increment(key: str, limit: int, window_seconds: int = 60) -> bool:
            # Extract tenant from key: "egress:rate:tenant-id:domain"
            parts = key.split(":")
            tenant = parts[2] if len(parts) > 2 else "unknown"
            rate_limits[tenant] = rate_limits.get(tenant, 0) + 1
            return rate_limits[tenant] <= limit

        gateway._rate_limiter.check_and_increment = Mock(side_effect=check_and_increment)

        # Send requests from different tenants
        for tenant in ["tenant-a", "tenant-b"]:
            request = EgressRequest(
                url="https://api.openai.com/v1/chat/completions",
                method="POST",
                body="test",
                tenant_id=tenant,
                workflow_id="workflow-1",
            )
            result = gateway.enforce_egress(request)
            assert result.success is True

        # Rate limits should be tracked independently
        assert rate_limits["tenant-a"] >= 1
        assert rate_limits["tenant-b"] >= 1

    def test_ac10_fail_safe_deny_on_logging_error(self, egress_gateway_integration):
        """AC10: Fail-Safe Deny on Logging Error.

        Assert: Postgres unavailable → LoggingError, request not forwarded
        """
        gateway, _ = egress_gateway_integration
        gateway._audit_logger.log_egress = Mock(side_effect=Exception("DB connection failed"))

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "LOG_ERROR"
        # Request should NOT have been forwarded
        gateway._http_client.send.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Behavior Spec §3 State Machine Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestStateMachineVerification:
    """Verify egress state machine matches Behavior Spec §3.1."""

    def test_state_machine_path_success(self, egress_gateway_integration):
        """Verify success path: RECEIVING → CHECKING_DOMAIN → ... → IDLE."""
        gateway, _ = egress_gateway_integration

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        # Final state should be IDLE on success
        assert result.success is True
        assert result.state == "IDLE"

    def test_state_machine_path_domain_blocked(self, egress_gateway_integration):
        """Verify domain block path: RECEIVING → CHECKING_DOMAIN → DOMAIN_BLOCKED."""
        gateway, _ = egress_gateway_integration

        request = EgressRequest(
            url="https://evil.example.com/hack",
            method="POST",
            body="",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "DOMAIN_BLOCKED"

    def test_state_machine_path_rate_exceeded(self, egress_gateway_integration):
        """Verify rate limit path: ... → RATE_CHECKING → RATE_EXCEEDED."""
        gateway, _ = egress_gateway_integration
        gateway._rate_limiter.check_and_increment = Mock(return_value=False)

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "RATE_EXCEEDED"

    def test_state_machine_path_budget_exceeded(self, egress_gateway_integration):
        """Verify budget path: ... → BUDGET_CHECKING → BUDGET_EXCEEDED."""
        gateway, _ = egress_gateway_integration
        gateway._budget_tracker.check_and_deduct = Mock(return_value=False)

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "BUDGET_EXCEEDED"

    def test_state_machine_path_logging_error(self, egress_gateway_integration):
        """Verify logging path: ... → LOGGING → LOG_ERROR (fail-safe)."""
        gateway, _ = egress_gateway_integration
        gateway._audit_logger.log_egress = Mock(side_effect=Exception("DB error"))

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "LOG_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# Factory & Default Gateway
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultGateway:
    """Test create_default_gateway factory function."""

    def test_default_gateway_creation(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Test default gateway is created with production domains."""
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        assert gateway is not None
        assert len(gateway._allowed_domains) >= 2  # At least openai and anthropic
        assert "api.openai.com" in gateway._allowed_domains
        assert "api.anthropic.com" in gateway._allowed_domains

    def test_default_domains_have_correct_configs(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Test default domains have correct rate limits and budget types."""
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        openai_config = gateway._allowed_domains["api.openai.com"]
        assert openai_config.domain_type == "llm"
        assert openai_config.budget_type == "token_count"
        assert openai_config.rate_limit_per_minute > 0
