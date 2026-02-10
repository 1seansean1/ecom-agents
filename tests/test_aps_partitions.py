"""Tests for APS partition schemes and classification functions."""

from __future__ import annotations

import pytest

from src.aps.partitions import (
    PartitionScheme,
    _PARTITION_REGISTRY,
    _k1_coarse_classify_input,
    _k1_coarse_classify_output,
    _k1_fine_classify_input,
    _k1_fine_classify_output,
    _k2_coarse_classify_output,
    _k2_fine_classify_input,
    _k2_fine_classify_output,
    _k3_coarse_classify_output,
    _k3_fine_classify_input,
    _k3_fine_classify_output,
    _k4_fine_classify_input,
    _k4_fine_classify_output,
    _k5_fine_classify_input,
    _k5_fine_classify_output,
    _k6_fine_classify_input,
    _k6_fine_classify_output,
    _k7_coarse_classify_input,
    _k7_fine_classify_input,
    _k7_fine_classify_output,
    get_active_partition,
    get_partition,
    register_all_partitions,
    set_active_partition,
)


@pytest.fixture(autouse=True)
def setup_partitions():
    """Ensure partitions are registered for each test."""
    _PARTITION_REGISTRY.clear()
    register_all_partitions()


class TestRegistration:
    def test_14_partitions_registered(self):
        assert len(_PARTITION_REGISTRY) == 14

    def test_all_channels_have_fine_and_coarse(self):
        for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
            assert f"theta_{ch}_fine" in _PARTITION_REGISTRY
            assert f"theta_{ch}_coarse" in _PARTITION_REGISTRY

    def test_active_defaults_to_fine(self):
        for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
            p = get_active_partition(ch)
            assert p.granularity == "fine"

    def test_set_active_partition(self):
        set_active_partition("K1", "theta_K1_coarse")
        p = get_active_partition("K1")
        assert p.granularity == "coarse"

    def test_partition_has_c1_c3_metadata(self):
        p = get_partition("theta_K1_fine")
        assert p.field_rule != ""
        assert p.intervention_story != ""
        assert p.locality_owner != ""


class TestK1Classification:
    def _make_state(self, content: str, payload: dict | None = None):
        from langchain_core.messages import HumanMessage
        return {
            "messages": [HumanMessage(content=content)],
            "trigger_payload": payload or {},
        }

    def test_order_check_fine(self):
        state = self._make_state("Check for new orders and fulfillments")
        assert _k1_fine_classify_input(state) == "order_check"

    def test_instagram_post_fine(self):
        state = self._make_state("Create an Instagram post")
        assert _k1_fine_classify_input(state) == "content_post"

    def test_revenue_report_fine(self):
        state = self._make_state("Generate daily revenue report")
        assert _k1_fine_classify_input(state) == "revenue_report"

    def test_campaign_fine(self):
        state = self._make_state("Plan weekly marketing campaign")
        assert _k1_fine_classify_input(state) == "full_campaign"

    def test_coarse_maps_correctly(self):
        state = self._make_state("Check for new orders")
        assert _k1_coarse_classify_input(state) == "ops_task"

        state = self._make_state("Create an Instagram post")
        assert _k1_coarse_classify_input(state) == "sales_task"

        state = self._make_state("Generate revenue report")
        assert _k1_coarse_classify_input(state) == "analytics_task"

    def test_output_error(self):
        result = {"route_to": "error_handler", "task_type": ""}
        assert _k1_fine_classify_output(result) == "error"

    def test_output_normal(self):
        result = {"task_type": "order_check", "route_to": "operations"}
        assert _k1_fine_classify_output(result) == "order_check"

    def test_coarse_output_routes(self):
        assert _k1_coarse_classify_output({"route_to": "sales_marketing"}) == "sales_marketing"
        assert _k1_coarse_classify_output({"route_to": "operations"}) == "operations"
        assert _k1_coarse_classify_output({"route_to": "revenue_analytics"}) == "revenue_analytics"
        assert _k1_coarse_classify_output({"route_to": "error_handler"}) == "error"


class TestK2Classification:
    def test_simple_post(self):
        state = {"task_type": "content_post", "task_complexity": "simple"}
        assert _k2_fine_classify_input(state) == "simple_post"

    def test_campaign_delegated(self):
        state = {"task_type": "full_campaign", "task_complexity": "complex"}
        assert _k2_fine_classify_input(state) == "campaign_delegated"

    def test_output_with_error(self):
        assert _k2_fine_classify_output({"error": "fail"}) == "error"

    def test_output_delegated(self):
        assert _k2_fine_classify_output({"should_spawn_sub_agents": True}) == "delegated"

    def test_output_json(self):
        assert _k2_fine_classify_output(
            {"sales_result": {"caption": "test", "status": "ok"}}
        ) == "completed_json"

    def test_coarse_success_failure(self):
        assert _k2_coarse_classify_output({}) == "success"
        assert _k2_coarse_classify_output({"error": "fail"}) == "failure"


class TestK3Classification:
    def test_order_check(self):
        assert _k3_fine_classify_input({"task_type": "order_check"}) == "order_check"

    def test_output_error(self):
        assert _k3_fine_classify_output({"error": "something"}) == "error"

    def test_output_completed(self):
        assert _k3_fine_classify_output(
            {"operations_result": {"status": "ok"}}
        ) == "completed"

    def test_output_malformed(self):
        assert _k3_fine_classify_output({"operations_result": "string"}) == "malformed"

    def test_coarse_output(self):
        assert _k3_coarse_classify_output({}) == "success"
        assert _k3_coarse_classify_output({"error": "fail"}) == "failure"


class TestK4Classification:
    def test_revenue_vs_pricing(self):
        assert _k4_fine_classify_input({"task_type": "revenue_report"}) == "revenue_report"
        assert _k4_fine_classify_input({"task_type": "pricing_review"}) == "pricing_review"

    def test_output_revenue_levels(self):
        assert _k4_fine_classify_output(
            {"revenue_result": {"summary": "high growth"}}
        ) == "daily_rev_high"
        assert _k4_fine_classify_output(
            {"revenue_result": {"summary": "decline in sales"}}
        ) == "daily_rev_low"

    def test_output_error(self):
        assert _k4_fine_classify_output({"error": "fail"}) == "error"


class TestK5K6Classification:
    def test_k5_product_brief(self):
        state = {"trigger_payload": {"task": "product launch"}}
        assert _k5_fine_classify_input(state) == "product_brief"

    def test_k5_campaign_brief(self):
        state = {"trigger_payload": {"task": "weekly campaign"}}
        assert _k5_fine_classify_input(state) == "campaign_brief"

    def test_k5_output_json_with_caption(self):
        result = {"sub_agent_results": {"content_writer": {"caption": "Hello!"}}}
        assert _k5_fine_classify_output(result) == "json_with_caption"

    def test_k6_full_results(self):
        state = {"sub_agent_results": {
            "content_writer": {}, "image_selector": {}, "hashtag_optimizer": {}
        }}
        assert _k6_fine_classify_input(state) == "full_results"

    def test_k6_partial_results(self):
        state = {"sub_agent_results": {"content_writer": {}}}
        assert _k6_fine_classify_input(state) == "partial_results"

    def test_k6_high_engagement(self):
        result = {"sub_agent_results": {"campaign_analyzer": {
            "expected_engagement_rate": "7.5%"
        }}}
        assert _k6_fine_classify_output(result) == "high_engagement"


class TestK7Classification:
    def test_known_tool(self):
        assert _k7_fine_classify_input({"tool_name": "shopify_query_products"}) == "shopify_query_products"

    def test_unknown_tool(self):
        assert _k7_fine_classify_input({"tool_name": "mystery_tool"}) == "unknown"

    def test_coarse_groups(self):
        assert _k7_coarse_classify_input({"tool_name": "stripe_revenue_query"}) == "stripe"
        assert _k7_coarse_classify_input({"tool_name": "printful_catalog"}) == "printful"

    def test_output_success(self):
        assert _k7_fine_classify_output({"data": {"id": 1}}) == "success_data"
        assert _k7_fine_classify_output({"data": None}) == "success_empty"

    def test_output_errors(self):
        assert _k7_fine_classify_output({"error": "timeout occurred"}) == "timeout"
        assert _k7_fine_classify_output({"error": "401 unauthorized"}) == "auth_error"
        assert _k7_fine_classify_output({"error": "429 rate limit"}) == "rate_limited"
        assert _k7_fine_classify_output({"error": "500 server error"}) == "http_error"
