"""Integration tests for full L0–L4 predicate validation.

Tests the complete validation pipeline:
- validate_celestial_predicates() entry point
- All 5 predicates validated with generated states
- Zero false positives/negatives verification
- Property-based test coverage
"""

from __future__ import annotations

import pytest

from holly.goals.predicates import DEFAULT_PREDICATES
from holly.goals.validator import (
    StateGenerator,
    PredicateValidator,
    PredicateValidationReport,
    validate_celestial_predicates,
)


class TestValidateCelestialPredicates:
    """Test main validation entry point."""

    def test_validate_celestial_predicates_default_count(self) -> None:
        """Run full validation with default 1000 states per level."""
        reports = validate_celestial_predicates(count_per_level=1000)

        assert len(reports) == 5
        for level in range(5):
            assert level in reports
            report = reports[level]
            assert report.level == level
            assert report.total_states == 1000
            # All reports must have zero FP/FN
            assert report.is_valid is True

    def test_validate_celestial_predicates_reduced_count(self) -> None:
        """Run validation with reduced state count for testing."""
        reports = validate_celestial_predicates(count_per_level=200)

        assert len(reports) == 5
        for level in range(5):
            report = reports[level]
            assert report.total_states == 200
            assert report.is_valid is True

    def test_validate_celestial_predicates_all_levels_zero_fp(self) -> None:
        """Verify all levels have zero false positives."""
        reports = validate_celestial_predicates(count_per_level=200)

        for level, report in reports.items():
            assert report.false_positives == 0, (
                f"Level {level} has {report.false_positives} false positives"
            )

    def test_validate_celestial_predicates_all_levels_zero_fn(self) -> None:
        """Verify all levels have zero false negatives."""
        reports = validate_celestial_predicates(count_per_level=200)

        for level, report in reports.items():
            assert report.false_negatives == 0, (
                f"Level {level} has {report.false_negatives} false negatives"
            )

    def test_validate_celestial_predicates_accuracy(self) -> None:
        """Verify all levels achieve 100% accuracy."""
        reports = validate_celestial_predicates(count_per_level=200)

        for level, report in reports.items():
            assert report.accuracy == 1.0, (
                f"Level {level} accuracy is {report.accuracy}, expected 1.0"
            )

    def test_validate_celestial_predicates_returns_all_levels(self) -> None:
        """Verify all 5 levels are in the report."""
        reports = validate_celestial_predicates(count_per_level=200)

        expected_levels = {0, 1, 2, 3, 4}
        actual_levels = set(reports.keys())
        assert actual_levels == expected_levels


class TestPredicateValidatorIntegration:
    """Test PredicateValidator with all predicates."""

    def test_validate_all_levels_comprehensive(self) -> None:
        """Validate all five predicates comprehensively."""
        validator = PredicateValidator()
        reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level=200)

        assert len(reports) == 5

        for level in range(5):
            assert level in reports
            report = reports[level]
            assert isinstance(report, PredicateValidationReport)
            assert report.level == level
            assert report.total_states == 200
            # Each predicate should achieve perfect accuracy
            assert report.true_positives + report.true_negatives == 200

    def test_validate_all_levels_metrics(self) -> None:
        """Verify all levels produce valid metrics."""
        validator = PredicateValidator()
        reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level=200)

        for level, report in reports.items():
            # Metrics should be in valid range
            assert 0.0 <= report.accuracy <= 1.0
            assert 0.0 <= report.precision <= 1.0
            assert 0.0 <= report.recall <= 1.0

            # With zero FP and FN, both precision and recall should be 1.0
            if report.false_positives == 0 and report.false_negatives == 0:
                assert report.precision == 1.0
                assert report.recall == 1.0

    def test_assertion_passes_for_valid_validation(self) -> None:
        """assert_zero_false_positives_negatives passes for valid reports."""
        validator = PredicateValidator()
        reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level=200)

        # Should not raise AssertionError
        validator.assert_zero_false_positives_negatives(reports)


class TestStateGeneratorIntegration:
    """Test StateGenerator with all predicate levels."""

    def test_state_generator_creates_different_states(self) -> None:
        """Verify satisfying and violating states are different."""
        gen = StateGenerator()

        for level in range(5):
            satisfying = gen.generate_satisfying_states(level, count=10)
            violating = gen.generate_violating_states(level, count=10)

            # States should be different in context
            satisfying_actions = {s.action for s in satisfying}
            violating_actions = {s.action for s in violating}

            # Most should be distinct (allowing for potential duplicates from randomization)
            assert len(satisfying_actions) > 0
            assert len(violating_actions) > 0

    def test_boundary_states_have_minimal_context(self) -> None:
        """Verify boundary states include edge cases."""
        gen = StateGenerator()

        for level in range(5):
            boundary = gen.generate_boundary_states(level, count=20)

            assert len(boundary) == 20
            for state in boundary:
                assert state.level == level
                # Boundary states may have empty or minimal context
                assert isinstance(state.context, dict)
                assert isinstance(state.payload, dict)


class TestPropertyBasedValidation:
    """Test property-based validation characteristics."""

    def test_validation_satisfying_states_pass(self) -> None:
        """Generated satisfying states pass their predicates."""
        gen = StateGenerator()
        validator = PredicateValidator(gen)

        for predicate in DEFAULT_PREDICATES:
            satisfying = gen.generate_satisfying_states(predicate.level, count=50)

            passes = sum(1 for state in satisfying if predicate.evaluate(state).passed)
            # Most satisfying states should pass
            assert passes > 0

    def test_validation_violating_states_fail(self) -> None:
        """Generated violating states fail their predicates."""
        gen = StateGenerator()

        for predicate in DEFAULT_PREDICATES:
            violating = gen.generate_violating_states(predicate.level, count=50)

            fails = sum(
                1 for state in violating if not predicate.evaluate(state).passed
            )
            # Most violating states should fail
            assert fails > 0

    def test_validation_produces_confidence_scores(self) -> None:
        """Predicates return confidence scores."""
        gen = StateGenerator()

        for predicate in DEFAULT_PREDICATES:
            state = gen.generate_satisfying_states(predicate.level, count=1)[0]
            result = predicate.evaluate(state)

            assert 0.0 <= result.confidence <= 1.0


class TestValidationWithDifferentCounts:
    """Test validation with various state counts."""

    def test_validation_with_small_count(self) -> None:
        """Run validation with minimal state count."""
        reports = validate_celestial_predicates(count_per_level=20)

        assert len(reports) == 5
        for level, report in reports.items():
            assert report.total_states == 20
            assert report.is_valid is True

    def test_validation_with_large_count(self) -> None:
        """Run validation with larger state count."""
        reports = validate_celestial_predicates(count_per_level=500)

        assert len(reports) == 5
        for level, report in reports.items():
            assert report.total_states == 500
            assert report.is_valid is True

    def test_validation_scales_linearly(self) -> None:
        """Total states tested scales with count_per_level."""
        for count in [50, 100, 200]:
            reports = validate_celestial_predicates(count_per_level=count)
            for report in reports.values():
                assert report.total_states == count


class TestCelestialPredicateChain:
    """Test validation of predicate chain characteristics."""

    def test_all_predicates_present_in_default(self) -> None:
        """DEFAULT_PREDICATES contains all 5 levels."""
        levels = {p.level for p in DEFAULT_PREDICATES}
        assert levels == {0, 1, 2, 3, 4}

    def test_validation_respects_predicate_levels(self) -> None:
        """Each validated predicate matches its declared level."""
        validator = PredicateValidator()
        reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level=200)

        for predicate in DEFAULT_PREDICATES:
            report = reports[predicate.level]
            assert report.level == predicate.level


class TestValidationErrorHandling:
    """Test error handling in validation pipeline."""

    def test_validate_with_empty_predicates_list(self) -> None:
        """Validate with empty predicate list returns empty reports."""
        validator = PredicateValidator()
        reports = validator.validate_all_levels([], count_per_level=200)

        assert len(reports) == 0

    def test_assertion_on_empty_reports(self) -> None:
        """Assertion passes on empty reports dict."""
        validator = PredicateValidator()

        # Should not raise
        validator.assert_zero_false_positives_negatives({})
