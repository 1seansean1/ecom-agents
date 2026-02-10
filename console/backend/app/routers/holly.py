"""Holly Grace API routes — proxies chat, session, and notification endpoints.

All requests proxy to the agents server at /holly/*.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.services.holly_client import get_client

router = APIRouter(prefix="/api/holly", tags=["holly"])

_503 = {"error": "Cannot reach Holly Grace agents server"}


@router.post("/message")
async def send_message(request: Request):
    """Send a message to Holly Grace."""
    client = get_client()
    body = await request.json()
    try:
        resp = await client.post("/holly/message", json=body, timeout=120.0)
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.get("/session")
async def get_session(session_id: str = "default"):
    """Get conversation session history."""
    client = get_client()
    try:
        resp = await client.get("/holly/session", params={"session_id": session_id})
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.post("/clear")
async def clear_session(request: Request):
    """Clear conversation session."""
    client = get_client()
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    try:
        resp = await client.post("/holly/clear", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.get("/greeting")
async def get_greeting(session_id: str = "default"):
    """Get Holly Grace greeting with system status."""
    client = get_client()
    try:
        resp = await client.get("/holly/greeting", params={"session_id": session_id})
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.get("/notifications")
async def get_notifications(limit: int = 20):
    """Get pending notifications."""
    client = get_client()
    try:
        resp = await client.get("/holly/notifications", params={"limit": limit})
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.get("/system-health")
async def system_health():
    """Proxy system health query for Holly's status bar."""
    client = get_client()
    try:
        # Use Holly's tool directly for richer data
        resp = await client.post("/holly/message", json={
            "message": "__system_health_check__",
            "session_id": "__health__",
        }, timeout=10.0)
        # Fall back to direct health endpoint
        health_resp = await client.get("/health")
        return JSONResponse(health_resp.json().get("checks", {}))
    except Exception:
        return JSONResponse(_503, status_code=503)
