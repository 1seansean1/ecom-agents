"""Integration tests for safety argument module.

Tests complete safety argument workflows, GSN export, and validation.
"""

import json
import pytest

from holly.safety.argument import (
    ClaimStatus,
    SafetyArgumentGraph,
    SafetyClaim,
    SafetyEvidence,
    SafetyGoal,
    SafetyStrategy,
    SILLevel,
    VerificationMethod,
    build_safety_argument,
    export_argument_gsn,
    export_argument_json,
    validate_argument_completeness,
)


class TestCompleteHollyGraceArgument:
    """Test building complete Holly Grace safety argument."""

    @pytest.fixture
    def holly_grace_argument(self):
        """Build complete Holly Grace safety argument with multiple layers."""
        # Level 0: Celestial Constraints
        goals = [
            SafetyGoal(
                goal_id="G-celestial-0",
                description="Holly Grace shall not cause harm to humans",
                rationale="Fundamental safety requirement for autonomous agents",
                sil_level=SILLevel.SIL2,
                context="Applies in all operating modes",
            ),
            SafetyGoal(
                goal_id="G-celestial-1",
                description="Holly Grace shall maintain mission integrity",
                rationale="System must complete assigned tasks safely",
                sil_level=SILLevel.SIL2,
                context="With SIL-2 assurance per IEC 61508",
            ),
            SafetyGoal(
                goal_id="G-celestial-2",
                description="Holly Grace shall respect human autonomy",
                rationale="User must retain control over agent actions",
                sil_level=SILLevel.SIL1,
                context="Via explicit approval mechanisms",
            ),
        ]

        # Strategies to achieve goals
        strategies = [
            SafetyStrategy(
                strategy_id="S-integrity",
                description="Verify system integrity via kernel isolation",
                parent_goal_id="G-celestial-0",
                context="Kernel provides memory safety guarantees",
            ),
            SafetyStrategy(
                strategy_id="S-monitoring",
                description="Continuous safety monitoring and anomaly detection",
                parent_goal_id="G-celestial-1",
                context="Real-time checks every 100ms",
            ),
            SafetyStrategy(
                strategy_id="S-control",
                description="Human-in-the-loop with explicit approval",
                parent_goal_id="G-celestial-2",
                context="Requires user confirmation for critical actions",
            ),
        ]

        # Evidence from testing and analysis
        evidence = [
            SafetyEvidence(
                evidence_id="E-kernel-tests",
                artifact_ref="tests/unit/test_kernel.py",
                verification_method=VerificationMethod.TESTING,
                description="Kernel memory safety and boundary tests",
                status="passed",
            ),
            SafetyEvidence(
                evidence_id="E-formal-proof",
                artifact_ref="docs/proofs/kernel_safety.pdf",
                verification_method=VerificationMethod.FORMAL_PROOF,
                description="Formal proof of kernel isolation properties",
                status="reviewed",
            ),
            SafetyEvidence(
                evidence_id="E-monitor-tests",
                artifact_ref="tests/unit/test_monitor.py",
                verification_method=VerificationMethod.TESTING,
                description="Safety monitor functional tests",
                status="passed",
            ),
            SafetyEvidence(
                evidence_id="E-integration-tests",
                artifact_ref="tests/integration/test_safety_integration.py",
                verification_method=VerificationMethod.TESTING,
                description="End-to-end safety workflow tests",
                status="passed",
            ),
            SafetyEvidence(
                evidence_id="E-control-inspection",
                artifact_ref="docs/control_flow_inspection.md",
                verification_method=VerificationMethod.INSPECTION,
                description="Control flow inspection for approval checks",
                status="approved",
            ),
        ]

        # Claims linking goals to evidence
        claims = [
            SafetyClaim(
                claim_id="C1",
                description="Kernel isolation prevents unauthorized memory access",
                goal_ref="G-celestial-0",
                evidence_refs=["E-kernel-tests", "E-formal-proof"],
            ),
            SafetyClaim(
                claim_id="C2",
                description="Monitoring detects and stops unsafe behavior",
                goal_ref="G-celestial-1",
                evidence_refs=["E-monitor-tests", "E-integration-tests"],
            ),
            SafetyClaim(
                claim_id="C3",
                description="Control mechanisms enforce human approval",
                goal_ref="G-celestial-2",
                evidence_refs=["E-control-inspection"],
            ),
        ]

        # Mark claims as proven
        claims[0].set_proven("All kernel tests pass; formal proof accepted")
        claims[1].set_proven("Monitor tests 100% pass; integration verified")
        claims[2].set_proven("Control flow inspection complete and approved")

        return build_safety_argument(
            goals=goals,
            strategies=strategies,
            claims=claims,
            evidence=evidence,
        )

    def test_complete_argument_structure(self, holly_grace_argument):
        """Test that complete argument has expected structure."""
        assert len(holly_grace_argument.goals) == 3
        assert len(holly_grace_argument.strategies) == 3
        assert len(holly_grace_argument.claims) == 3
        assert len(holly_grace_argument.evidence) == 5
        assert holly_grace_argument.node_count() == 14

    def test_complete_argument_is_valid(self, holly_grace_argument):
        """Test that complete argument validates successfully."""
        result = validate_argument_completeness(holly_grace_argument)
        assert result["valid"]
        assert len(result["unproven_claims"]) == 0
        assert len(result["goals_without_claims"]) == 0
        assert len(result["claims_without_evidence"]) == 0

    def test_complete_argument_no_cycles(self, holly_grace_argument):
        """Test that complete argument has no cycles."""
        assert not holly_grace_argument.has_cycle()

    def test_gsn_export_complete(self, holly_grace_argument):
        """Test GSN export of complete argument."""
        gsn = export_argument_gsn(holly_grace_argument)
        
        # Check structure
        assert "Holly Grace Safety Argument" in gsn
        assert "## Goals" in gsn
        assert "## Strategies" in gsn
        assert "## Claims" in gsn
        assert "## Evidence" in gsn
        assert "## Completeness Check" in gsn
        
        # Check content
        assert "G-celestial-0" in gsn
        assert "S-integrity" in gsn
        assert "C1" in gsn
        assert "E-kernel-tests" in gsn
        
        # Check validity marker
        assert "Valid: True" in gsn

    def test_json_export_complete(self, holly_grace_argument):
        """Test JSON export of complete argument."""
        json_str = export_argument_json(holly_grace_argument)
        data = json.loads(json_str)
        
        # Check structure
        assert data["metadata"]["node_count"] == 14
        assert len(data["goals"]) == 3
        assert len(data["strategies"]) == 3
        assert len(data["claims"]) == 3
        assert len(data["evidence"]) == 5
        
        # Check specific content
        assert "G-celestial-0" in data["goals"]
        assert data["goals"]["G-celestial-0"]["sil_level"] == "SIL2"

    def test_descendant_tracking(self, holly_grace_argument):
        """Test that descendant relationships are tracked."""
        descendants = holly_grace_argument.get_goal_descendants("G-celestial-0")
        assert "S-integrity" in descendants
        assert "C1" in descendants

    def test_claim_status_tracking(self, holly_grace_argument):
        """Test that all claims have expected status."""
        for claim in holly_grace_argument.claims.values():
            assert claim.status == ClaimStatus.PROVEN


class TestIncompleteArgumentValidation:
    """Test validation of incomplete arguments detects gaps."""

    def test_unproven_claim_detection(self):
        """Test that unproven claims are detected."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Unproven claim",
            goal_ref="G1",
        )
        graph.add_goal(goal)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["unproven_claims"]

    def test_missing_evidence_detection(self):
        """Test that claims without evidence are detected."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim without evidence",
            goal_ref="G1",
        )
        claim.set_proven()
        graph.add_goal(goal)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["claims_without_evidence"]

    def test_multiple_gaps(self):
        """Test detection of multiple validation gaps."""
        graph = SafetyArgumentGraph()
        goal1 = SafetyGoal(
            goal_id="G1",
            description="Goal 1",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        goal2 = SafetyGoal(
            goal_id="G2",
            description="Goal 2",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        claim1 = SafetyClaim(
            claim_id="C1",
            description="Unproven",
            goal_ref="G1",
        )

        graph.add_goal(goal1)
        graph.add_goal(goal2)
        graph.add_claim(claim1)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["unproven_claims"]
        assert "G2" in result["goals_without_claims"]


class TestArgumentBuilderWorkflow:
    """Test end-to-end argument building workflows."""

    def test_incremental_argument_building(self):
        """Test building argument incrementally."""
        graph = SafetyArgumentGraph()

        # Add goals
        goal = SafetyGoal(
            goal_id="G1",
            description="System safe",
            rationale="Required",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        assert len(graph.goals) == 1

        # Add strategy
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G1",
        )
        graph.add_strategy(strategy)
        assert len(graph.strategies) == 1

        # Add evidence
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.py",
            verification_method=VerificationMethod.TESTING,
        )
        graph.add_evidence(evidence)
        assert len(graph.evidence) == 1

        # Add claim
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
            evidence_refs=["E1"],
        )
        claim.set_proven()
        graph.add_claim(claim)
        assert len(graph.claims) == 1

        # Verify
        result = validate_argument_completeness(graph)
        assert result["valid"]

    def test_multiple_claims_per_goal(self):
        """Test goal with multiple supporting claims."""
        graph = SafetyArgumentGraph()

        goal = SafetyGoal(
            goal_id="G1",
            description="System safe",
            rationale="Required",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)

        evidence_list = [
            SafetyEvidence(
                evidence_id=f"E{i}",
                artifact_ref=f"test{i}.py",
                verification_method=VerificationMethod.TESTING,
            )
            for i in range(3)
        ]
        for e in evidence_list:
            graph.add_evidence(e)

        claims = [
            SafetyClaim(
                claim_id=f"C{i}",
                description=f"Claim {i}",
                goal_ref="G1",
                evidence_refs=[f"E{i}"],
            )
            for i in range(3)
        ]
        for c in claims:
            c.set_proven()
            graph.add_claim(c)

        result = validate_argument_completeness(graph)
        assert result["valid"]
        assert len(graph.claims) == 3

    def test_export_roundtrip_consistency(self):
        """Test that GSN export is consistent."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Test goal",
            rationale="Test rationale",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)

        export1 = export_argument_gsn(graph)
        export2 = export_argument_gsn(graph)

        # Exports should be consistent (ignoring timestamps)
        assert "G1" in export1
        assert "G1" in export2
        assert "Test goal" in export1
        assert "Test goal" in export2


class TestArgumentEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_goal_list(self):
        """Test building argument with empty goal list."""
        graph = build_safety_argument(
            goals=[],
            strategies=[],
            claims=[],
            evidence=[],
        )
        assert graph.node_count() == 0
        result = validate_argument_completeness(graph)
        assert result["valid"]

    def test_large_argument_structure(self):
        """Test building large argument with many nodes."""
        goals = [
            SafetyGoal(
                goal_id=f"G{i}",
                description=f"Goal {i}",
                rationale="Test",
                sil_level=SILLevel.SIL1,
            )
            for i in range(10)
        ]

        evidence = [
            SafetyEvidence(
                evidence_id=f"E{i}",
                artifact_ref=f"test{i}.py",
                verification_method=VerificationMethod.TESTING,
            )
            for i in range(10)
        ]

        claims = [
            SafetyClaim(
                claim_id=f"C{i}",
                description=f"Claim {i}",
                goal_ref=f"G{i}",
                evidence_refs=[f"E{i}"],
            )
            for i in range(10)
        ]
        for c in claims:
            c.set_proven()

        graph = build_safety_argument(
            goals=goals,
            strategies=[],
            claims=claims,
            evidence=evidence,
        )

        assert graph.node_count() == 30
        result = validate_argument_completeness(graph)
        assert result["valid"]

    def test_assumed_claim_in_argument(self):
        """Test handling of assumed (not proven) claims."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="vendor.pdf",
            verification_method=VerificationMethod.ANALYSIS,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Vendor claim",
            goal_ref="G1",
            evidence_refs=["E1"],
        )
        claim.set_assumed("Third-party guarantee")

        graph.add_goal(goal)
        graph.add_evidence(evidence)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["unproven_claims"]

    def test_json_roundtrip(self):
        """Test JSON export and parse consistency."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Rationale",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)

        json_str = export_argument_json(graph)
        data = json.loads(json_str)

        assert data["goals"]["G1"]["description"] == "Goal"
        assert data["goals"]["G1"]["sil_level"] == "SIL2"
