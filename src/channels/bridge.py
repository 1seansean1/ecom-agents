"""Event bridge — connects EventBroadcaster to ChannelDock.

Maps internal event types to notification messages and dispatches
them through the channel dock.

The bridge runs as a background asyncio task that subscribes to
the EventBroadcaster and routes events to channels.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.channels.protocol import ChannelDock, NotificationMessage, dock
from src.channels.sanitizer import sanitize_notification
from src.events import broadcaster

logger = logging.getLogger(__name__)


# Event type -> notification severity mapping
_EVENT_SEVERITY: dict[str, str] = {
    "webhook_received": "info",
    "node_entered": "info",
    "node_exited": "info",
    "agent_error": "error",
    "dlq_insert": "warning",
    "approval_required": "warning",
    "approval_expired": "warning",
    "cascade_trigger": "warning",
    "cascade_tier_escalation": "critical",
    "budget_exceeded": "error",
    "budget_warning": "warning",
    "morphogenetic_evaluation": "info",
    "goal_status_change": "info",
}

# Event types that should generate notifications (not all events)
_NOTIFIABLE_EVENTS: set[str] = {
    "webhook_received",
    "agent_error",
    "dlq_insert",
    "approval_required",
    "approval_expired",
    "cascade_trigger",
    "cascade_tier_escalation",
    "budget_exceeded",
    "budget_warning",
    "goal_status_change",
}


def _event_to_notification(event: dict[str, Any]) -> NotificationMessage | None:
    """Convert an internal event to a notification message.

    Returns None if the event type is not notifiable.
    """
    event_type = event.get("type", "")

    if event_type not in _NOTIFIABLE_EVENTS:
        return None

    severity = _EVENT_SEVERITY.get(event_type, "info")

    # Build title and body from event data
    title = _format_title(event_type, event)
    body = _format_body(event_type, event)

    return NotificationMessage(
        title=title,
        body=body,
        severity=severity,
        event_type=event_type,
        metadata={k: v for k, v in event.items() if k not in ("type", "timestamp")},
    )


def _format_title(event_type: str, event: dict[str, Any]) -> str:
    """Format a notification title from event data."""
    titles = {
        "webhook_received": f"Webhook: {event.get('provider', '?')}/{event.get('event_type', '?')}",
        "agent_error": f"Agent Error: {event.get('agent', 'unknown')}",
        "dlq_insert": f"DLQ: {event.get('job_id', 'unknown')} failed",
        "approval_required": f"Approval Needed: {event.get('action', 'unknown')}",
        "approval_expired": f"Approval Expired: {event.get('approval_id', '?')}",
        "cascade_trigger": f"Cascade Triggered: Tier {event.get('tier', '?')}",
        "cascade_tier_escalation": f"Cascade Escalation: Tier {event.get('from_tier', '?')} -> {event.get('to_tier', '?')}",
        "budget_exceeded": f"Budget Exceeded: {event.get('budget_type', '?')}",
        "budget_warning": f"Budget Warning: {event.get('budget_type', '?')}",
        "goal_status_change": f"Goal Update: {event.get('goal_id', '?')}",
    }
    return titles.get(event_type, f"Event: {event_type}")


def _format_body(event_type: str, event: dict[str, Any]) -> str:
    """Format a notification body from event data."""
    if event_type == "webhook_received":
        return event.get("task_description", "Webhook event received")
    if event_type == "agent_error":
        return f"Error in {event.get('node', 'unknown')}: {event.get('error', 'unknown error')}"
    if event_type == "dlq_insert":
        return f"Job {event.get('job_id', '?')} failed: {event.get('error', 'unknown error')}"
    if event_type == "approval_required":
        return f"Action: {event.get('action', '?')} requires human approval. Expires in {event.get('ttl', '?')}s."
    if event_type == "approval_expired":
        return f"Approval {event.get('approval_id', '?')} expired without response."
    if event_type == "cascade_trigger":
        return f"APS cascade triggered at tier {event.get('tier', '?')} for channel {event.get('channel', '?')}."
    if event_type == "cascade_tier_escalation":
        return f"APS cascade escalating from tier {event.get('from_tier', '?')} to tier {event.get('to_tier', '?')}."
    if event_type in ("budget_exceeded", "budget_warning"):
        return f"{event.get('budget_type', '?')} budget: {event.get('used', '?')}/{event.get('limit', '?')}"
    if event_type == "goal_status_change":
        return f"Goal {event.get('goal_id', '?')} status changed to {event.get('new_status', '?')}."
    return str(event.get("message", ""))


async def notification_bridge(dock_instance: ChannelDock | None = None) -> None:
    """Background task that bridges EventBroadcaster to ChannelDock.

    Subscribes to the broadcaster and dispatches notifiable events
    to all matching channels.

    This coroutine runs forever until cancelled.
    """
    target_dock = dock_instance or dock
    sub_id, queue = broadcaster.subscribe()
    logger.info("Notification bridge started (subscriber=%s)", sub_id)

    try:
        while True:
            event = await queue.get()

            notification = _event_to_notification(event)
            if notification is None:
                continue

            # Sanitize before dispatch
            notification = sanitize_notification(notification)

            # Dispatch to all matching channels
            results = target_dock.dispatch(notification)

            for result in results:
                if not result.success:
                    logger.warning(
                        "Notification dispatch failed: channel=%s error=%s",
                        result.channel_id,
                        result.error,
                    )
    except asyncio.CancelledError:
        logger.info("Notification bridge stopped")
        broadcaster.unsubscribe(sub_id)
        raise
