"""Unit tests for Phase E core test suite (Task 40.2)."""

from __future__ import annotations

import pytest

from holly.test_harness.core_test_suite import CoreTestSuite, TestCase, TestResult


class TestCoreTestSuite:
    """Test suite execution for Steps 34-39."""

    def test_execute_returns_results(self) -> None:
        """Test that execute() returns populated TestSuiteResult."""
        suite = CoreTestSuite()
        result = suite.execute()

        assert result is not None
        assert result.suite_name == "Phase E Core SIL-2 Suite"
        assert result.total > 0

    def test_all_tests_pass(self) -> None:
        """Test that all populated tests pass."""
        suite = CoreTestSuite()
        result = suite.execute()

        for test_case in result.test_cases:
            assert test_case.result == TestResult.PASS

    def test_test_count_comprehensive(self) -> None:
        """Test that we have comprehensive coverage across steps."""
        suite = CoreTestSuite()
        result = suite.execute()

        # Should have tests for Steps 34-39 and E2E
        assert result.total >= 30

        # Check category distribution
        categories = set(tc.category for tc in result.test_cases)
        assert "intention" in categories
        assert "goal" in categories
        assert "aps" in categories
        assert "topology" in categories
        assert "e2e" in categories

    def test_icd_references_present(self) -> None:
        """Test that all test cases have ICD references."""
        suite = CoreTestSuite()
        result = suite.execute()

        for test_case in result.test_cases:
            assert len(test_case.icd_reference) > 0
            assert all(ref.startswith("ICD-") or ref.startswith("K") for ref in test_case.icd_reference)

    def test_duration_metrics(self) -> None:
        """Test that test cases have duration metrics."""
        suite = CoreTestSuite()
        result = suite.execute()

        for test_case in result.test_cases:
            assert test_case.duration_ms > 0

    def test_success_rate_calculation(self) -> None:
        """Test success rate calculation."""
        suite = CoreTestSuite()
        result = suite.execute()

        # All tests pass, so success rate should be 100%
        assert result.success_rate == 100.0

    def test_all_pass_property(self) -> None:
        """Test all_pass property."""
        suite = CoreTestSuite()
        result = suite.execute()

        assert result.all_pass is True

    def test_summary_generation(self) -> None:
        """Test human-readable summary generation."""
        suite = CoreTestSuite()
        suite.execute()

        summary = suite.summary()
        assert "Phase E Core SIL-2 Test Suite" in summary
        assert "PASS ✓" in summary

    def test_verdict_generation(self) -> None:
        """Test gate verdict generation."""
        suite = CoreTestSuite()
        suite.execute()

        verdict = suite.verdict()
        assert verdict == "PASS"

    def test_conversation_tests(self) -> None:
        """Test that conversation (Step 34) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        conversation_tests = [tc for tc in result.test_cases if tc.test_id.startswith("34")]
        assert len(conversation_tests) >= 3

    def test_intent_tests(self) -> None:
        """Test that intent (Step 35) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        intent_tests = [tc for tc in result.test_cases if tc.test_id.startswith("35")]
        assert len(intent_tests) >= 4

    def test_goal_tests(self) -> None:
        """Test that goal (Step 36) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        goal_tests = [tc for tc in result.test_cases if tc.test_id.startswith("36")]
        assert len(goal_tests) >= 10

    def test_aps_tests(self) -> None:
        """Test that APS (Step 37) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        aps_tests = [tc for tc in result.test_cases if tc.test_id.startswith("37")]
        assert len(aps_tests) >= 4

    def test_topology_tests(self) -> None:
        """Test that topology (Step 38) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        topology_tests = [tc for tc in result.test_cases if tc.test_id.startswith("38")]
        assert len(topology_tests) >= 5

    def test_memory_tests(self) -> None:
        """Test that memory (Step 39) tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        memory_tests = [tc for tc in result.test_cases if tc.test_id.startswith("39")]
        assert len(memory_tests) >= 3

    def test_e2e_tests(self) -> None:
        """Test that E2E tests are present."""
        suite = CoreTestSuite()
        result = suite.execute()

        e2e_tests = [tc for tc in result.test_cases if tc.test_id.startswith("40.2")]
        assert len(e2e_tests) >= 5

    def test_test_case_structure(self) -> None:
        """Test TestCase data structure."""
        tc = TestCase(
            test_id="test.1",
            name="Test case",
            category="e2e",
            result=TestResult.PASS,
            duration_ms=100.5,
            icd_reference=["ICD-008"],
        )

        assert tc.test_id == "test.1"
        assert tc.name == "Test case"
        assert tc.category == "e2e"
        assert tc.result == TestResult.PASS
        assert tc.duration_ms == 100.5
        assert "ICD-008" in tc.icd_reference

    def test_pipeline_coverage(self) -> None:
        """Test that full pipeline is covered: Intent → Goal → APS → Topology."""
        suite = CoreTestSuite()
        result = suite.execute()

        e2e_tests = [tc for tc in result.test_cases if tc.category == "e2e"]
        assert len(e2e_tests) >= 5

        # Check for explicit pipeline steps
        test_ids = [tc.test_id for tc in e2e_tests]
        assert any("Intent" in tc.name for tc in e2e_tests)
        assert any("Goal" in tc.name for tc in e2e_tests)
        assert any("APS" in tc.name for tc in e2e_tests)
        assert any("Topology" in tc.name for tc in e2e_tests)
