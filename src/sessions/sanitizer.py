"""PII sanitization for LLM dispatch — strips customer PII before sending to external LLMs.

Security contract:
- Replace real names with [CUSTOMER_REF: xxx]
- Redact email, phone, SSN, credit card patterns
- Strip addresses
- Return sanitized text that's safe for LLM context
"""

from __future__ import annotations

import re
from typing import Any

from src.sessions.models import CustomerSession, SessionMessage

# PII patterns (reuses patterns from channel sanitizer)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|"
    r"Boulevard|Blvd|Court|Ct|Place|Pl|Way)\b",
    re.IGNORECASE,
)


def sanitize_text_for_llm(text: str, customer_ref: str = "") -> str:
    """Sanitize text content for LLM dispatch.

    Replaces PII patterns with safe placeholders.
    """
    result = text

    # Redact PII patterns
    result = _EMAIL_PATTERN.sub("[EMAIL]", result)
    result = _PHONE_PATTERN.sub("[PHONE]", result)
    result = _SSN_PATTERN.sub("[SSN]", result)
    result = _CC_PATTERN.sub("[CARD]", result)
    result = _ADDRESS_PATTERN.sub("[ADDRESS]", result)

    return result


def sanitize_messages_for_llm(
    messages: list[SessionMessage],
    customer_ref: str = "",
) -> list[dict[str, str]]:
    """Sanitize session messages for LLM context.

    Returns list of {role, content} dicts safe for LLM dispatch.
    """
    sanitized = []
    for msg in messages:
        sanitized.append({
            "role": msg.role,
            "content": sanitize_text_for_llm(msg.content, customer_ref),
        })
    return sanitized


def sanitize_session_context(session: CustomerSession, max_messages: int = 20) -> dict[str, Any]:
    """Build a sanitized context dict for LLM dispatch.

    Includes customer ref (non-PII) and sanitized message history.
    Does NOT include identities (raw PII).
    """
    recent = session.messages[-max_messages:]
    return {
        "customer_ref": session.customer_ref,
        "session_id_prefix": session.session_id[:8],
        "message_count": session.message_count,
        "messages": sanitize_messages_for_llm(recent, session.customer_ref),
    }
