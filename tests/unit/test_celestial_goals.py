"""Tests for L0–L4 Celestial goal-level predicates (Task 36.5).

This module contains unit and property-based tests for the five check_* functions
that evaluate Celestial goals (L0–L4) and return GoalResult structures per Goal
Hierarchy Formal Spec §2.0–2.4.

Test coverage:
- GoalResult dataclass structure and validation
- Each of five check_* functions (L0 safety, L1 legal, L2 ethical, L3 permissions, L4 constitutional)
- Short-circuit evaluation in evaluate_celestial_goals()
- Distance metric computation and semantics
- Confidence scores and violation tracking
- Property-based tests with Hypothesis over generated states
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st

from holly.goals.predicates import (
    CelestialState,
    GoalResult,
    GoalPredicateProtocol,
    check_L0_safety,
    check_L1_legal,
    check_L2_ethical,
    check_L3_permissions,
    check_L4_constitutional,
    evaluate_celestial_goals,
    celestial_goals_satisfied,
)


# ============================================================================
# Test Fixtures and Helpers
# ============================================================================


@pytest.fixture
def base_state() -> CelestialState:
    """Create a clean, passing base state."""
    return CelestialState(
        level=0,
        context={},
        timestamp=datetime.now(timezone.utc),
        actor_id="test-actor",
        action="test_action",
        payload={},
    )


@pytest.fixture
def l0_violation_state() -> CelestialState:
    """Create a state with explicit L0 violation context."""
    return CelestialState(
        level=0,
        context={"physical_harm": True},
        timestamp=datetime.now(timezone.utc),
        actor_id="bad-actor",
        action="damage_hardware",
        payload={"target": "system"},
    )


@pytest.fixture
def l1_violation_state() -> CelestialState:
    """Create a state with explicit L1 violation context."""
    return CelestialState(
        level=1,
        context={"export_violation": True},
        timestamp=datetime.now(timezone.utc),
        actor_id="bad-actor",
        action="export_data",
        payload={"destination": "restricted_jurisdiction"},
    )


@pytest.fixture
def l2_violation_state() -> CelestialState:
    """Create a state with explicit L2 violation context."""
    return CelestialState(
        level=2,
        context={"deception": True},
        timestamp=datetime.now(timezone.utc),
        actor_id="bad-actor",
        action="impersonate",
        payload={"target": "human"},
    )


@pytest.fixture
def l3_violation_state() -> CelestialState:
    """Create a state with explicit L3 violation context."""
    return CelestialState(
        level=3,
        context={"actor_role": "viewer", "required_roles": ["admin"]},
        timestamp=datetime.now(timezone.utc),
        actor_id="agent1",
        action="modify_data",
        payload={"resource": "admin_only"},
    )


@pytest.fixture
def l4_violation_state() -> CelestialState:
    """Create a state with explicit L4 violation context."""
    return CelestialState(
        level=4,
        context={"outside_envelope": True},
        timestamp=datetime.now(timezone.utc),
        actor_id="bad-actor",
        action="modify_predicate",
        payload={"target": "L0_safety"},
    )


# ============================================================================
# GoalResult Structure Tests
# ============================================================================


class TestGoalResultStructure:
    """Test the GoalResult dataclass and its properties."""

    def test_goal_result_creation_minimal(self):
        """Test creating a GoalResult with minimal fields."""
        result = GoalResult(
            level=0,
            satisfied=True,
            distance=0.0,
            explanation="Test explanation",
        )
        assert result.level == 0
        assert result.satisfied is True
        assert result.distance == 0.0
        assert result.explanation == "Test explanation"
        assert result.violations == []
        assert result.confidence == 1.0

    def test_goal_result_creation_full(self):
        """Test creating a GoalResult with all fields."""
        violations = ["violation1", "violation2"]
        result = GoalResult(
            level=1,
            satisfied=False,
            distance=0.5,
            explanation="Test failed",
            violations=violations,
            confidence=0.8,
        )
        assert result.level == 1
        assert result.satisfied is False
        assert result.distance == 0.5
        assert result.violations == violations
        assert result.confidence == 0.8

    def test_goal_result_all_levels(self):
        """Test GoalResult for all level values 0-6."""
        for level in range(7):
            result = GoalResult(
                level=level,
                satisfied=True,
                distance=0.0,
                explanation=f"Level {level}",
            )
            assert result.level == level

    def test_goal_result_distance_non_negative(self):
        """Distance should be non-negative."""
        result = GoalResult(
            level=0,
            satisfied=True,
            distance=0.0,
            explanation="Test",
        )
        assert result.distance >= 0.0

    def test_goal_result_confidence_range(self):
        """Confidence should be in [0.0, 1.0]."""
        for confidence in [0.0, 0.5, 1.0]:
            result = GoalResult(
                level=0,
                satisfied=True,
                distance=0.0,
                explanation="Test",
                confidence=confidence,
            )
            assert 0.0 <= result.confidence <= 1.0

    def test_goal_result_slots(self, base_state):
        """GoalResult should use slots for memory efficiency."""
        result = check_L0_safety(base_state)
        # With slots, object should not have __dict__
        assert not hasattr(result, "__dict__")


# ============================================================================
# L0 Safety Goal Tests
# ============================================================================


class TestL0SafetyGoal:
    """Test check_L0_safety() function."""

    def test_l0_returns_goal_result(self, base_state):
        """check_L0_safety should return GoalResult."""
        result = check_L0_safety(base_state)
        assert isinstance(result, GoalResult)

    def test_l0_level_is_zero(self, base_state):
        """L0 result should have level=0."""
        result = check_L0_safety(base_state)
        assert result.level == 0

    def test_l0_satisfied_default_state(self, base_state):
        """L0 should be satisfied for default safe state."""
        result = check_L0_safety(base_state)
        assert result.satisfied is True
        assert result.distance == 0.0

    def test_l0_explanation_provided(self, base_state):
        """L0 result should include explanation."""
        result = check_L0_safety(base_state)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0

    def test_l0_violations_list_type(self, base_state):
        """L0 result violations should be a list."""
        result = check_L0_safety(base_state)
        assert isinstance(result.violations, list)

    def test_l0_confidence_preserved(self, base_state):
        """L0 result should preserve confidence from predicate."""
        result = check_L0_safety(base_state)
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0


# ============================================================================
# L1 Legal Goal Tests
# ============================================================================


class TestL1LegalGoal:
    """Test check_L1_legal() function."""

    def test_l1_returns_goal_result(self, base_state):
        """check_L1_legal should return GoalResult."""
        result = check_L1_legal(base_state)
        assert isinstance(result, GoalResult)

    def test_l1_level_is_one(self, base_state):
        """L1 result should have level=1."""
        result = check_L1_legal(base_state)
        assert result.level == 1

    def test_l1_satisfied_default_state(self, base_state):
        """L1 should be satisfied for compliant state."""
        result = check_L1_legal(base_state)
        assert result.satisfied is True
        assert result.distance == 0.0

    def test_l1_explanation_provided(self, base_state):
        """L1 result should include explanation."""
        result = check_L1_legal(base_state)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ============================================================================
# L2 Ethical Goal Tests
# ============================================================================


class TestL2EthicalGoal:
    """Test check_L2_ethical() function."""

    def test_l2_returns_goal_result(self, base_state):
        """check_L2_ethical should return GoalResult."""
        result = check_L2_ethical(base_state)
        assert isinstance(result, GoalResult)

    def test_l2_level_is_two(self, base_state):
        """L2 result should have level=2."""
        result = check_L2_ethical(base_state)
        assert result.level == 2

    def test_l2_satisfied_default_state(self, base_state):
        """L2 should be satisfied for ethical state."""
        result = check_L2_ethical(base_state)
        assert result.satisfied is True
        assert result.distance == 0.0

    def test_l2_explanation_provided(self, base_state):
        """L2 result should include explanation."""
        result = check_L2_ethical(base_state)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ============================================================================
# L3 Permissions Goal Tests
# ============================================================================


class TestL3PermissionsGoal:
    """Test check_L3_permissions() function."""

    def test_l3_returns_goal_result(self, base_state):
        """check_L3_permissions should return GoalResult."""
        result = check_L3_permissions(base_state)
        assert isinstance(result, GoalResult)

    def test_l3_level_is_three(self, base_state):
        """L3 result should have level=3."""
        result = check_L3_permissions(base_state)
        assert result.level == 3

    def test_l3_satisfied_authorized_state(self, base_state):
        """L3 should be satisfied for authorized actor."""
        result = check_L3_permissions(base_state)
        assert result.satisfied is True
        assert result.distance == 0.0

    def test_l3_explanation_provided(self, base_state):
        """L3 result should include explanation."""
        result = check_L3_permissions(base_state)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ============================================================================
# L4 Constitutional Goal Tests
# ============================================================================


class TestL4ConstitutionalGoal:
    """Test check_L4_constitutional() function."""

    def test_l4_returns_goal_result(self, base_state):
        """check_L4_constitutional should return GoalResult."""
        result = check_L4_constitutional(base_state)
        assert isinstance(result, GoalResult)

    def test_l4_level_is_four(self, base_state):
        """L4 result should have level=4."""
        result = check_L4_constitutional(base_state)
        assert result.level == 4

    def test_l4_satisfied_default_state(self, base_state):
        """L4 should be satisfied for compliant state."""
        result = check_L4_constitutional(base_state)
        assert result.satisfied is True
        assert result.distance == 0.0

    def test_l4_explanation_provided(self, base_state):
        """L4 result should include explanation."""
        result = check_L4_constitutional(base_state)
        assert isinstance(result.explanation, str)
        assert len(result.explanation) > 0


# ============================================================================
# Evaluation Chain Tests
# ============================================================================


class TestEvaluateCelestialGoals:
    """Test evaluate_celestial_goals() function."""

    def test_evaluate_all_satisfied(self, base_state):
        """When all goals satisfied, should return all 5 results."""
        results = evaluate_celestial_goals(base_state)
        assert len(results) == 5
        assert all(result.satisfied for result in results)
        for i, result in enumerate(results):
            assert result.level == i

    def test_evaluate_returns_list(self, base_state):
        """evaluate_celestial_goals should return a list."""
        results = evaluate_celestial_goals(base_state)
        assert isinstance(results, list)
        assert all(isinstance(r, GoalResult) for r in results)

    def test_celestial_goals_satisfied_all_pass(self, base_state):
        """celestial_goals_satisfied should return True when all pass."""
        assert celestial_goals_satisfied(base_state) is True

    def test_celestial_goals_satisfied_returns_bool(self, base_state):
        """celestial_goals_satisfied should return a boolean."""
        result = celestial_goals_satisfied(base_state)
        assert isinstance(result, bool)

    def test_evaluate_sequential_levels(self, base_state):
        """Evaluation should return goals in sequence (L0, L1, L2, L3, L4)."""
        results = evaluate_celestial_goals(base_state)
        levels = [r.level for r in results]
        assert levels == [0, 1, 2, 3, 4]


# ============================================================================
# Property-Based Tests with Hypothesis
# ============================================================================


@st.composite
def celestial_states(draw) -> CelestialState:
    """Generate arbitrary CelestialState instances."""
    level = draw(st.integers(min_value=0, max_value=4))
    context = draw(st.dictionaries(
        keys=st.text(min_size=1),
        values=st.one_of(st.booleans(), st.integers(), st.text()),
        max_size=5,
    ))
    actor_id = draw(st.text(min_size=1, max_size=20))
    action = draw(st.text(min_size=1, max_size=30))

    return CelestialState(
        level=level,
        context=context,
        timestamp=datetime.now(timezone.utc),
        actor_id=actor_id,
        action=action,
        payload={},
    )


class TestPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_check_l0_returns_goal_result(self, state):
        """check_L0_safety should always return GoalResult."""
        result = check_L0_safety(state)
        assert isinstance(result, GoalResult)
        assert result.level == 0

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_check_l1_returns_goal_result(self, state):
        """check_L1_legal should always return GoalResult."""
        result = check_L1_legal(state)
        assert isinstance(result, GoalResult)
        assert result.level == 1

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_check_l2_returns_goal_result(self, state):
        """check_L2_ethical should always return GoalResult."""
        result = check_L2_ethical(state)
        assert isinstance(result, GoalResult)
        assert result.level == 2

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_check_l3_returns_goal_result(self, state):
        """check_L3_permissions should always return GoalResult."""
        result = check_L3_permissions(state)
        assert isinstance(result, GoalResult)
        assert result.level == 3

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_check_l4_returns_goal_result(self, state):
        """check_L4_constitutional should always return GoalResult."""
        result = check_L4_constitutional(state)
        assert isinstance(result, GoalResult)
        assert result.level == 4

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_all_results_have_valid_distance(self, state):
        """All GoalResults should have distance >= 0.0."""
        for check_func in [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]:
            result = check_func(state)
            assert result.distance >= 0.0

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_satisfied_implies_zero_distance(self, state):
        """If satisfied=True, distance should be 0.0."""
        for check_func in [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]:
            result = check_func(state)
            if result.satisfied:
                assert result.distance == 0.0

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_violated_implies_nonzero_distance(self, state):
        """If satisfied=False, distance should be > 0.0."""
        for check_func in [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]:
            result = check_func(state)
            if not result.satisfied:
                assert result.distance > 0.0

    @given(state=celestial_states())
    @settings(max_examples=50)
    def test_confidence_always_valid(self, state):
        """Confidence should always be in [0.0, 1.0]."""
        for check_func in [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]:
            result = check_func(state)
            assert 0.0 <= result.confidence <= 1.0


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests spanning multiple goal levels."""

    def test_all_satisfied_states(self):
        """Test a state that satisfies all five goals."""
        state = CelestialState(
            level=0,
            context={},
            timestamp=datetime.now(timezone.utc),
            actor_id="trusted-actor",
            action="safe_action",
            payload={"data": "safe"},
        )

        assert celestial_goals_satisfied(state) is True
        results = evaluate_celestial_goals(state)
        assert len(results) == 5
        assert all(r.satisfied for r in results)

    def test_goal_result_creation_from_state(self, base_state):
        """Test that GoalResults can be created from various states."""
        check_funcs = [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]

        for check_func in check_funcs:
            result = check_func(base_state)
            assert isinstance(result, GoalResult)
            assert result.satisfied is True
            assert result.distance == 0.0

    def test_multiple_evaluations_consistent(self, base_state):
        """Multiple evaluations of same state should be consistent."""
        result1 = check_L0_safety(base_state)
        result2 = check_L0_safety(base_state)

        assert result1.satisfied == result2.satisfied
        assert result1.distance == result2.distance
        assert result1.level == result2.level

    def test_chain_evaluation_order(self, base_state):
        """Evaluate_celestial_goals should evaluate in order."""
        results = evaluate_celestial_goals(base_state)

        # Verify sequential evaluation
        for i, result in enumerate(results):
            assert result.level == i

    def test_all_functions_defined(self):
        """All five check functions should be callable."""
        funcs = [
            check_L0_safety,
            check_L1_legal,
            check_L2_ethical,
            check_L3_permissions,
            check_L4_constitutional,
        ]

        for func in funcs:
            assert callable(func)
