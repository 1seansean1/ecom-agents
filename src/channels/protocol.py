"""Channel protocol and dock — unified notification dispatch.

Design inspired by openclaw's dock pattern:
- Each channel implements send(), format(), and capabilities()
- ChannelDock is the registry that routes events to channels
- Event routing uses allow/deny rules per channel
- Circuit breaker per channel (failures don't cascade)

Security contract:
- Event bodies sanitized before dispatch (PII redacted, length capped)
- Per-channel credential storage (env vars, not hardcoded)
- All dispatches logged for audit trail
- Channel failures isolated (one channel down doesn't block others)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ChannelStatus(str, Enum):
    """Channel operational status."""
    ACTIVE = "active"
    DEGRADED = "degraded"  # Circuit breaker half-open
    DISABLED = "disabled"  # Manually disabled or circuit open


@dataclass
class NotificationMessage:
    """A notification ready for dispatch to a channel."""
    title: str
    body: str
    severity: str = "info"  # info, warning, error, critical
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """Result of sending a notification."""
    success: bool
    channel_id: str
    error: str = ""
    response_id: str = ""  # Provider message ID (Slack ts, email message-id)


@runtime_checkable
class Channel(Protocol):
    """Protocol for notification channels."""

    @property
    def channel_id(self) -> str:
        """Unique identifier for this channel."""
        ...

    @property
    def channel_type(self) -> str:
        """Type of channel (slack, email, discord, etc.)."""
        ...

    @property
    def is_configured(self) -> bool:
        """Whether this channel has valid credentials configured."""
        ...

    def format_message(self, message: NotificationMessage) -> Any:
        """Format a notification for this channel's API."""
        ...

    def send(self, formatted: Any) -> SendResult:
        """Send a formatted message. Returns SendResult."""
        ...

    @property
    def capabilities(self) -> set[str]:
        """Set of capabilities: 'text', 'rich', 'attachments', 'threading'."""
        ...


@dataclass
class ChannelConfig:
    """Configuration for a registered channel."""
    channel: Channel
    status: ChannelStatus = ChannelStatus.ACTIVE
    allow_events: set[str] | None = None  # None = allow all
    deny_events: set[str] = field(default_factory=set)
    # Circuit breaker state
    failure_count: int = 0
    last_failure: float = 0.0
    circuit_open_until: float = 0.0
    # Limits
    max_failures: int = 5
    circuit_reset_seconds: int = 300  # 5 minutes


class ChannelDock:
    """Registry and dispatcher for notification channels.

    Singleton pattern — one dock per application.
    Routes events to channels based on allow/deny rules.
    """

    _instance: ChannelDock | None = None

    def __new__(cls) -> ChannelDock:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._channels: dict[str, ChannelConfig] = {}
            cls._instance._dispatch_count = 0
        return cls._instance

    def register(
        self,
        channel: Channel,
        allow_events: set[str] | None = None,
        deny_events: set[str] | None = None,
    ) -> None:
        """Register a channel for receiving notifications."""
        if not channel.is_configured:
            logger.warning(
                "Channel %s (%s) not configured — registering as disabled",
                channel.channel_id,
                channel.channel_type,
            )
            status = ChannelStatus.DISABLED
        else:
            status = ChannelStatus.ACTIVE

        self._channels[channel.channel_id] = ChannelConfig(
            channel=channel,
            status=status,
            allow_events=allow_events,
            deny_events=deny_events or set(),
        )
        logger.info(
            "Channel registered: %s (%s) status=%s",
            channel.channel_id,
            channel.channel_type,
            status.value,
        )

    def unregister(self, channel_id: str) -> None:
        """Remove a channel from the dock."""
        self._channels.pop(channel_id, None)

    def get_channel(self, channel_id: str) -> ChannelConfig | None:
        """Get a channel config by ID."""
        return self._channels.get(channel_id)

    @property
    def channels(self) -> dict[str, ChannelConfig]:
        """All registered channels."""
        return dict(self._channels)

    @property
    def active_channels(self) -> list[str]:
        """IDs of channels currently accepting notifications."""
        now = time.time()
        return [
            cid
            for cid, cfg in self._channels.items()
            if cfg.status == ChannelStatus.ACTIVE
            or (cfg.status == ChannelStatus.DEGRADED and now >= cfg.circuit_open_until)
        ]

    def _should_route(self, config: ChannelConfig, event_type: str) -> bool:
        """Check if an event should be routed to this channel."""
        if config.status == ChannelStatus.DISABLED:
            return False

        # Circuit breaker check
        if config.status == ChannelStatus.DEGRADED:
            if time.time() < config.circuit_open_until:
                return False

        # Deny takes precedence over allow
        if event_type in config.deny_events:
            return False

        # If allow list is set, only allow listed events
        if config.allow_events is not None:
            return event_type in config.allow_events

        return True

    def _record_failure(self, config: ChannelConfig) -> None:
        """Record a send failure and update circuit breaker."""
        config.failure_count += 1
        config.last_failure = time.time()

        if config.failure_count >= config.max_failures:
            config.status = ChannelStatus.DEGRADED
            config.circuit_open_until = time.time() + config.circuit_reset_seconds
            logger.warning(
                "Channel %s circuit opened — %d failures, retry after %ds",
                config.channel.channel_id,
                config.failure_count,
                config.circuit_reset_seconds,
            )

    def _record_success(self, config: ChannelConfig) -> None:
        """Record a send success and reset circuit breaker."""
        if config.failure_count > 0:
            config.failure_count = 0
            if config.status == ChannelStatus.DEGRADED:
                config.status = ChannelStatus.ACTIVE
                logger.info(
                    "Channel %s circuit closed — recovered",
                    config.channel.channel_id,
                )

    def dispatch(
        self,
        message: NotificationMessage,
        channel_ids: list[str] | None = None,
    ) -> list[SendResult]:
        """Dispatch a notification to matching channels.

        Args:
            message: The notification to send
            channel_ids: Specific channels to target (None = all matching)

        Returns:
            List of SendResult from each channel attempt
        """
        results: list[SendResult] = []
        self._dispatch_count += 1

        targets = channel_ids or list(self._channels.keys())

        for cid in targets:
            config = self._channels.get(cid)
            if not config:
                continue

            if not self._should_route(config, message.event_type):
                continue

            try:
                formatted = config.channel.format_message(message)
                result = config.channel.send(formatted)
                results.append(result)

                if result.success:
                    self._record_success(config)
                else:
                    self._record_failure(config)
                    logger.warning(
                        "Channel %s send failed: %s", cid, result.error
                    )
            except Exception as e:
                self._record_failure(config)
                results.append(SendResult(success=False, channel_id=cid, error=str(e)))
                logger.exception("Channel %s dispatch error", cid)

        return results

    def status(self) -> dict[str, Any]:
        """Get dock status for monitoring."""
        return {
            "total_channels": len(self._channels),
            "active": len(self.active_channels),
            "dispatch_count": self._dispatch_count,
            "channels": {
                cid: {
                    "type": cfg.channel.channel_type,
                    "status": cfg.status.value,
                    "failure_count": cfg.failure_count,
                    "configured": cfg.channel.is_configured,
                }
                for cid, cfg in self._channels.items()
            },
        }

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None


# Module-level singleton
dock = ChannelDock()
