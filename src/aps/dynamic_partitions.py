"""Dynamic Partitions: auto-generate APS partition schemes and theta configs
for dynamically created agents.

When a new agent is created, this module generates:
- Fine partition: classifies by error/success + result structure
- Coarse partition: binary success/failure
- 3 theta configs: nominal (fine, passive), degraded (coarse, confirm),
  critical (coarse, crosscheck)

Channel IDs for dynamic agents start at K8 and increment.
"""

from __future__ import annotations

import json
import logging

from src.aps.partitions import PartitionScheme, register_partition, set_active_partition
from src.aps.theta import (
    ProtocolLevel,
    ThetaConfig,
    THETA_REGISTRY,
    set_active_theta,
)

logger = logging.getLogger(__name__)

# Track the next available channel number
_next_channel_num = 8


def _get_next_channel_id() -> str:
    """Get the next available channel ID (K8, K9, ...)."""
    global _next_channel_num
    cid = f"K{_next_channel_num}"
    _next_channel_num += 1
    return cid


def _make_generic_fine_classify_input(agent_id: str):
    """Build a generic fine-grained input classifier.

    Classifies based on task_type presence and message content length.
    """

    def classify(state: dict) -> str:
        task_type = state.get("task_type", "")
        if task_type:
            return task_type

        messages = state.get("messages", [])
        if messages:
            last = messages[-1]
            text = getattr(last, "content", str(last))
            if len(text) > 500:
                return "complex_input"
            return "simple_input"

        payload = state.get("trigger_payload")
        if payload:
            return "triggered"

        return "unknown"

    return classify


def _make_generic_fine_classify_output(agent_id: str):
    """Build a generic fine-grained output classifier.

    Classifies based on error presence, JSON structure, and result content.
    """

    def classify(result: dict) -> str:
        if result.get("error"):
            return "error"

        # Check agent_results for this agent
        agent_results = result.get("agent_results", {})
        agent_result = agent_results.get(agent_id, {})

        if not agent_result and not result.get("current_agent"):
            return "empty"

        # Check the result content
        check = agent_result if agent_result else result
        if isinstance(check, dict):
            if check.get("status") == "error":
                return "error"
            if check.get("raw_content"):
                return "completed_raw"
            # Has structured JSON fields
            keys = set(check.keys()) - {"status", "raw_content"}
            if len(keys) > 2:
                return "completed_structured"
            return "completed_simple"

        return "completed_raw"

    return classify


def _make_generic_coarse_classify_input(agent_id: str):
    """Build a generic coarse input classifier: just 'task'."""

    def classify(state: dict) -> str:
        return "task"

    return classify


def _make_generic_coarse_classify_output(agent_id: str):
    """Build a generic coarse output classifier: success/failure."""

    def classify(result: dict) -> str:
        if result.get("error"):
            return "failure"
        agent_results = result.get("agent_results", {})
        agent_result = agent_results.get(agent_id, {})
        if isinstance(agent_result, dict) and agent_result.get("status") == "error":
            return "failure"
        return "success"

    return classify


def generate_partitions_for_agent(
    agent_id: str,
    channel_id: str,
) -> tuple[PartitionScheme, PartitionScheme]:
    """Generate fine and coarse partition schemes for a dynamic agent.

    Args:
        agent_id: The agent identifier.
        channel_id: The APS channel ID (e.g., "K8").

    Returns:
        Tuple of (fine_partition, coarse_partition).
    """
    fine = PartitionScheme(
        partition_id=f"theta_{channel_id}_fine",
        channel_id=channel_id,
        granularity="fine",
        sigma_in_alphabet=[
            "simple_input", "complex_input", "triggered", "unknown",
            "content_post", "full_campaign", "product_launch",
            "order_check", "inventory_sync", "revenue_report", "pricing_review",
        ],
        sigma_out_alphabet=[
            "completed_structured", "completed_simple", "completed_raw",
            "empty", "error",
        ],
        classify_input=_make_generic_fine_classify_input(agent_id),
        classify_output=_make_generic_fine_classify_output(agent_id),
        field_rule=f"inspects state for agent {agent_id}: task_type, messages, trigger_payload",
        intervention_story=f"different inputs to {agent_id} produce different classifications",
        locality_owner=f"owned by dynamic agent {agent_id} (auto-generated)",
    )

    coarse = PartitionScheme(
        partition_id=f"theta_{channel_id}_coarse",
        channel_id=channel_id,
        granularity="coarse",
        sigma_in_alphabet=["task"],
        sigma_out_alphabet=["success", "failure"],
        classify_input=_make_generic_coarse_classify_input(agent_id),
        classify_output=_make_generic_coarse_classify_output(agent_id),
        field_rule=f"all inputs to {agent_id} map to single coarse symbol",
        intervention_story=f"coarse view only distinguishes success from failure for {agent_id}",
        locality_owner=f"owned by dynamic agent {agent_id} (auto-generated)",
    )

    return fine, coarse


def generate_thetas_for_agent(
    agent_id: str,
    channel_id: str,
) -> list[ThetaConfig]:
    """Generate 3 theta configs (nominal, degraded, critical) for a dynamic agent.

    Args:
        agent_id: The agent identifier.
        channel_id: The APS channel ID (e.g., "K8").

    Returns:
        List of 3 ThetaConfig objects.
    """
    return [
        ThetaConfig(
            theta_id=f"theta_{channel_id}_nominal",
            channel_id=channel_id,
            level=0,
            partition_id=f"theta_{channel_id}_fine",
            model_override=None,
            protocol_level=ProtocolLevel.PASSIVE,
            description=f"Nominal: fine partition, configured model, passive (agent: {agent_id})",
        ),
        ThetaConfig(
            theta_id=f"theta_{channel_id}_degraded",
            channel_id=channel_id,
            level=1,
            partition_id=f"theta_{channel_id}_coarse",
            model_override=None,
            protocol_level=ProtocolLevel.CONFIRM,
            description=f"Degraded: coarse, retry on failure (agent: {agent_id})",
        ),
        ThetaConfig(
            theta_id=f"theta_{channel_id}_critical",
            channel_id=channel_id,
            level=2,
            partition_id=f"theta_{channel_id}_coarse",
            model_override=None,
            protocol_level=ProtocolLevel.CROSSCHECK,
            description=f"Critical: coarse, crosscheck output (agent: {agent_id})",
        ),
    ]


def register_dynamic_agent(agent_id: str, channel_id: str) -> str:
    """Register APS partitions and theta configs for a new dynamic agent.

    Creates fine/coarse partitions, 3 theta configs, and sets nominal
    as the default active theta.

    Args:
        agent_id: The agent identifier.
        channel_id: The APS channel ID for this agent.

    Returns:
        The channel_id used.
    """
    # Generate and register partitions
    fine, coarse = generate_partitions_for_agent(agent_id, channel_id)
    register_partition(fine)
    register_partition(coarse)
    set_active_partition(channel_id, fine.partition_id)

    # Generate and register theta configs
    thetas = generate_thetas_for_agent(agent_id, channel_id)
    for theta in thetas:
        THETA_REGISTRY[theta.theta_id] = theta

    # Set nominal as default
    set_active_theta(channel_id, f"theta_{channel_id}_nominal")

    logger.info(
        "Registered dynamic APS for agent=%s channel=%s (2 partitions, 3 thetas)",
        agent_id,
        channel_id,
    )

    return channel_id


def ensure_dynamic_agent_registered(agent_id: str, channel_id: str) -> None:
    """Ensure a dynamic agent has APS partitions registered.

    Idempotent — does nothing if already registered.
    """
    fine_id = f"theta_{channel_id}_fine"
    try:
        from src.aps.partitions import get_partition
        get_partition(fine_id)
        # Already registered
    except KeyError:
        register_dynamic_agent(agent_id, channel_id)
