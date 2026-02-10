"""Webhook HTTP handlers — FastAPI route handlers for inbound webhooks.

Each handler:
1. Reads raw body (needed for HMAC verification)
2. Verifies provider-specific signature
3. Checks idempotency (reject duplicates)
4. Parses and dispatches event
5. Returns 202 Accepted immediately (async processing)

Security contract:
- Never return error details to webhook caller (info disclosure)
- Return 202 even for unrecognized events (don't leak event support map)
- Return 401 only for signature failures
- Log all webhook activity for audit trail
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.webhooks.dispatcher import dispatch_event, parse_event
from src.webhooks.idempotency import is_duplicate
from src.webhooks.verification import verify_webhook

logger = logging.getLogger(__name__)

# Webhook receive counter for monitoring (simple in-memory for now)
_webhook_counts: dict[str, int] = {}


def _log_webhook(provider: str, event_type: str, webhook_id: str, status: str) -> None:
    """Audit log for webhook activity."""
    _webhook_counts[provider] = _webhook_counts.get(provider, 0) + 1
    logger.info(
        "WEBHOOK_AUDIT provider=%s event=%s id=%s status=%s count=%d",
        provider,
        event_type,
        webhook_id,
        status,
        _webhook_counts[provider],
    )


async def _handle_webhook(request: Request, provider: str) -> JSONResponse:
    """Generic webhook handler for any provider.

    Returns 202 on success, 401 on signature failure.
    Never returns error details.
    """
    start = time.time()

    # Read raw body for signature verification
    body = await request.body()

    # Build lowercase headers dict
    headers = {k.lower(): v for k, v in request.headers.items()}

    # 1. Verify signature
    if not verify_webhook(provider, body, headers):
        _log_webhook(provider, "unknown", "unknown", "signature_failed")
        return JSONResponse(
            {"status": "unauthorized"},
            status_code=401,
        )

    # 2. Parse JSON payload
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        _log_webhook(provider, "unknown", "unknown", "invalid_json")
        # Return 202 anyway — don't leak that we couldn't parse
        return JSONResponse({"status": "received"}, status_code=202)

    # 3. Extract event type for Shopify (comes from header, not payload)
    if provider == "shopify":
        topic = headers.get("x-shopify-topic", "")
        payload["_topic"] = topic

    # 4. Parse into normalized event
    event = parse_event(provider, payload)

    if event is None:
        # Unrecognized event type — still return 202
        _log_webhook(provider, "unrecognized", "", "skipped")
        return JSONResponse({"status": "received"}, status_code=202)

    # 5. Check idempotency
    if is_duplicate(provider, event.webhook_id):
        _log_webhook(provider, event.event_type, event.webhook_id, "duplicate")
        return JSONResponse({"status": "received"}, status_code=200)

    # 6. Dispatch for async processing
    try:
        dispatch_event(event)
        _log_webhook(provider, event.event_type, event.webhook_id, "dispatched")
    except Exception:
        logger.exception("Failed to dispatch webhook event: %s/%s", provider, event.event_type)
        _log_webhook(provider, event.event_type, event.webhook_id, "dispatch_failed")

    elapsed_ms = (time.time() - start) * 1000
    logger.debug("Webhook processed in %.1fms: %s/%s", elapsed_ms, provider, event.event_type)

    return JSONResponse({"status": "received"}, status_code=202)


def register_webhook_routes(app: FastAPI) -> None:
    """Register webhook endpoint routes on the FastAPI app.

    Call this BEFORE install_security_middleware() so routes are available
    for middleware to inspect.
    """

    @app.post("/webhooks/shopify")
    async def shopify_webhook(request: Request):
        """Receive Shopify webhooks (signature-verified)."""
        return await _handle_webhook(request, "shopify")

    @app.post("/webhooks/shopify/{topic:path}")
    async def shopify_webhook_with_topic(request: Request, topic: str):
        """Receive Shopify webhooks with topic subpath."""
        return await _handle_webhook(request, "shopify")

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        """Receive Stripe webhooks (signature-verified)."""
        return await _handle_webhook(request, "stripe")

    @app.post("/webhooks/printful")
    async def printful_webhook(request: Request):
        """Receive Printful webhooks (signature-verified)."""
        return await _handle_webhook(request, "printful")

    @app.get("/webhooks/status")
    async def webhook_status():
        """Webhook receive counts (requires auth — not public)."""
        return {"counts": dict(_webhook_counts)}

    logger.info("Webhook routes registered: /webhooks/{shopify,stripe,printful}")
