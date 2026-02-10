"""Webhook signature verification — constant-time HMAC for each provider.

Security contract:
- All verifications use hmac.compare_digest() (constant-time, no timing attacks)
- Verification failure -> 401 immediately, no payload processing
- Missing secret env var -> verification always fails (fail-closed)
- Stripe timestamp tolerance: 300s (5 min) to prevent replay
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

logger = logging.getLogger(__name__)

# Provider webhook secrets from environment
_SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "")
_STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_PRINTFUL_WEBHOOK_SECRET = os.environ.get("PRINTFUL_WEBHOOK_SECRET", "")

# Stripe timestamp tolerance (seconds)
_STRIPE_TIMESTAMP_TOLERANCE = 300


def verify_shopify(body: bytes, signature_header: str | None) -> bool:
    """Verify Shopify webhook HMAC-SHA256 signature.

    Shopify sends: X-Shopify-Hmac-SHA256 header (base64-encoded HMAC-SHA256).

    Args:
        body: Raw request body bytes
        signature_header: Value of X-Shopify-Hmac-SHA256 header

    Returns:
        True if signature is valid
    """
    if not _SHOPIFY_WEBHOOK_SECRET:
        logger.warning("SHOPIFY_WEBHOOK_SECRET not set — rejecting webhook")
        return False
    if not signature_header:
        return False

    import base64

    computed = hmac.new(
        _SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")

    return hmac.compare_digest(computed_b64, signature_header)


def verify_stripe(body: bytes, signature_header: str | None) -> bool:
    """Verify Stripe webhook signature (v1 scheme).

    Stripe sends: Stripe-Signature header with format:
    t=<timestamp>,v1=<signature>[,v0=<deprecated>]

    Args:
        body: Raw request body bytes
        signature_header: Value of Stripe-Signature header

    Returns:
        True if signature is valid and timestamp is within tolerance
    """
    if not _STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not set — rejecting webhook")
        return False
    if not signature_header:
        return False

    # Parse header: t=timestamp,v1=sig1,v1=sig2,...
    parts = {}
    for item in signature_header.split(","):
        kv = item.strip().split("=", 1)
        if len(kv) == 2:
            key, value = kv
            if key in parts:
                # Multiple v1 signatures — store as list
                if isinstance(parts[key], list):
                    parts[key].append(value)
                else:
                    parts[key] = [parts[key], value]
            else:
                parts[key] = value

    timestamp_str = parts.get("t")
    if not timestamp_str:
        return False

    try:
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        return False

    # Check timestamp tolerance (replay protection)
    if abs(time.time() - timestamp) > _STRIPE_TIMESTAMP_TOLERANCE:
        logger.warning("Stripe webhook timestamp too old/future: %s", timestamp)
        return False

    # Compute expected signature: HMAC-SHA256(timestamp.body)
    signed_payload = f"{timestamp}.".encode("utf-8") + body
    expected = hmac.new(
        _STRIPE_WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    # Compare against all v1 signatures
    v1_sigs = parts.get("v1")
    if not v1_sigs:
        return False
    if isinstance(v1_sigs, str):
        v1_sigs = [v1_sigs]

    return any(hmac.compare_digest(expected, sig) for sig in v1_sigs)


def verify_printful(body: bytes, signature_header: str | None) -> bool:
    """Verify Printful webhook signature.

    Printful uses a simple HMAC-SHA256 hex digest in X-Printful-Signature header.

    Args:
        body: Raw request body bytes
        signature_header: Value of X-Printful-Signature header

    Returns:
        True if signature is valid
    """
    if not _PRINTFUL_WEBHOOK_SECRET:
        logger.warning("PRINTFUL_WEBHOOK_SECRET not set — rejecting webhook")
        return False
    if not signature_header:
        return False

    computed = hmac.new(
        _PRINTFUL_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature_header)


# Provider -> verifier mapping
VERIFIERS = {
    "shopify": verify_shopify,
    "stripe": verify_stripe,
    "printful": verify_printful,
}

# Provider -> (header_name, secret_env_var)
PROVIDER_CONFIG = {
    "shopify": ("x-shopify-hmac-sha256", "SHOPIFY_WEBHOOK_SECRET"),
    "stripe": ("stripe-signature", "STRIPE_WEBHOOK_SECRET"),
    "printful": ("x-printful-signature", "PRINTFUL_WEBHOOK_SECRET"),
}


def verify_webhook(provider: str, body: bytes, headers: dict[str, str]) -> bool:
    """Verify webhook signature for a given provider.

    Args:
        provider: One of 'shopify', 'stripe', 'printful'
        body: Raw request body
        headers: Request headers (lowercase keys)

    Returns:
        True if signature is valid
    """
    verifier = VERIFIERS.get(provider)
    if not verifier:
        logger.warning("Unknown webhook provider: %s", provider)
        return False

    header_name = PROVIDER_CONFIG[provider][0]
    signature = headers.get(header_name)
    return verifier(body, signature)
