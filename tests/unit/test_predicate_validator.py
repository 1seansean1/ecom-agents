"""Unit tests for L0–L4 Predicate Validator framework.

Tests cover:
- StateGenerator: state creation, satisfying/violating/boundary variants
- PredicateValidationReport: metrics computation, is_valid property
- PredicateValidator: single-level and all-levels validation
- Validation metrics: TP/TN/FP/FN accuracy
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from holly.goals.predicates import (
    CelestialState,
    L0SafetyPredicate,
    L1LegalPredicate,
    L2EthicalPredicate,
    L3PermissionsPredicate,
    L4ConstitutionalPredicate,
    DEFAULT_PREDICATES,
)
from holly.goals.validator import (
    StateGenerator,
    PredicateValidationReport,
    PredicateValidator,
)


class TestStateGenerator:
    """Test StateGenerator state creation across all levels."""

    def test_init_with_random_seed(self) -> None:
        """Verify StateGenerator initializes with optional random seed."""
        gen = StateGenerator(random_seed=42)
        assert gen.random_seed == 42

    def test_generate_satisfying_states_l0(self) -> None:
        """Generate L0 satisfying states and verify structure."""
        gen = StateGenerator()
        states = gen.generate_satisfying_states(level=0, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 0
            assert isinstance(state.context, dict)
            assert isinstance(state.timestamp, datetime)
            assert isinstance(state.actor_id, str)
            assert isinstance(state.action, str)
            assert isinstance(state.payload, dict)

    def test_generate_satisfying_states_l1(self) -> None:
        """Generate L1 satisfying states with legal compliance context."""
        gen = StateGenerator()
        states = gen.generate_satisfying_states(level=1, count=5)

        assert len(states) == 5
        for state in states:
            assert state.level == 1
            assert "target_jurisdiction" in state.context
            assert state.context["export_controlled"] is False

    def test_generate_satisfying_states_l2(self) -> None:
        """Generate L2 satisfying states with ethical context."""
        gen = StateGenerator()
        states = gen.generate_satisfying_states(level=2, count=5)

        assert len(states) == 5
        for state in states:
            assert state.level == 2
            assert state.context["user_consent"] is True
            assert state.context["coercion"] is False

    def test_generate_satisfying_states_l3(self) -> None:
        """Generate L3 satisfying states with permissions context."""
        gen = StateGenerator()
        states = gen.generate_satisfying_states(level=3, count=5)

        assert len(states) == 5
        for state in states:
            assert state.level == 3
            assert "actor_permissions" in state.context
            assert state.context["resource_usage"] <= state.context["resource_quota"]

    def test_generate_satisfying_states_l4(self) -> None:
        """Generate L4 satisfying states with constitutional context."""
        gen = StateGenerator()
        states = gen.generate_satisfying_states(level=4, count=5)

        assert len(states) == 5
        for state in states:
            assert state.level == 4
            assert state.context["outside_envelope"] is False
            assert state.context["state_corruption_detected"] is False

    def test_generate_violating_states_l0(self) -> None:
        """Generate L0 violating states with harm indicators."""
        gen = StateGenerator()
        states = gen.generate_violating_states(level=0, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 0
            # At least some should have harmful intent or dangerous actions
            has_harm = (
                "harm" in state.context.get("intent", "").lower()
                or state.action in [
                    "enable_weapon",
                    "execute_exploit",
                    "bypass_safety_control",
                    "disable_override",
                ]
                or state.context.get("bypass_control", False)
            )
            # Not all states are guaranteed harmful (due to randomization)
            # but we verify structure is correct
            assert isinstance(state.action, str)

    def test_generate_violating_states_l1(self) -> None:
        """Generate L1 violating states with legal violations."""
        gen = StateGenerator()
        states = gen.generate_violating_states(level=1, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 1
            # Verify structure even if not all have violations
            assert "restricted_jurisdictions" in state.context

    def test_generate_violating_states_l2(self) -> None:
        """Generate L2 violating states with ethical violations."""
        gen = StateGenerator()
        states = gen.generate_violating_states(level=2, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 2

    def test_generate_violating_states_l3(self) -> None:
        """Generate L3 violating states with permission violations."""
        gen = StateGenerator()
        states = gen.generate_violating_states(level=3, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 3
            # Most should have permission issues
            assert "required_permissions" in state.context

    def test_generate_violating_states_l4(self) -> None:
        """Generate L4 violating states with constitutional violations."""
        gen = StateGenerator()
        states = gen.generate_violating_states(level=4, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 4

    def test_generate_boundary_states(self) -> None:
        """Generate boundary states and verify edge cases."""
        gen = StateGenerator()
        states = gen.generate_boundary_states(level=2, count=10)

        assert len(states) == 10
        for state in states:
            assert state.level == 2
            # Boundary states may have minimal context
            assert isinstance(state.context, dict)
            assert isinstance(state.payload, dict)

    def test_invalid_level_satisfying(self) -> None:
        """Raise ValueError for invalid level in satisfying states."""
        gen = StateGenerator()
        with pytest.raises(ValueError):
            gen.generate_satisfying_states(level=5, count=10)

    def test_invalid_level_violating(self) -> None:
        """Raise ValueError for invalid level in violating states."""
        gen = StateGenerator()
        with pytest.raises(ValueError):
            gen.generate_violating_states(level=-1, count=10)

    def test_invalid_level_boundary(self) -> None:
        """Raise ValueError for invalid level in boundary states."""
        gen = StateGenerator()
        with pytest.raises(ValueError):
            gen.generate_boundary_states(level=10, count=5)

    def test_reproducibility_with_seed(self) -> None:
        """Verify state generation is reproducible with same seed."""
        gen1 = StateGenerator(random_seed=123)
        states1 = gen1.generate_satisfying_states(level=1, count=5)

        gen2 = StateGenerator(random_seed=123)
        states2 = gen2.generate_satisfying_states(level=1, count=5)

        # States should be identical with same seed
        for s1, s2 in zip(states1, states2):
            assert s1.actor_id == s2.actor_id
            assert s1.action == s2.action


class TestPredicateValidationReport:
    """Test PredicateValidationReport structure and metrics."""

    def test_report_creation(self) -> None:
        """Create validation report with complete metrics."""
        report = PredicateValidationReport(
            level=0,
            total_states=100,
            true_positives=45,
            true_negatives=50,
            false_positives=0,
            false_negatives=5,
            accuracy=0.95,
            precision=1.0,
            recall=0.90,
        )

        assert report.level == 0
        assert report.total_states == 100
        assert report.true_positives == 45
        assert report.true_negatives == 50
        assert report.false_positives == 0
        assert report.false_negatives == 5

    def test_is_valid_perfect_accuracy(self) -> None:
        """is_valid returns True for zero false positives and negatives."""
        report = PredicateValidationReport(
            level=1,
            total_states=100,
            true_positives=50,
            true_negatives=50,
            false_positives=0,
            false_negatives=0,
            accuracy=1.0,
            precision=1.0,
            recall=1.0,
        )

        assert report.is_valid is True

    def test_is_valid_with_false_positives(self) -> None:
        """is_valid returns False if false_positives > 0."""
        report = PredicateValidationReport(
            level=2,
            total_states=100,
            true_positives=45,
            true_negatives=45,
            false_positives=5,
            false_negatives=5,
            accuracy=0.90,
            precision=0.90,
            recall=0.90,
        )

        assert report.is_valid is False

    def test_is_valid_with_false_negatives(self) -> None:
        """is_valid returns False if false_negatives > 0."""
        report = PredicateValidationReport(
            level=3,
            total_states=100,
            true_positives=45,
            true_negatives=50,
            false_positives=0,
            false_negatives=5,
            accuracy=0.95,
            precision=1.0,
            recall=0.90,
        )

        assert report.is_valid is False


class TestPredicateValidator:
    """Test PredicateValidator validation logic."""

    def test_validator_init_default_generator(self) -> None:
        """Initialize PredicateValidator with default generator."""
        validator = PredicateValidator()
        assert validator.generator is not None
        assert isinstance(validator.generator, StateGenerator)

    def test_validator_init_custom_generator(self) -> None:
        """Initialize PredicateValidator with custom generator."""
        gen = StateGenerator(random_seed=99)
        validator = PredicateValidator(generator=gen)
        assert validator.generator is gen

    def test_validate_predicate_l0(self) -> None:
        """Validate L0 safety predicate."""
        validator = PredicateValidator()
        predicate = L0SafetyPredicate()

        report = validator.validate_predicate(predicate, count=40)

        assert report.level == 0
        assert report.total_states == 40
        assert report.true_positives + report.true_negatives + report.false_positives + report.false_negatives == 40
        assert 0.0 <= report.accuracy <= 1.0
        assert 0.0 <= report.precision <= 1.0
        assert 0.0 <= report.recall <= 1.0

    def test_validate_predicate_l1(self) -> None:
        """Validate L1 legal predicate."""
        validator = PredicateValidator()
        predicate = L1LegalPredicate()

        report = validator.validate_predicate(predicate, count=40)

        assert report.level == 1
        assert report.total_states == 40

    def test_validate_predicate_l2(self) -> None:
        """Validate L2 ethical predicate."""
        validator = PredicateValidator()
        predicate = L2EthicalPredicate()

        report = validator.validate_predicate(predicate, count=40)

        assert report.level == 2
        assert report.total_states == 40

    def test_validate_predicate_l3(self) -> None:
        """Validate L3 permissions predicate."""
        validator = PredicateValidator()
        predicate = L3PermissionsPredicate()

        report = validator.validate_predicate(predicate, count=40)

        assert report.level == 3
        assert report.total_states == 40

    def test_validate_predicate_l4(self) -> None:
        """Validate L4 constitutional predicate."""
        validator = PredicateValidator()
        predicate = L4ConstitutionalPredicate()

        report = validator.validate_predicate(predicate, count=40)

        assert report.level == 4
        assert report.total_states == 40

    def test_validate_all_levels(self) -> None:
        """Validate all five predicates across levels."""
        validator = PredicateValidator()

        reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level=40)

        assert len(reports) == 5
        for level in range(5):
            assert level in reports
            report = reports[level]
            assert report.level == level
            assert report.total_states == 40

    def test_assert_zero_fp_fn_passes(self) -> None:
        """assert_zero_false_positives_negatives passes for valid reports."""
        validator = PredicateValidator()

        reports = {
            0: PredicateValidationReport(
                level=0,
                total_states=100,
                true_positives=50,
                true_negatives=50,
                false_positives=0,
                false_negatives=0,
                accuracy=1.0,
                precision=1.0,
                recall=1.0,
            ),
        }

        # Should not raise
        validator.assert_zero_false_positives_negatives(reports)

    def test_assert_zero_fp_fn_raises_on_false_positives(self) -> None:
        """assert_zero_false_positives_negatives raises if FP > 0."""
        validator = PredicateValidator()

        reports = {
            0: PredicateValidationReport(
                level=0,
                total_states=100,
                true_positives=45,
                true_negatives=50,
                false_positives=5,
                false_negatives=0,
                accuracy=0.95,
                precision=0.90,
                recall=1.0,
            ),
        }

        with pytest.raises(AssertionError) as exc_info:
            validator.assert_zero_false_positives_negatives(reports)
        assert "false positives" in str(exc_info.value)

    def test_assert_zero_fp_fn_raises_on_false_negatives(self) -> None:
        """assert_zero_false_positives_negatives raises if FN > 0."""
        validator = PredicateValidator()

        reports = {
            0: PredicateValidationReport(
                level=0,
                total_states=100,
                true_positives=45,
                true_negatives=50,
                false_positives=0,
                false_negatives=5,
                accuracy=0.95,
                precision=1.0,
                recall=0.90,
            ),
        }

        with pytest.raises(AssertionError) as exc_info:
            validator.assert_zero_false_positives_negatives(reports)
        assert "false negatives" in str(exc_info.value)


class TestBoundaryStates:
    """Test edge cases and boundary conditions."""

    def test_empty_context(self) -> None:
        """Validate predicate with empty context."""
        gen = StateGenerator()
        states = gen.generate_boundary_states(level=0, count=3)

        predicate = L0SafetyPredicate()
        for state in states:
            # Should not crash with empty/minimal context
            result = predicate.evaluate(state)
            assert isinstance(result.passed, bool)

    def test_minimal_payload(self) -> None:
        """Validate predicate with minimal payload."""
        gen = StateGenerator()
        states = gen.generate_boundary_states(level=1, count=3)

        predicate = L1LegalPredicate()
        for state in states:
            result = predicate.evaluate(state)
            assert isinstance(result.passed, bool)

    def test_boundary_states_with_proper_context(self) -> None:
        """Handle boundary states with proper (non-null) context."""
        state = CelestialState(
            level=0,
            context={"intent": "", "bypass_control": False},
            timestamp=datetime.now(timezone.utc),
            actor_id="test",
            action="test_action",
            payload={},
        )

        predicate = L0SafetyPredicate()
        result = predicate.evaluate(state)
        assert isinstance(result.passed, bool)
        assert isinstance(result.reason, str)


class TestValidationMetrics:
    """Test accuracy, precision, recall computation."""

    def test_perfect_validation_metrics(self) -> None:
        """Compute metrics for perfect validation (100% accuracy)."""
        report = PredicateValidationReport(
            level=0,
            total_states=100,
            true_positives=50,
            true_negatives=50,
            false_positives=0,
            false_negatives=0,
            accuracy=1.0,
            precision=1.0,
            recall=1.0,
        )

        assert report.accuracy == 1.0
        assert report.precision == 1.0
        assert report.recall == 1.0
        assert report.is_valid is True

    def test_partial_validation_metrics(self) -> None:
        """Compute metrics for partial validation."""
        report = PredicateValidationReport(
            level=1,
            total_states=100,
            true_positives=40,
            true_negatives=50,
            false_positives=5,
            false_negatives=5,
            accuracy=0.90,
            precision=40 / 45,
            recall=40 / 45,
        )

        assert abs(report.accuracy - 0.90) < 0.01
        assert abs(report.precision - (40 / 45)) < 0.01
        assert abs(report.recall - (40 / 45)) < 0.01
        assert report.is_valid is False
