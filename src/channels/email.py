"""Email notification channel — sends alerts via SMTP.

Uses standard SMTP with TLS. Credentials stored in env vars:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Security: Password stored in env var, never logged.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from src.channels.protocol import (
    NotificationMessage,
    SendResult,
)

logger = logging.getLogger(__name__)

_SEVERITY_SUBJECT_PREFIX = {
    "info": "[INFO]",
    "warning": "[WARN]",
    "error": "[ERROR]",
    "critical": "[CRITICAL]",
}


class EmailChannel:
    """Email notification channel via SMTP."""

    def __init__(
        self,
        channel_id: str = "email-default",
        recipients: list[str] | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        smtp_from: str | None = None,
    ):
        self._channel_id = channel_id
        self._recipients = recipients or os.environ.get("SMTP_RECIPIENTS", "").split(",")
        self._recipients = [r.strip() for r in self._recipients if r.strip()]
        self._host = smtp_host or os.environ.get("SMTP_HOST", "")
        self._port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self._user = smtp_user or os.environ.get("SMTP_USER", "")
        self._password = smtp_password or os.environ.get("SMTP_PASSWORD", "")
        self._from = smtp_from or os.environ.get("SMTP_FROM", self._user)

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def channel_type(self) -> str:
        return "email"

    @property
    def is_configured(self) -> bool:
        return bool(self._host and self._user and self._recipients)

    @property
    def capabilities(self) -> set[str]:
        return {"text", "rich", "attachments"}

    def format_message(self, message: NotificationMessage) -> MIMEMultipart:
        """Format as MIME email message."""
        prefix = _SEVERITY_SUBJECT_PREFIX.get(message.severity, "[INFO]")
        subject = f"{prefix} {message.title}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = ", ".join(self._recipients)

        # Plain text version
        text_body = f"{message.title}\n\n{message.body}"
        msg.attach(MIMEText(text_body, "plain"))

        # HTML version
        severity_color = {
            "info": "#36a64f",
            "warning": "#ff9900",
            "error": "#cc0000",
            "critical": "#8b0000",
        }.get(message.severity, "#333")

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <div style="border-left: 4px solid {severity_color}; padding: 12px;">
                <h2 style="margin: 0 0 8px 0; color: {severity_color};">{message.title}</h2>
                <p style="margin: 0; color: #333;">{message.body}</p>
            </div>
            <p style="font-size: 11px; color: #999; margin-top: 16px;">
                Holly Grace notification system
            </p>
        </div>
        """
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def send(self, formatted: MIMEMultipart) -> SendResult:
        """Send via SMTP with TLS."""
        if not self.is_configured:
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error="Email not configured (missing SMTP_HOST/SMTP_USER/SMTP_RECIPIENTS)",
            )

        try:
            with smtplib.SMTP(self._host, self._port, timeout=15) as server:
                server.starttls()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.send_message(formatted)
            return SendResult(success=True, channel_id=self._channel_id)
        except smtplib.SMTPException as e:
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error=f"SMTP error: {e}",
            )
        except Exception as e:
            return SendResult(
                success=False,
                channel_id=self._channel_id,
                error=str(e),
            )
