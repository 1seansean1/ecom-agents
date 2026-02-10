"""Customer session data models.

Security contract:
- Customer can only access own session (enforced by session token)
- PII stored only in session model, sanitized before LLM dispatch
- Session tokens are separate from JWT (1h TTL, customer-scoped)
- Identity linking requires verification (not done at model layer)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    """Customer session lifecycle states."""
    ACTIVE = "active"
    IDLE = "idle"       # No activity for > idle_threshold
    EXPIRED = "expired"  # Past TTL
    CLOSED = "closed"   # Explicitly closed


@dataclass
class CustomerIdentity:
    """Linked identity for a customer session."""
    identity_type: str  # email, phone, shopify_customer_id
    identity_value: str  # The actual value (PII)
    verified: bool = False
    linked_at: float = 0.0


@dataclass
class SessionMessage:
    """A message in the session conversation history."""
    role: str  # customer, agent, system
    content: str
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomerSession:
    """A customer session with conversation history and identity links.

    Security notes:
    - session_id is the access token (not guessable)
    - identities contain PII (must sanitize before LLM)
    - messages may contain PII (must sanitize before LLM)
    """
    session_id: str = ""
    customer_ref: str = ""  # Non-PII customer reference
    status: SessionStatus = SessionStatus.ACTIVE
    identities: list[CustomerIdentity] = field(default_factory=list)
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: float = 0.0
    last_activity: float = 0.0
    expires_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    # Memory compaction tracking
    compacted_at: float = 0.0
    message_count_at_compaction: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE and not self.is_expired

    @property
    def message_count(self) -> int:
        return len(self.messages)


def create_session(
    customer_ref: str = "",
    ttl_seconds: int = 3600,
) -> CustomerSession:
    """Create a new customer session.

    Args:
        customer_ref: Non-PII customer reference
        ttl_seconds: Session lifetime in seconds (default 1h)

    Returns:
        New CustomerSession with generated session_id
    """
    now = time.time()
    return CustomerSession(
        session_id=str(uuid.uuid4()),
        customer_ref=customer_ref or f"cust_{uuid.uuid4().hex[:8]}",
        status=SessionStatus.ACTIVE,
        created_at=now,
        last_activity=now,
        expires_at=now + ttl_seconds,
    )
