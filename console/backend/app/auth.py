"""Console authentication — JWT via httpOnly cookie."""

from __future__ import annotations

import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request, WebSocket
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_COOKIE_NAME = "holly_token"
_TOKEN_TTL = timedelta(hours=24)

# Paths that skip authentication (exact method + path match)
_PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/api/auth/login"),
    ("GET", "/api/health"),
    ("GET", "/"),
}


def create_console_token(email: str) -> str:
    """Create a JWT for the console user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, settings.console_jwt_secret, algorithm=_ALGORITHM)


def verify_console_token(token: str) -> dict | None:
    """Verify a console JWT. Returns claims or None."""
    try:
        return jwt.decode(token, settings.console_jwt_secret, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def check_credentials(email: str, password: str) -> bool:
    """Constant-time credential check."""
    email_ok = hmac.compare_digest(email, settings.console_user_email)
    password_ok = hmac.compare_digest(password, settings.console_user_password)
    return email_ok and password_ok


def get_cookie_token(request: Request) -> str | None:
    """Extract holly_token from request cookies."""
    return request.cookies.get(_COOKIE_NAME)


def get_ws_cookie_token(websocket: WebSocket) -> str | None:
    """Extract holly_token from WebSocket handshake cookies."""
    return websocket.cookies.get(_COOKIE_NAME)


class ConsoleAuthMiddleware(BaseHTTPMiddleware):
    """Enforce authentication on all /api/* routes except public ones."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # Skip non-API routes and public routes
        if not path.startswith("/api"):
            return await call_next(request)
        if (method, path) in _PUBLIC_ROUTES:
            return await call_next(request)

        # Check cookie
        token = get_cookie_token(request)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        claims = verify_console_token(token)
        if not claims:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        request.state.console_user = claims["sub"]
        return await call_next(request)
