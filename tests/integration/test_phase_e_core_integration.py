"""Integration tests for Phase E Core SIL-2 suite (Task 40.2, 40.3, 40.5)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from holly.test_harness.core_test_suite import CoreTestSuite
from holly.test_harness.core_eval_suite import CoreEvalSuite
from holly.test_harness.phase_e_gate import evaluate_phase_e_gate, render_report


class TestPhaseEIntegration:
    """Integration tests for Phase E SIL-2 test and eval suites."""

    def test_core_test_suite_full_execution(self) -> None:
        """Test full core test suite execution end-to-end."""
        suite = CoreTestSuite()
        result = suite.execute()

        # Verify comprehensive coverage
        assert result.total >= 30
        assert result.passed == result.total
        assert result.all_pass

    def test_core_eval_suite_full_execution(self) -> None:
        """Test full core eval suite execution end-to-end."""
        suite = CoreEvalSuite()
        result = suite.execute()

        # Verify all components evaluated
        assert result.component_count == 4
        assert result.all_pass

    def test_phase_e_gate_complete(self) -> None:
        """Test Phase E gate evaluation end-to-end."""
        report = evaluate_phase_e_gate()

        # All items pass
        assert report.all_pass
        assert report.failed == 0
        assert len(report.items) >= 10

    def test_test_suite_to_gate_flow(self) -> None:
        """Test flow from test suite to gate."""
        # Execute tests
        test_suite = CoreTestSuite()
        test_result = test_suite.execute()
        assert test_suite.verdict() == "PASS"

        # Execute evals
        eval_suite = CoreEvalSuite()
        eval_result = eval_suite.execute()
        assert eval_suite.verdict() == "PASS"

        # Gate decision
        gate = evaluate_phase_e_gate()
        assert gate.all_pass

    def test_gate_report_generation(self) -> None:
        """Test that gate report can be generated."""
        gate = evaluate_phase_e_gate()
        markdown = render_report(gate)

        # Verify structure
        assert "Phase E Gate Report" in markdown
        assert "Phase E Overview" in markdown
        assert "Gate Items" in markdown
        assert "Critical Path" in markdown
        assert "Safety Case Summary" in markdown

    def test_gate_report_persistence(self) -> None:
        """Test that gate report can be written and read back."""
        gate = evaluate_phase_e_gate()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "phase_e_gate_report.md"
            from holly.test_harness.phase_e_gate import write_report
            write_report(gate, path)

            # Verify file created
            assert path.exists()

            # Verify content
            content = path.read_text()
            assert "Phase E Gate Report" in content
            assert "PASS" in content

    def test_all_steps_covered(self) -> None:
        """Test that all Phase E steps are covered in test suite."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        # Check coverage
        test_ids = [tc.test_id for tc in result.test_cases]

        # Should have tests from each step
        steps = set()
        for test_id in test_ids:
            if test_id[0].isdigit():
                step = test_id.split(".")[0]
                steps.add(step)

        assert len(steps) >= 6  # Steps 34-39

    def test_all_icds_referenced_in_tests(self) -> None:
        """Test that core ICDs are referenced in tests."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        all_icds = set()
        for tc in result.test_cases:
            all_icds.update(tc.icd_reference)

        # Check core ICDs
        assert "ICD-008" in all_icds  # Conversation
        assert "ICD-009" in all_icds  # Intent
        assert "ICD-010" in all_icds  # Goal
        assert "ICD-011" in all_icds  # APS
        assert "ICD-012" in all_icds  # Topology

    def test_celestial_predicates_in_gate(self) -> None:
        """Test that all Celestial L0-L4 predicates are in gate."""
        gate = evaluate_phase_e_gate()
        all_text = " ".join(i.evidence for i in gate.items) + " ".join(i.name for i in gate.items)

        # All Celestial levels should be mentioned
        assert "L0" in all_text or "safety" in all_text
        assert "L1" in all_text or "legal" in all_text
        assert "L2" in all_text or "ethical" in all_text
        assert "L3" in all_text or "permissions" in all_text
        assert "L4" in all_text or "constitutional" in all_text

    def test_memory_coverage(self) -> None:
        """Test that memory tier implementation is tested."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        memory_tests = [tc for tc in result.test_cases if tc.test_id.startswith("39")]
        assert len(memory_tests) > 0

        # Should test all tiers
        all_refs = " ".join(" ".join(tc.icd_reference) for tc in memory_tests)
        assert "ICD-041" in all_refs  # Redis
        assert "ICD-042" in all_refs  # PostgreSQL
        assert "ICD-043" in all_refs  # ChromaDB

    def test_e2e_pipeline(self) -> None:
        """Test that E2E pipeline tests are present."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        e2e_tests = [tc for tc in result.test_cases if tc.category == "e2e"]
        assert len(e2e_tests) >= 5

    def test_eval_baseline_achievement(self) -> None:
        """Test that all eval metrics achieve baseline."""
        eval_suite = CoreEvalSuite()
        result = eval_suite.execute()

        for eval_result in result.eval_results:
            for metric in eval_result.metrics:
                # All metrics should pass
                assert metric.passed

    def test_topology_contract_verification(self) -> None:
        """Test that topology contract verification is in tests."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        contract_tests = [tc for tc in result.test_cases if "contract" in tc.name.lower()]
        assert len(contract_tests) > 0

    def test_eigenspectrum_coverage(self) -> None:
        """Test that eigenspectrum is covered in tests."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        eigen_tests = [tc for tc in result.test_cases if "eigenspectrum" in tc.name.lower()]
        assert len(eigen_tests) >= 2

    def test_property_based_testing(self) -> None:
        """Test that property-based tests are included."""
        test_suite = CoreTestSuite()
        result = test_suite.execute()

        prop_tests = [tc for tc in result.test_cases if "property" in tc.name.lower()]
        assert len(prop_tests) > 0

    def test_gate_verdict_consistency(self) -> None:
        """Test that gate verdict is consistent with test/eval results."""
        test_suite = CoreTestSuite()
        eval_suite = CoreEvalSuite()
        gate = evaluate_phase_e_gate()

        # All should pass
        assert test_suite.execute().all_pass
        assert eval_suite.execute().all_pass
        assert gate.all_pass
