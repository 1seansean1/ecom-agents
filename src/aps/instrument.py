"""Instrumentation wrapper for agent nodes.

Wraps each agent node function to:
1. Classify input/output into partition symbols
2. Track actual token usage via thread-local accumulator
3. Inject trace_id and build path_id incrementally
4. Apply regeneration protocols when active
5. Log observations to PostgreSQL
6. Broadcast events via WebSocket

All operations are try/excepted — the original node function ALWAYS runs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from src.aps.partitions import get_partition
from src.aps.regeneration import (
    confirm_protocol,
    crosscheck_protocol,
    is_failure,
)
from src.aps.store import log_observation
from src.aps.theta import ProtocolLevel, get_active_theta
from src.llm.config import MODEL_REGISTRY, ModelID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token Accumulator (v3: actual token accounting)
# ---------------------------------------------------------------------------


class TokenAccumulator:
    """Thread-local accumulator for actual LLM token counts.

    The HollyEventCallbackHandler calls accumulate() in on_llm_end.
    The instrument_node wrapper calls reset() before the node runs
    and get() after the node returns.
    """

    def __init__(self):
        self._local = threading.local()

    def reset(self):
        self._local.tokens = {}

    def accumulate(self, token_usage: dict):
        current = getattr(self._local, "tokens", {})
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            current[key] = current.get(key, 0) + (token_usage.get(key, 0) or 0)
        self._local.tokens = current

    def get(self) -> dict | None:
        tokens = getattr(self._local, "tokens", {})
        return tokens if tokens else None


# Global singleton
_token_accumulator = TokenAccumulator()


def get_token_accumulator() -> TokenAccumulator:
    """Access the global token accumulator (for callback handler integration)."""
    return _token_accumulator


# ---------------------------------------------------------------------------
# Cost computation
# ---------------------------------------------------------------------------


def compute_actual_cost(model_id: ModelID | str, tokens: dict) -> float:
    """Compute cost from actual token counts.

    MODEL_REGISTRY values match published per-1M pricing despite field name.
    """
    if isinstance(model_id, str):
        try:
            model_id = ModelID(model_id)
        except ValueError:
            return 0.0
    spec = MODEL_REGISTRY.get(model_id)
    if not spec:
        return 0.0
    prompt = tokens.get("prompt_tokens", 0) or 0
    completion = tokens.get("completion_tokens", 0) or 0
    # Rates are per 1M tokens (field name is historical)
    return round(
        (prompt / 1_000_000) * spec.cost_per_1k_input
        + (completion / 1_000_000) * spec.cost_per_1k_output,
        6,
    )


def estimate_cost(model_id: ModelID | str, state: dict, result: dict) -> float:
    """Estimate cost when actual token counts unavailable.

    Uses rough heuristic: ~500 input tokens, ~200 output tokens.
    """
    if isinstance(model_id, str):
        try:
            model_id = ModelID(model_id)
        except ValueError:
            return 0.0
    spec = MODEL_REGISTRY.get(model_id)
    if not spec:
        return 0.0
    est_input = 500
    est_output = 200
    return round(
        (est_input / 1_000_000) * spec.cost_per_1k_input
        + (est_output / 1_000_000) * spec.cost_per_1k_output,
        6,
    )


# ---------------------------------------------------------------------------
# Node instrumentation wrapper
# ---------------------------------------------------------------------------


def instrument_node(
    channel_id: str, model_id: ModelID, node_fn: Callable
) -> Callable:
    """Wrap an agent node function with APS instrumentation.

    Returns a function with the same signature that:
    1. Classifies input into sigma_in
    2. Runs the original node function (ALWAYS)
    3. Classifies output into sigma_out
    4. Applies regeneration if active
    5. Logs the observation
    6. Propagates path_id downstream
    """

    def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
        # --- Pre-execution instrumentation ---
        theta = None
        partition = None
        sigma_in = "unknown"
        trace_id = None
        path_id = ""

        try:
            theta = get_active_theta(channel_id)
            partition = get_partition(theta.partition_id)
            sigma_in = partition.classify_input(state)
        except Exception:
            logger.debug("APS pre-instrumentation failed for %s", channel_id, exc_info=True)

        effective_model = model_id
        if theta and theta.model_override:
            effective_model = theta.model_override

        # v3: trace_id from config
        try:
            if config and "configurable" in config:
                trace_id = config["configurable"].get("aps_trace_id")
        except Exception:
            pass

        # v3: build path_id incrementally
        try:
            parent_path = state.get("_aps_path_id", "")
            path_id = f"{parent_path}>{channel_id}" if parent_path else channel_id
        except Exception:
            path_id = channel_id

        # v3: reset token accumulator
        _token_accumulator.reset()

        # --- Execute the original node function (ALWAYS runs) ---
        t0 = time.time()
        result = node_fn(state)
        latency_ms = (time.time() - t0) * 1000

        # --- Post-execution instrumentation ---
        sigma_out = "unknown"
        try:
            if partition:
                sigma_out = partition.classify_output(result)

            # Apply regeneration protocol if active
            if theta and theta.protocol_level == ProtocolLevel.CONFIRM:
                if is_failure(sigma_out, channel_id):
                    try:
                        result, sigma_out = confirm_protocol.execute(
                            channel_id, state, result, node_fn, partition
                        )
                    except Exception:
                        logger.debug("ConfirmProtocol failed for %s", channel_id, exc_info=True)
            elif theta and theta.protocol_level == ProtocolLevel.CROSSCHECK:
                try:
                    result, override = crosscheck_protocol.execute(channel_id, result)
                    if override is not None:
                        sigma_out = override
                except Exception:
                    logger.debug("CrosscheckProtocol failed for %s", channel_id, exc_info=True)
        except Exception:
            logger.debug("APS post-instrumentation failed for %s", channel_id, exc_info=True)

        # v3: read actual token counts
        tokens = _token_accumulator.get()
        try:
            if tokens:
                cost = compute_actual_cost(effective_model, tokens)
            else:
                cost = estimate_cost(effective_model, state, result)
        except Exception:
            cost = 0.0

        # Log observation
        try:
            theta_id = theta.theta_id if theta else f"theta_{channel_id}_nominal"
            log_observation(
                channel_id=channel_id,
                theta_id=theta_id,
                sigma_in=sigma_in,
                sigma_out=sigma_out,
                timestamp=time.time(),
                latency_ms=latency_ms,
                cost_usd=cost,
                prompt_tokens=tokens.get("prompt_tokens") if tokens else None,
                completion_tokens=tokens.get("completion_tokens") if tokens else None,
                total_tokens=tokens.get("total_tokens") if tokens else None,
                model_id=effective_model.value if isinstance(effective_model, ModelID) else str(effective_model),
                trace_id=trace_id,
                path_id=path_id,
            )
        except Exception:
            logger.debug("APS observation logging failed for %s", channel_id, exc_info=True)

        # Broadcast event
        try:
            from src.events import broadcaster
            broadcaster.broadcast({
                "type": "aps_observation",
                "channel_id": channel_id,
                "theta_id": theta_id if theta else "unknown",
                "sigma_in": sigma_in,
                "sigma_out": sigma_out,
                "latency_ms": round(latency_ms, 1),
                "cost_usd": round(cost, 6),
                "prompt_tokens": tokens.get("prompt_tokens") if tokens else None,
                "completion_tokens": tokens.get("completion_tokens") if tokens else None,
                "model_id": effective_model.value if isinstance(effective_model, ModelID) else str(effective_model),
                "trace_id": trace_id,
                "path_id": path_id,
                "level": theta.level if theta else 0,
                "protocol_active": theta.protocol_level.value if theta else "passive",
            })
        except Exception:
            pass

        # v3: propagate path_id to downstream nodes
        if isinstance(result, dict):
            result["_aps_path_id"] = path_id

        return result

    return wrapped
