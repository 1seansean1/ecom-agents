"""Slack notification channel — sends alerts via Slack Incoming Webhook.

Uses Incoming Webhook URL (no bot token needed for simple notifications).
For full bot functionality, use SLACK_BOT_TOKEN with chat.postMessage API.

Security: Token stored in env var SLACK_WEBHOOK_URL, never logged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

from src.channels.protocol import (
    NotificationMessage,
    SendResult,
)

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    "info": "",
    "warning": ":warning:",
    "error": ":x:",
    "critical": ":rotating_light:",
}

_SEVERITY_COLOR = {
    "info": "#36a64f",     # green
    "warning": "#ff9900",  # orange
    "error": "#cc0000",    # red
    "critical": "#8b0000", # dark red
}


class SlackChannel:
    """Slack notification channel via Incoming Webhook."""

    def __init__(
        self,
        channel_id: str = "slack-default",
        webhook_url: str | None = None,
    ):
        self._channel_id = channel_id
        self._webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def channel_type(self) -> str:
        return "slack"

    @property
    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    @property
    def capabilities(self) -> set[str]:
        return {"text", "rich", "attachments"}

    def format_message(self, message: NotificationMessage) -> dict[str, Any]:
        """Format as Slack Block Kit message."""
        emoji = _SEVERITY_EMOJI.get(message.severity, "")
        color = _SEVERITY_COLOR.get(message.severity, "#36a64f")

        title = f"{emoji} {message.title}".strip()

        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{title}*\n{message.body}",
                            },
                        },
                    ],
                    "fallback": f"{title}: {message.body}",
                }
            ]
        }

    def send(self, formatted: dict[str, Any]) -> SendResult:
        """Send via Slack Incoming Webhook."""
        if not self._webhook_url:
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error="Slack webhook URL not configured",
            )

        try:
            resp = requests.post(
                self._webhook_url,
                json=formatted,
                timeout=10,
            )
            if resp.status_code == 200:
                return SendResult(success=True, channel_id=self._channel_id)
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error=f"Slack API error: {resp.status_code}",
            )
        except requests.RequestException as e:
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error=str(e),
            )
