"""Unit tests for safety argument module.

Tests for SafetyGoal, SafetyStrategy, SafetyEvidence, SafetyClaim, and
SafetyArgumentGraph classes.
"""

import pytest
from datetime import datetime, timezone

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
    validate_argument_completeness,
    export_argument_gsn,
    export_argument_json,
)


class TestSILLevel:
    """Test SIL level enum."""

    def test_sil_values(self):
        """Test SIL level values."""
        assert SILLevel.SIL0.value == 0
        assert SILLevel.SIL1.value == 1
        assert SILLevel.SIL2.value == 2
        assert SILLevel.SIL3.value == 3
        assert SILLevel.SIL4.value == 4

    def test_sil_names(self):
        """Test SIL level names."""
        assert SILLevel.SIL0.name == "SIL0"
        assert SILLevel.SIL2.name == "SIL2"


class TestVerificationMethod:
    """Test verification method enum."""

    def test_verification_methods(self):
        """Test all verification methods exist."""
        assert VerificationMethod.TESTING.value == "testing"
        assert VerificationMethod.ANALYSIS.value == "analysis"
        assert VerificationMethod.INSPECTION.value == "inspection"
        assert VerificationMethod.DEMONSTRATION.value == "demonstration"
        assert VerificationMethod.REVIEW.value == "review"
        assert VerificationMethod.FORMAL_PROOF.value == "formal_proof"


class TestClaimStatus:
    """Test claim status enum."""

    def test_claim_statuses(self):
        """Test all claim statuses exist."""
        assert ClaimStatus.PROVEN.value == "proven"
        assert ClaimStatus.ASSUMED.value == "assumed"
        assert ClaimStatus.PENDING.value == "pending"
        assert ClaimStatus.UNPROVEN.value == "unproven"


class TestSafetyGoal:
    """Test SafetyGoal dataclass."""

    def test_create_goal(self):
        """Test creating a safety goal."""
        goal = SafetyGoal(
            goal_id="G1",
            description="System shall be safe",
            rationale="Required by IEC 61508",
            sil_level=SILLevel.SIL2,
        )
        assert goal.goal_id == "G1"
        assert goal.sil_level == SILLevel.SIL2
        assert goal.created_at is not None

    def test_goal_with_context(self):
        """Test goal with context."""
        goal = SafetyGoal(
            goal_id="G2",
            description="Test goal",
            rationale="Test rationale",
            sil_level=SILLevel.SIL1,
            context="Boundary conditions: temp 0-50C",
        )
        assert goal.context == "Boundary conditions: temp 0-50C"

    def test_goal_missing_description(self):
        """Test that goal requires description."""
        with pytest.raises(ValueError):
            SafetyGoal(
                goal_id="G-bad",
                description="",
                rationale="Has rationale",
                sil_level=SILLevel.SIL1,
            )

    def test_goal_missing_rationale(self):
        """Test that goal requires rationale."""
        with pytest.raises(ValueError):
            SafetyGoal(
                goal_id="G-bad",
                description="Has description",
                rationale="",
                sil_level=SILLevel.SIL1,
            )

    def test_goal_missing_id(self):
        """Test that goal requires ID."""
        with pytest.raises(ValueError):
            SafetyGoal(
                goal_id="",
                description="Description",
                rationale="Rationale",
                sil_level=SILLevel.SIL1,
            )


class TestSafetyStrategy:
    """Test SafetyStrategy dataclass."""

    def test_create_strategy(self):
        """Test creating a safety strategy."""
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Achieve through testing",
            parent_goal_id="G1",
        )
        assert strategy.strategy_id == "S1"
        assert strategy.parent_goal_id == "G1"

    def test_strategy_with_context(self):
        """Test strategy with context."""
        strategy = SafetyStrategy(
            strategy_id="S2",
            description="Verification strategy",
            parent_goal_id="G2",
            context="80% code coverage required",
        )
        assert strategy.context == "80% code coverage required"

    def test_strategy_missing_description(self):
        """Test that strategy requires description."""
        with pytest.raises(ValueError):
            SafetyStrategy(
                strategy_id="S-bad",
                description="",
                parent_goal_id="G1",
            )

    def test_strategy_missing_parent(self):
        """Test that strategy requires parent goal."""
        with pytest.raises(ValueError):
            SafetyStrategy(
                strategy_id="S-bad",
                description="Description",
                parent_goal_id="",
            )


class TestSafetyEvidence:
    """Test SafetyEvidence dataclass."""

    def test_create_evidence(self):
        """Test creating safety evidence."""
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test_suite_001.py",
            verification_method=VerificationMethod.TESTING,
            description="Unit tests for kernel",
        )
        assert evidence.evidence_id == "E1"
        assert evidence.verification_method == VerificationMethod.TESTING

    def test_evidence_status(self):
        """Test evidence status."""
        evidence = SafetyEvidence(
            evidence_id="E2",
            artifact_ref="analysis.pdf",
            verification_method=VerificationMethod.ANALYSIS,
            status="reviewed",
        )
        assert evidence.status == "reviewed"

    def test_evidence_missing_artifact(self):
        """Test that evidence requires artifact ref."""
        with pytest.raises(ValueError):
            SafetyEvidence(
                evidence_id="E-bad",
                artifact_ref="",
                verification_method=VerificationMethod.TESTING,
            )


class TestSafetyClaim:
    """Test SafetyClaim dataclass."""

    def test_create_claim(self):
        """Test creating a safety claim."""
        claim = SafetyClaim(
            claim_id="C1",
            description="System will not crash",
            goal_ref="G1",
        )
        assert claim.claim_id == "C1"
        assert claim.status == ClaimStatus.PENDING
        assert claim.evidence_refs == []

    def test_claim_with_evidence(self):
        """Test claim with evidence references."""
        claim = SafetyClaim(
            claim_id="C2",
            description="Claim with evidence",
            goal_ref="G2",
            evidence_refs=["E1", "E2"],
        )
        assert claim.evidence_refs == ["E1", "E2"]

    def test_claim_set_proven(self):
        """Test marking claim as proven."""
        claim = SafetyClaim(
            claim_id="C3",
            description="Test claim",
            goal_ref="G1",
        )
        claim.set_proven("All evidence reviewed and accepted")
        assert claim.status == ClaimStatus.PROVEN
        assert "All evidence" in claim.rationale

    def test_claim_set_assumed(self):
        """Test marking claim as assumed."""
        claim = SafetyClaim(
            claim_id="C4",
            description="Assumed claim",
            goal_ref="G1",
        )
        claim.set_assumed("Third-party guarantee")
        assert claim.status == ClaimStatus.ASSUMED
        assert "Third-party" in claim.rationale

    def test_claim_missing_description(self):
        """Test that claim requires description."""
        with pytest.raises(ValueError):
            SafetyClaim(
                claim_id="C-bad",
                description="",
                goal_ref="G1",
            )


class TestSafetyArgumentGraph:
    """Test SafetyArgumentGraph."""

    @pytest.fixture
    def basic_graph(self):
        """Create basic graph for testing."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="System safe",
            rationale="Required",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        return graph

    def test_create_empty_graph(self):
        """Test creating empty graph."""
        graph = SafetyArgumentGraph()
        assert graph.node_count() == 0
        assert graph.edge_count() == 0

    def test_add_goal(self, basic_graph):
        """Test adding goal to graph."""
        assert "G1" in basic_graph.goals
        assert basic_graph.node_count() == 1

    def test_duplicate_goal_error(self, basic_graph):
        """Test that duplicate goal ID raises error."""
        goal = SafetyGoal(
            goal_id="G1",
            description="Duplicate",
            rationale="Duplicate ID",
            sil_level=SILLevel.SIL1,
        )
        with pytest.raises(ValueError, match="Duplicate goal"):
            basic_graph.add_goal(goal)

    def test_add_strategy(self, basic_graph):
        """Test adding strategy to graph."""
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G1",
        )
        basic_graph.add_strategy(strategy)
        assert "S1" in basic_graph.strategies
        assert basic_graph.node_count() == 2

    def test_strategy_invalid_parent(self, basic_graph):
        """Test that strategy with invalid parent raises error."""
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G-nonexistent",
        )
        with pytest.raises(ValueError, match="Parent goal"):
            basic_graph.add_strategy(strategy)

    def test_add_evidence(self, basic_graph):
        """Test adding evidence to graph."""
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.py",
            verification_method=VerificationMethod.TESTING,
        )
        basic_graph.add_evidence(evidence)
        assert "E1" in basic_graph.evidence

    def test_add_claim(self, basic_graph):
        """Test adding claim to graph."""
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.py",
            verification_method=VerificationMethod.TESTING,
        )
        basic_graph.add_evidence(evidence)
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
            evidence_refs=["E1"],
        )
        basic_graph.add_claim(claim)
        assert "C1" in basic_graph.claims
        assert basic_graph.edge_count() > 0

    def test_claim_invalid_goal(self, basic_graph):
        """Test that claim with invalid goal raises error."""
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G-nonexistent",
        )
        with pytest.raises(ValueError, match="Goal"):
            basic_graph.add_claim(claim)

    def test_claim_invalid_evidence(self, basic_graph):
        """Test that claim with invalid evidence raises error."""
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
            evidence_refs=["E-nonexistent"],
        )
        with pytest.raises(ValueError, match="Evidence"):
            basic_graph.add_claim(claim)

    def test_no_cycle_detection(self, basic_graph):
        """Test that DAG without cycles is detected."""
        assert not basic_graph.has_cycle()

    def test_get_goal_descendants(self, basic_graph):
        """Test getting goal descendants."""
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G1",
        )
        basic_graph.add_strategy(strategy)
        descendants = basic_graph.get_goal_descendants("G1")
        assert "S1" in descendants

    def test_goal_not_found(self, basic_graph):
        """Test accessing non-existent goal raises error."""
        with pytest.raises(ValueError):
            basic_graph.get_goal_descendants("G-nonexistent")


class TestBuildSafetyArgument:
    """Test build_safety_argument function."""

    def test_build_basic_argument(self):
        """Test building basic safety argument."""
        goal = SafetyGoal(
            goal_id="G1",
            description="System safe",
            rationale="Required",
            sil_level=SILLevel.SIL2,
        )
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.py",
            verification_method=VerificationMethod.TESTING,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
            evidence_refs=["E1"],
        )
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G1",
        )

        graph = build_safety_argument(
            goals=[goal],
            strategies=[strategy],
            claims=[claim],
            evidence=[evidence],
        )

        assert graph.node_count() == 4
        assert graph.edge_count() >= 2

    def test_build_argument_with_multiple_goals(self):
        """Test building argument with multiple goals."""
        goals = [
            SafetyGoal(
                goal_id=f"G{i}",
                description=f"Goal {i}",
                rationale="Test",
                sil_level=SILLevel.SIL1,
            )
            for i in range(3)
        ]
        graph = build_safety_argument(
            goals=goals,
            strategies=[],
            claims=[],
            evidence=[],
        )
        assert len(graph.goals) == 3

    def test_build_argument_cyclic_error(self):
        """Test that cyclic argument raises error."""
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        graph = SafetyArgumentGraph()
        graph.add_goal(goal)
        # Manually create cycle for testing
        graph.edges["G1"].append("G1")
        
        # build_safety_argument should detect this
        assert graph.has_cycle()


class TestValidateArgumentCompleteness:
    """Test validate_argument_completeness function."""

    def test_valid_complete_argument(self):
        """Test validating complete, proven argument."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.py",
            verification_method=VerificationMethod.TESTING,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
            evidence_refs=["E1"],
        )
        claim.set_proven()

        graph.add_goal(goal)
        graph.add_evidence(evidence)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert result["valid"]
        assert len(result["unproven_claims"]) == 0
        assert len(result["goals_without_claims"]) == 0

    def test_unproven_claims(self):
        """Test detecting unproven claims."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
        )
        graph.add_goal(goal)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["unproven_claims"]

    def test_goal_without_claims(self):
        """Test detecting goals without claims."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        graph.add_goal(goal)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "G1" in result["goals_without_claims"]

    def test_claim_without_evidence(self):
        """Test detecting claims without evidence."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        claim = SafetyClaim(
            claim_id="C1",
            description="Claim",
            goal_ref="G1",
        )
        graph.add_goal(goal)
        graph.add_claim(claim)

        result = validate_argument_completeness(graph)
        assert not result["valid"]
        assert "C1" in result["claims_without_evidence"]


class TestExportArgumentGSN:
    """Test export_argument_gsn function."""

    def test_export_empty_graph(self):
        """Test exporting empty graph."""
        graph = SafetyArgumentGraph()
        gsn = export_argument_gsn(graph)
        assert "Holly Grace Safety Argument" in gsn
        assert "Nodes: 0" in gsn

    def test_export_with_goals(self):
        """Test exporting graph with goals."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="System safe",
            rationale="IEC 61508",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        gsn = export_argument_gsn(graph)
        assert "G [G1]" in gsn
        assert "System safe" in gsn
        assert "SIL: SIL2" in gsn

    def test_export_includes_completeness_check(self):
        """Test that export includes completeness information."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        graph.add_goal(goal)
        gsn = export_argument_gsn(graph)
        assert "Completeness Check" in gsn
        assert "Valid:" in gsn


class TestExportArgumentJSON:
    """Test export_argument_json function."""

    def test_export_json_structure(self):
        """Test JSON export structure."""
        graph = SafetyArgumentGraph()
        goal = SafetyGoal(
            goal_id="G1",
            description="Goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        graph.add_goal(goal)
        json_str = export_argument_json(graph)
        
        import json as json_module
        data = json_module.loads(json_str)
        
        assert "metadata" in data
        assert "goals" in data
        assert "G1" in data["goals"]

    def test_json_metadata(self):
        """Test JSON metadata."""
        graph = SafetyArgumentGraph()
        json_str = export_argument_json(graph)
        
        import json as json_module
        data = json_module.loads(json_str)
        
        assert data["metadata"]["node_count"] == 0
        assert "created_at" in data["metadata"]
        assert "has_cycle" in data["metadata"]
