"""Per-agent tool permission scoping (least-privilege access).

Enforces which tools each agent is allowed to call:
- Orchestrator: no mutation tools (read-only routing)
- Sales/Marketing: Shopify read + Instagram write
- Operations: Shopify read/write + Printful read
- Revenue: Stripe read only
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Map agent_id -> set of allowed tool names
AGENT_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "orchestrator": set(),  # Orchestrator has no direct tools
    "sales_marketing": {
        "shopify_query_products",
        "shopify_query_orders",
        "instagram_publish_post",
        "instagram_get_insights",
    },
    "operations": {
        "shopify_query_products",
        "shopify_query_orders",
        "shopify_create_product",
        "printful_list_catalog",
        "printful_list_products",
        "printful_get_store_products",
        "printful_order_status",
    },
    "revenue": {
        "stripe_list_products",
        "stripe_revenue_query",
    },
    "content_writer": {
        "shopify_query_products",
        "instagram_get_insights",
    },
    "campaign_analyzer": {
        "shopify_query_products",
        "shopify_query_orders",
        "stripe_revenue_query",
        "instagram_get_insights",
    },
}


def get_allowed_tools(agent_id: str) -> set[str]:
    """Get the set of tool names an agent is allowed to use."""
    return AGENT_TOOL_ALLOWLIST.get(agent_id, set())


def is_tool_allowed(agent_id: str, tool_name: str) -> bool:
    """Check if a specific tool is allowed for an agent."""
    allowed = AGENT_TOOL_ALLOWLIST.get(agent_id)
    if allowed is None:
        # Unknown agent — allow all tools (permissive for custom agents)
        return True
    return tool_name in allowed


def filter_tools_for_agent(agent_id: str, tools: list) -> list:
    """Filter a list of LangChain tools to only those allowed for an agent.

    Args:
        agent_id: The agent requesting tools.
        tools: List of LangChain BaseTool instances.

    Returns:
        Filtered list containing only permitted tools.
    """
    allowed = AGENT_TOOL_ALLOWLIST.get(agent_id)
    if allowed is None:
        return tools  # Unknown agent — return all

    filtered = [t for t in tools if t.name in allowed]
    denied = [t.name for t in tools if t.name not in allowed]
    if denied:
        logger.info(
            "Tool permission: agent=%s denied=%s allowed=%d",
            agent_id,
            denied,
            len(filtered),
        )
    return filtered
