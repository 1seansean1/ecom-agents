"""Event broadcasting for real-time workflow monitoring.

Provides:
- EventBroadcaster: Fan-out events to multiple WebSocket subscribers
- HollyEventCallbackHandler: LangChain callback → event bridge
- WebSocketLogHandler: Python logging → event bridge
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Singleton that fans out events to all connected WebSocket clients."""

    _instance: EventBroadcaster | None = None

    def __new__(cls) -> EventBroadcaster:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: dict[str, asyncio.Queue] = {}
        return cls._instance

    def subscribe(self) -> tuple[str, asyncio.Queue]:
        """Register a new subscriber. Returns (subscriber_id, queue)."""
        sub_id = str(uuid.uuid4())[:8]
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers[sub_id] = queue
        logger.info("Event subscriber connected: %s (total: %d)", sub_id, len(self._subscribers))
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscriber."""
        self._subscribers.pop(sub_id, None)
        logger.info("Event subscriber disconnected: %s (total: %d)", sub_id, len(self._subscribers))

    def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all subscribers (non-blocking)."""
        event["timestamp"] = time.time()
        for sub_id, queue in list(self._subscribers.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event to make room
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


# Global singleton
broadcaster = EventBroadcaster()


class HollyEventCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that broadcasts graph execution events."""

    name = "forge_event_handler"

    def __init__(self) -> None:
        self._run_map: dict[str, str] = {}  # run_id → node name
        self._aps_tool_starts: dict[str, dict] = {}  # run_id → tool info for K7

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: uuid.UUID, parent_run_id: uuid.UUID | None = None, **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name", "") or kwargs.get("name", "")
        # Filter out internal LangGraph/LangChain nodes — only broadcast real agent nodes
        _INTERNAL_NODES = {
            "RunnableSequence", "RunnableLambda", "LangGraph", "RunnableWithFallbacks",
            "RunnableParallel", "RunnablePassthrough", "ChannelWrite", "ChannelRead",
            "_route_from_orchestrator", "_route_from_error", "_route_from_sales",
        }
        if name and name not in _INTERNAL_NODES and not name.startswith("/"):
            self._run_map[str(run_id)] = name
            broadcaster.broadcast({
                "type": "node_entered",
                "node": name,
                "run_id": str(run_id),
                "inputs_preview": _safe_preview(inputs),
            })

    def on_chain_end(
        self, outputs: dict[str, Any], *, run_id: uuid.UUID, **kwargs: Any
    ) -> None:
        name = self._run_map.pop(str(run_id), None)
        if name:
            broadcaster.broadcast({
                "type": "node_exited",
                "node": name,
                "run_id": str(run_id),
                "outputs_preview": _safe_preview(outputs),
            })

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *, run_id: uuid.UUID, **kwargs: Any
    ) -> None:
        ser = serialized or {}
        model_name = ser.get("id", ["", "", ""])[-1] if ser.get("id") else ""
        broadcaster.broadcast({
            "type": "llm_start",
            "model": model_name,
            "run_id": str(run_id),
        })

    def on_llm_end(self, response: Any, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        token_usage = {}
        if hasattr(response, "llm_output") and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
        # v3: Feed actual token counts into APS token accumulator
        if token_usage:
            try:
                from src.aps.instrument import get_token_accumulator
                get_token_accumulator().accumulate(token_usage)
            except Exception:
                pass
        broadcaster.broadcast({
            "type": "llm_end",
            "run_id": str(run_id),
            "token_usage": token_usage,
        })

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: uuid.UUID, **kwargs: Any
    ) -> None:
        tool_name = (serialized or {}).get("name", "unknown")
        # APS K7: track tool start for observation logging
        self._aps_tool_starts[str(run_id)] = {
            "tool_name": tool_name,
            "start_time": time.time(),
        }
        broadcaster.broadcast({
            "type": "tool_start",
            "tool": tool_name,
            "run_id": str(run_id),
        })

    def on_tool_end(self, output: str, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        # APS K7: log tool call observation
        tool_info = self._aps_tool_starts.pop(str(run_id), None)
        if tool_info:
            try:
                from src.aps.partitions import get_active_partition
                from src.aps.store import log_observation
                from src.aps.theta import get_active_theta

                tool_name = tool_info["tool_name"]
                latency = (time.time() - tool_info["start_time"]) * 1000
                theta = get_active_theta("K7")
                partition = get_active_partition("K7")
                sigma_in = partition.classify_input({"tool_name": tool_name})
                # Classify output based on whether it looks like an error
                out_str = str(output)[:500].lower()
                result_dict: dict[str, Any] = {"data": output}
                if any(kw in out_str for kw in ("error", "exception", "failed", "timeout")):
                    result_dict = {"error": output}
                sigma_out = partition.classify_output(result_dict)
                log_observation(
                    channel_id="K7",
                    theta_id=theta.theta_id,
                    sigma_in=sigma_in,
                    sigma_out=sigma_out,
                    timestamp=time.time(),
                    latency_ms=latency,
                )
            except Exception:
                pass  # Never let APS crash the callback
        broadcaster.broadcast({
            "type": "tool_end",
            "run_id": str(run_id),
            "output_preview": str(output)[:200],
        })

    def on_chain_error(self, error: BaseException, *, run_id: uuid.UUID, **kwargs: Any) -> None:
        name = self._run_map.pop(str(run_id), None)
        broadcaster.broadcast({
            "type": "node_error",
            "node": name or "unknown",
            "run_id": str(run_id),
            "error": str(error)[:300],
        })


class WebSocketLogHandler(logging.Handler):
    """Python logging handler that broadcasts log records as events."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            broadcaster.broadcast({
                "type": "log",
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": self.format(record),
                "agent": _extract_agent_from_logger(record.name),
            })
        except Exception:
            pass  # Never let logging handler crash the app


def _safe_preview(data: Any, max_len: int = 300) -> str:
    """Safely serialize data for preview, truncating if needed."""
    try:
        text = json.dumps(data, default=str)
        return text[:max_len] + ("..." if len(text) > max_len else "")
    except Exception:
        return str(data)[:max_len]


def _extract_agent_from_logger(logger_name: str) -> str | None:
    """Extract agent name from logger like 'src.agents.orchestrator'."""
    if "orchestrator" in logger_name:
        return "orchestrator"
    if "sales" in logger_name:
        return "sales_marketing"
    if "operations" in logger_name:
        return "operations"
    if "revenue" in logger_name:
        return "revenue_analytics"
    if "sub_agent" in logger_name:
        return "sub_agents"
    return None
