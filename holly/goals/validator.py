"""L0–L4 Predicate Validator — property-based test framework.

This module provides comprehensive validation for Celestial predicates (L0–L4)
using property-based test generation. It creates states that should satisfy and
violate each predicate level, then verifies the predicate's accuracy across:
- True positives: correctly accepted valid states
- True negatives: correctly rejected invalid states
- False positives: incorrectly accepted invalid states
- False negatives: incorrectly rejected valid states

Key classes:
- StateGenerator: creates satisfying/violating/boundary states for each level
- PredicateValidationReport: metrics (TP/TN/FP/FN, accuracy, precision, recall)
- PredicateValidator: validation harness for single and multiple predicates

Main entry point: validate_celestial_predicates(count_per_level: int = 1000)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from holly.goals.predicates import (
    CelestialPredicateProtocol,
    CelestialState,
    DEFAULT_PREDICATES,
)


@dataclass(slots=True)
class StateGenerator:
    """Generates CelestialState instances for predicate validation.

    This generator creates states that should satisfy predicates (negative testing)
    and states that should violate predicates (positive testing), allowing
    comprehensive validation of predicate logic across all five Celestial levels.

    Attributes:
        random_seed: Optional seed for reproducible state generation.
    """

    random_seed: int | None = None

    def __post_init__(self) -> None:
        """Initialize random seed if provided."""
        if self.random_seed is not None:
            random.seed(self.random_seed)

    def generate_satisfying_states(
        self, level: int, count: int = 100
    ) -> list[CelestialState]:
        """Generate states that SHOULD satisfy level `level` predicate.

        Creates states with no constraint violations for the given level.
        Each state is designed to pass the predicate's validation checks.

        Args:
            level: Celestial level (0–4) for which to generate states.
            count: Number of states to generate (default 100).

        Returns:
            List of CelestialState instances that should satisfy the predicate.

        Raises:
            ValueError: If level is not in range 0–4.
        """
        if not 0 <= level <= 4:
            raise ValueError(f"Level must be 0–4, got {level}")

        states = []

        for i in range(count):
            timestamp = datetime.now(timezone.utc)
            actor_id = f"actor_{level}_{i}"
            action = f"safe_action_{i}"

            if level == 0:
                # L0: Safety — generate safe states (no harm, no dangerous actions)
                context = {
                    "intent": "benign_operation",
                    "bypass_control": False,
                }
                payload = {"data": "safe_content"}

            elif level == 1:
                # L1: Legal — generate compliant states
                context = {
                    "target_jurisdiction": "us",
                    "restricted_jurisdictions": ["iran", "north_korea"],
                    "export_controlled": False,
                    "pattern": "legal_pattern",
                }
                payload = {"content": "non_restricted"}

            elif level == 2:
                # L2: Ethical — generate ethical states
                context = {
                    "discrimination_markers": [],
                    "coercion": False,
                    "forced_action": False,
                    "undisclosed_processing": False,
                    "user_consent": True,
                }
                payload = {"intent": "transparent_operation"}

            elif level == 3:
                # L3: Permissions — generate authorized states
                context = {
                    "actor_permissions": {"read", "write"},
                    "required_permissions": {"read"},
                    "privilege_escalation_attempt": False,
                    "actor_role": "user",
                    "required_roles": ["user", "admin"],
                    "resource_usage": 50,
                    "resource_quota": 100,
                }
                payload = {"resource": "file_data"}

            else:  # level == 4
                # L4: Constitutional — generate constitutional states
                context = {
                    "outside_envelope": False,
                    "override_celestial_predicate": False,
                    "consistency_issues": [],
                    "state_corruption_detected": False,
                }
                payload = {"operation": "constitutional_action"}

            state = CelestialState(
                level=level,
                context=context,
                timestamp=timestamp,
                actor_id=actor_id,
                action=action,
                payload=payload,
            )
            states.append(state)

        return states

    def generate_violating_states(
        self, level: int, count: int = 100
    ) -> list[CelestialState]:
        """Generate states that SHOULD violate level `level` predicate.

        Creates states with constraint violations for the given level.
        Each state is designed to fail the predicate's validation checks.

        Args:
            level: Celestial level (0–4) for which to generate states.
            count: Number of states to generate (default 100).

        Returns:
            List of CelestialState instances that should violate the predicate.

        Raises:
            ValueError: If level is not in range 0–4.
        """
        if not 0 <= level <= 4:
            raise ValueError(f"Level must be 0–4, got {level}")

        states = []

        for i in range(count):
            timestamp = datetime.now(timezone.utc)
            actor_id = f"bad_actor_{level}_{i}"

            if level == 0:
                # L0: Safety — generate unsafe states
                harm_actions = [
                    "enable_weapon",
                    "execute_exploit",
                    "bypass_safety_control",
                    "disable_override",
                ]
                action = harm_actions[i % len(harm_actions)]
                context = {
                    "intent": "harm humans" if i % 2 == 0 else "normal",
                    "bypass_control": i % 3 == 0,
                }
                payload = {
                    "weapon": "explosive" if i % 2 == 0 else None,
                    "malware": "virus" if i % 4 == 0 else None,
                }

            elif level == 1:
                # L1: Legal — generate non-compliant states
                # Ensure we always have at least one violation
                action = "restricted_access"
                
                # Cycle through different violation types to ensure coverage
                violation_type = i % 3
                
                if violation_type == 0:
                    # Restricted jurisdiction violation
                    context = {
                        "target_jurisdiction": "iran",
                        "restricted_jurisdictions": ["iran", "north_korea"],
                        "export_controlled": False,
                        "pattern": "legal_pattern",
                    }
                elif violation_type == 1:
                    # Export controlled violation
                    context = {
                        "target_jurisdiction": "us",
                        "restricted_jurisdictions": ["iran"],
                        "export_controlled": True,
                        "pattern": "legal_pattern",
                    }
                else:
                    # Illegal pattern violation
                    context = {
                        "target_jurisdiction": "us",
                        "restricted_jurisdictions": ["iran"],
                        "export_controlled": False,
                        "pattern": "launder_money",
                    }
                
                payload = {
                    "content": "dmca_circumvention" if i % 2 == 0 else "normal"
                }

            elif level == 2:
                # L2: Ethical — generate unethical states
                deception_actions = ["mislead", "deceive", "manipulate", "impersonate"]
                action = deception_actions[i % len(deception_actions)]
                context = {
                    "discrimination_markers": (
                        ["race", "gender"] if i % 2 == 0 else []
                    ),
                    "coercion": i % 3 == 0,
                    "forced_action": i % 4 == 0,
                    "undisclosed_processing": i % 2 == 0,
                    "user_consent": i % 2 != 0,
                }
                payload = {"intent": action}

            elif level == 3:
                # L3: Permissions — generate unauthorized states
                action = "unauthorized_access"
                context = {
                    "actor_permissions": {"read"} if i % 2 == 0 else set(),
                    "required_permissions": {"read", "write", "admin"},
                    "privilege_escalation_attempt": i % 3 == 0,
                    "actor_role": "guest",
                    "required_roles": ["admin"],
                    "resource_usage": 150,
                    "resource_quota": 100,
                }
                payload = {"resource": "sensitive_file"}

            else:  # level == 4
                # L4: Constitutional — generate unconstitutional states
                bad_actions = [
                    "modify_predicate",
                    "patch_kernel",
                    "rewrite_constitution",
                    "disable_gating",
                ]
                action = bad_actions[i % len(bad_actions)]
                context = {
                    "outside_envelope": i % 2 == 0,
                    "override_celestial_predicate": i % 3 == 0,
                    "consistency_issues": (
                        ["data_mismatch"] if i % 2 == 0 else []
                    ),
                    "state_corruption_detected": i % 4 == 0,
                }
                payload = {"operation": action}

            state = CelestialState(
                level=level,
                context=context,
                timestamp=timestamp,
                actor_id=actor_id,
                action=action,
                payload=payload,
            )
            states.append(state)

        return states

    def generate_boundary_states(
        self, level: int, count: int = 20
    ) -> list[CelestialState]:
        """Generate edge cases near the level boundary.

        Creates states that test boundary conditions and edge cases:
        - Missing optional context fields
        - Empty payloads
        - Null values in context
        - Minimal vs. maximal configurations

        Args:
            level: Celestial level (0–4).
            count: Number of boundary states to generate (default 20).

        Returns:
            List of CelestialState instances representing boundary conditions.

        Raises:
            ValueError: If level is not in range 0–4.
        """
        if not 0 <= level <= 4:
            raise ValueError(f"Level must be 0–4, got {level}")

        states = []

        for i in range(count):
            timestamp = datetime.now(timezone.utc)
            actor_id = f"boundary_{level}_{i}"
            action = "boundary_action"

            # Create minimal context
            context: dict[str, Any] = {}
            payload: dict[str, Any] = {}

            # Add some fields but not all
            if i % 3 == 0:
                context = {}  # Empty context
                payload = {}  # Empty payload
            elif i % 3 == 1:
                context = {"level": level}  # Minimal context
                payload = {"data": None}  # Null payload value
            else:
                context = {
                    "extra_field": "value",
                    "nested": {"key": "value"},
                }
                payload = {}

            state = CelestialState(
                level=level,
                context=context,
                timestamp=timestamp,
                actor_id=actor_id,
                action=action,
                payload=payload,
            )
            states.append(state)

        return states


@dataclass(slots=True)
class PredicateValidationReport:
    """Results of validating a predicate against generated states.

    Metrics for evaluating predicate accuracy:
    - true_positives: states that should pass and did pass
    - true_negatives: states that should fail and did fail
    - false_positives: states that should fail but passed
    - false_negatives: states that should pass but failed

    Attributes:
        level: Celestial level validated (0–4).
        total_states: Total number of states tested.
        true_positives: Count of correctly accepted states.
        true_negatives: Count of correctly rejected states.
        false_positives: Count of incorrectly accepted states.
        false_negatives: Count of incorrectly rejected states.
        accuracy: (TP + TN) / Total (0.0–1.0).
        precision: TP / (TP + FP) (0.0–1.0, or NaN if TP + FP == 0).
        recall: TP / (TP + FN) (0.0–1.0, or NaN if TP + FN == 0).
    """

    level: int
    total_states: int
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    accuracy: float
    precision: float
    recall: float

    @property
    def is_valid(self) -> bool:
        """Returns True only if zero false positives AND zero false negatives.

        A predicate is considered fully valid only when it has perfect accuracy
        on the generated test set (no false positives or false negatives).

        Returns:
            True if false_positives == 0 and false_negatives == 0, else False.
        """
        return self.false_positives == 0 and self.false_negatives == 0


class PredicateValidator:
    """Validates predicate implementations against generated state sets.

    This validator runs property-based tests on predicates by generating
    large sets of states that should satisfy and violate each predicate,
    then checking if the predicate correctly classifies them.

    Attributes:
        generator: StateGenerator instance for creating test states.
    """

    def __init__(self, generator: StateGenerator | None = None) -> None:
        """Initialize validator with optional custom generator.

        Args:
            generator: Optional StateGenerator. Creates new one if None.
        """
        self.generator = generator or StateGenerator()

    def validate_predicate(
        self,
        predicate: CelestialPredicateProtocol,
        count: int = 200,
    ) -> PredicateValidationReport:
        """Run validation: generate satisfying and violating states.

        Tests the predicate against:
        - count/2 states that should satisfy (pass)
        - count/2 states that should violate (fail)

        Calculates TP/TN/FP/FN metrics and accuracy/precision/recall.

        Args:
            predicate: Predicate to validate (must implement CelestialPredicateProtocol).
            count: Total states to test (half satisfying, half violating).

        Returns:
            PredicateValidationReport with complete metrics.
        """
        level = predicate.level
        half_count = count // 2

        # Generate test states
        satisfying_states = self.generator.generate_satisfying_states(
            level, half_count
        )
        violating_states = self.generator.generate_violating_states(
            level, half_count
        )

        # Count correct and incorrect classifications
        true_positives = 0
        true_negatives = 0
        false_positives = 0
        false_negatives = 0

        # Test satisfying states (should pass)
        for state in satisfying_states:
            result = predicate.evaluate(state)
            if result.passed:
                true_positives += 1
            else:
                false_negatives += 1

        # Test violating states (should fail)
        for state in violating_states:
            result = predicate.evaluate(state)
            if not result.passed:
                true_negatives += 1
            else:
                false_positives += 1

        # Calculate metrics
        total = count
        accuracy = (true_positives + true_negatives) / total if total > 0 else 0.0

        if true_positives + false_positives > 0:
            precision = true_positives / (true_positives + false_positives)
        else:
            precision = 1.0 if true_positives == 0 else 0.0

        if true_positives + false_negatives > 0:
            recall = true_positives / (true_positives + false_negatives)
        else:
            recall = 1.0 if true_positives == 0 else 0.0

        return PredicateValidationReport(
            level=level,
            total_states=total,
            true_positives=true_positives,
            true_negatives=true_negatives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
        )

    def validate_all_levels(
        self, predicates: list[CelestialPredicateProtocol], count_per_level: int = 200
    ) -> dict[int, PredicateValidationReport]:
        """Validate all predicates across all levels.

        Tests each predicate in the list independently and returns a
        mapping from level to validation report.

        Args:
            predicates: List of predicates to validate.
            count_per_level: Total states to test per level (default 200).

        Returns:
            Dictionary mapping Celestial level → PredicateValidationReport.
        """
        reports: dict[int, PredicateValidationReport] = {}

        for predicate in predicates:
            report = self.validate_predicate(predicate, count_per_level)
            reports[predicate.level] = report

        return reports

    def assert_zero_false_positives_negatives(
        self, reports: dict[int, PredicateValidationReport]
    ) -> None:
        """Raises AssertionError if any level has false positives or negatives.

        Ensures that all predicates in the validation set achieved perfect
        accuracy (zero false positives and zero false negatives).

        Args:
            reports: Dictionary of level → PredicateValidationReport.

        Raises:
            AssertionError: If any report has FP > 0 or FN > 0.
        """
        for level, report in reports.items():
            if report.false_positives > 0:
                raise AssertionError(
                    f"Level {level} has {report.false_positives} false positives"
                )
            if report.false_negatives > 0:
                raise AssertionError(
                    f"Level {level} has {report.false_negatives} false negatives"
                )


def validate_celestial_predicates(
    count_per_level: int = 1000,
) -> dict[int, PredicateValidationReport]:
    """Main entry point: validate all 5 predicates with generated states.

    This is the primary validation function for the L0–L4 predicate hierarchy.
    It tests each of the five predicates with count_per_level states
    (count_per_level/2 satisfying + count_per_level/2 violating) per level,
    for a total of 5 * count_per_level states tested.

    The function ensures zero false positives and zero false negatives across
    all levels before returning the reports.

    Args:
        count_per_level: States to test per level (default 1000 per task spec).

    Returns:
        Dictionary mapping Celestial level (0–4) → PredicateValidationReport.

    Raises:
        AssertionError: If any predicate exhibits false positives or negatives.

    Example:
        >>> reports = validate_celestial_predicates(count_per_level=1000)
        >>> for level, report in reports.items():
        ...     print(f"Level {level}: {report.total_states} states tested")
        ...     print(f"  Accuracy: {report.accuracy:.2%}")
        ...     print(f"  Zero FP/FN: {report.is_valid}")
    """
    generator = StateGenerator()
    validator = PredicateValidator(generator)

    # Validate all five predicates
    reports = validator.validate_all_levels(DEFAULT_PREDICATES, count_per_level)

    # Ensure zero false positives and false negatives
    validator.assert_zero_false_positives_negatives(reports)

    return reports
