"""Email tool: send emails via Gmail SMTP with App Password.

Used by the Sage agent to communicate directly with Sean.
Runs output validation before sending to prevent secret leakage.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def sage_send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.

    Returns:
        Status message indicating success or failure.
    """
    from src.guardrails.output_validator import validate_output

    validation = validate_output(body)
    safe_body = validation.sanitized if not validation.safe else body

    gmail_user = os.getenv("SAGE_GMAIL_USER")
    gmail_pass = os.getenv("SAGE_GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        return "Error: SAGE_GMAIL_USER or SAGE_GMAIL_APP_PASSWORD not configured"

    msg = MIMEText(safe_body)
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
        return f"Email sent to {to}: {subject}"
    except Exception as e:
        logger.exception("Failed to send email to %s", to)
        return f"Failed to send email: {e}"
