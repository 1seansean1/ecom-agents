"""Partition schemes for 7 induced macro-channels.

Each channel gets two schemes (fine + coarse) with:
- Deterministic classify_input / classify_output functions
- C1-C3 admissibility audit metadata
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PartitionScheme:
    """A partition that maps AgentState fields to discrete symbols."""

    partition_id: str
    channel_id: str
    granularity: str  # "fine" or "coarse"
    sigma_in_alphabet: list[str] = field(default_factory=list)
    sigma_out_alphabet: list[str] = field(default_factory=list)
    classify_input: Callable[[dict], str] = field(default=lambda s: "unknown")
    classify_output: Callable[[dict], str] = field(default=lambda s: "unknown")
    # v3: C1-C3 admissibility audit metadata
    field_rule: str = ""       # C1: which AgentState fields are inspected
    intervention_story: str = ""  # C2: how sigma changes under feasible control
    locality_owner: str = ""     # C3: which module owns the symbol


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PARTITION_REGISTRY: dict[str, PartitionScheme] = {}
_ACTIVE_PARTITION: dict[str, str] = {}  # channel_id -> active partition_id


def register_partition(scheme: PartitionScheme) -> None:
    _PARTITION_REGISTRY[scheme.partition_id] = scheme


def get_partition(partition_id: str) -> PartitionScheme:
    return _PARTITION_REGISTRY[partition_id]


def get_active_partition(channel_id: str) -> PartitionScheme:
    pid = _ACTIVE_PARTITION.get(channel_id)
    if pid is None:
        raise KeyError(f"No active partition for channel {channel_id}")
    return _PARTITION_REGISTRY[pid]


def set_active_partition(channel_id: str, partition_id: str) -> None:
    _ACTIVE_PARTITION[channel_id] = partition_id


def get_all_partition_states() -> dict[str, str]:
    return dict(_ACTIVE_PARTITION)


# ---------------------------------------------------------------------------
# K1 — Orchestrator Routing Channel
# ---------------------------------------------------------------------------

_K1_TASK_KEYWORDS: dict[str, list[str]] = {
    "content_post": ["instagram", "post", "content", "social"],
    "full_campaign": ["campaign", "marketing", "weekly"],
    "product_launch": ["launch", "new product", "listing"],
    "order_check": ["order", "fulfillment", "pending"],
    "inventory_sync": ["inventory", "sync", "stock"],
    "revenue_report": ["revenue", "report", "sales analysis"],
    "pricing_review": ["pricing", "price", "margin"],
}

_K1_COARSE_MAP: dict[str, str] = {
    "content_post": "sales_task",
    "full_campaign": "sales_task",
    "product_launch": "sales_task",
    "order_check": "ops_task",
    "inventory_sync": "ops_task",
    "revenue_report": "analytics_task",
    "pricing_review": "analytics_task",
}


def _k1_fine_classify_input(state: dict) -> str:
    text = ""
    messages = state.get("messages", [])
    if messages:
        last = messages[-1]
        text = getattr(last, "content", str(last)).lower()
    payload = state.get("trigger_payload", {})
    if payload:
        text += " " + json.dumps(payload).lower()

    for symbol, keywords in _K1_TASK_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return symbol
    return "content_post"


def _k1_fine_classify_output(result: dict) -> str:
    task_type = result.get("task_type", "")
    route = result.get("route_to", "")
    if route == "error_handler" or not task_type:
        return "error"
    return task_type if task_type in _K1_TASK_KEYWORDS else "unknown"


def _k1_coarse_classify_input(state: dict) -> str:
    fine = _k1_fine_classify_input(state)
    return _K1_COARSE_MAP.get(fine, "ops_task")


def _k1_coarse_classify_output(result: dict) -> str:
    route = result.get("route_to", "")
    if route in ("sales_marketing", "operations", "revenue_analytics"):
        return route
    return "error"


# ---------------------------------------------------------------------------
# K2 — Sales & Marketing Execution Channel
# ---------------------------------------------------------------------------


def _k2_fine_classify_input(state: dict) -> str:
    task_type = state.get("task_type", "")
    complexity = state.get("task_complexity", "")
    if task_type == "content_post" and complexity in ("trivial", "simple"):
        return "simple_post"
    if task_type == "full_campaign":
        return "campaign_delegated"
    if task_type == "product_launch":
        return "product_launch_delegated"
    return "simple_post"


def _k2_fine_classify_output(result: dict) -> str:
    if result.get("error"):
        return "error"
    if result.get("should_spawn_sub_agents"):
        return "delegated"
    sales = result.get("sales_result", {})
    if isinstance(sales, dict):
        try:
            json.dumps(sales)
            if sales.get("caption") or sales.get("status"):
                return "completed_json"
        except (TypeError, ValueError):
            pass
    if sales:
        return "completed_raw"
    return "completed_raw"


def _k2_coarse_classify_input(state: dict) -> str:
    if state.get("task_complexity") in ("moderate", "complex"):
        return "delegated_task"
    return "direct_task"


def _k2_coarse_classify_output(result: dict) -> str:
    if result.get("error"):
        return "failure"
    return "success"


# ---------------------------------------------------------------------------
# K3 — Operations Execution Channel
# ---------------------------------------------------------------------------

_K3_FINE_INPUT_MAP: dict[str, str] = {
    "order_check": "order_check",
    "inventory_sync": "inventory_sync",
}


def _k3_fine_classify_input(state: dict) -> str:
    task_type = state.get("task_type", "")
    if task_type in _K3_FINE_INPUT_MAP:
        return _K3_FINE_INPUT_MAP[task_type]
    payload = json.dumps(state.get("trigger_payload", {})).lower()
    if "fulfill" in payload:
        return "fulfill_order"
    if "status" in payload:
        return "order_status"
    return "order_check"


def _k3_fine_classify_output(result: dict) -> str:
    if result.get("error"):
        return "error"
    ops = result.get("operations_result", {})
    if not isinstance(ops, dict):
        return "malformed"
    if ops.get("error") or ops.get("status") == "error":
        return "error"
    if ops.get("needs_action") or ops.get("action_required"):
        return "needs_action"
    return "completed"


def _k3_coarse_classify_input(state: dict) -> str:
    task_type = state.get("task_type", "")
    if task_type in ("inventory_sync", "fulfill_order"):
        return "write_operation"
    return "read_operation"


def _k3_coarse_classify_output(result: dict) -> str:
    if result.get("error"):
        return "failure"
    ops = result.get("operations_result", {})
    if isinstance(ops, dict) and (ops.get("error") or ops.get("status") == "error"):
        return "failure"
    return "success"


# ---------------------------------------------------------------------------
# K4 — Revenue Analytics Execution Channel
# ---------------------------------------------------------------------------


def _k4_fine_classify_input(state: dict) -> str:
    task_type = state.get("task_type", "")
    if task_type == "pricing_review":
        return "pricing_review"
    return "revenue_report"


def _k4_fine_classify_output(result: dict) -> str:
    if result.get("error"):
        return "error"
    rev = result.get("revenue_result", {})
    if not isinstance(rev, dict):
        return "error"
    task_type = result.get("task_type", "")
    # Determine revenue level heuristically from result content
    text = json.dumps(rev).lower()
    if task_type == "pricing_review" or "pricing" in text:
        if "high" in text or "increase" in text:
            return "pricing_high"
        if "low" in text or "decrease" in text:
            return "pricing_low"
        return "pricing_med"
    if "high" in text or "growth" in text or "increase" in text:
        return "daily_rev_high"
    if "low" in text or "decline" in text or "decrease" in text:
        return "daily_rev_low"
    return "daily_rev_med"


def _k4_coarse_classify_input(state: dict) -> str:
    return "analytics_task"


def _k4_coarse_classify_output(result: dict) -> str:
    if result.get("error"):
        return "error"
    rev = result.get("revenue_result", {})
    if not isinstance(rev, dict):
        return "error"
    text = json.dumps(rev).lower()
    if any(kw in text for kw in ("recommend", "action", "should", "increase", "decrease")):
        return "actionable"
    return "informational"


# ---------------------------------------------------------------------------
# K5 — Content Writer Sub-Agent Channel
# ---------------------------------------------------------------------------


def _k5_fine_classify_input(state: dict) -> str:
    payload = state.get("trigger_payload", {})
    task = json.dumps(payload).lower() if payload else ""
    if "product" in task:
        return "product_brief"
    return "campaign_brief"


def _k5_fine_classify_output(result: dict) -> str:
    sub = result.get("sub_agent_results", {})
    writer = sub.get("content_writer", {}) if isinstance(sub, dict) else {}
    if not writer:
        return "error"
    if isinstance(writer, dict) and writer.get("caption"):
        return "json_with_caption"
    if isinstance(writer, dict):
        return "json_no_caption"
    return "raw_text"


def _k5_coarse_classify_input(state: dict) -> str:
    return "brief"


def _k5_coarse_classify_output(result: dict) -> str:
    sub = result.get("sub_agent_results", {})
    writer = sub.get("content_writer", {}) if isinstance(sub, dict) else {}
    if writer:
        return "usable"
    return "unusable"


# ---------------------------------------------------------------------------
# K6 — Campaign Analyzer Sub-Agent Channel
# ---------------------------------------------------------------------------


def _k6_fine_classify_input(state: dict) -> str:
    sub = state.get("sub_agent_results", {})
    if not isinstance(sub, dict):
        return "partial_results"
    expected = {"content_writer", "image_selector", "hashtag_optimizer"}
    present = set(sub.keys()) & expected
    if len(present) >= 3:
        return "full_results"
    return "partial_results"


def _k6_fine_classify_output(result: dict) -> str:
    sub = result.get("sub_agent_results", {})
    analyzer = sub.get("campaign_analyzer", {}) if isinstance(sub, dict) else {}
    if not analyzer:
        return "analysis_failed"
    text = json.dumps(analyzer).lower()
    rate = analyzer.get("expected_engagement_rate", "")
    if isinstance(rate, str):
        try:
            val = float(rate.strip("%"))
        except (ValueError, AttributeError):
            val = 0
    else:
        val = float(rate) if rate else 0
    if val > 5:
        return "high_engagement"
    if val > 2:
        return "medium_engagement"
    if val > 0:
        return "low_engagement"
    if "high" in text:
        return "high_engagement"
    if "low" in text:
        return "low_engagement"
    return "medium_engagement"


def _k6_coarse_classify_input(state: dict) -> str:
    return "analysis_input"


def _k6_coarse_classify_output(result: dict) -> str:
    sub = result.get("sub_agent_results", {})
    analyzer = sub.get("campaign_analyzer", {}) if isinstance(sub, dict) else {}
    if analyzer:
        return "pass"
    return "fail"


# ---------------------------------------------------------------------------
# K7 — Tool Call Channel
# ---------------------------------------------------------------------------

_K7_SERVICE_MAP: dict[str, str] = {}
_K7_TOOL_NAMES = [
    "shopify_query_products", "shopify_create_product", "shopify_query_orders",
    "stripe_create_product", "stripe_payment_link", "stripe_revenue_query",
    "stripe_list_products", "printful_catalog", "printful_products",
    "printful_store", "printful_order_status", "instagram_publish",
    "instagram_insights",
]
for _t in _K7_TOOL_NAMES:
    for _svc in ("shopify", "stripe", "printful", "instagram"):
        if _t.startswith(_svc):
            _K7_SERVICE_MAP[_t] = _svc
            break


def _k7_fine_classify_input(state: dict) -> str:
    """Classify by exact tool function name.

    For K7, 'state' is actually a dict with 'tool_name' injected by the
    callback handler instrumentation.
    """
    name = state.get("tool_name", "unknown")
    if name in _K7_TOOL_NAMES:
        return name
    return "unknown"


def _k7_fine_classify_output(result: dict) -> str:
    """Classify tool call result into fine-grained outcome."""
    error = result.get("error")
    if error:
        err_str = str(error).lower()
        if "timeout" in err_str:
            return "timeout"
        if "401" in err_str or "403" in err_str or "auth" in err_str:
            return "auth_error"
        if "429" in err_str or "rate" in err_str:
            return "rate_limited"
        if "parse" in err_str or "json" in err_str:
            return "parse_error"
        return "http_error"
    data = result.get("data")
    if data is None or data == "" or data == [] or data == {}:
        return "success_empty"
    return "success_data"


def _k7_coarse_classify_input(state: dict) -> str:
    name = state.get("tool_name", "unknown")
    return _K7_SERVICE_MAP.get(name, "unknown")


def _k7_coarse_classify_output(result: dict) -> str:
    if result.get("error"):
        return "failure"
    return "success"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _make_all_partitions() -> list[PartitionScheme]:
    """Build all 14 partition scheme definitions."""
    return [
        # K1 Fine
        PartitionScheme(
            partition_id="theta_K1_fine",
            channel_id="K1",
            granularity="fine",
            sigma_in_alphabet=[
                "content_post", "full_campaign", "product_launch",
                "order_check", "inventory_sync", "revenue_report", "pricing_review",
            ],
            sigma_out_alphabet=[
                "content_post", "full_campaign", "product_launch",
                "order_check", "inventory_sync", "revenue_report", "pricing_review",
                "error", "unknown",
            ],
            classify_input=_k1_fine_classify_input,
            classify_output=_k1_fine_classify_output,
            field_rule="inspects state['messages'][-1].content and state['trigger_payload'] via keyword matching",
            intervention_story="different task descriptions produce different sigma_in values; achievable via scheduler job configuration",
            locality_owner="owned by orchestrator module (src/agents/orchestrator.py)",
        ),
        # K1 Coarse
        PartitionScheme(
            partition_id="theta_K1_coarse",
            channel_id="K1",
            granularity="coarse",
            sigma_in_alphabet=["sales_task", "ops_task", "analytics_task"],
            sigma_out_alphabet=["sales_marketing", "operations", "revenue_analytics", "error"],
            classify_input=_k1_coarse_classify_input,
            classify_output=_k1_coarse_classify_output,
            field_rule="maps fine-grained task type to 3 coarse groups",
            intervention_story="different task categories produce different coarse sigma_in values",
            locality_owner="owned by orchestrator module (src/agents/orchestrator.py)",
        ),
        # K2 Fine
        PartitionScheme(
            partition_id="theta_K2_fine",
            channel_id="K2",
            granularity="fine",
            sigma_in_alphabet=["simple_post", "campaign_delegated", "product_launch_delegated"],
            sigma_out_alphabet=["completed_json", "completed_raw", "delegated", "error"],
            classify_input=_k2_fine_classify_input,
            classify_output=_k2_fine_classify_output,
            field_rule="inspects state['task_type'] and state['task_complexity']",
            intervention_story="different task types and complexities produce different classifications",
            locality_owner="owned by sales_marketing module (src/agents/sales_marketing.py)",
        ),
        # K2 Coarse
        PartitionScheme(
            partition_id="theta_K2_coarse",
            channel_id="K2",
            granularity="coarse",
            sigma_in_alphabet=["direct_task", "delegated_task"],
            sigma_out_alphabet=["success", "failure"],
            classify_input=_k2_coarse_classify_input,
            classify_output=_k2_coarse_classify_output,
            field_rule="inspects state['task_complexity'] for delegation decision",
            intervention_story="simple vs complex tasks produce different coarse inputs",
            locality_owner="owned by sales_marketing module (src/agents/sales_marketing.py)",
        ),
        # K3 Fine
        PartitionScheme(
            partition_id="theta_K3_fine",
            channel_id="K3",
            granularity="fine",
            sigma_in_alphabet=["order_check", "inventory_sync", "fulfill_order", "order_status"],
            sigma_out_alphabet=["completed", "needs_action", "error", "malformed"],
            classify_input=_k3_fine_classify_input,
            classify_output=_k3_fine_classify_output,
            field_rule="inspects state['task_type'] and state['trigger_payload']",
            intervention_story="different operational tasks produce different fine-grained inputs",
            locality_owner="owned by operations module (src/agents/operations.py)",
        ),
        # K3 Coarse
        PartitionScheme(
            partition_id="theta_K3_coarse",
            channel_id="K3",
            granularity="coarse",
            sigma_in_alphabet=["read_operation", "write_operation"],
            sigma_out_alphabet=["success", "failure"],
            classify_input=_k3_coarse_classify_input,
            classify_output=_k3_coarse_classify_output,
            field_rule="maps task_type to read/write classification",
            intervention_story="read vs write operations produce different coarse inputs",
            locality_owner="owned by operations module (src/agents/operations.py)",
        ),
        # K4 Fine
        PartitionScheme(
            partition_id="theta_K4_fine",
            channel_id="K4",
            granularity="fine",
            sigma_in_alphabet=["revenue_report", "pricing_review"],
            sigma_out_alphabet=[
                "daily_rev_high", "daily_rev_med", "daily_rev_low",
                "pricing_high", "pricing_med", "pricing_low", "error",
            ],
            classify_input=_k4_fine_classify_input,
            classify_output=_k4_fine_classify_output,
            field_rule="inspects state['task_type'] for revenue vs pricing",
            intervention_story="revenue vs pricing tasks produce different input symbols",
            locality_owner="owned by revenue module (src/agents/revenue.py)",
        ),
        # K4 Coarse
        PartitionScheme(
            partition_id="theta_K4_coarse",
            channel_id="K4",
            granularity="coarse",
            sigma_in_alphabet=["analytics_task"],
            sigma_out_alphabet=["actionable", "informational", "error"],
            classify_input=_k4_coarse_classify_input,
            classify_output=_k4_coarse_classify_output,
            field_rule="all analytics tasks map to single coarse input",
            intervention_story="coarse view only distinguishes actionable from informational",
            locality_owner="owned by revenue module (src/agents/revenue.py)",
        ),
        # K5 Fine
        PartitionScheme(
            partition_id="theta_K5_fine",
            channel_id="K5",
            granularity="fine",
            sigma_in_alphabet=["campaign_brief", "product_brief"],
            sigma_out_alphabet=["json_with_caption", "json_no_caption", "raw_text", "error"],
            classify_input=_k5_fine_classify_input,
            classify_output=_k5_fine_classify_output,
            field_rule="inspects state['trigger_payload'] for product vs campaign keywords",
            intervention_story="product vs campaign briefs produce different input symbols",
            locality_owner="owned by sub_agents content_writer (src/agents/sub_agents.py)",
        ),
        # K5 Coarse
        PartitionScheme(
            partition_id="theta_K5_coarse",
            channel_id="K5",
            granularity="coarse",
            sigma_in_alphabet=["brief"],
            sigma_out_alphabet=["usable", "unusable"],
            classify_input=_k5_coarse_classify_input,
            classify_output=_k5_coarse_classify_output,
            field_rule="all briefs map to single coarse input",
            intervention_story="coarse view only distinguishes usable from unusable output",
            locality_owner="owned by sub_agents content_writer (src/agents/sub_agents.py)",
        ),
        # K6 Fine
        PartitionScheme(
            partition_id="theta_K6_fine",
            channel_id="K6",
            granularity="fine",
            sigma_in_alphabet=["full_results", "partial_results"],
            sigma_out_alphabet=[
                "high_engagement", "medium_engagement",
                "low_engagement", "analysis_failed",
            ],
            classify_input=_k6_fine_classify_input,
            classify_output=_k6_fine_classify_output,
            field_rule="inspects state['sub_agent_results'] keys for completeness",
            intervention_story="full vs partial upstream results produce different inputs",
            locality_owner="owned by sub_agents campaign_analyzer (src/agents/sub_agents.py)",
        ),
        # K6 Coarse
        PartitionScheme(
            partition_id="theta_K6_coarse",
            channel_id="K6",
            granularity="coarse",
            sigma_in_alphabet=["analysis_input"],
            sigma_out_alphabet=["pass", "fail"],
            classify_input=_k6_coarse_classify_input,
            classify_output=_k6_coarse_classify_output,
            field_rule="all analysis inputs map to single coarse input",
            intervention_story="coarse view only distinguishes pass from fail",
            locality_owner="owned by sub_agents campaign_analyzer (src/agents/sub_agents.py)",
        ),
        # K7 Fine
        PartitionScheme(
            partition_id="theta_K7_fine",
            channel_id="K7",
            granularity="fine",
            sigma_in_alphabet=_K7_TOOL_NAMES + ["unknown"],
            sigma_out_alphabet=[
                "success_data", "success_empty", "http_error",
                "timeout", "auth_error", "rate_limited", "parse_error",
            ],
            classify_input=_k7_fine_classify_input,
            classify_output=_k7_fine_classify_output,
            field_rule="inspects serialized['name'] from LangChain on_tool_start callback",
            intervention_story="different tool invocations produce different sigma_in values",
            locality_owner="owned by tool implementations (src/tools/*.py)",
        ),
        # K7 Coarse
        PartitionScheme(
            partition_id="theta_K7_coarse",
            channel_id="K7",
            granularity="coarse",
            sigma_in_alphabet=["shopify", "stripe", "printful", "instagram", "unknown"],
            sigma_out_alphabet=["success", "failure"],
            classify_input=_k7_coarse_classify_input,
            classify_output=_k7_coarse_classify_output,
            field_rule="maps tool names to 4 service groups",
            intervention_story="different services produce different coarse inputs",
            locality_owner="owned by tool implementations (src/tools/*.py)",
        ),
    ]


def register_all_partitions() -> None:
    """Register all 14 partition schemes and set fine partitions as defaults."""
    for scheme in _make_all_partitions():
        register_partition(scheme)

    # Default: all channels start at fine partition (level 0 nominal)
    for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
        set_active_partition(ch, f"theta_{ch}_fine")

    logger.info("Registered %d partition schemes", len(_PARTITION_REGISTRY))
