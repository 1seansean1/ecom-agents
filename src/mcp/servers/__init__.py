"""Built-in MCP servers — pre-seeded on startup."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def seed_github_reader() -> None:
    """Register the github-reader MCP server and sync its tools.

    Idempotent — skips if the server already exists.
    """
    from src.mcp.store import create_server, get_server, update_server
    from src.mcp.manager import get_mcp_manager

    server_id = "github-reader"

    existing = get_server(server_id)
    if existing is not None:
        # Fix command if it was registered with wrong binary name
        if existing.get("stdio_command") != "python3":
            update_server(server_id, {"stdio_command": "python3"})
            logger.info("MCP server '%s' updated stdio_command to python3", server_id)
        else:
            logger.debug("MCP server '%s' already registered, skipping seed", server_id)
    else:
        create_server(
            server_id=server_id,
            display_name="GitHub Reader",
            description="Read-only access to the ecom-agents GitHub repo via REST API",
            transport="stdio",
            enabled=True,
            stdio_command="python3",
            stdio_args=["-m", "src.mcp.servers.github_reader"],
            env_allow=["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_BRANCH"],
        )
        logger.info("MCP server '%s' registered", server_id)

    try:
        result = get_mcp_manager().sync_tools(server_id)
        logger.info("MCP server '%s' tools synced: %s", server_id, result)
    except Exception:
        logger.warning("Failed to sync tools for '%s' (server registered but tools not yet available)", server_id, exc_info=True)
