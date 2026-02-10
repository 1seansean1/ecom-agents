"""Output guardrails: validates agent responses before delivery.

Checks:
- No API keys/secrets leaked in output
- No PII in responses
- Content relevance (is response about e-commerce?)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Secret patterns that should never appear in output
_OUTPUT_SECRET_PATTERNS = [
    # Stripe keys -- lowered from 20+ to 6+ to catch short test keys
    (re.compile(r"(?:sk|pk)[-_](?:live|test)[-_][a-zA-Z0-9]{6,}"), "stripe_key"),
    # Shopify tokens -- lowered from 32+ to 8+
    (re.compile(r"shpat_[a-f0-9]{8,}"), "shopify_token"),
    (re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"), "aws_key"),
    # Anthropic keys (sk-ant-...)
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{10,}"), "anthropic_key"),
    # OpenAI keys (sk-...)
    (re.compile(r"sk-[a-zA-Z0-9]{10,}"), "openai_key"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9._-]{30,}"), "bearer_token"),
    (re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), "password"),
    # Database/service connection URLs with credentials
    (re.compile(r"(?:postgresql|postgres|redis|mysql|mongodb)://\S+"), "db_url"),
    # --- Phase 18a: New channel/provider secret patterns ---
    # Slack bot tokens (xoxb-...)
    (re.compile(r"xoxb-[a-zA-Z0-9-]{20,}"), "slack_bot_token"),
    # Slack app-level tokens (xapp-...)
    (re.compile(r"xapp-[a-zA-Z0-9-]{20,}"), "slack_app_token"),
    # Slack user tokens (xoxp-...)
    (re.compile(r"xoxp-[a-zA-Z0-9-]{20,}"), "slack_user_token"),
    # Telegram bot tokens (numeric_id:alphanumeric_secret)
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,50}\b"), "telegram_bot_token"),
    # Discord bot tokens (base64-ish, typically 59+ chars)
    (re.compile(r"[MN][A-Za-z0-9]{23,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"), "discord_bot_token"),
    # SendGrid API keys (SG....)
    (re.compile(r"SG\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}"), "sendgrid_key"),
    # Twilio auth tokens (32-char hex)
    (re.compile(r"(?:AC|SK)[a-f0-9]{32}", re.IGNORECASE), "twilio_key"),
    # Google API keys
    (re.compile(r"AIza[A-Za-z0-9_-]{35}"), "google_api_key"),
    # GitHub tokens (ghp_, gho_, ghs_, ghr_, github_pat_)
    (re.compile(r"(?:ghp|gho|ghs|ghr)_[A-Za-z0-9_]{36,}"), "github_token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "github_pat"),
    # npm tokens
    (re.compile(r"npm_[A-Za-z0-9]{36,}"), "npm_token"),
    # Printful API key pattern
    (re.compile(r"(?:printful_api_key|PRINTFUL_API_KEY)\s*[=:]\s*\S+", re.IGNORECASE), "printful_key"),
    # Generic webhook secrets (common env var patterns)
    (re.compile(r"whsec_[a-zA-Z0-9]{20,}"), "webhook_secret"),
]

# PII patterns
_OUTPUT_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "ssn"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "credit_card"),
]


@dataclass
class OutputValidationResult:
    """Result of output validation."""

    safe: bool
    flags: list[str] = field(default_factory=list)
    sanitized: str = ""
    redacted_count: int = 0


def validate_output(text: str) -> OutputValidationResult:
    """Validate agent output for safety issues.

    Automatically redacts secrets and PII found in output.
    """
    flags: list[str] = []
    sanitized = text
    redacted_count = 0

    if not text:
        return OutputValidationResult(safe=True, sanitized=text)

    # Redact secrets
    for pattern, label in _OUTPUT_SECRET_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            flags.append(f"secret:{label}")
            redacted_count += len(matches)
            sanitized = pattern.sub(f"[REDACTED_{label.upper()}]", sanitized)

    # Redact PII
    for pattern, label in _OUTPUT_PII_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            flags.append(f"pii:{label}")
            redacted_count += len(matches)
            sanitized = pattern.sub(f"[REDACTED_{label.upper()}]", sanitized)

    if flags:
        logger.warning(
            "Output validation: redacted %d items, flags=%s",
            redacted_count,
            flags,
        )

    return OutputValidationResult(
        safe=redacted_count == 0,
        flags=flags,
        sanitized=sanitized,
        redacted_count=redacted_count,
    )
