"""Tests for dynamic routing — data-driven routing conditions."""

from __future__ import annotations

import pytest
from langgraph.graph import END

from src.dynamic_routing import (
    RoutingCondition,
    build_dynamic_router,
    build_route_map,
    conditions_from_dicts,
)


# ---------------------------------------------------------------------------
# Tests: RoutingCondition.evaluate
# ---------------------------------------------------------------------------


class TestRoutingConditionEvaluate:
    def test_field_equals_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales_marketing")
        assert cond.evaluate({"route_to": "sales_marketing"}) is True

    def test_field_equals_no_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales_marketing")
        assert cond.evaluate({"route_to": "operations"}) is False

    def test_field_equals_missing_field(self):
        cond = RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales_marketing")
        assert cond.evaluate({}) is False

    def test_field_contains_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_contains", field="task_type", value="campaign")
        assert cond.evaluate({"task_type": "full_campaign"}) is True

    def test_field_contains_no_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_contains", field="task_type", value="campaign")
        assert cond.evaluate({"task_type": "order_check"}) is False

    def test_field_in_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_in", field="task_type", value="content_post,full_campaign,product_launch")
        assert cond.evaluate({"task_type": "full_campaign"}) is True

    def test_field_in_no_match(self):
        cond = RoutingCondition(target="sales", condition_type="field_in", field="task_type", value="content_post,full_campaign")
        assert cond.evaluate({"task_type": "order_check"}) is False

    def test_default_always_matches(self):
        cond = RoutingCondition(target="fallback", condition_type="default")
        assert cond.evaluate({}) is True
        assert cond.evaluate({"any": "state"}) is True

    def test_unknown_type_returns_false(self):
        cond = RoutingCondition(target="x", condition_type="unknown_type", field="f", value="v")
        assert cond.evaluate({"f": "v"}) is False


# ---------------------------------------------------------------------------
# Tests: conditions_from_dicts
# ---------------------------------------------------------------------------


class TestConditionsFromDicts:
    def test_parse_conditions(self):
        raw = [
            {"target": "sales", "type": "field_equals", "field": "route_to", "value": "sales"},
            {"target": "ops", "type": "field_contains", "field": "task_type", "value": "order"},
            {"target": "fallback", "type": "default"},
        ]
        conditions = conditions_from_dicts(raw)
        assert len(conditions) == 3
        assert conditions[0].target == "sales"
        assert conditions[0].condition_type == "field_equals"
        assert conditions[1].condition_type == "field_contains"
        assert conditions[2].condition_type == "default"

    def test_missing_type_defaults(self):
        raw = [{"target": "x"}]
        conditions = conditions_from_dicts(raw)
        assert conditions[0].condition_type == "default"


# ---------------------------------------------------------------------------
# Tests: build_dynamic_router
# ---------------------------------------------------------------------------


class TestBuildDynamicRouter:
    def test_routes_to_matching_condition(self):
        conditions = [
            RoutingCondition(target="sales_marketing", condition_type="field_equals", field="route_to", value="sales_marketing"),
            RoutingCondition(target="operations", condition_type="field_equals", field="route_to", value="operations"),
            RoutingCondition(target="error_handler", condition_type="default"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"route_to": "sales_marketing"}) == "sales_marketing"
        assert router({"route_to": "operations"}) == "operations"

    def test_routes_to_default_when_no_match(self):
        conditions = [
            RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales"),
            RoutingCondition(target="fallback", condition_type="default"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"route_to": "unknown"}) == "fallback"

    def test_routes_to_end_when_no_conditions_match(self):
        conditions = [
            RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"route_to": "ops"}) == END

    def test_error_routes_to_error_handler(self):
        conditions = [
            RoutingCondition(target="sales", condition_type="field_equals", field="route_to", value="sales"),
            RoutingCondition(target="error_handler", condition_type="default"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"error": "something broke", "route_to": "sales"}) == "error_handler"

    def test_first_match_wins(self):
        conditions = [
            RoutingCondition(target="first", condition_type="field_equals", field="x", value="1"),
            RoutingCondition(target="second", condition_type="field_equals", field="x", value="1"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"x": "1"}) == "first"

    def test_field_in_routing(self):
        conditions = [
            RoutingCondition(target="sales", condition_type="field_in", field="task_type", value="content_post,full_campaign,product_launch"),
            RoutingCondition(target="ops", condition_type="field_in", field="task_type", value="order_check,inventory_sync"),
            RoutingCondition(target="revenue", condition_type="field_in", field="task_type", value="revenue_report,pricing_review"),
        ]
        router = build_dynamic_router(conditions)

        assert router({"task_type": "full_campaign"}) == "sales"
        assert router({"task_type": "inventory_sync"}) == "ops"
        assert router({"task_type": "revenue_report"}) == "revenue"


# ---------------------------------------------------------------------------
# Tests: build_route_map
# ---------------------------------------------------------------------------


class TestBuildRouteMap:
    def test_basic_map(self):
        conditions = [
            RoutingCondition(target="a", condition_type="default"),
            RoutingCondition(target="b", condition_type="default"),
        ]
        mapping = build_route_map(conditions)
        assert mapping["a"] == "a"
        assert mapping["b"] == "b"
        assert mapping[END] == END

    def test_deduplicates_targets(self):
        conditions = [
            RoutingCondition(target="a", condition_type="field_equals", field="x", value="1"),
            RoutingCondition(target="a", condition_type="field_equals", field="x", value="2"),
        ]
        mapping = build_route_map(conditions)
        assert len([k for k in mapping if k != END]) == 1
