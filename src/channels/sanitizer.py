"""Event sanitization for notification dispatch.

Sanitizes event data before sending to external channels:
- Redacts PII (emails, phone numbers)
- Strips internal identifiers
- Caps message length
- Removes secret patterns (reuses output_validator patterns)

Security contract:
- Events MAY contain customer emails, order details, internal IDs
- External channels MUST receive sanitized versions only
- This is the last-mile defense before data leaves the system
"""

from __future__ import annotations

import re
from typing import Any

from src.channels.protocol import NotificationMessage

# Max body length for notifications
_MAX_BODY_LENGTH = 500

# PII patterns to redact
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Internal patterns to strip
_INTERNAL_PATTERNS = [
    re.compile(r"postgresql://\S+"),
    re.compile(r"redis://\S+"),
    re.compile(r"sk[-_](?:live|test)[-_][a-zA-Z0-9]+"),
    re.compile(r"shpat_[a-f0-9]+"),
]


def sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Sanitize an event dict for external channel dispatch.

    Returns a new dict with PII and secrets redacted.
    """
    sanitized = {}
    for key, value in event.items():
        if isinstance(value, str):
            sanitized[key] = _sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_event(value)
        else:
            sanitized[key] = value
    return sanitized


def _sanitize_string(text: str) -> str:
    """Sanitize a single string value."""
    result = text

    # Redact emails
    result = _EMAIL_PATTERN.sub("[email]", result)

    # Redact phone numbers
    result = _PHONE_PATTERN.sub("[phone]", result)

    # Redact SSNs
    result = _SSN_PATTERN.sub("[ssn]", result)

    # Redact credit cards
    result = _CC_PATTERN.sub("[card]", result)

    # Strip internal patterns
    for pattern in _INTERNAL_PATTERNS:
        result = pattern.sub("[redacted]", result)

    return result


def sanitize_notification(message: NotificationMessage) -> NotificationMessage:
    """Sanitize a notification message before dispatch."""
    body = _sanitize_string(message.body)
    if len(body) > _MAX_BODY_LENGTH:
        body = body[:_MAX_BODY_LENGTH] + "..."

    title = _sanitize_string(message.title)

    return NotificationMessage(
        title=title,
        body=body,
        severity=message.severity,
        event_type=message.event_type,
        metadata=sanitize_event(message.metadata),
    )
