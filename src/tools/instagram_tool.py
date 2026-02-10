"""Instagram tool via Meta Graph API.

Posts content to Instagram Business accounts using the Meta Graph API.
Rate limit: 25 posts per 24 hours (enforced locally).
Content-hash dedup prevents identical posts within 24 hours.
"""

from __future__ import annotations

import logging
import os
import time

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.tools.idempotency import get_idempotency_store
from src.tools.retry import retry_with_backoff

logger = logging.getLogger(__name__)

META_GRAPH_BASE = "https://graph.facebook.com/v21.0"

# Simple in-memory rate limiter (resets on restart)
_post_timestamps: list[float] = []
MAX_POSTS_PER_DAY = 25


def _check_rate_limit() -> bool:
    """Return True if we're under the rate limit."""
    now = time.time()
    cutoff = now - 86400  # 24 hours
    _post_timestamps[:] = [t for t in _post_timestamps if t > cutoff]
    return len(_post_timestamps) < MAX_POSTS_PER_DAY


@retry_with_backoff(max_retries=3, base_delay=2.0, max_delay=30.0)
def _meta_request(method: str, path: str, params: dict | None = None) -> dict:
    """Make an authenticated Meta Graph API request.

    Token is sent via Authorization header (not URL query params) to avoid
    leaking credentials in server logs and browser history.
    """
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
    headers = {"Authorization": f"Bearer {access_token}"}

    response = httpx.request(
        method,
        f"{META_GRAPH_BASE}{path}",
        params=params if method == "GET" else None,
        data=params if method == "POST" else None,
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


class PublishPostInput(BaseModel):
    image_url: str = Field(description="Public URL of the image to post")
    caption: str = Field(description="Post caption text")


@tool(args_schema=PublishPostInput)
def instagram_publish_post(image_url: str, caption: str) -> dict:
    """Publish an image post to Instagram (with content-hash dedup).

    Two-step process:
    1. Create a media container
    2. Publish the container
    """
    # Content-hash dedup: prevent identical posts within 24h
    store = get_idempotency_store()
    params = {"image_url": image_url, "caption": caption}
    idem_key = store.generate_key("instagram_publish_post", params)

    cached = store.check_and_set(idem_key, ttl=86400)  # 24h TTL
    if cached:
        logger.info("Duplicate Instagram post prevented for key=%s", idem_key)
        return {**cached.result, "_idempotent": True, "status": "duplicate_prevented"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded (25 posts/24hrs)", "status": "rate_limited"}

    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if not account_id:
        return {"error": "INSTAGRAM_BUSINESS_ACCOUNT_ID not configured", "status": "error"}

    # Step 1: Create media container
    container = _meta_request(
        "POST",
        f"/{account_id}/media",
        {"image_url": image_url, "caption": caption},
    )
    container_id = container.get("id")
    if not container_id:
        return {"error": "Failed to create media container", "status": "error"}

    # Step 2: Wait for processing (simple poll)
    for _ in range(10):
        status = _meta_request("GET", f"/{container_id}", {"fields": "status_code"})
        if status.get("status_code") == "FINISHED":
            break
        time.sleep(2)

    # Step 3: Publish
    result = _meta_request(
        "POST",
        f"/{account_id}/media_publish",
        {"creation_id": container_id},
    )

    _post_timestamps.append(time.time())

    post_result = {
        "post_id": result.get("id"),
        "status": "published",
        "remaining_today": MAX_POSTS_PER_DAY - len(_post_timestamps),
    }
    store.store(idem_key, post_result, ttl=86400)
    return post_result


@tool
def instagram_get_insights() -> dict:
    """Get basic Instagram account insights."""
    account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if not account_id:
        return {"error": "INSTAGRAM_BUSINESS_ACCOUNT_ID not configured"}

    result = _meta_request(
        "GET",
        f"/{account_id}",
        {"fields": "followers_count,media_count,username"},
    )

    return {
        "username": result.get("username"),
        "followers": result.get("followers_count"),
        "media_count": result.get("media_count"),
    }


def get_instagram_tools() -> list:
    """Return all Instagram tools for agent use."""
    return [instagram_publish_post, instagram_get_insights]
