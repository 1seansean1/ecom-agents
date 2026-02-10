"""SMS tool: send SMS via email-to-SMS carrier gateway.

Uses Gmail SMTP to send to carrier gateways (e.g. 8083875629@vtext.com).
Zero infrastructure — no Twilio, no OAuth, no MCP server needed.
The tool interface stays identical if transport changes later.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

CARRIER_GATEWAYS = {
    "verizon": "vtext.com",
    "tmobile": "tmomail.net",
    "att": "txt.att.net",
    "sprint": "messaging.sprintpcs.com",
}

SMS_MAX_CHARS = 300


@tool
def sage_send_sms(message: str) -> str:
    """Send an SMS to Sean via email-to-SMS gateway.

    Args:
        message: The message to send (truncated to 300 chars).

    Returns:
        Status message indicating success or failure.
    """
    from src.guardrails.output_validator import validate_output

    validation = validate_output(message)
    safe_message = validation.sanitized if not validation.safe else message
    safe_message = safe_message[:SMS_MAX_CHARS]

    phone = os.getenv("SAGE_SMS_NUMBER", "8083875629")
    carrier = os.getenv("SAGE_SMS_CARRIER", "verizon").lower()
    gmail_user = os.getenv("SAGE_GMAIL_USER")
    gmail_pass = os.getenv("SAGE_GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        return "Error: SAGE_GMAIL_USER or SAGE_GMAIL_APP_PASSWORD not configured"

    gateway = CARRIER_GATEWAYS.get(carrier)
    if not gateway:
        return f"Error: Unknown carrier '{carrier}'. Supported: {list(CARRIER_GATEWAYS.keys())}"

    sms_address = f"{phone}@{gateway}"

    msg = MIMEText(safe_message)
    msg["From"] = gmail_user
    msg["To"] = sms_address

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        logger.info("SMS sent to %s via %s", phone, gateway)
        return f"SMS sent to {phone}"
    except Exception as e:
        logger.exception("Failed to send SMS to %s", phone)
        return f"Failed to send SMS: {e}"
