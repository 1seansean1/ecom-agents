"""Holly Grace Egress Gateway Module.

Implements L7 application-layer egress control per ICD-030 and Behavior Spec §3.
All outbound requests to external APIs must pass through this pipeline:

1. Domain allowlist validation (L7)
2. Request payload redaction (canonical library)
3. Rate limit enforcement (per tenant, per domain)
4. Budget enforcement (per workflow)
5. Audit logging (before transmission)
6. Response payload redaction
7. Budget update (post-transmission)

This module enforces fail-safe deny: on any check failure, the request is blocked
and logged but NOT forwarded to external service.

Domain allowlist is configured per ICD-030, with per-domain rate limits and budget types.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from typing import Any

from holly.redaction import RedactionResult, redact

__all__ = [
    "AllowedDomainConfig",
    "BudgetExceededError",
    "DomainBlockedError",
    "EgressError",
    "EgressGateway",
    "EgressPipelineResult",
    "EgressRequest",
    "EgressResponse",
    "ForwardError",
    "LoggingError",
    "RateLimitError",
    "RedactionError",
    "TimeoutError",
    "create_default_gateway",
]

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class EgressError(Exception):
    """Base exception for egress gateway errors."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DomainBlockedError(EgressError):
    """Raised when request domain is not in allowlist."""

    __slots__ = ()


class RateLimitError(EgressError):
    """Raised when request exceeds per-tenant rate limit for domain."""

    __slots__ = ()


class BudgetExceededError(EgressError):
    """Raised when request would exceed workflow budget."""

    __slots__ = ()


class RedactionError(EgressError):
    """Raised when redaction of payload fails."""

    __slots__ = ()


class LoggingError(EgressError):
    """Raised when audit logging fails (fail-safe: blocks request)."""

    __slots__ = ()


class ForwardError(EgressError):
    """Raised when forwarding request to external service fails."""

    __slots__ = ()


class TimeoutError(EgressError):
    """Raised when request to external service exceeds timeout."""

    __slots__ = ()


# ─────────────────────────────────────────────────────────────────────────────
# Domain Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class AllowedDomainConfig:
    """Configuration for an allowlisted domain.

    Attributes
    ----------
    domain : str
        Fully-qualified domain name (e.g., "api.openai.com").
    domain_type : str
        Classification of domain: "llm", "email", "messaging", etc.
        Used for budget tracking granularity.
    rate_limit_per_minute : int
        Maximum requests per minute for this domain (per tenant).
    budget_type : str
        Budget unit for this domain: "token_count", "messages", "calls", etc.
    timeout_seconds : int
        HTTP request timeout (default 30s).
    """

    domain: str
    domain_type: str
    rate_limit_per_minute: int = 100
    budget_type: str = "token_count"
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        """Validate domain configuration."""
        if not self.domain:
            raise ValueError("domain must not be empty")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute must be > 0")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class EgressRequest:
    """Request to be sent to external service.

    Attributes
    ----------
    url : str
        Target URL (must match allowlisted domain).
    method : str
        HTTP method (GET, POST, etc.).
    headers : dict[str, str]
        Request headers (will be redacted).
    body : str
        Request body (will be redacted before transmission).
    tenant_id : str
        Tenant context (for rate limiting).
    workflow_id : str
        Workflow context (for budget tracking).
    correlation_id : str
        Trace correlation ID (for audit logging).
    """

    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    tenant_id: str = ""
    workflow_id: str = ""
    correlation_id: str = ""


@dataclass(slots=True)
class EgressResponse:
    """Response from external service.

    Attributes
    ----------
    status_code : int
        HTTP response status code.
    headers : dict[str, str]
        Response headers (will be redacted).
    body : str
        Response body (will be redacted before return).
    """

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Result Type
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class EgressPipelineResult:
    """Result of egress pipeline execution.

    Attributes
    ----------
    success : bool
        True if request was forwarded; False if rejected/blocked.
    state : str
        Final state in the state machine (e.g., "LOGGED", "DOMAIN_BLOCKED", "FAULTED").
    response : EgressResponse | None
        Response from external service (if success=True).
    error : EgressError | None
        Exception raised by any stage (if success=False).
    redaction_result : RedactionResult | None
        Result of redaction applied to request/response.
    timestamp : datetime
        When pipeline executed.
    audit_entry : dict[str, Any]
        Audit log entry for this request.
    """

    success: bool
    state: str
    response: EgressResponse | None = None
    error: EgressError | None = None
    redaction_result: RedactionResult | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    audit_entry: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Client Protocol (dependency injection)
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class HTTPClientProto(Protocol):
    """Protocol for HTTP client dependency injection.

    Allows egress gateway to be tested without real network calls.
    """

    def send(
        self,
        request: EgressRequest,
    ) -> EgressResponse:
        """Send HTTP request to external service.

        Parameters
        ----------
        request : EgressRequest
            Request with redacted payload and allowed domain.

        Returns
        -------
        EgressResponse
            Response from external service.

        Raises
        ------
        TimeoutError
            If request exceeds timeout.
        ForwardError
            If request fails (network error, 5xx response, etc.).
        """
        ...


@runtime_checkable
class RateLimiterProto(Protocol):
    """Protocol for rate limiter (Redis-backed)."""

    def check_and_increment(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
    ) -> bool:
        """Check if key is under limit, then increment counter.

        Parameters
        ----------
        key : str
            Rate limit key (e.g., "egress:rate:tenant_id:domain").
        limit : int
            Maximum count per window.
        window_seconds : int
            Window duration (default 60s).

        Returns
        -------
        bool
            True if under limit; False if at/over limit.
        """
        ...


@runtime_checkable
class BudgetTrackerProto(Protocol):
    """Protocol for budget tracker (Postgres-backed)."""

    def check_and_deduct(
        self,
        workflow_id: str,
        budget_type: str,
        amount: int,
    ) -> bool:
        """Check if budget allows amount, then deduct.

        Parameters
        ----------
        workflow_id : str
            Workflow ID.
        budget_type : str
            Budget category (e.g., "token_count", "messages").
        amount : int
            Amount to deduct.

        Returns
        -------
        bool
            True if budget allowed deduction; False if would exceed.
        """
        ...


@runtime_checkable
class AuditLoggerProto(Protocol):
    """Protocol for audit logging (Postgres-backed)."""

    def log_egress(
        self,
        audit_entry: dict[str, Any],
    ) -> None:
        """Write egress event to audit log.

        Parameters
        ----------
        audit_entry : dict[str, Any]
            Audit entry with tenant_id, workflow_id, domain, request, etc.

        Raises
        ------
        LoggingError
            If write fails.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Main Egress Gateway
# ─────────────────────────────────────────────────────────────────────────────


class EgressGateway:
    """L7 egress gateway enforcing domain allowlist, redaction, rate limits, budgets.

    Per Behavior Spec §3.1, implements the egress filter pipeline:
    RECEIVING → CHECKING_DOMAIN → REDACTING → RATE_CHECKING → BUDGET_CHECKING
    → LOGGING → FORWARDING → RESPONSE_REDACTING → IDLE

    All checks are fail-safe deny: on any error, request is blocked.

    Attributes
    ----------
    allowed_domains : dict[str, AllowedDomainConfig]
        Map of domain → configuration for allowed outbound targets.
    http_client : HTTPClientProto
        HTTP client for forwarding requests.
    rate_limiter : RateLimiterProto
        Redis-backed rate limiter.
    budget_tracker : BudgetTrackerProto
        Postgres-backed budget tracker.
    audit_logger : AuditLoggerProto
        Postgres-backed audit logger.
    """

    __slots__ = (
        "_allowed_domains",
        "_audit_logger",
        "_budget_tracker",
        "_http_client",
        "_rate_limiter",
    )

    def __init__(
        self,
        allowed_domains: dict[str, AllowedDomainConfig],
        http_client: HTTPClientProto,
        rate_limiter: RateLimiterProto,
        budget_tracker: BudgetTrackerProto,
        audit_logger: AuditLoggerProto,
    ) -> None:
        """Initialize egress gateway.

        Parameters
        ----------
        allowed_domains : dict[str, AllowedDomainConfig]
            Map of domain → allowed configuration.
        http_client : HTTPClientProto
            HTTP client for forwarding.
        rate_limiter : RateLimiterProto
            Rate limiter implementation.
        budget_tracker : BudgetTrackerProto
            Budget tracker implementation.
        audit_logger : AuditLoggerProto
            Audit logger implementation.
        """
        self._allowed_domains = allowed_domains
        self._http_client = http_client
        self._rate_limiter = rate_limiter
        self._budget_tracker = budget_tracker
        self._audit_logger = audit_logger

    def enforce_egress(self, request: EgressRequest) -> EgressPipelineResult:
        """Enforce egress gateway pipeline on outbound request.

        Implements full Behavior Spec §3.1 state machine:
        - Domain check (CHECKING_DOMAIN)
        - Redaction (REDACTING)
        - Rate limiting (RATE_CHECKING)
        - Budget enforcement (BUDGET_CHECKING)
        - Audit logging (LOGGING)
        - Forwarding (FORWARDING)
        - Response redaction (RESPONSE_REDACTING)

        Parameters
        ----------
        request : EgressRequest
            Outbound request to external API.

        Returns
        -------
        EgressPipelineResult
            Result of pipeline with final state and any errors.

        Notes
        -----
        On any failure, request is not forwarded and error is logged.
        """
        audit_entry: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": request.tenant_id,
            "workflow_id": request.workflow_id,
            "correlation_id": request.correlation_id,
            "url": request.url,
            "method": request.method,
        }

        # State: RECEIVING
        state = "RECEIVING"

        try:
            # State: CHECKING_DOMAIN
            state = "CHECKING_DOMAIN"
            domain = self._extract_domain(request.url)
            if domain not in self._allowed_domains:
                state = "DOMAIN_BLOCKED"
                error = DomainBlockedError(f"Domain {domain} not in allowlist")
                log.warning(
                    f"Egress blocked: domain {domain} not allowed | "
                    f"tenant={request.tenant_id} workflow={request.workflow_id}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "DOMAIN_ALLOWED"
            domain_config = self._allowed_domains[domain]

            # State: REDACTING (request)
            state = "REDACTING"
            try:
                redaction_result = redact(request.body)
                redacted_body = redaction_result.redacted_text
                redacted_headers = self._redact_headers(request.headers)
            except Exception as e:
                state = "REDACTION_ERROR"
                error = RedactionError(f"Request redaction failed: {e}")
                log.exception(
                    f"Egress redaction error | tenant={request.tenant_id} "
                    f"workflow={request.workflow_id}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "REDACTED"

            # State: RATE_CHECKING
            state = "RATE_CHECKING"
            rate_key = f"egress:rate:{request.tenant_id}:{domain}"
            rate_allowed = self._rate_limiter.check_and_increment(
                rate_key,
                domain_config.rate_limit_per_minute,
                window_seconds=60,
            )
            if not rate_allowed:
                state = "RATE_EXCEEDED"
                error = RateLimitError(
                    f"Rate limit {domain_config.rate_limit_per_minute}/min "
                    f"exceeded for {domain}"
                )
                log.warning(
                    f"Egress rate limited | tenant={request.tenant_id} "
                    f"domain={domain} workflow={request.workflow_id}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "RATE_ALLOWED"

            # State: BUDGET_CHECKING
            state = "BUDGET_CHECKING"
            # Estimate tokens in redacted request (rough: 1 token ≈ 4 chars)
            tokens_estimated = max(1, len(redacted_body) // 4)
            budget_allowed = self._budget_tracker.check_and_deduct(
                request.workflow_id,
                domain_config.budget_type,
                tokens_estimated,
            )
            if not budget_allowed:
                state = "BUDGET_EXCEEDED"
                error = BudgetExceededError(
                    f"Workflow budget exceeded for {domain_config.budget_type}"
                )
                log.warning(
                    f"Egress budget exceeded | tenant={request.tenant_id} "
                    f"workflow={request.workflow_id} domain={domain}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "BUDGET_ALLOWED"

            # State: LOGGING
            state = "LOGGING"
            audit_entry["state"] = "LOGGING"
            audit_entry["domain"] = domain
            audit_entry["domain_type"] = domain_config.domain_type
            audit_entry["redacted_request_preview"] = redacted_body[:200]
            audit_entry["tokens_estimated"] = tokens_estimated

            try:
                self._audit_logger.log_egress(audit_entry)
            except Exception as e:
                state = "LOG_ERROR"
                error = LoggingError(f"Failed to write audit log: {e}")
                log.exception(
                    f"Egress logging error (fail-safe deny) | "
                    f"tenant={request.tenant_id} workflow={request.workflow_id}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "LOGGED"

            # State: FORWARDING
            state = "FORWARDING"
            # Create forwarding request with redacted payload
            forward_request = EgressRequest(
                url=request.url,
                method=request.method,
                headers=redacted_headers,
                body=redacted_body,
                tenant_id=request.tenant_id,
                workflow_id=request.workflow_id,
                correlation_id=request.correlation_id,
            )

            try:
                response = self._http_client.send(forward_request)
            except TimeoutError as e:
                state = "FORWARD_ERROR"
                error = ForwardError(f"Request timeout: {e}")
                log.warning(
                    f"Egress forward timeout | tenant={request.tenant_id} "
                    f"workflow={request.workflow_id} domain={domain}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )
            except Exception as e:
                state = "FORWARD_ERROR"
                error = ForwardError(f"Request failed: {e}")
                log.warning(
                    f"Egress forward error | tenant={request.tenant_id} "
                    f"workflow={request.workflow_id} domain={domain}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                )

            state = "RESPONSE_RECEIVED"

            # State: RESPONSE_REDACTING
            state = "RESPONSE_REDACTING"
            try:
                response_redaction = redact(response.body)
                redacted_response_body = response_redaction.redacted_text
                redacted_response_headers = self._redact_headers(response.headers)
                response.body = redacted_response_body
                response.headers = redacted_response_headers
            except Exception as e:
                state = "REDACTION_ERROR"
                error = RedactionError(f"Response redaction failed: {e}")
                log.exception(
                    f"Egress response redaction error | "
                    f"tenant={request.tenant_id} workflow={request.workflow_id}"
                )
                audit_entry["state"] = state
                audit_entry["error"] = str(error)
                return EgressPipelineResult(
                    success=False,
                    state=state,
                    error=error,
                    audit_entry=audit_entry,
                    response=response,
                )

            state = "RESPONSE_REDACTED"

            # State: IDLE
            state = "IDLE"
            audit_entry["state"] = "FORWARDED"
            audit_entry["response_status"] = response.status_code

            log.info(
                f"Egress forwarded | tenant={request.tenant_id} "
                f"workflow={request.workflow_id} domain={domain} "
                f"status={response.status_code}"
            )

            return EgressPipelineResult(
                success=True,
                state=state,
                response=response,
                redaction_result=redaction_result,
                audit_entry=audit_entry,
            )

        except EgressError as e:
            # All EgressError subclasses are already handled above
            return EgressPipelineResult(
                success=False,
                state=state,
                error=e,
                audit_entry=audit_entry,
            )
        except Exception as e:
            # Unexpected error: fail-safe deny
            state = "FAULTED"
            error = EgressError(f"Unexpected error in egress pipeline: {e}")
            log.exception(
                f"Unexpected egress error | tenant={request.tenant_id} "
                f"workflow={request.workflow_id}"
            )
            audit_entry["state"] = state
            audit_entry["error"] = str(error)
            return EgressPipelineResult(
                success=False,
                state=state,
                error=error,
                audit_entry=audit_entry,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.

        Parameters
        ----------
        url : str
            Full URL (e.g., "https://api.openai.com/v1/chat/completions").

        Returns
        -------
        str
            Domain only (e.g., "api.openai.com").
        """
        # Simple regex: extract domain from URL
        # Handles https://, http://, ports, and paths
        match = re.match(r"https?://([^/?#:]+)", url)
        if match:
            return match.group(1).lower()
        return ""

    def _redact_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Redact sensitive headers (Authorization, X-API-Key, etc.).

        Parameters
        ----------
        headers : dict[str, str]
            HTTP headers.

        Returns
        -------
        dict[str, str]
            Headers with sensitive values redacted.
        """
        sensitive_header_keys = {
            "authorization",
            "x-api-key",
            "x-auth-token",
            "cookie",
            "set-cookie",
            "x-access-token",
        }
        redacted = {}
        for key, value in headers.items():
            if key.lower() in sensitive_header_keys:
                redacted[key] = "[secret redacted]"
            else:
                redacted[key] = value
        return redacted


# ─────────────────────────────────────────────────────────────────────────────
# Factory Function
# ─────────────────────────────────────────────────────────────────────────────


def create_default_gateway(
    http_client: HTTPClientProto,
    rate_limiter: RateLimiterProto,
    budget_tracker: BudgetTrackerProto,
    audit_logger: AuditLoggerProto,
) -> EgressGateway:
    """Create egress gateway with default allowed domains per ICD-030.

    Parameters
    ----------
    http_client : HTTPClientProto
        HTTP client for forwarding requests.
    rate_limiter : RateLimiterProto
        Rate limiter (Redis-backed).
    budget_tracker : BudgetTrackerProto
        Budget tracker (Postgres-backed).
    audit_logger : AuditLoggerProto
        Audit logger (Postgres-backed).

    Returns
    -------
    EgressGateway
        Configured egress gateway with production allowlist.
    """
    allowed_domains: dict[str, AllowedDomainConfig] = {
        "api.openai.com": AllowedDomainConfig(
            domain="api.openai.com",
            domain_type="llm",
            rate_limit_per_minute=100,
            budget_type="token_count",
            timeout_seconds=30,
        ),
        "api.anthropic.com": AllowedDomainConfig(
            domain="api.anthropic.com",
            domain_type="llm",
            rate_limit_per_minute=100,
            budget_type="token_count",
            timeout_seconds=30,
        ),
        "api.gmail.com": AllowedDomainConfig(
            domain="api.gmail.com",
            domain_type="email",
            rate_limit_per_minute=10,
            budget_type="messages",
            timeout_seconds=30,
        ),
        "api.slack.com": AllowedDomainConfig(
            domain="api.slack.com",
            domain_type="messaging",
            rate_limit_per_minute=50,
            budget_type="messages",
            timeout_seconds=30,
        ),
    }

    return EgressGateway(
        allowed_domains=allowed_domains,
        http_client=http_client,
        rate_limiter=rate_limiter,
        budget_tracker=budget_tracker,
        audit_logger=audit_logger,
    )
