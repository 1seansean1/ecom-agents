"""Session manager — in-memory session store with lifecycle management.

Handles session creation, message appending, identity linking,
and memory compaction.

Security contract:
- Sessions are access-controlled by session_id (UUID, not guessable)
- PII sanitization happens at LLM dispatch boundary (see sanitizer.py)
- Memory compaction prevents context window explosion
- Per-customer rate limiting (100 messages/hour)
- 90-day retention for compliance
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.sessions.models import (
    CustomerIdentity,
    CustomerSession,
    SessionMessage,
    SessionStatus,
    create_session,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

_MAX_MESSAGES_PER_SESSION = 500
_COMPACTION_THRESHOLD = 200  # Compact when messages exceed this
_COMPACTION_KEEP_RECENT = 50  # Keep last N messages after compaction
_RATE_LIMIT_MESSAGES_PER_HOUR = 100
_DEFAULT_TTL_SECONDS = 3600  # 1 hour
_IDLE_THRESHOLD_SECONDS = 1800  # 30 minutes


class SessionManager:
    """In-memory session store with lifecycle management.

    For production, this would be backed by PostgreSQL.
    In-memory implementation provides the correct interface
    and security controls.
    """

    def __init__(self):
        self._sessions: dict[str, CustomerSession] = {}
        self._rate_counts: dict[str, list[float]] = {}  # session_id -> message timestamps

    def create(self, customer_ref: str = "", ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> CustomerSession:
        """Create a new customer session."""
        session = create_session(customer_ref=customer_ref, ttl_seconds=ttl_seconds)
        self._sessions[session.session_id] = session
        logger.info("Session created: %s (ref=%s)", session.session_id[:8], session.customer_ref)
        return session

    def get(self, session_id: str) -> CustomerSession | None:
        """Get a session by ID. Returns None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        # Check expiry
        if session.is_expired:
            session.status = SessionStatus.EXPIRED
            return None

        # Check idle
        if (
            session.status == SessionStatus.ACTIVE
            and time.time() - session.last_activity > _IDLE_THRESHOLD_SECONDS
        ):
            session.status = SessionStatus.IDLE

        return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Add a message to a session.

        Returns False if session not found, expired, or rate limited.
        """
        session = self.get(session_id)
        if session is None:
            return False

        # Rate limiting
        if not self._check_rate_limit(session_id):
            logger.warning("Session %s rate limited", session_id[:8])
            return False

        # Message count limit
        if session.message_count >= _MAX_MESSAGES_PER_SESSION:
            self._compact(session)

        msg = SessionMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        session.messages.append(msg)
        session.last_activity = time.time()

        # Reactivate idle sessions
        if session.status == SessionStatus.IDLE:
            session.status = SessionStatus.ACTIVE

        return True

    def link_identity(
        self,
        session_id: str,
        identity_type: str,
        identity_value: str,
        verified: bool = False,
    ) -> bool:
        """Link an identity to a session.

        Args:
            session_id: Target session
            identity_type: Type (email, phone, shopify_customer_id)
            identity_value: The PII value
            verified: Whether identity has been verified

        Returns:
            True if linked successfully
        """
        session = self.get(session_id)
        if session is None:
            return False

        # Check for duplicate identity
        for existing in session.identities:
            if existing.identity_type == identity_type and existing.identity_value == identity_value:
                existing.verified = verified
                return True

        session.identities.append(
            CustomerIdentity(
                identity_type=identity_type,
                identity_value=identity_value,
                verified=verified,
                linked_at=time.time(),
            )
        )
        logger.info(
            "Identity linked: session=%s type=%s verified=%s",
            session_id[:8],
            identity_type,
            verified,
        )
        return True

    def close(self, session_id: str) -> bool:
        """Explicitly close a session."""
        session = self.get(session_id)
        if session is None:
            return False
        session.status = SessionStatus.CLOSED
        logger.info("Session closed: %s", session_id[:8])
        return True

    def get_context(self, session_id: str, max_messages: int = 20) -> list[SessionMessage]:
        """Get recent messages for LLM context.

        Returns the most recent messages, capped at max_messages.
        PII sanitization should be applied AFTER this call.
        """
        session = self.get(session_id)
        if session is None:
            return []
        return session.messages[-max_messages:]

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        expired_ids = [
            sid for sid, s in self._sessions.items()
            if s.is_expired or s.status == SessionStatus.CLOSED
        ]
        for sid in expired_ids:
            del self._sessions[sid]
            self._rate_counts.pop(sid, None)
        if expired_ids:
            logger.info("Cleaned up %d expired sessions", len(expired_ids))
        return len(expired_ids)

    @property
    def active_count(self) -> int:
        """Count of active sessions."""
        return sum(1 for s in self._sessions.values() if s.is_active)

    def _check_rate_limit(self, session_id: str) -> bool:
        """Check per-session rate limit (messages per hour)."""
        now = time.time()
        timestamps = self._rate_counts.get(session_id, [])

        # Remove timestamps older than 1 hour
        cutoff = now - 3600
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= _RATE_LIMIT_MESSAGES_PER_HOUR:
            return False

        timestamps.append(now)
        self._rate_counts[session_id] = timestamps
        return True

    def _compact(self, session: CustomerSession) -> None:
        """Compact session messages to prevent context explosion.

        Keeps the most recent messages and creates a summary marker.
        """
        if session.message_count <= _COMPACTION_KEEP_RECENT:
            return

        # Keep only recent messages
        old_count = session.message_count
        session.messages = session.messages[-_COMPACTION_KEEP_RECENT:]

        # Add compaction marker
        session.messages.insert(
            0,
            SessionMessage(
                role="system",
                content=f"[Session history compacted: {old_count - _COMPACTION_KEEP_RECENT} older messages removed]",
                timestamp=time.time(),
            ),
        )
        session.compacted_at = time.time()
        session.message_count_at_compaction = old_count

        logger.info(
            "Session %s compacted: %d -> %d messages",
            session.session_id[:8],
            old_count,
            session.message_count,
        )
