"""Email inbox listener: persistent IMAP IDLE connection for instant message routing.

Maintains a long-lived IMAP connection to Gmail using the IDLE command (RFC 2177).
When a new email arrives, it's processed immediately and routed to Sage.
Runs as a daemon thread — starts with the server, dies with the server.
"""

from __future__ import annotations

import email
import imaplib
import logging
import os
import threading
import time
from dataclasses import dataclass
from email.header import decode_header

logger = logging.getLogger(__name__)

# Senders we care about — SMS gateway replies + Sean's direct emails
_TRUSTED_SENDERS: set[str] = set()

# IMAP IDLE re-issues every 25 minutes (Gmail drops idle after 29 min)
IDLE_TIMEOUT_SECONDS = 25 * 60

# Reconnect backoff on failure
RECONNECT_BASE_SECONDS = 5
RECONNECT_MAX_SECONDS = 120


def _get_trusted_senders() -> set[str]:
    """Build the set of trusted sender addresses."""
    global _TRUSTED_SENDERS
    if _TRUSTED_SENDERS:
        return _TRUSTED_SENDERS

    gmail_user = os.getenv("SAGE_GMAIL_USER", "")
    phone = os.getenv("SAGE_SMS_NUMBER", "8083875629")
    carrier = os.getenv("SAGE_SMS_CARRIER", "verizon").lower()

    from src.tools.sms_tool import CARRIER_GATEWAYS
    gateway = CARRIER_GATEWAYS.get(carrier, "vtext.com")

    _TRUSTED_SENDERS = {
        gmail_user.lower(),
        f"{phone}@{gateway}".lower(),
    }
    return _TRUSTED_SENDERS


@dataclass
class InboundMessage:
    """A message received from Sean."""
    sender: str
    subject: str
    body: str
    source: str  # "email" or "sms"


def _decode_header_value(value: str) -> str:
    """Decode an email header value."""
    decoded_parts = decode_header(value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace").strip()
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace").strip()
        return ""


def _parse_message(raw_email: bytes, trusted: set[str]) -> InboundMessage | None:
    """Parse a raw email into an InboundMessage if from a trusted sender."""
    msg = email.message_from_bytes(raw_email)

    sender_raw = msg.get("From", "")
    if "<" in sender_raw:
        sender_addr = sender_raw.split("<")[1].rstrip(">").strip().lower()
    else:
        sender_addr = sender_raw.strip().lower()

    if sender_addr not in trusted:
        return None

    subject = _decode_header_value(msg.get("Subject", ""))
    body = _extract_body(msg)

    if not body:
        return None

    phone = os.getenv("SAGE_SMS_NUMBER", "8083875629")
    source = "sms" if phone in sender_addr else "email"

    return InboundMessage(sender=sender_addr, subject=subject, body=body, source=source)


def _fetch_unseen(imap: imaplib.IMAP4_SSL, callback) -> None:
    """Fetch all unseen messages and dispatch them via callback."""
    trusted = _get_trusted_senders()

    status, data = imap.search(None, "UNSEEN")
    if status != "OK" or not data[0]:
        return

    for msg_id in data[0].split():
        try:
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            parsed = _parse_message(msg_data[0][1], trusted)
            if parsed:
                imap.store(msg_id, "+FLAGS", "\\Seen")
                logger.info("Inbound %s from %s: %s", parsed.source, parsed.sender, parsed.subject or parsed.body[:50])
                callback(parsed)
        except Exception:
            logger.exception("Failed to process message %s", msg_id)


def _idle_loop(callback) -> None:
    """Persistent IMAP IDLE loop. Reconnects on failure with exponential backoff."""
    gmail_user = os.getenv("SAGE_GMAIL_USER")
    gmail_pass = os.getenv("SAGE_GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        logger.warning("Sage inbox listener not started: no Gmail credentials")
        return

    backoff = RECONNECT_BASE_SECONDS

    while True:
        imap = None
        try:
            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(gmail_user, gmail_pass)
            imap.select("INBOX")
            logger.info("Sage inbox listener connected (IMAP IDLE)")
            backoff = RECONNECT_BASE_SECONDS  # reset on success

            # Process any messages that arrived while disconnected
            _fetch_unseen(imap, callback)

            while True:
                # Enter IDLE mode
                tag = imap._new_tag().decode()
                imap.send(f"{tag} IDLE\r\n".encode())

                # Read until we get continuation response "+"
                while True:
                    line = imap.readline().decode().strip()
                    if line.startswith("+"):
                        break

                # Wait for server notification or timeout
                # Gmail sends "* N EXISTS" when new mail arrives
                imap.sock.settimeout(IDLE_TIMEOUT_SECONDS)
                try:
                    response = imap.readline().decode().strip()
                except (TimeoutError, OSError):
                    response = ""

                # Exit IDLE
                imap.send(b"DONE\r\n")
                # Read the tagged response
                imap.readline()

                # Reset socket timeout
                imap.sock.settimeout(None)

                if "EXISTS" in response:
                    _fetch_unseen(imap, callback)

                # Re-select to keep connection alive even on timeout
                imap.noop()

        except Exception:
            logger.exception("Sage inbox listener disconnected, reconnecting in %ds", backoff)
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass

            time.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SECONDS)


_listener_thread: threading.Thread | None = None


def start_inbox_listener(callback) -> None:
    """Start the IMAP IDLE listener as a daemon thread.

    Args:
        callback: Function that receives an InboundMessage when one arrives.
    """
    global _listener_thread
    if _listener_thread and _listener_thread.is_alive():
        logger.debug("Inbox listener already running")
        return

    _listener_thread = threading.Thread(
        target=_idle_loop,
        args=(callback,),
        daemon=True,
        name="sage-inbox-idle",
    )
    _listener_thread.start()
    logger.info("Sage inbox listener thread started")


# Keep check_inbox for backward compat / manual use
def check_inbox() -> list[InboundMessage]:
    """One-shot inbox check (for manual use or fallback)."""
    gmail_user = os.getenv("SAGE_GMAIL_USER")
    gmail_pass = os.getenv("SAGE_GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        return []

    trusted = _get_trusted_senders()
    messages: list[InboundMessage] = []

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(gmail_user, gmail_pass)
        imap.select("INBOX")

        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            imap.logout()
            return []

        for msg_id in data[0].split():
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            parsed = _parse_message(msg_data[0][1], trusted)
            if parsed:
                imap.store(msg_id, "+FLAGS", "\\Seen")
                messages.append(parsed)

        imap.logout()
    except Exception:
        logger.exception("Inbox check failed")

    return messages
