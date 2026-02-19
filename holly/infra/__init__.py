"""Holly infra module — egress gateway and secrets management.

Public API:
- EgressGateway: L7 egress control (domain allowlist, redaction, rate limiting)
- create_default_gateway: Factory for production egress gateway
"""

from __future__ import annotations

from holly.infra.egress import (
    AllowedDomainConfig,
    AuditLoggerProto,
    BudgetExceededError,
    BudgetTrackerProto,
    DomainBlockedError,
    EgressError,
    EgressGateway,
    EgressPipelineResult,
    EgressRequest,
    EgressResponse,
    ForwardError,
    HTTPClientProto,
    LoggingError,
    RateLimiterProto,
    RateLimitError,
    RedactionError,
    TimeoutError,
    create_default_gateway,
)

__all__ = [
    "AllowedDomainConfig",
    "AuditLoggerProto",
    "BudgetExceededError",
    "BudgetTrackerProto",
    "DomainBlockedError",
    "EgressError",
    "EgressGateway",
    "EgressPipelineResult",
    "EgressRequest",
    "EgressResponse",
    "ForwardError",
    "HTTPClientProto",
    "LoggingError",
    "RateLimitError",
    "RateLimiterProto",
    "RedactionError",
    "TimeoutError",
    "create_default_gateway",
]
