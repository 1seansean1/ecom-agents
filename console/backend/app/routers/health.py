"""Health API routes — proxies to Holly Grace agents and enriches."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.holly_client import get_client

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health():
    """Get combined health status from Holly Grace agents."""
    client = get_client()
    try:
        resp = await client.get("/health")
        data = resp.json()
        data["holly_console"] = "connected"
        return JSONResponse(data, status_code=resp.status_code)
    except Exception:
        return JSONResponse(
            {
                "status": "disconnected",
                "service": "Holly Grace agents",
                "holly_console": "healthy",
                "checks": {},
                "error": "Cannot reach Holly Grace agents server",
            },
            status_code=503,
        )


@router.get("/circuit-breakers")
async def circuit_breakers():
    """Get circuit breaker states from Holly Grace agents."""
    client = get_client()
    try:
        resp = await client.get("/circuit-breakers")
        return resp.json()
    except Exception:
        return JSONResponse(
            {"error": "Cannot reach Holly Grace agents server"},
            status_code=503,
        )
