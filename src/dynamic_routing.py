"""Dynamic Routing: data-driven routing conditions for workflow edges.

Supports conditional edges in user-defined workflows. Each condition
evaluates against the AgentState dict to determine which target node
to route to.

Condition types:
    - field_equals:   state[field] == value
    - field_contains: value in str(state[field])
    - field_in:       state[field] in value (comma-separated list)
    - default:        always matches (fallback route)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class RoutingCondition:
    """A single routing condition for a conditional edge."""

    target: str
    condition_type: str  # field_equals | field_contains | field_in | default
    field: str = ""
    value: str = ""

    def evaluate(self, state: dict[str, Any]) -> bool:
        """Evaluate this condition against the given state."""
        if self.condition_type == "default":
            return True

        field_value = state.get(self.field)
        if field_value is None:
            return False

        if self.condition_type == "field_equals":
            return str(field_value) == self.value

        if self.condition_type == "field_contains":
            return self.value in str(field_value)

        if self.condition_type == "field_in":
            allowed = [v.strip() for v in self.value.split(",")]
            return str(field_value) in allowed

        logger.warning("Unknown condition type: %s", self.condition_type)
        return False


@dataclass
class RoutingRule:
    """A complete routing rule: ordered list of conditions for one edge source."""

    source_node: str
    conditions: list[RoutingCondition] = field(default_factory=list)
    default_target: str = ""


def conditions_from_dicts(raw: list[dict[str, Any]]) -> list[RoutingCondition]:
    """Parse routing conditions from JSON-serializable dicts.

    Expected format per condition:
        {"target": "agent_id", "type": "field_equals", "field": "route_to", "value": "sales"}
    """
    conditions = []
    for d in raw:
        conditions.append(
            RoutingCondition(
                target=d["target"],
                condition_type=d.get("type", "default"),
                field=d.get("field", ""),
                value=d.get("value", ""),
            )
        )
    return conditions


def build_dynamic_router(
    conditions: list[RoutingCondition],
) -> Callable[[dict[str, Any]], str]:
    """Build a routing function from a list of conditions.

    The returned function evaluates conditions in order and returns the
    target of the first matching condition. If no condition matches,
    returns END.

    Returns:
        A callable(state) -> str suitable for StateGraph.add_conditional_edges().
    """
    from langgraph.graph import END

    def router(state: dict[str, Any]) -> str:
        # Check for errors first
        if state.get("error"):
            # Look for an error_handler target in conditions
            for cond in conditions:
                if cond.target == "error_handler":
                    return "error_handler"

        for cond in conditions:
            if cond.evaluate(state):
                logger.debug(
                    "Route matched: %s (type=%s, field=%s, value=%s)",
                    cond.target,
                    cond.condition_type,
                    cond.field,
                    cond.value,
                )
                return cond.target

        logger.warning("No routing condition matched, ending workflow")
        return END

    return router


def build_route_map(conditions: list[RoutingCondition]) -> dict[str, str]:
    """Build the target mapping dict for add_conditional_edges().

    Returns a dict like {"sales_marketing": "sales_marketing", "operations": "operations"}
    needed as the third argument to StateGraph.add_conditional_edges().
    """
    from langgraph.graph import END

    mapping: dict[str, str] = {}
    for cond in conditions:
        mapping[cond.target] = cond.target
    # Always include END as a possible route
    mapping[END] = END
    return mapping
