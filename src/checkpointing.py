"""PostgreSQL checkpoint saver for LangGraph state persistence.

Stores graph execution checkpoints for crash recovery and audit trails.
Uses the graph_checkpoints table in the existing PostgreSQL database.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from src.aps.store import get_checkpoints, get_latest_checkpoint, store_checkpoint

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages graph execution checkpoints via PostgreSQL.

    Provides methods to save, load, and list checkpoints for thread-based
    graph executions. Each checkpoint captures the full channel state
    at a specific node in the graph execution.
    """

    @staticmethod
    def save(
        thread_id: str,
        node_name: str,
        channel_values: dict[str, Any],
        parent_checkpoint_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save a checkpoint. Returns the checkpoint_id."""
        checkpoint_id = f"cp_{uuid.uuid4().hex[:12]}"

        # Serialize channel values — filter out non-serializable items
        safe_values = {}
        for k, v in channel_values.items():
            try:
                json.dumps(v, default=str)
                safe_values[k] = v
            except (TypeError, ValueError):
                safe_values[k] = str(v)[:500]

        store_checkpoint(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            parent_id=parent_checkpoint_id,
            channel_values=safe_values,
            metadata={
                "node_name": node_name,
                **(metadata or {}),
            },
        )

        logger.debug(
            "Checkpoint saved: thread=%s cp=%s node=%s",
            thread_id,
            checkpoint_id,
            node_name,
        )
        return checkpoint_id

    @staticmethod
    def load_latest(thread_id: str) -> dict[str, Any] | None:
        """Load the most recent checkpoint for a thread."""
        return get_latest_checkpoint(thread_id)

    @staticmethod
    def load_all(thread_id: str) -> list[dict[str, Any]]:
        """Load all checkpoints for a thread (full execution history)."""
        return get_checkpoints(thread_id)

    @staticmethod
    def generate_thread_id() -> str:
        """Generate a new unique thread ID for graph execution."""
        return f"thread_{uuid.uuid4().hex[:16]}"
