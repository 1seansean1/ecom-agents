"""Security middleware for FastAPI: auth, CORS, rate limiting.

Middleware ordering (outermost first):
1. CORS -- handles OPTIONS preflight before auth
2. Rate limiting -- reject floods before processing
3. Auth -- verify Bearer token, inject user context
"""

from __future__ import annotations

import logging
import os
import re

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from src.security.auth import (
    PUBLIC_ALLOWLIST,
    SKIP_METHODS,
    check_authorization,
    extract_bearer_token,
    is_webhook_path,
    verify_token,
)

logger = logging.getLogger(__name__)

# Trusted proxy CIDRs -- only trust X-Forwarded-For when set
_TRUSTED_PROXIES = os.environ.get("TRUSTED_PROXIES", "")

# CORS allowed origins
_CORS_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8050",
).split(",")


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting TRUSTED_PROXIES config."""
    if _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Rate limiter
limiter = Limiter(key_func=_get_client_ip)


def _match_route_template(app: FastAPI, method: str, path: str) -> str | None:
    """Find the route template matching a request path."""
    for route in app.routes:
        if hasattr(route, "methods") and method in route.methods:
            # Build regex from path template
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", route.path)
            if re.fullmatch(pattern, path):
                return route.path
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate and authorize all requests.

    Runs AFTER CORS middleware (so OPTIONS preflights are already handled).
    Runs BEFORE request body parsing (so unauthenticated POST returns 401 not 422).
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Skip methods handled by CORS middleware
        if method in SKIP_METHODS:
            return await call_next(request)

        # Public endpoints (exact match)
        if (method, path) in PUBLIC_ALLOWLIST:
            return await call_next(request)

        # Webhook endpoints — public but signature-verified by handler, not JWT-verified.
        # POST only; other methods still require JWT auth.
        if method == "POST" and is_webhook_path(path):
            return await call_next(request)

        # Extract and verify token
        auth_header = request.headers.get("authorization")
        token_str = extract_bearer_token(auth_header)

        if not token_str:
            return JSONResponse(
                {"error": "Authentication required"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = verify_token(token_str)
        except ValueError as e:
            logger.debug("Auth failed: %s", e)
            return JSONResponse(
                {"error": "Invalid or expired credentials"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Authorization check
        role = payload.get("role", "viewer")
        path_template = _match_route_template(request.app, method, path)
        if path_template is None:
            # Unknown route -- let FastAPI handle 404
            request.state.user = payload
            return await call_next(request)

        auth_error = check_authorization(role, method, path_template)
        if auth_error:
            return JSONResponse(
                {"error": auth_error},
                status_code=403,
            )

        # Attach user info to request state
        request.state.user = payload
        return await call_next(request)


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        {"error": "Rate limit exceeded", "retry_after": retry_after},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


def install_security_middleware(app: FastAPI) -> None:
    """Install all security middleware on the FastAPI app.

    Call this AFTER all routes are registered but BEFORE the app starts.
    Middleware is added in reverse order (last added = outermost = runs first).
    """
    # 3. Auth middleware (innermost -- runs last, after CORS and rate limit)
    app.add_middleware(AuthMiddleware)

    # 2. Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 1. CORS middleware (outermost -- runs first, handles OPTIONS preflight)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
