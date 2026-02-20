"""Unit tests for Phase E core eval suite (Task 40.3)."""

from __future__ import annotations

import pytest

from holly.test_harness.core_eval_suite import CoreEvalSuite, EvalMetric


class TestCoreEvalSuite:
    """Test evaluation suite for Steps 34-39."""

    def test_execute_returns_results(self) -> None:
        """Test that execute() returns populated CoreEvalSuiteResult."""
        suite = CoreEvalSuite()
        result = suite.execute()

        assert result is not None
        assert result.suite_name == "Phase E Core Evaluation Suite"
        assert result.component_count > 0

    def test_all_components_pass(self) -> None:
        """Test that all eval components pass."""
        suite = CoreEvalSuite()
        result = suite.execute()

        assert result.all_pass is True

    def test_component_count(self) -> None:
        """Test that all components are evaluated."""
        suite = CoreEvalSuite()
        result = suite.execute()

        # Should evaluate intent, goal, APS, topology
        assert result.component_count == 4

    def test_component_names(self) -> None:
        """Test that components have correct names."""
        suite = CoreEvalSuite()
        result = suite.execute()

        component_names = [er.component for er in result.eval_results]
        assert any("Intent" in name for name in component_names)
        assert any("Goal" in name for name in component_names)
        assert any("APS" in name for name in component_names)
        assert any("Topology" in name for name in component_names)

    def test_intent_metrics(self) -> None:
        """Test intent classifier eval metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        intent_eval = next(er for er in result.eval_results if "Intent" in er.component)
        assert intent_eval.total >= 5
        assert all(m.passed for m in intent_eval.metrics)

    def test_goal_metrics(self) -> None:
        """Test goal decomposer eval metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        goal_eval = next(er for er in result.eval_results if "Goal" in er.component)
        assert goal_eval.total >= 7
        assert all(m.passed for m in goal_eval.metrics)

    def test_aps_metrics(self) -> None:
        """Test APS controller eval metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        aps_eval = next(er for er in result.eval_results if "APS" in er.component)
        assert aps_eval.total >= 6
        assert all(m.passed for m in aps_eval.metrics)

    def test_topology_metrics(self) -> None:
        """Test topology manager eval metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        topology_eval = next(er for er in result.eval_results if "Topology" in er.component)
        assert topology_eval.total >= 6
        assert all(m.passed for m in topology_eval.metrics)

    def test_metric_structure(self) -> None:
        """Test EvalMetric data structure."""
        metric = EvalMetric(
            metric_name="test_metric",
            value=0.95,
            baseline=0.90,
            threshold=5.0,
            unit="fraction",
            passed=True,
        )

        assert metric.metric_name == "test_metric"
        assert metric.value == 0.95
        assert metric.baseline == 0.90
        assert metric.threshold == 5.0
        assert metric.unit == "fraction"
        assert metric.passed is True

    def test_baseline_validation(self) -> None:
        """Test that metrics meet baseline."""
        suite = CoreEvalSuite()
        result = suite.execute()

        for eval_result in result.eval_results:
            for metric in eval_result.metrics:
                # Either metric directly passes, or meets_baseline is True
                assert metric.passed or metric.meets_baseline

    def test_summary_generation(self) -> None:
        """Test human-readable summary generation."""
        suite = CoreEvalSuite()
        suite.execute()

        summary = suite.summary()
        assert "Phase E Core Evaluation Suite" in summary
        assert "ALL PASS" in summary

    def test_verdict_generation(self) -> None:
        """Test gate verdict generation."""
        suite = CoreEvalSuite()
        suite.execute()

        verdict = suite.verdict()
        assert verdict == "PASS"

    def test_intent_classifier_accuracy(self) -> None:
        """Test intent classifier has accuracy metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        intent_eval = next(er for er in result.eval_results if "Intent" in er.component)
        metric_names = [m.metric_name for m in intent_eval.metrics]

        assert "direct_solve_accuracy" in metric_names
        assert "team_spawn_accuracy" in metric_names
        assert "clarify_accuracy" in metric_names
        assert "f1_weighted" in metric_names

    def test_goal_predicate_coverage(self) -> None:
        """Test goal decomposer has L0-L4 predicate metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        goal_eval = next(er for er in result.eval_results if "Goal" in er.component)
        metric_names = [m.metric_name for m in goal_eval.metrics]

        assert "l0_safety_detection" in metric_names
        assert "l1_legal_detection" in metric_names
        assert "l2_ethical_detection" in metric_names
        assert "l3_permissions_detection" in metric_names
        assert "l4_constitutional_detection" in metric_names

    def test_aps_tier_coverage(self) -> None:
        """Test APS has T0-T3 tier metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        aps_eval = next(er for er in result.eval_results if "APS" in er.component)
        metric_names = [m.metric_name for m in aps_eval.metrics]

        assert "t0_classification" in metric_names
        assert "t1_classification" in metric_names
        assert "t2_classification" in metric_names
        assert "t3_classification" in metric_names

    def test_topology_operator_coverage(self) -> None:
        """Test topology has spawn/steer/dissolve metrics."""
        suite = CoreEvalSuite()
        result = suite.execute()

        topology_eval = next(er for er in result.eval_results if "Topology" in er.component)
        metric_names = [m.metric_name for m in topology_eval.metrics]

        assert "spawn_success_rate" in metric_names
        assert "steer_success_rate" in metric_names
        assert "dissolve_success_rate" in metric_names

    def test_eval_result_descriptions(self) -> None:
        """Test that eval results have descriptions."""
        suite = CoreEvalSuite()
        result = suite.execute()

        for eval_result in result.eval_results:
            assert len(eval_result.description) > 0
            assert "Goal Hierarchy" in eval_result.description or "per" in eval_result.description

    def test_metric_units(self) -> None:
        """Test that metrics have appropriate units."""
        suite = CoreEvalSuite()
        result = suite.execute()

        for eval_result in result.eval_results:
            for metric in eval_result.metrics:
                assert metric.unit in ["fraction", "bits", "ms"]

    def test_baseline_thresholds(self) -> None:
        """Test that baseline thresholds are reasonable."""
        suite = CoreEvalSuite()
        result = suite.execute()

        for eval_result in result.eval_results:
            for metric in eval_result.metrics:
                # Threshold should be a small percentage or absolute value
                assert 0 <= metric.threshold <= 100
                assert metric.value > 0
