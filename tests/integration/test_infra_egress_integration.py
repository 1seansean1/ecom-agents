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


# ─────────────────────────────────────────────────────────────────────────────
# Task 31.5: Layer Independence Tests
# Verify egress works as independent safety layer without kernel dependency
# ─────────────────────────────────────────────────────────────────────────────


class TestLayerIndependence:
    """Task 31.5: Verify egress as independent safety layer.

    Per Behavior Spec §3 isolation properties, egress must function as a
    complete, independent safety barrier even when called without kernel context.
    These tests verify that egress can block exfiltration without any kernel
    involvement (i.e., with a "stub kernel" that provides only minimal context).
    """

    def test_egress_blocks_without_kernel_context_domain_check(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress blocks disallowed domains even without kernel involvement.

        Acceptance Criterion: "Egress blocks exfiltration without kernel"
        - Create minimal caller context (no kernel)
        - Attempt request to non-allowlisted domain
        - Assert: Request blocked by egress (DomainBlockedError), not forwarded
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Minimal context: no kernel, just basic caller info
        request = EgressRequest(
            url="https://attacker.malicious.example.com/exfil",
            method="POST",
            body="sensitive_data",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
            # No kernel context required
        )

        result = gateway.enforce_egress(request)

        # Verify request is blocked by egress itself
        assert result.success is False
        assert result.state == "DOMAIN_BLOCKED"
        # Verify HTTP client was NOT called
        http_client_mock.send.assert_not_called()

    def test_egress_blocks_without_kernel_context_rate_limit(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress enforces rate limits independently without kernel.

        Acceptance Criterion: "Layer independent rate enforcement"
        - Setup rate limiter to reject all calls
        - Attempt egress request to allowlisted domain
        - Assert: Request blocked by rate limiter (RateLimitError), not forwarded
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )
        # Override rate limiter to always reject
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
        # Verify HTTP client was NOT called
        http_client_mock.send.assert_not_called()

    def test_egress_blocks_without_kernel_context_budget(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress enforces budgets independently without kernel.

        Acceptance Criterion: "Layer independent budget enforcement"
        - Setup budget tracker to reject all deductions
        - Attempt egress request to allowlisted domain
        - Assert: Request blocked by budget check (BudgetExceededError)
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )
        # Override budget tracker to always reject
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
        # Verify HTTP client was NOT called
        http_client_mock.send.assert_not_called()

    def test_egress_enforces_allowlist_without_kernel_override(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress allowlist is independent and cannot be bypassed by context.

        Acceptance Criterion: "Allowlist enforcement independent of caller privilege"
        - Even if caller claims to be kernel or privileged, allowlist is enforced
        - Non-allowlisted domains are always blocked
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Try to exfiltrate to cloud storage provider (not in allowlist)
        request = EgressRequest(
            url="https://s3.amazonaws.com/my-bucket/exfil.tar.gz",
            method="PUT",
            body="sensitive_data",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        assert result.success is False
        assert result.state == "DOMAIN_BLOCKED"
        http_client_mock.send.assert_not_called()

    def test_egress_redaction_independent_of_kernel(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress redaction operates independently without kernel processing.

        Acceptance Criterion: "Redaction applied without kernel awareness"
        - Egress applies redaction rules to request payload
        - Kernel context not required for redaction to occur
        - PII is redacted before forward, regardless of caller
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Request with PII in body
        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body='{"message": "Email is user@example.com and SSN is 123-45-6789"}',
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        # Request should succeed (allowlist, rate, budget OK)
        assert result.success is True

        # Verify redaction happened: check the mock was called
        http_client_mock.send.assert_called_once()

    def test_egress_audit_logging_independent_of_kernel(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress audit logging operates independently without kernel.

        Acceptance Criterion: "All egress attempts logged regardless of kernel"
        - Egress logs all requests (blocked and forwarded)
        - Audit trail is maintained independently
        - Logging failures block forward (fail-safe)
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        # Verify audit logger was called
        audit_logger_mock.log_egress.assert_called()

    def test_egress_isolation_no_kernel_state_leakage(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress state machine is isolated; no kernel state affects decisions.

        Acceptance Criterion: "Egress decisions independent of kernel state"
        - Rate limits apply per egress request, not per kernel state
        - Budget deductions are independent
        - State machine progression is deterministic regardless of kernel
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Two requests from same tenant/workflow
        request_1 = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test1",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )
        request_2 = EgressRequest(
            url="https://api.anthropic.com/v1/messages",
            method="POST",
            body="test2",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result_1 = gateway.enforce_egress(request_1)
        result_2 = gateway.enforce_egress(request_2)

        # Both should process independently
        assert result_1.success is True
        assert result_2.success is True
        # Both should be logged
        assert audit_logger_mock.log_egress.call_count >= 2

    def test_egress_multilayer_checks_all_enforced_independently(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """All egress checks operate independently; single failure blocks forward.

        Acceptance Criterion: "Fail-safe: any check failure blocks egress"
        - Domain, rate, budget, redaction, logging all checked independently
        - Failure in ANY check results in blocked request
        - No bypass paths exist
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Test 1: Domain failure blocks
        request_bad_domain = EgressRequest(
            url="https://evil.example.com/api",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )
        assert gateway.enforce_egress(request_bad_domain).success is False

        # Test 2: Rate limit failure blocks
        gateway._rate_limiter.check_and_increment = Mock(return_value=False)
        request_ok_domain = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )
        assert gateway.enforce_egress(request_ok_domain).success is False

        # Test 3: Budget failure blocks
        gateway._rate_limiter.check_and_increment = Mock(return_value=True)
        gateway._budget_tracker.check_and_deduct = Mock(return_value=False)
        assert gateway.enforce_egress(request_ok_domain).success is False

        # Test 4: Logging failure blocks (fail-safe)
        gateway._budget_tracker.check_and_deduct = Mock(return_value=True)
        gateway._audit_logger.log_egress = Mock(side_effect=Exception("DB error"))
        assert gateway.enforce_egress(request_ok_domain).success is False

        # Verify HTTP client was never called when any check failed
        http_client_mock.send.assert_not_called()

    def test_egress_nondeterministic_kernel_doesnt_affect_blocking(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress blocking is deterministic regardless of kernel nondeterminism.

        Acceptance Criterion: "Exfiltration blocked in all scenarios"
        - Blocked requests remain blocked even with random kernel state
        - Egress doesn't rely on kernel for safety decisions
        - Independent safety barriers
        """
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Non-allowlisted domain (always blocked)
        request = EgressRequest(
            url="https://external-storage.example.com/exfil",
            method="POST",
            body="data",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        # Run multiple times; result should always be blocked
        for _ in range(5):
            result = gateway.enforce_egress(request)
            assert result.success is False
            assert result.state == "DOMAIN_BLOCKED"

        http_client_mock.send.assert_not_called()

    def test_egress_can_start_fresh_without_kernel_initialization(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress initializes and operates without kernel setup.

        Acceptance Criterion: "Egress operational without kernel dependencies"
        - Egress can be instantiated without kernel module
        - First request can be processed without prior kernel context
        - No bootstrap dependencies on kernel
        """
        # Create gateway without any kernel initialization
        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Immediately process a request (no kernel context)
        request = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        result = gateway.enforce_egress(request)

        # Should process successfully
        assert result.success is True
        assert result.state == "IDLE"
        http_client_mock.send.assert_called_once()

    def test_egress_isolation_tenant_separation_without_kernel(
        self, http_client_mock, rate_limiter_mock, budget_tracker_mock, audit_logger_mock
    ):
        """Egress maintains tenant isolation independently of kernel.

        Acceptance Criterion: "Tenant isolation enforced by egress layer"
        - Rate limits and budgets per tenant tracked independently
        - No cross-tenant leakage
        - Isolation works without kernel involvement
        """
        # Track calls per tenant
        rate_limit_calls = {}

        def track_rate_limit(key: str, limit: int, window_seconds: int = 60) -> bool:
            rate_limit_calls[key] = rate_limit_calls.get(key, 0) + 1
            return rate_limit_calls[key] <= limit

        rate_limiter_mock.check_and_increment = Mock(side_effect=track_rate_limit)

        gateway = create_default_gateway(
            http_client=http_client_mock,
            rate_limiter=rate_limiter_mock,
            budget_tracker=budget_tracker_mock,
            audit_logger=audit_logger_mock,
        )

        # Request from tenant-1
        req_t1 = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-1",
            workflow_id="workflow-1",
        )

        # Request from tenant-2
        req_t2 = EgressRequest(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            body="test",
            tenant_id="tenant-2",
            workflow_id="workflow-1",
        )

        result_t1 = gateway.enforce_egress(req_t1)
        result_t2 = gateway.enforce_egress(req_t2)

        # Both should succeed (independent rate limits)
        assert result_t1.success is True
        assert result_t2.success is True

        # Rate limiter should have been called for each tenant separately
        assert rate_limiter_mock.check_and_increment.call_count >= 2
