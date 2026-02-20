"""Integration tests for Phase D Safety Case.

Tests end-to-end construction and validation of the complete Phase D
safety case with ICD integration and 100% coverage validation.
"""

from __future__ import annotations

import pytest

from holly.safety.argument import (
    SafetyArgumentGraph,
    SafetyClaim,
    SafetyEvidence,
    SafetyGoal,
    SafetyStrategy,
    VerificationMethod,
    ClaimStatus,
    SILLevel,
)
from holly.safety.icd_integration import (
    ALL_ICDS,
    build_icd_trace_matrix,
    validate_icd_coverage,
)
from holly.safety.phase_d_safety_case import (
    PhaseDSafetyCase,
    build_phase_d_safety_case,
)


class TestPhaseDSafetyCaseCreation:
    """Tests for Phase D Safety Case creation and validation."""

    @pytest.fixture
    def basic_argument_graph(self) -> SafetyArgumentGraph:
        """Create a basic safety argument graph for testing."""
        graph = SafetyArgumentGraph()
        
        # Add goals
        goal = SafetyGoal(
            goal_id="G1",
            description="System safety goal",
            rationale="Required for safe operation",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        
        # Add evidence
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test_artifact.pdf",
            description="Safety analysis report",
            verification_method=VerificationMethod.ANALYSIS,
        )
        graph.add_evidence(evidence)
        
        # Add strategy
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy to achieve goal",
            parent_goal_id="G1",
        )
        graph.add_strategy(strategy)
        
        # Add claim citing ICD-001
        claim = SafetyClaim(
            claim_id="C1",
            description="User authentication enforced via ICD-001 OAuth2 boundary",
            goal_ref="G1",
            status=ClaimStatus.PROVEN,
            evidence_refs=["E1"],
        )
        graph.add_claim(claim)
        
        return graph

    def test_phase_d_creation_valid(self, basic_argument_graph: SafetyArgumentGraph) -> None:
        """Test creation of Phase D Safety Case with valid argument."""
        matrix = build_icd_trace_matrix(basic_argument_graph, ALL_ICDS)
        # Manually mark all ICDs as covered (since basic graph only covers a few)
        for icd_id in matrix.icds:
            if not matrix.trace_entries[icd_id].is_covered():
                matrix.add_icd_claim_link(icd_id, "C1")
        
        report = validate_icd_coverage(matrix)
        
        phase_d = PhaseDSafetyCase(
            argument_graph=basic_argument_graph,
            icd_trace_matrix=matrix,
            coverage_report=report,
        )
        
        assert phase_d.version == "D"
        assert phase_d.total_icds == 49
        assert phase_d.total_claims >= 1

    def test_phase_d_rejects_incomplete_coverage(
        self, basic_argument_graph: SafetyArgumentGraph
    ) -> None:
        """Test that Phase D rejects incomplete ICD coverage."""
        matrix = build_icd_trace_matrix(basic_argument_graph, ALL_ICDS)
        # Don't cover all ICDs
        
        # Build incomplete report
        from holly.safety.icd_integration import CoverageReport
        report = CoverageReport(
            total_icds=49,
            covered_icds=1,
            uncovered_icds=[f"ICD-{i:03d}" for i in range(2, 50)],
        )
        
        with pytest.raises(ValueError, match="incomplete"):
            PhaseDSafetyCase(
                argument_graph=basic_argument_graph,
                icd_trace_matrix=matrix,
                coverage_report=report,
            )

    def test_phase_d_properties(self, basic_argument_graph: SafetyArgumentGraph) -> None:
        """Test Phase D Safety Case properties."""
        matrix = build_icd_trace_matrix(basic_argument_graph, ALL_ICDS)
        for icd_id in matrix.icds:
            if not matrix.trace_entries[icd_id].is_covered():
                matrix.add_icd_claim_link(icd_id, "C1")
        
        report = validate_icd_coverage(matrix)
        phase_d = PhaseDSafetyCase(
            argument_graph=basic_argument_graph,
            icd_trace_matrix=matrix,
            coverage_report=report,
        )
        
        assert phase_d.coverage_percentage == 1.0
        assert phase_d.total_icds == 49


class TestPhaseDBuildFunction:
    """Tests for build_phase_d_safety_case function."""

    @pytest.fixture
    def complete_argument_graph(self) -> SafetyArgumentGraph:
        """Create a complete safety argument graph."""
        graph = SafetyArgumentGraph()
        
        # Add goal
        goal = SafetyGoal(
            goal_id="G-phase-d",
            description="Achieve Phase D safety case with full ICD integration",
            rationale="Complete safety assurance required",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        
        # Add evidence
        evidence = SafetyEvidence(
            evidence_id="E-phase-d",
            artifact_ref="phase_d_evidence.pdf",
            description="Complete ICD specification and safety analysis",
            verification_method=VerificationMethod.REVIEW,
        )
        graph.add_evidence(evidence)
        
        # Add strategy
        strategy = SafetyStrategy(
            strategy_id="S-phase-d",
            description="Integrate all ICDs with trace matrix",
            parent_goal_id="G-phase-d",
        )
        graph.add_strategy(strategy)
        
        # Add claims for multiple ICDs
        for i in range(1, 50):
            claim = SafetyClaim(
                claim_id=f"C-icd-{i:03d}",
                description=f"ICD-{i:03d} integrated with safety case",
                goal_ref="G-phase-d",
                status=ClaimStatus.PROVEN,
                evidence_refs=["E-phase-d"],
            )
            graph.add_claim(claim)
        
        return graph

    def test_build_phase_d_successful(
        self, complete_argument_graph: SafetyArgumentGraph
    ) -> None:
        """Test successful Phase D safety case construction."""
        phase_d = build_phase_d_safety_case(complete_argument_graph)
        
        assert phase_d is not None
        assert phase_d.version == "D"
        assert phase_d.coverage_report.is_complete
        assert phase_d.coverage_report.total_icds == 49
        assert phase_d.coverage_report.covered_icds == 49


class TestPhaseDBuildExports:
    """Tests for Phase D export functions."""

    @pytest.fixture
    def phase_d_with_coverage(self) -> PhaseDSafetyCase:
        """Create a Phase D safety case with full coverage."""
        graph = SafetyArgumentGraph()
        
        goal = SafetyGoal(
            goal_id="G1",
            description="Safety goal",
            rationale="Required",
            sil_level=SILLevel.SIL2,
        )
        graph.add_goal(goal)
        
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.pdf",
            description="Evidence",
            verification_method=VerificationMethod.TESTING,
        )
        graph.add_evidence(evidence)
        
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Strategy",
            parent_goal_id="G1",
        )
        graph.add_strategy(strategy)
        
        claim = SafetyClaim(
            claim_id="C1",
            description="All ICDs integrated",
            goal_ref="G1",
            status=ClaimStatus.PROVEN,
            evidence_refs=["E1"],
        )
        graph.add_claim(claim)
        
        matrix = build_icd_trace_matrix(graph, ALL_ICDS)
        for icd_id in matrix.icds:
            if not matrix.trace_entries[icd_id].is_covered():
                matrix.add_icd_claim_link(icd_id, "C1")
        
        report = validate_icd_coverage(matrix)
        
        return PhaseDSafetyCase(
            argument_graph=graph,
            icd_trace_matrix=matrix,
            coverage_report=report,
        )

    def test_export_json(self, phase_d_with_coverage: PhaseDSafetyCase) -> None:
        """Test JSON export of Phase D safety case."""
        export = phase_d_with_coverage.export_json()
        
        assert export["version"] == "D"
        assert "exported_at" in export
        assert "coverage" in export
        assert "argument_stats" in export
        assert "trace_matrix" in export
        
        coverage = export["coverage"]
        assert coverage["total_icds"] == 49
        assert coverage["is_complete"]

    def test_export_markdown(self, phase_d_with_coverage: PhaseDSafetyCase) -> None:
        """Test Markdown export of Phase D safety case."""
        markdown = phase_d_with_coverage.export_markdown()
        
        assert "Phase D Safety Case" in markdown
        assert "ICD Coverage Matrix" in markdown
        assert "All 49 ICDs are covered" in markdown
        assert "ICD-001" in markdown
        assert "ICD-049" in markdown

    def test_get_icd_summary(self, phase_d_with_coverage: PhaseDSafetyCase) -> None:
        """Test retrieving ICD summary."""
        summary = phase_d_with_coverage.get_icd_summary("ICD-001")
        
        assert summary is not None
        assert summary["icd_id"] == "ICD-001"
        assert "title" in summary
        assert "description" in summary
        assert "safety_properties" in summary
        assert "sil_level" in summary
        assert "claim_ids" in summary

    def test_get_nonexistent_icd_summary(
        self, phase_d_with_coverage: PhaseDSafetyCase
    ) -> None:
        """Test retrieving summary for nonexistent ICD."""
        summary = phase_d_with_coverage.get_icd_summary("ICD-999")
        assert summary is None


class TestPhaseD49ICDIntegration:
    """Integration tests specific to 49 ICD coverage."""

    def test_all_49_icds_in_constant(self) -> None:
        """Test that ALL_ICDS contains exactly 49 ICDs."""
        assert len(ALL_ICDS) == 49
        ids = [icd.icd_id for icd in ALL_ICDS]
        assert len(set(ids)) == 49  # All unique

    def test_icd_trace_matrix_with_all_icds(self) -> None:
        """Test trace matrix with all 49 ICDs."""
        graph = SafetyArgumentGraph()
        
        goal = SafetyGoal(
            goal_id="G1",
            description="Test goal",
            rationale="Test",
            sil_level=SILLevel.SIL1,
        )
        graph.add_goal(goal)
        
        evidence = SafetyEvidence(
            evidence_id="E1",
            artifact_ref="test.pdf",
            description="Test evidence",
            verification_method=VerificationMethod.TESTING,
        )
        graph.add_evidence(evidence)
        
        strategy = SafetyStrategy(
            strategy_id="S1",
            description="Test strategy",
            parent_goal_id="G1",
        )
        graph.add_strategy(strategy)
        
        claim = SafetyClaim(
            claim_id="C1",
            description="Test claim",
            goal_ref="G1",
            status=ClaimStatus.PROVEN,
            evidence_refs=["E1"],
        )
        graph.add_claim(claim)
        
        matrix = build_icd_trace_matrix(graph, ALL_ICDS)
        assert len(matrix.icds) == 49
        
        # Ensure all can be linked
        for icd_id in matrix.icds:
            matrix.add_icd_claim_link(icd_id, "C1")
        
        report = matrix.validate_coverage()
        assert report.total_icds == 49
        assert report.covered_icds == 49
