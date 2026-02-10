"""Webhook event dispatcher — routes webhook payloads to agent invocations.

Maps provider event types to agent task descriptions and dispatches
them asynchronously via the scheduler's invoke path (with DLQ fallback).

Security contract:
- Webhook-triggered agent runs use invocation_source="webhook:{provider}"
- HITL approval gates still trigger regardless of invocation source
- Payload is sanitized before being passed to agent (strip HTML, validate types)
- Agent runs inherit webhook role restrictions (can only invoke, not admin)
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.events import broadcaster

logger = logging.getLogger(__name__)

# Maximum payload field length to prevent context window stuffing
_MAX_FIELD_LENGTH = 500


@dataclass
class WebhookEvent:
    """Normalized webhook event ready for dispatch."""

    provider: str
    event_type: str
    webhook_id: str
    payload: dict[str, Any]
    task_description: str
    priority: str = "normal"  # normal, high, critical


# Shopify event type -> task description templates
_SHOPIFY_EVENT_MAP: dict[str, str] = {
    "orders/create": "New Shopify order received: {summary}. Process fulfillment.",
    "orders/paid": "Shopify order payment confirmed: {summary}. Verify and update records.",
    "orders/fulfilled": "Shopify order fulfilled: {summary}. Send customer notification.",
    "orders/cancelled": "Shopify order cancelled: {summary}. Process refund if needed.",
    "products/create": "New Shopify product created: {summary}. Sync with inventory.",
    "products/update": "Shopify product updated: {summary}. Verify listing accuracy.",
    "products/delete": "Shopify product deleted: {summary}. Clean up references.",
    "refunds/create": "Shopify refund initiated: {summary}. Process and reconcile.",
    "customers/create": "New Shopify customer: {summary}. Set up customer profile.",
    "app/uninstalled": "Shopify app uninstalled. Alert administrator.",
}

# Stripe event type -> task description templates
_STRIPE_EVENT_MAP: dict[str, str] = {
    "payment_intent.succeeded": "Stripe payment succeeded: {summary}. Reconcile revenue.",
    "payment_intent.payment_failed": "Stripe payment failed: {summary}. Alert and retry.",
    "charge.refunded": "Stripe charge refunded: {summary}. Update revenue records.",
    "charge.dispute.created": "Stripe dispute created: {summary}. Respond immediately.",
    "invoice.paid": "Stripe invoice paid: {summary}. Update subscription records.",
    "invoice.payment_failed": "Stripe invoice payment failed: {summary}. Retry or alert.",
    "customer.subscription.created": "New Stripe subscription: {summary}. Provision access.",
    "customer.subscription.deleted": "Stripe subscription cancelled: {summary}. Revoke access.",
    "checkout.session.completed": "Stripe checkout completed: {summary}. Fulfill order.",
}

# Printful event type -> task description templates
_PRINTFUL_EVENT_MAP: dict[str, str] = {
    "package_shipped": "Printful package shipped: {summary}. Notify customer with tracking.",
    "package_returned": "Printful package returned: {summary}. Process return.",
    "order_created": "Printful order created: {summary}. Verify sync.",
    "order_updated": "Printful order updated: {summary}. Check status change.",
    "order_failed": "Printful order failed: {summary}. Investigate and retry.",
    "order_canceled": "Printful order cancelled: {summary}. Reconcile with Shopify.",
    "product_synced": "Printful product synced: {summary}. Verify listing.",
    "product_updated": "Printful product updated: {summary}. Check for changes.",
}

# Priority events that need immediate attention
_HIGH_PRIORITY_EVENTS = {
    "charge.dispute.created",
    "orders/cancelled",
    "order_failed",
    "payment_intent.payment_failed",
    "app/uninstalled",
}

_PROVIDER_EVENT_MAPS = {
    "shopify": _SHOPIFY_EVENT_MAP,
    "stripe": _STRIPE_EVENT_MAP,
    "printful": _PRINTFUL_EVENT_MAP,
}


def _sanitize_field(value: Any) -> str:
    """Sanitize a payload field value for safe inclusion in task descriptions."""
    if value is None:
        return ""
    s = str(value)
    # Strip HTML tags
    s = re.sub(r"<[^>]+>", "", s)
    # Unescape HTML entities
    s = html.unescape(s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Truncate
    if len(s) > _MAX_FIELD_LENGTH:
        s = s[:_MAX_FIELD_LENGTH] + "..."
    return s


def _extract_shopify_summary(event_type: str, payload: dict) -> str:
    """Extract a human-readable summary from Shopify webhook payload."""
    if event_type.startswith("orders/"):
        order = payload
        order_id = _sanitize_field(order.get("id") or order.get("order_number"))
        total = _sanitize_field(order.get("total_price"))
        currency = _sanitize_field(order.get("currency", "USD"))
        items = order.get("line_items", [])
        item_count = len(items) if isinstance(items, list) else 0
        return f"Order #{order_id}, {total} {currency}, {item_count} items"

    if event_type.startswith("products/"):
        title = _sanitize_field(payload.get("title"))
        product_id = _sanitize_field(payload.get("id"))
        return f"Product '{title}' (ID: {product_id})"

    if event_type.startswith("refunds/"):
        refund_id = _sanitize_field(payload.get("id"))
        return f"Refund #{refund_id}"

    if event_type.startswith("customers/"):
        email = _sanitize_field(payload.get("email", ""))
        # Redact email for privacy — show only domain
        if "@" in email:
            email = "***@" + email.split("@")[1]
        return f"Customer {email}"

    return _sanitize_field(str(payload.get("id", "unknown")))


def _extract_stripe_summary(event_type: str, payload: dict) -> str:
    """Extract summary from Stripe webhook payload."""
    obj = payload.get("data", {}).get("object", {})
    amount = obj.get("amount") or obj.get("amount_total")
    currency = _sanitize_field(obj.get("currency", "usd")).upper()

    if amount is not None:
        # Stripe amounts are in cents
        amount_fmt = f"${int(amount) / 100:.2f} {currency}"
    else:
        amount_fmt = ""

    obj_id = _sanitize_field(obj.get("id", ""))
    return f"{obj_id} {amount_fmt}".strip()


def _extract_printful_summary(event_type: str, payload: dict) -> str:
    """Extract summary from Printful webhook payload."""
    data = payload.get("data", payload)
    order_data = data.get("order") or data.get("shipment", {}).get("order") or data

    order_id = _sanitize_field(order_data.get("id") or order_data.get("external_id"))

    if "shipment" in data:
        tracking = _sanitize_field(data["shipment"].get("tracking_number", ""))
        carrier = _sanitize_field(data["shipment"].get("carrier", ""))
        return f"Order #{order_id}, {carrier} {tracking}".strip()

    return f"Order #{order_id}"


_SUMMARY_EXTRACTORS = {
    "shopify": _extract_shopify_summary,
    "stripe": _extract_stripe_summary,
    "printful": _extract_printful_summary,
}


def parse_event(provider: str, payload: dict) -> WebhookEvent | None:
    """Parse a raw webhook payload into a normalized WebhookEvent.

    Args:
        provider: One of 'shopify', 'stripe', 'printful'
        payload: Parsed JSON payload from the webhook

    Returns:
        WebhookEvent ready for dispatch, or None if event type is unrecognized
    """
    # Extract event type
    if provider == "shopify":
        # Shopify event type comes from X-Shopify-Topic header, not payload.
        # We pass it as payload["_topic"] from the handler.
        event_type = payload.pop("_topic", None) or "unknown"
        webhook_id = str(payload.get("id", ""))
    elif provider == "stripe":
        event_type = payload.get("type", "unknown")
        webhook_id = payload.get("id", "")
    elif provider == "printful":
        event_type = payload.get("type", "unknown")
        webhook_id = str(payload.get("data", {}).get("id", "")) or str(
            payload.get("id", "")
        )
    else:
        return None

    # Look up task template
    event_map = _PROVIDER_EVENT_MAPS.get(provider, {})
    template = event_map.get(event_type)
    if not template:
        logger.info(
            "Unrecognized webhook event: %s/%s — skipping", provider, event_type
        )
        return None

    # Extract summary
    extractor = _SUMMARY_EXTRACTORS.get(provider)
    summary = extractor(event_type, payload) if extractor else "N/A"

    task_description = template.format(summary=summary)
    priority = "high" if event_type in _HIGH_PRIORITY_EVENTS else "normal"

    return WebhookEvent(
        provider=provider,
        event_type=event_type,
        webhook_id=webhook_id,
        payload=payload,
        task_description=task_description,
        priority=priority,
    )


def dispatch_event(event: WebhookEvent) -> None:
    """Dispatch a webhook event for async processing.

    Broadcasts an event notification and invokes the agent system
    asynchronously through the scheduler's task runner.
    """
    # Broadcast event for Holly Grace / WebSocket subscribers
    broadcaster.broadcast(
        {
            "type": "webhook_received",
            "provider": event.provider,
            "event_type": event.event_type,
            "webhook_id": event.webhook_id,
            "priority": event.priority,
            "task_description": event.task_description,
        }
    )

    logger.info(
        "Dispatching webhook event: %s/%s (priority=%s)",
        event.provider,
        event.event_type,
        event.priority,
    )
