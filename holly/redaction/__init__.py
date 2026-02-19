"""Canonical redaction library per ICD v0.1.

This module provides the single source of truth for redaction of personally
identifiable information (PII) and secrets across all Holly interfaces.

Per ICD v0.1 Redaction Policy, all interfaces that handle user input, audit
logs, event channels, or external API communication must apply these rules
before persistence or transmission.

Redaction Rules (in application order)
======================================

1. **Email** → ``[email hidden]``
   Matches RFC 5322-simplified email addresses.

2. **API Keys / Tokens** → ``[secret redacted]``
   Matches three patterns:
   - OpenAI format: ``sk-<24+ alphanumeric>``
   - Bearer tokens: ``Bearer <long_string>``
   - Generic patterns: ``{api_key,key,secret,token}=<string>``

3. **Credit Cards** → ``****-****-****-<last4>``
   Matches 16-digit cards in 4 groups (preserves last 4 digits per PCI DSS).

4. **SSN** → ``[pii redacted]``
   Matches NNN-NN-NNNN format.

5. **Phone Numbers** → ``[pii redacted]``
   Matches US phone numbers with optional country code and various separators.

Usage
=====

Typical usage in other modules:

    from holly.redaction import redact, detect_pii

    # Check if text contains PII before processing
    if detect_pii(user_input):
        log.warning("Input contains PII; will be redacted before storage")

    # Apply redaction before logging or transmission
    result = redact(audit_log_entry)
    safe_text = result.redacted_text
    rules_fired = result.rules_applied  # e.g., ["email", "api_key"]

Integration Points
==================

- **K6 gate** (ICD-025): Redact ``WALEntry.operation_result`` before append
- **Event channels** (ICD-024/025): Redact event data before publish
- **Trace store** (ICD-028): Redact trace payloads before persist
- **Egress gateway** (ICD-030): Redact prompt/completion before sending
- **Guardrails** (Step 28): Redact output before returning to Core
- **Secret scanner** (Step 30): Detect + redact secrets in traces
"""

from __future__ import annotations

from holly.redaction.core import (
    API_KEY_PATTERNS,
    CREDIT_CARD_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    SSN_PATTERN,
    RedactionError,
    RedactionResult,
    RedactionRule,
    canonicalize_redaction_rules,
    detect_pii,
    redact,
)

__all__ = [
    "API_KEY_PATTERNS",
    "CREDIT_CARD_PATTERN",
    "EMAIL_PATTERN",
    "PHONE_PATTERN",
    "SSN_PATTERN",
    "RedactionError",
    "RedactionResult",
    "RedactionRule",
    "canonicalize_redaction_rules",
    "detect_pii",
    "redact",
]
