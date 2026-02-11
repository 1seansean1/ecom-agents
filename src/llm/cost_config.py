"""LLM cost configuration — model pricing, routing rules, and cost tracking.

Defines per-model costs and routing rules to minimize API spend:
- Classification/routing → GPT-4o-mini ($0.15/1M input, $0.60/1M output)
- Content generation → GPT-4o-mini (cheapest capable model)
- Complex reasoning → Claude Opus ($15/1M input, $75/1M output)
- Quality content → GPT-4o ($2.50/1M input, $10/1M output)
- Local tasks → Ollama qwen2.5:3b (free, but not available on ECS)

The cost tracker logs per-workflow token usage for budget monitoring.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Model cost matrix (per 1M tokens, USD) ──────────────────────────────

@dataclass(frozen=True)
class ModelCost:
    model_id: str
    display_name: str
    input_per_1m: float   # $ per 1M input tokens
    output_per_1m: float  # $ per 1M output tokens
    is_local: bool = False  # Available without API call

    @property
    def input_per_token(self) -> float:
        return self.input_per_1m / 1_000_000

    @property
    def output_per_token(self) -> float:
        return self.output_per_1m / 1_000_000


MODEL_COSTS: dict[str, ModelCost] = {
    # OpenAI
    "gpt-4o": ModelCost("gpt-4o", "GPT-4o", 2.50, 10.00),
    "gpt-4o-mini": ModelCost("gpt-4o-mini", "GPT-4o Mini", 0.15, 0.60),
    # Anthropic
    "claude-opus-4-6": ModelCost("claude-opus-4-6", "Claude Opus 4.6", 15.00, 75.00),
    "claude-sonnet-4-5": ModelCost("claude-sonnet-4-5", "Claude Sonnet 4.5", 3.00, 15.00),
    "claude-haiku-4-5": ModelCost("claude-haiku-4-5", "Claude Haiku 4.5", 0.80, 4.00),
    # Local (free)
    "qwen2.5:3b": ModelCost("qwen2.5:3b", "Qwen 2.5 3B", 0.0, 0.0, is_local=True),
    "llama3.1:8b": ModelCost("llama3.1:8b", "Llama 3.1 8B", 0.0, 0.0, is_local=True),
    "phi3:mini": ModelCost("phi3:mini", "Phi-3 Mini", 0.0, 0.0, is_local=True),
}


# ── Task-to-model routing rules ─────────────────────────────────────────

TASK_ROUTING: dict[str, str] = {
    # Cheap tasks → GPT-4o-mini
    "classification": "gpt-4o-mini",
    "routing": "gpt-4o-mini",
    "content_generation": "gpt-4o-mini",
    "description_writing": "gpt-4o-mini",
    "social_media": "gpt-4o-mini",
    "email_drafting": "gpt-4o-mini",
    "summarization": "gpt-4o-mini",
    "seo_optimization": "gpt-4o-mini",
    # Quality tasks → GPT-4o
    "quality_content": "gpt-4o",
    "campaign_planning": "gpt-4o",
    "data_analysis": "gpt-4o",
    "code_review": "gpt-4o",
    # Complex reasoning → Opus
    "strategy": "claude-opus-4-6",
    "complex_reasoning": "claude-opus-4-6",
    "architecture_design": "claude-opus-4-6",
    "security_review": "claude-opus-4-6",
    "research": "claude-opus-4-6",
    # Local when available
    "trivial_routing": "qwen2.5:3b",
    "health_check": "qwen2.5:3b",
}


def get_model_for_task(task_type: str) -> str:
    """Get the recommended model for a task type. Falls back to gpt-4o-mini."""
    model = TASK_ROUTING.get(task_type, "gpt-4o-mini")
    # If local model selected but Ollama not available, fall back
    cost = MODEL_COSTS.get(model)
    if cost and cost.is_local:
        if not os.environ.get("OLLAMA_BASE_URL"):
            return "gpt-4o-mini"
    return model


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a model call."""
    cost = MODEL_COSTS.get(model_id)
    if not cost:
        return 0.0
    return cost.input_per_token * input_tokens + cost.output_per_token * output_tokens


def get_cost_summary() -> list[dict]:
    """Return all models with their costs for Holly's introspection."""
    return [
        {
            "model_id": c.model_id,
            "display_name": c.display_name,
            "input_per_1m": c.input_per_1m,
            "output_per_1m": c.output_per_1m,
            "is_local": c.is_local,
        }
        for c in sorted(MODEL_COSTS.values(), key=lambda x: x.input_per_1m)
    ]


# ── Cost tracker (in-memory, per-workflow) ───────────────────────────────

@dataclass
class WorkflowCostEntry:
    workflow_id: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    recorded_at: str = ""


_cost_log: list[WorkflowCostEntry] = []
_cost_lock = threading.Lock()


def track_cost(workflow_id: str, model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Track a model call's cost. Returns the cost in USD."""
    cost = estimate_cost(model_id, input_tokens, output_tokens)
    entry = WorkflowCostEntry(
        workflow_id=workflow_id,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        calls=1,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    with _cost_lock:
        _cost_log.append(entry)
        # Keep last 1000 entries
        if len(_cost_log) > 1000:
            _cost_log[:] = _cost_log[-500:]
    return cost


def get_workflow_costs(workflow_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent cost entries, optionally filtered by workflow."""
    with _cost_lock:
        entries = list(_cost_log)
    if workflow_id:
        entries = [e for e in entries if e.workflow_id == workflow_id]
    entries = entries[-limit:]
    return [
        {
            "workflow_id": e.workflow_id,
            "model_id": e.model_id,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": round(e.cost_usd, 6),
            "calls": e.calls,
            "recorded_at": e.recorded_at,
        }
        for e in entries
    ]


def get_total_cost_by_workflow() -> dict[str, float]:
    """Get total cost per workflow (from in-memory log)."""
    totals: dict[str, float] = {}
    with _cost_lock:
        for e in _cost_log:
            totals[e.workflow_id] = totals.get(e.workflow_id, 0.0) + e.cost_usd
    return {k: round(v, 4) for k, v in sorted(totals.items())}
