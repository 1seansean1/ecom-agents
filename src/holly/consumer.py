"""Holly Grace bus consumer — reads from Redis Streams and triages events.

Runs as a background thread, reading from all holly:* streams via
consumer groups. Events are triaged into three categories:
- auto_ack: routine events that don't need human attention
- queue: events to surface at the next conversation turn
- urgent: events that should push-notify immediately

Queued/urgent events are stored in holly_notifications table.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from src.bus import (
    CONSUMER_GROUP,
    STREAM_HUMAN_INBOUND,
    STREAM_SYSTEM_HEALTH,
    STREAM_TOWER_EVENTS,
    STREAM_TOWER_TICKETS,
    ack,
    claim_stale,
    read_multi,
)

logger = logging.getLogger(__name__)

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://holly:holly_dev_password@localhost:5434/holly_grace",
)

# Message types that are auto-acknowledged (routine, no human attention needed)
AUTO_ACK_TYPES = {
    "run.queued",
    "run.running",
    "run.started",
    "health.check",
}

# Message types that are urgent (push-notify immediately)
URGENT_TYPES = {
    "ticket.created",  # Only if high risk — checked in triage logic
    "run.failed",
    "revenue.phase_change",
}


def _get_conn() -> psycopg.Connection:
    return psycopg.connect(_DB_URL, autocommit=True, row_factory=dict_row)


def _store_notification(
    msg_type: str,
    payload: dict,
    priority: str = "normal",
) -> int:
    """Store a notification for Holly Grace to surface."""
    with _get_conn() as conn:
        row = conn.execute(
            """INSERT INTO holly_notifications (msg_type, payload, priority)
               VALUES (%s, %s, %s) RETURNING id""",
            (msg_type, json.dumps(payload, default=str), priority),
        ).fetchone()
    return row["id"]


def get_pending_notifications(limit: int = 20) -> list[dict]:
    """Get pending notifications for Holly Grace to surface."""
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM holly_notifications
               WHERE status = 'pending'
               ORDER BY
                   CASE priority
                       WHEN 'critical' THEN 0
                       WHEN 'high' THEN 1
                       WHEN 'normal' THEN 2
                       WHEN 'low' THEN 3
                       ELSE 4
                   END,
                   created_at
               LIMIT %s""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_notification_surfaced(notification_id: int, session_id: str = "default") -> None:
    """Mark a notification as surfaced (presented to the human)."""
    with _get_conn() as conn:
        conn.execute(
            """UPDATE holly_notifications
               SET status = 'surfaced', surfaced_at = NOW(), session_id = %s
               WHERE id = %s""",
            (session_id, notification_id),
        )


def _triage(msg_type: str, payload: dict) -> tuple[str, str]:
    """Triage a message into (action, priority).

    Returns:
        action: 'auto_ack', 'queue', or 'urgent'
        priority: 'low', 'normal', 'high', or 'critical'
    """
    # Auto-ack routine events
    if msg_type in AUTO_ACK_TYPES:
        return "auto_ack", "low"

    # Completed runs are low priority but worth noting
    if msg_type == "run.completed":
        return "queue", "low"

    # Ticket created — triage by risk level
    if msg_type == "ticket.created":
        risk = payload.get("risk_level", "medium")
        if risk == "high":
            return "urgent", "high"
        elif risk == "medium":
            return "queue", "normal"
        else:
            return "queue", "low"

    # Ticket decided (informational)
    if msg_type == "ticket.decided":
        return "queue", "low"

    # Run failures are always urgent
    if msg_type == "run.failed":
        return "urgent", "high"

    # Scheduler events are informational
    if msg_type == "scheduler.fired":
        return "queue", "low"

    # Cascade completions
    if msg_type == "cascade.completed":
        return "queue", "normal"

    # Tool approval requests
    if msg_type == "tool.approval_requested":
        risk = payload.get("risk", "medium")
        if risk == "high":
            return "urgent", "high"
        return "queue", "normal"

    # Human messages are always urgent
    if msg_type == "human.message":
        return "urgent", "critical"

    # Default: queue at normal priority
    return "queue", "normal"


class HollyConsumer:
    """Background consumer that reads from all Holly Grace streams."""

    def __init__(self, consumer_name: str = "holly-grace-0"):
        self._consumer_name = consumer_name
        self._running = False
        self._thread: threading.Thread | None = None
        # Streams to consume (priority order — tickets first)
        self._streams = [
            STREAM_TOWER_TICKETS,
            STREAM_TOWER_EVENTS,
            STREAM_HUMAN_INBOUND,
            STREAM_SYSTEM_HEALTH,
        ]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="holly-consumer",
        )
        self._thread.start()
        logger.info("Holly consumer started: %s", self._consumer_name)

    def stop(self) -> None:
        self._running = False
        logger.info("Holly consumer stopped")

    def _poll_loop(self) -> None:
        while self._running:
            try:
                # 1. Claim stale messages first (recovery)
                for stream in self._streams:
                    stale = claim_stale(
                        stream, self._consumer_name,
                        min_idle_ms=60_000, count=5,
                    )
                    for entry_id, fields in stale:
                        self._process(stream, entry_id, fields)

                # 2. Read new messages from all streams
                entries = read_multi(
                    self._streams, self._consumer_name,
                    count=20, block_ms=2000,
                )
                for stream, entry_id, fields in entries:
                    self._process(stream, entry_id, fields)

                if not entries:
                    time.sleep(0.5)

            except Exception:
                logger.exception("Holly consumer poll error")
                time.sleep(2)

    def _process(self, stream: str, entry_id: str, fields: dict) -> None:
        msg_type = fields.get("msg_type", "")
        try:
            payload = json.loads(fields.get("payload", "{}"))
        except json.JSONDecodeError:
            payload = {}

        action, priority = _triage(msg_type, payload)

        if action == "auto_ack":
            # Routine — just ack and move on
            ack(stream, entry_id)
            return

        if action in ("queue", "urgent"):
            # Store notification for Holly Grace to surface
            try:
                _store_notification(msg_type, payload, priority)
            except Exception:
                logger.exception("Failed to store notification for %s", msg_type)

        # Always ack after processing
        ack(stream, entry_id)
