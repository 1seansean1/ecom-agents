"""Master LangGraph StateGraph: orchestrates all agents and routing.

Includes:
- Input guardrails (validate before orchestrator)
- Output guardrails (sanitize before END)
- Execution budget enforcement (per-invocation limits)
- Loop detection
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

from src.agent_registry import AgentConfigRegistry, get_registry
from src.agents.orchestrator import build_orchestrator_node
from src.agents.operations import build_operations_node
from src.agents.revenue import build_revenue_node
from src.agents.sage import build_sage_node
from src.agents.sales_marketing import build_sales_marketing_node
from src.agents.sub_agents import build_sub_agent_subgraph
from src.aps.instrument import instrument_node
from src.execution_limits import BudgetTracker, ExecutionBudget, LoopDetector
from src.guardrails.input_validator import validate_input, wrap_user_input
from src.guardrails.output_validator import validate_output
from src.llm.config import ModelID
from src.llm.router import LLMRouter
from src.state import AgentState

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _input_guardrail(state: AgentState) -> dict:
    """Validate input before processing. Blocks prompt injection attempts."""
    messages = state.get("messages", [])
    if not messages:
        return {"_guardrail_blocked": False}

    last_msg = messages[-1]
    text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    result = validate_input(text)

    if not result.safe:
        logger.warning("Input guardrail blocked: flags=%s", result.flags)
        return {
            "_guardrail_blocked": True,
            "_input_validation": {"safe": False, "flags": result.flags},
            "messages": [
                AIMessage(
                    content="I cannot process this request. It was flagged by our safety system: "
                    + ", ".join(result.flags)
                )
            ],
        }

    # Wrap user input to prevent injection (only for human messages)
    if isinstance(last_msg, HumanMessage) and result.flags:
        logger.info("Input guardrail: PII detected but safe, flags=%s", result.flags)

    return {
        "_guardrail_blocked": False,
        "_input_validation": {"safe": True, "flags": result.flags},
    }


def _route_from_guardrail(state: AgentState) -> str:
    """Route from input guardrail: block or continue to orchestrator."""
    if state.get("_guardrail_blocked"):
        return END
    return "orchestrator"


def _output_guardrail(state: AgentState) -> dict:
    """Sanitize output before delivery. Redacts secrets and PII."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    if not hasattr(last_msg, "content"):
        return {}

    result = validate_output(last_msg.content)
    if result.redacted_count > 0:
        logger.warning(
            "Output guardrail: redacted %d items, flags=%s",
            result.redacted_count,
            result.flags,
        )
        return {
            "messages": [AIMessage(content=result.sanitized)],
        }

    return {}


def _route_from_orchestrator(state: AgentState) -> str:
    """Route from orchestrator to the target agent."""
    # Budget check
    if state.get("_budget_exhausted"):
        return END

    route = state.get("route_to", "")
    if state.get("error"):
        return "error_handler"
    if route == "sales_marketing":
        return "sales_marketing"
    elif route == "operations":
        return "operations"
    elif route == "revenue_analytics":
        return "revenue_analytics"
    elif route == "sage":
        return "sage"
    return "error_handler"


def _route_from_sales(state: AgentState) -> str:
    """Route from sales: to sub-agents if needed, otherwise output guardrail."""
    if state.get("should_spawn_sub_agents"):
        return "sub_agents"
    return "output_guardrail"


def _error_handler(state: AgentState) -> dict:
    """Handle errors with retry logic."""
    retry_count = state.get("retry_count", 0)
    error = state.get("error", "Unknown error")

    if retry_count < MAX_RETRIES:
        logger.warning("Retrying (attempt %d/%d): %s", retry_count + 1, MAX_RETRIES, error)
        return {
            "retry_count": retry_count + 1,
            "error": "",
            "current_agent": "error_handler",
        }

    logger.error("Max retries exceeded: %s", error)
    return {
        "current_agent": "error_handler",
        "messages": [
            AIMessage(
                content=f"Task failed after {MAX_RETRIES} retries: {error}"
            )
        ],
    }


def _route_from_error(state: AgentState) -> str:
    """Route from error handler: retry or END."""
    if state.get("retry_count", 0) < MAX_RETRIES and not state.get("error"):
        return "orchestrator"
    return "output_guardrail"


def build_graph(router: LLMRouter) -> StateGraph:
    """Build the master agent graph.

    Flow:
    START -> input_guardrail -> orchestrator -> {sales, ops, revenue, sage}
    sales -> sub_agents (conditional) -> output_guardrail -> END
    operations -> output_guardrail -> END
    revenue -> output_guardrail -> END
    sage -> output_guardrail -> END
    error_handler -> orchestrator (retry) or output_guardrail -> END
    """
    registry = get_registry()
    graph = StateGraph(AgentState)

    # Guardrail nodes
    graph.add_node("input_guardrail", _input_guardrail)
    graph.add_node("output_guardrail", _output_guardrail)

    # Agent nodes (APS-instrumented)
    graph.add_node("orchestrator", instrument_node("K1", ModelID.OLLAMA_QWEN, build_orchestrator_node(router, registry)))
    graph.add_node("sales_marketing", instrument_node("K2", ModelID.GPT4O, build_sales_marketing_node(router, registry)))
    graph.add_node("operations", instrument_node("K3", ModelID.GPT4O_MINI, build_operations_node(router, registry)))
    graph.add_node("revenue_analytics", instrument_node("K4", ModelID.CLAUDE_OPUS, build_revenue_node(router, registry)))
    graph.add_node("sage", instrument_node("K8", ModelID.CLAUDE_OPUS, build_sage_node(router, registry)))
    graph.add_node("error_handler", _error_handler)

    # Sub-agent subgraph
    sub_graph = build_sub_agent_subgraph(router, registry)
    graph.add_node("sub_agents", sub_graph.compile())

    # Entry point: input guardrail
    graph.set_entry_point("input_guardrail")

    # Input guardrail -> orchestrator or END
    graph.add_conditional_edges(
        "input_guardrail",
        _route_from_guardrail,
        {
            "orchestrator": "orchestrator",
            END: END,
        },
    )

    # Orchestrator -> target agent
    graph.add_conditional_edges(
        "orchestrator",
        _route_from_orchestrator,
        {
            "sales_marketing": "sales_marketing",
            "operations": "operations",
            "revenue_analytics": "revenue_analytics",
            "sage": "sage",
            "error_handler": "error_handler",
            END: END,
        },
    )

    # Sales -> sub-agents or output guardrail
    graph.add_conditional_edges(
        "sales_marketing",
        _route_from_sales,
        {
            "sub_agents": "sub_agents",
            "output_guardrail": "output_guardrail",
        },
    )

    graph.add_edge("sub_agents", "output_guardrail")
    graph.add_edge("operations", "output_guardrail")
    graph.add_edge("revenue_analytics", "output_guardrail")
    graph.add_edge("sage", "output_guardrail")

    # Error handler -> retry or output guardrail
    graph.add_conditional_edges(
        "error_handler",
        _route_from_error,
        {
            "orchestrator": "orchestrator",
            "output_guardrail": "output_guardrail",
        },
    )

    # Output guardrail -> END
    graph.add_edge("output_guardrail", END)

    return graph
