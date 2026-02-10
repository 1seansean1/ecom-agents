"""Workflow Compiler: converts a WorkflowDefinition JSON into a LangGraph StateGraph.

Given a workflow definition with nodes and edges, this module:
1. Creates a StateGraph(AgentState)
2. Adds dynamic nodes (wrapped with APS instrument_node)
3. Adds direct and conditional edges with dynamic routers
4. Sets the entry point
5. Caches compiled graphs by (workflow_id, version)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from src.agent_registry import AgentConfigRegistry, get_registry
from src.agents.orchestrator import build_orchestrator_node
from src.agents.operations import build_operations_node
from src.agents.revenue import build_revenue_node
from src.agents.sales_marketing import build_sales_marketing_node
from src.agents.sub_agents import build_sub_agent_subgraph
from src.aps.dynamic_partitions import ensure_dynamic_agent_registered
from src.aps.instrument import instrument_node
from src.dynamic_executor import build_dynamic_node
from src.dynamic_routing import (
    RoutingCondition,
    build_dynamic_router,
    build_route_map,
    conditions_from_dicts,
)
from src.graph import MAX_RETRIES, _error_handler
from src.llm.config import ModelID
from src.llm.router import LLMRouter
from src.state import AgentState
from src.tool_registry import ToolRegistry, get_tool_registry
from src.workflow_registry import WorkflowDefinition, WorkflowNodeDef

logger = logging.getLogger(__name__)

# Compiled graph cache: (workflow_id, version) -> StateGraph
_compiled_cache: dict[tuple[str, int], StateGraph] = {}

# Built-in agent node builders (for the default workflow's hardcoded agents)
_BUILTIN_NODE_BUILDERS = {
    "orchestrator",
    "sales_marketing",
    "operations",
    "revenue",
    "error_handler",
    "sub_agents",
}

# Map agent_id to its APS channel_id and ModelID
_BUILTIN_CHANNEL_MAP: dict[str, tuple[str, ModelID]] = {
    "orchestrator": ("K1", ModelID.OLLAMA_QWEN),
    "sales_marketing": ("K2", ModelID.GPT4O),
    "operations": ("K3", ModelID.GPT4O_MINI),
    "revenue": ("K4", ModelID.CLAUDE_OPUS),
}


def _build_builtin_node(
    node_def: WorkflowNodeDef,
    router: LLMRouter,
    registry: AgentConfigRegistry,
) -> Any:
    """Build a builtin agent node using the original builder functions."""
    agent_id = node_def.agent_id

    if agent_id == "orchestrator":
        channel, model = _BUILTIN_CHANNEL_MAP["orchestrator"]
        return instrument_node(channel, model, build_orchestrator_node(router, registry))

    if agent_id == "sales_marketing":
        channel, model = _BUILTIN_CHANNEL_MAP["sales_marketing"]
        return instrument_node(channel, model, build_sales_marketing_node(router, registry))

    if agent_id == "operations":
        channel, model = _BUILTIN_CHANNEL_MAP["operations"]
        return instrument_node(channel, model, build_operations_node(router, registry))

    if agent_id == "revenue":
        channel, model = _BUILTIN_CHANNEL_MAP["revenue"]
        return instrument_node(channel, model, build_revenue_node(router, registry))

    if agent_id == "error_handler":
        return _error_handler

    if agent_id == "sub_agents":
        return build_sub_agent_subgraph(router, registry).compile()

    raise ValueError(f"Unknown builtin agent: {agent_id}")


def _build_dynamic_node_instrumented(
    node_def: WorkflowNodeDef,
    router: LLMRouter,
    registry: AgentConfigRegistry,
    tool_registry: ToolRegistry,
) -> Any:
    """Build a dynamic agent node wrapped with APS instrumentation."""
    agent_id = node_def.agent_id

    # Get agent config to determine channel_id and model
    config = registry.get(agent_id)
    channel_id = config.channel_id
    model_id = ModelID(config.model_id)

    # Ensure APS partitions exist for this dynamic agent
    ensure_dynamic_agent_registered(agent_id, channel_id)

    # Build the dynamic node
    raw_node = build_dynamic_node(agent_id, registry, router, tool_registry)

    # Wrap with APS instrumentation
    return instrument_node(channel_id, model_id, raw_node)


def compile_workflow(
    definition: WorkflowDefinition,
    router: LLMRouter,
    version: int = 1,
    use_cache: bool = True,
) -> StateGraph:
    """Compile a WorkflowDefinition into a LangGraph StateGraph.

    Args:
        definition: The workflow definition to compile.
        router: LLM router for model access.
        version: Workflow version for cache key.
        use_cache: Whether to use the compiled graph cache.

    Returns:
        A compiled StateGraph ready for .compile().invoke().
    """
    cache_key = (definition.workflow_id, version)
    if use_cache and cache_key in _compiled_cache:
        return _compiled_cache[cache_key]

    registry = get_registry()
    tool_registry = get_tool_registry()
    graph = StateGraph(AgentState)

    # Map node_id -> node_def for edge resolution
    node_map: dict[str, WorkflowNodeDef] = {}
    entry_point: str | None = None

    # Add nodes
    for node_def in definition.nodes:
        node_map[node_def.node_id] = node_def

        if node_def.is_entry_point:
            entry_point = node_def.node_id

        # Build the node function
        if node_def.agent_id in _BUILTIN_NODE_BUILDERS:
            node_fn = _build_builtin_node(node_def, router, registry)
        else:
            node_fn = _build_dynamic_node_instrumented(
                node_def, router, registry, tool_registry
            )

        graph.add_node(node_def.node_id, node_fn)

    # Set entry point
    if not entry_point:
        # Fallback: use first node
        entry_point = definition.nodes[0].node_id if definition.nodes else None

    if entry_point:
        graph.set_entry_point(entry_point)

    # Group edges by source node to merge conditional edges
    edges_by_source: dict[str, list] = {}
    for edge in definition.edges:
        edges_by_source.setdefault(edge.source_node_id, []).append(edge)

    # Add edges
    for source_id, edges in edges_by_source.items():
        # Check if any edge is conditional
        conditional_edges = [e for e in edges if e.edge_type == "conditional" and e.conditions]
        direct_edges = [e for e in edges if e.edge_type == "direct"]

        if conditional_edges:
            # Merge all conditions from conditional edges for this source
            all_conditions: list[RoutingCondition] = []
            for edge in conditional_edges:
                all_conditions.extend(conditions_from_dicts(edge.conditions))

            router_fn = build_dynamic_router(all_conditions)
            route_map = build_route_map(all_conditions)

            graph.add_conditional_edges(source_id, router_fn, route_map)
        elif direct_edges:
            # Simple direct edge(s)
            for edge in direct_edges:
                target = edge.target_node_id
                if target == "__end__":
                    graph.add_edge(source_id, END)
                else:
                    graph.add_edge(source_id, target)

    # Cache the compiled graph
    if use_cache:
        _compiled_cache[cache_key] = graph

    logger.info(
        "Compiled workflow %s v%d (%d nodes, %d edges)",
        definition.workflow_id,
        version,
        len(definition.nodes),
        len(definition.edges),
    )

    return graph


def invalidate_cache(workflow_id: str | None = None) -> None:
    """Invalidate compiled graph cache.

    Args:
        workflow_id: If provided, only invalidate entries for this workflow.
                     If None, clear the entire cache.
    """
    if workflow_id is None:
        _compiled_cache.clear()
    else:
        keys_to_remove = [k for k in _compiled_cache if k[0] == workflow_id]
        for k in keys_to_remove:
            del _compiled_cache[k]


def validate_workflow(definition: WorkflowDefinition) -> list[str]:
    """Validate a workflow definition without compiling.

    Returns a list of error messages (empty if valid).
    """
    errors = []

    if not definition.nodes:
        errors.append("Workflow must have at least one node")
        return errors

    # Check entry point
    entry_points = [n for n in definition.nodes if n.is_entry_point]
    if len(entry_points) == 0:
        errors.append("Workflow must have exactly one entry point")
    elif len(entry_points) > 1:
        errors.append(f"Workflow has {len(entry_points)} entry points, expected 1")

    # Check all node_ids are unique
    node_ids = [n.node_id for n in definition.nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("Duplicate node IDs found")

    # Check edge references
    valid_nodes = set(node_ids) | {"__end__"}
    for edge in definition.edges:
        if edge.source_node_id not in node_ids:
            errors.append(f"Edge {edge.edge_id} references unknown source: {edge.source_node_id}")
        if edge.target_node_id not in valid_nodes:
            errors.append(f"Edge {edge.edge_id} references unknown target: {edge.target_node_id}")

        # Validate conditional edges have conditions
        if edge.edge_type == "conditional" and not edge.conditions:
            errors.append(f"Conditional edge {edge.edge_id} has no conditions")

        # Validate condition targets exist
        if edge.conditions:
            for cond in edge.conditions:
                target = cond.get("target", "")
                if target and target not in valid_nodes:
                    errors.append(
                        f"Edge {edge.edge_id} condition targets unknown node: {target}"
                    )

    return errors
