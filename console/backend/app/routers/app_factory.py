"""App Factory API routes — proxies to Holly Grace agents."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.holly_client import get_client

router = APIRouter(prefix="/api/app-factory", tags=["app_factory"])

_503 = {"error": "Cannot reach Holly Grace agents server"}


@router.post("/projects")
async def create_project(request: Request):
    """Create a new App Factory project."""
    client = get_client()
    body = await request.json()
    try:
        resp = await client.post("/app-factory/projects", json=body)
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.get("/projects")
async def list_projects():
    """List all App Factory projects."""
    client = get_client()
    try:
        resp = await client.get("/app-factory/projects")
        return resp.json()
    except Exception:
        return JSONResponse({**_503, "projects": [], "count": 0}, status_code=503)


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get full project detail."""
    client = get_client()
    try:
        resp = await client.get(f"/app-factory/projects/{project_id}")
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project."""
    client = get_client()
    try:
        resp = await client.delete(f"/app-factory/projects/{project_id}")
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception:
        return JSONResponse(_503, status_code=503)
