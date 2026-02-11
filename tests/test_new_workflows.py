"""Tests for new workflows, tools, and features.

Covers:
- Shopify content scoring (shopify_content.py)
- Signal generator workflow (signal_generator.py)
- Revenue engine workflow (revenue_engine.py)
- LLM cost config (cost_config.py)
- Enneagram personality system (enneagram.py)
- Holly epsilon tuning + workflow tools (tools.py)
- Workflow registry additions (workflow_registry.py)
- Scheduler job registration (autonomous.py)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# Shopify Content Scoring
# =========================================================================


class TestScoreDescription:
    """Tests for src.tools.shopify_content.score_description."""

    def test_empty_text_returns_zeros(self):
        from src.tools.shopify_content import score_description
        result = score_description("")
        assert result["composite"] == 0
        assert result["word_count"] == 0

    def test_none_text_returns_zeros(self):
        from src.tools.shopify_content import score_description
        result = score_description(None)
        assert result["composite"] == 0

    def test_short_text_low_length_score(self):
        from src.tools.shopify_content import score_description
        result = score_description("Short text")
        assert result["length"] < 1.0
        assert result["word_count"] == 2

    def test_ideal_length_text(self):
        from src.tools.shopify_content import score_description
        words = " ".join(["word"] * 80)
        result = score_description(words)
        assert result["length"] == 1.0
        assert result["word_count"] == 80

    def test_long_text_penalized(self):
        from src.tools.shopify_content import score_description
        words = " ".join(["word"] * 400)
        result = score_description(words)
        assert result["length"] < 1.0

    def test_html_structure_bonus(self):
        from src.tools.shopify_content import score_description
        plain = "This is a plain description about our quality product"
        html = "<p>This is a <strong>quality</strong> product</p><ul><li>Premium materials</li></ul>"
        score_plain = score_description(plain)
        score_html = score_description(html)
        assert score_html["structure"] >= score_plain["structure"]

    def test_keyword_density_scoring(self):
        from src.tools.shopify_content import score_description
        # No keywords
        no_kw = "The quick brown fox jumps over the lazy dog " * 5
        # Has keywords
        has_kw = "This premium quality handcrafted unique perfect gift " * 5
        score_no = score_description(no_kw)
        score_has = score_description(has_kw)
        assert score_has["keyword_density"] > score_no["keyword_density"]

    def test_composite_is_weighted_sum(self):
        from src.tools.shopify_content import score_description
        text = "<p>A quality premium product that is unique and perfect as a gift.</p>"
        result = score_description(text)
        expected = (
            result["readability"] * 30
            + result["length"] * 30
            + result["keyword_density"] * 20
            + result["structure"] * 20
        )
        assert abs(result["composite"] - expected) < 0.5

    def test_custom_keywords(self):
        from src.tools.shopify_content import score_description
        text = "Our sustainable eco-friendly organic product is green and natural."
        result = score_description(text, keywords=["sustainable", "eco-friendly", "organic", "green", "natural"])
        assert result["keyword_density"] > 0

    def test_flesch_reading_ease_in_range(self):
        from src.tools.shopify_content import score_description
        result = score_description("Simple short words are easy to read. This is fun.")
        assert 0 <= result["flesch"] <= 100

    def test_kd_pct_in_result(self):
        from src.tools.shopify_content import score_description
        result = score_description("A quality premium gift.")
        assert "kd_pct" in result
        assert isinstance(result["kd_pct"], float)


# =========================================================================
# LLM Cost Config
# =========================================================================


class TestCostConfig:
    """Tests for src.llm.cost_config."""

    def test_model_costs_populated(self):
        from src.llm.cost_config import MODEL_COSTS
        assert "gpt-4o-mini" in MODEL_COSTS
        assert "claude-opus-4-6" in MODEL_COSTS
        assert len(MODEL_COSTS) >= 6

    def test_model_cost_pricing(self):
        from src.llm.cost_config import MODEL_COSTS
        mini = MODEL_COSTS["gpt-4o-mini"]
        assert mini.input_per_1m == 0.15
        assert mini.output_per_1m == 0.60
        assert not mini.is_local

    def test_local_models_are_free(self):
        from src.llm.cost_config import MODEL_COSTS
        qwen = MODEL_COSTS["qwen2.5:3b"]
        assert qwen.is_local
        assert qwen.input_per_1m == 0.0
        assert qwen.output_per_1m == 0.0

    def test_estimate_cost(self):
        from src.llm.cost_config import estimate_cost
        # GPT-4o-mini: $0.15/1M input, $0.60/1M output
        cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
        assert abs(cost - 0.75) < 0.01

    def test_estimate_cost_unknown_model(self):
        from src.llm.cost_config import estimate_cost
        assert estimate_cost("nonexistent-model", 1000, 1000) == 0.0

    def test_get_model_for_task_routing(self):
        from src.llm.cost_config import get_model_for_task
        assert get_model_for_task("classification") == "gpt-4o-mini"
        assert get_model_for_task("strategy") == "claude-opus-4-6"

    def test_get_model_for_task_fallback(self):
        from src.llm.cost_config import get_model_for_task
        assert get_model_for_task("unknown_task_type") == "gpt-4o-mini"

    @patch.dict("os.environ", {"OLLAMA_BASE_URL": ""})
    def test_local_model_fallback_no_ollama(self):
        from src.llm.cost_config import get_model_for_task
        result = get_model_for_task("trivial_routing")
        assert result == "gpt-4o-mini"

    @patch.dict("os.environ", {"OLLAMA_BASE_URL": "http://localhost:11435"})
    def test_local_model_used_with_ollama(self):
        from src.llm.cost_config import get_model_for_task
        result = get_model_for_task("trivial_routing")
        assert result == "qwen2.5:3b"

    def test_track_cost(self):
        from src.llm.cost_config import track_cost, _cost_log, _cost_lock
        initial_len = len(_cost_log)
        cost = track_cost("test_workflow", "gpt-4o-mini", 1000, 500)
        assert cost > 0
        assert len(_cost_log) > initial_len

    def test_get_cost_summary(self):
        from src.llm.cost_config import get_cost_summary
        summary = get_cost_summary()
        assert isinstance(summary, list)
        assert len(summary) >= 6
        # Should be sorted by input cost (cheapest first)
        costs = [m["input_per_1m"] for m in summary]
        assert costs == sorted(costs)

    def test_get_total_cost_by_workflow(self):
        from src.llm.cost_config import get_total_cost_by_workflow, track_cost
        track_cost("test_wf_a", "gpt-4o-mini", 1000, 500)
        totals = get_total_cost_by_workflow()
        assert "test_wf_a" in totals
        assert totals["test_wf_a"] > 0


# =========================================================================
# Enneagram Personality System
# =========================================================================


class TestEnneagram:
    """Tests for src.holly.crew.enneagram."""

    def test_all_nine_types_defined(self):
        from src.holly.crew.enneagram import ENNEAGRAM_TYPES
        assert len(ENNEAGRAM_TYPES) == 9
        for i in range(1, 10):
            assert i in ENNEAGRAM_TYPES

    def test_type_structure(self):
        from src.holly.crew.enneagram import ENNEAGRAM_TYPES
        t = ENNEAGRAM_TYPES[5]
        assert t.name == "Investigator"
        assert t.triad == "thinking"
        assert len(t.voice_traits) >= 3

    def test_triads_correct(self):
        from src.holly.crew.enneagram import ENNEAGRAM_TYPES
        thinking = [t for t in ENNEAGRAM_TYPES.values() if t.triad == "thinking"]
        feeling = [t for t in ENNEAGRAM_TYPES.values() if t.triad == "feeling"]
        gut = [t for t in ENNEAGRAM_TYPES.values() if t.triad == "gut"]
        assert len(thinking) == 3  # 5, 6, 7
        assert len(feeling) == 3   # 2, 3, 4
        assert len(gut) == 3       # 8, 9, 1

    def test_all_crew_agents_mapped(self):
        from src.holly.crew.enneagram import CREW_ENNEAGRAM_MAP
        from src.holly.crew.registry import CREW_AGENTS
        # All mapped agents should exist in registry
        for agent_id in CREW_ENNEAGRAM_MAP:
            assert agent_id in CREW_AGENTS, f"{agent_id} in map but not registry"

    def test_get_crew_type(self):
        from src.holly.crew.enneagram import get_crew_type
        t = get_crew_type("crew_architect")
        assert t is not None
        assert t.number == 5
        assert t.name == "Investigator"

    def test_get_crew_type_unknown(self):
        from src.holly.crew.enneagram import get_crew_type
        assert get_crew_type("nonexistent_agent") is None

    def test_get_coupling_axes(self):
        from src.holly.crew.enneagram import get_coupling_axes
        axes = get_coupling_axes("crew_architect")
        assert len(axes) > 0
        for ax in axes:
            assert "partner" in ax
            assert "axis" in ax
            assert "strength" in ax
            assert "direction" in ax
            assert ax["direction"] in ("synergy", "tension", "mentoring")

    def test_sensitivity_matrix_strength_bounds(self):
        from src.holly.crew.enneagram import SENSITIVITY_MATRIX
        for ca in SENSITIVITY_MATRIX:
            assert 0.0 <= ca.strength <= 1.0
            assert ca.direction in ("synergy", "tension", "mentoring")

    def test_build_enneagram_prompt_section(self):
        from src.holly.crew.enneagram import build_enneagram_prompt_section
        section = build_enneagram_prompt_section("crew_architect")
        assert "Enneagram" in section
        assert "Investigator" in section
        assert "Triad: Thinking" in section
        assert "Team Coupling" in section

    def test_build_enneagram_prompt_section_unknown(self):
        from src.holly.crew.enneagram import build_enneagram_prompt_section
        assert build_enneagram_prompt_section("nonexistent") == ""

    def test_team_balance_report(self):
        from src.holly.crew.enneagram import get_team_balance_report
        report = get_team_balance_report()
        assert "triad_balance" in report
        assert "type_distribution" in report
        assert "total_agents" in report
        assert report["total_agents"] > 0
        # All three triads should be represented
        triads = report["triad_balance"]
        assert triads["thinking"] > 0
        assert triads["feeling"] > 0
        assert triads["gut"] > 0

    def test_apply_enneagram_prompts_idempotent(self):
        """apply_enneagram_prompts should be idempotent."""
        import copy
        from src.holly.crew.registry import CREW_AGENTS, apply_enneagram_prompts

        # Save originals
        originals = {k: copy.deepcopy(v) for k, v in CREW_AGENTS.items()}

        try:
            count1 = apply_enneagram_prompts()
            count2 = apply_enneagram_prompts()
            # Second call should update 0 (already applied)
            assert count2 == 0
        finally:
            # Restore originals
            for k, v in originals.items():
                CREW_AGENTS[k] = v


# =========================================================================
# Signal Generator Workflow
# =========================================================================


class TestSignalGenerator:
    """Tests for src.workflows.signal_generator."""

    @patch("src.workflows.signal_generator._fetch_products")
    def test_no_products_returns_empty(self, mock_fetch):
        from src.workflows.signal_generator import run_signal_generator
        mock_fetch.return_value = []
        result = run_signal_generator()
        assert result["products_analyzed"] == 0
        assert "No products found" in result["errors"][0]

    @patch("src.workflows.signal_generator._store_eval_results")
    @patch("src.workflows.signal_generator._generate_variants")
    @patch("src.workflows.signal_generator._fetch_products")
    def test_products_analyzed(self, mock_fetch, mock_variants, mock_store):
        from src.workflows.signal_generator import run_signal_generator
        mock_fetch.return_value = [
            {"id": "gid://shopify/Product/1", "title": "Test Product",
             "description_html": "<p>A quality premium gift</p>", "price": "29.99"},
        ]
        mock_variants.return_value = []
        result = run_signal_generator()
        assert result["products_analyzed"] == 1
        assert result["variants_generated"] == 0

    @patch("src.workflows.signal_generator._store_eval_results")
    @patch("src.workflows.signal_generator._generate_variants")
    @patch("src.workflows.signal_generator._fetch_products")
    def test_variant_scoring(self, mock_fetch, mock_variants, mock_store):
        from src.workflows.signal_generator import run_signal_generator
        mock_fetch.return_value = [
            {"id": "gid://shopify/Product/1", "title": "Test",
             "description_html": "bad", "price": "10.00"},
        ]
        # Return 3 better descriptions
        mock_variants.return_value = [
            "<p>A quality premium handcrafted unique gift. Perfect for any occasion. "
            "This product is truly special and crafted with care.</p>",
            "<p>Premium quality unique gift, handcrafted with love.</p>",
            "<p>The perfect quality gift. Unique, premium, handcrafted.</p>",
        ]
        result = run_signal_generator()
        assert result["variants_generated"] == 3
        assert len(result["eval_results"]) == 1

    def test_score_description_integration(self):
        """The score_description function works as expected in the pipeline."""
        from src.tools.shopify_content import score_description
        bad = score_description("bad")
        good = score_description(
            "<p>This premium quality handcrafted product is the perfect unique gift. "
            "Made with care and attention to detail. Order yours today!</p>"
        )
        assert good["composite"] > bad["composite"]


# =========================================================================
# Revenue Engine Workflow
# =========================================================================


class TestRevenueEngine:
    """Tests for src.workflows.revenue_engine."""

    def test_audit_product_seo_short_title(self):
        from src.workflows.revenue_engine import _audit_product_seo
        issues = _audit_product_seo({"title": "Hi", "description_html": ""})
        assert any("Title too short" in i for i in issues)

    def test_audit_product_seo_long_title(self):
        from src.workflows.revenue_engine import _audit_product_seo
        issues = _audit_product_seo({
            "title": "x" * 80,
            "description_html": "<p>" + " ".join(["word"] * 150) + "</p>"
        })
        assert any("Title too long" in i for i in issues)

    def test_audit_product_seo_thin_description(self):
        from src.workflows.revenue_engine import _audit_product_seo
        issues = _audit_product_seo({
            "title": "Good Product Title Here",
            "description_html": "Short desc",
        })
        assert any("too thin" in i or "could be richer" in i for i in issues)

    def test_audit_product_seo_missing_structure(self):
        from src.workflows.revenue_engine import _audit_product_seo
        issues = _audit_product_seo({
            "title": "Good Product Title Here",
            "description_html": "Plain text without any HTML tags at all " * 10,
        })
        assert any("No HTML structure" in i for i in issues)

    def test_audit_product_seo_no_cta(self):
        from src.workflows.revenue_engine import _audit_product_seo
        issues = _audit_product_seo({
            "title": "Good Product Title Here",
            "description_html": "<p>" + "This product is nice. " * 20 + "</p>",
        })
        assert any("call-to-action" in i.lower() for i in issues)

    @patch("src.workflows.revenue_engine._fetch_products_for_seo")
    def test_run_revenue_engine_empty(self, mock_fetch):
        from src.workflows.revenue_engine import run_revenue_engine
        mock_fetch.return_value = []
        result = run_revenue_engine()
        assert result["products_analyzed"] == 0


# =========================================================================
# Holly Epsilon Tuning Tools
# =========================================================================


class TestHollyNewTools:
    """Tests for new Holly tools (tune_epsilon, run_workflow, query_crew_enneagram)."""

    def test_tune_epsilon_unknown_action(self):
        from src.holly.tools import tune_epsilon
        result = tune_epsilon(action="invalid")
        assert "error" in result

    @patch("src.aps.revenue_epsilon.get_revenue_epsilon", return_value=0.08)
    @patch("src.aps.financial_health.get_latest_health", return_value=None)
    def test_tune_epsilon_revenue_phase(self, mock_health, mock_epsilon):
        from src.holly.tools import tune_epsilon
        result = tune_epsilon(action="revenue_phase")
        assert "epsilon_r" in result

    def test_tune_epsilon_costs(self):
        from src.holly.tools import tune_epsilon
        result = tune_epsilon(action="costs")
        assert "models" in result
        assert isinstance(result["models"], list)

    def test_tune_epsilon_adjust_no_goal_id(self):
        from src.holly.tools import tune_epsilon
        result = tune_epsilon(action="adjust")
        assert "error" in result
        assert "goal_id" in result["error"]

    def test_tune_epsilon_adjust_bad_epsilon(self):
        from src.holly.tools import tune_epsilon
        result = tune_epsilon(action="adjust", goal_id="test", new_epsilon=1.5)
        assert "error" in result

    def test_run_workflow_unknown(self):
        from src.holly.tools import run_workflow
        result = run_workflow("nonexistent")
        assert "error" in result

    @patch("src.workflows.signal_generator.run_signal_generator")
    def test_run_workflow_signal_generator(self, mock_run):
        from src.holly.tools import run_workflow
        mock_run.return_value = {"products_analyzed": 2}
        result = run_workflow("signal_generator")
        assert result["status"] == "completed"
        mock_run.assert_called_once()

    @patch("src.workflows.revenue_engine.run_revenue_engine")
    def test_run_workflow_revenue_engine(self, mock_run):
        from src.holly.tools import run_workflow
        mock_run.return_value = {"seo_improvements": 1}
        result = run_workflow("revenue_engine")
        assert result["status"] == "completed"

    def test_query_crew_enneagram_team_report(self):
        from src.holly.tools import query_crew_enneagram
        result = query_crew_enneagram()
        assert "triad_balance" in result
        assert "total_agents" in result

    def test_query_crew_enneagram_specific_agent(self):
        from src.holly.tools import query_crew_enneagram
        result = query_crew_enneagram(agent_id="crew_architect")
        assert result["type"] == 5
        assert result["name"] == "Investigator"

    def test_query_crew_enneagram_unknown_agent(self):
        from src.holly.tools import query_crew_enneagram
        result = query_crew_enneagram(agent_id="nonexistent")
        assert "error" in result


# =========================================================================
# Workflow Registry Additions
# =========================================================================


class TestWorkflowRegistryAdditions:
    """Tests for new workflow definitions in workflow_registry.py."""

    def test_signal_generator_workflow_defined(self):
        from src.workflow_registry import SIGNAL_GENERATOR_WORKFLOW
        assert SIGNAL_GENERATOR_WORKFLOW.workflow_id == "signal_generator"
        assert len(SIGNAL_GENERATOR_WORKFLOW.nodes) == 2
        assert len(SIGNAL_GENERATOR_WORKFLOW.edges) == 2

    def test_revenue_engine_workflow_defined(self):
        from src.workflow_registry import REVENUE_ENGINE_WORKFLOW
        assert REVENUE_ENGINE_WORKFLOW.workflow_id == "revenue_engine"
        assert len(REVENUE_ENGINE_WORKFLOW.nodes) == 3
        assert len(REVENUE_ENGINE_WORKFLOW.edges) == 3

    def test_signal_generator_has_entry_point(self):
        from src.workflow_registry import SIGNAL_GENERATOR_WORKFLOW
        entry = [n for n in SIGNAL_GENERATOR_WORKFLOW.nodes if n.is_entry_point]
        assert len(entry) == 1
        assert entry[0].node_id == "orchestrator"

    def test_revenue_engine_has_entry_point(self):
        from src.workflow_registry import REVENUE_ENGINE_WORKFLOW
        entry = [n for n in REVENUE_ENGINE_WORKFLOW.nodes if n.is_entry_point]
        assert len(entry) == 1

    def test_workflow_to_dict_roundtrip(self):
        from src.workflow_registry import SIGNAL_GENERATOR_WORKFLOW, WorkflowDefinition
        d = SIGNAL_GENERATOR_WORKFLOW.to_dict()
        restored = WorkflowDefinition.from_dict(d)
        assert restored.workflow_id == "signal_generator"
        assert len(restored.nodes) == 2


# =========================================================================
# Holly Tool Schema Completeness
# =========================================================================


class TestToolSchemas:
    """Ensure all HOLLY_TOOLS have matching schemas."""

    def test_all_tools_have_schemas(self):
        from src.holly.tools import HOLLY_TOOLS, HOLLY_TOOL_SCHEMAS
        schema_names = {s["name"] for s in HOLLY_TOOL_SCHEMAS}
        for tool_name in HOLLY_TOOLS:
            assert tool_name in schema_names, f"Tool '{tool_name}' has no schema"

    def test_all_schemas_have_tools(self):
        from src.holly.tools import HOLLY_TOOLS, HOLLY_TOOL_SCHEMAS
        for schema in HOLLY_TOOL_SCHEMAS:
            assert schema["name"] in HOLLY_TOOLS, f"Schema '{schema['name']}' has no tool"

    def test_tool_count_matches(self):
        from src.holly.tools import HOLLY_TOOLS, HOLLY_TOOL_SCHEMAS
        assert len(HOLLY_TOOLS) == len(HOLLY_TOOL_SCHEMAS)

    def test_new_tools_registered(self):
        from src.holly.tools import HOLLY_TOOLS
        assert "tune_epsilon" in HOLLY_TOOLS
        assert "run_workflow" in HOLLY_TOOLS
        assert "query_crew_enneagram" in HOLLY_TOOLS
