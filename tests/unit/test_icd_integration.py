"""Unit tests for ICD integration module.

Tests dataclass creation, validation, trace matrix construction,
and coverage validation for ICD safety case integration.
"""

from __future__ import annotations

import pytest

from holly.safety.argument import SILLevel
from holly.safety.icd_integration import (
    ALL_ICDS,
    CoverageReport,
    CoverageStatus,
    ICD,
    ICDTraceEntry,
    ICDTraceMatrix,
    validate_icd_coverage,
)


class TestICDDataclass:
    """Tests for ICD dataclass creation and validation."""

    def test_icd_creation_valid(self) -> None:
        """Test creation of valid ICD."""
        icd = ICD(
            icd_id="ICD-001",
            title="Test ICD",
            description="Test description",
            safety_properties=["property1"],
            sil_level=SILLevel.SIL1,
        )
        assert icd.icd_id == "ICD-001"
        assert icd.title == "Test ICD"
        assert icd.description == "Test description"
        assert icd.safety_properties == ["property1"]
        assert icd.sil_level == SILLevel.SIL1

    def test_icd_creation_minimal(self) -> None:
        """Test creation with minimal required fields."""
        icd = ICD(
            icd_id="ICD-002",
            title="Minimal ICD",
            description="Minimal description",
        )
        assert icd.icd_id == "ICD-002"
        assert icd.safety_properties == []
        assert icd.sil_level == SILLevel.SIL1
        assert icd.protocol == "unknown"
        assert icd.direction == "unidirectional"

    def test_icd_invalid_id_format(self) -> None:
        """Test validation rejects invalid ICD ID format."""
        with pytest.raises(ValueError, match="Invalid ICD ID"):
            ICD(
                icd_id="INVALID-001",
                title="Test",
                description="Test",
            )

    def test_icd_missing_title(self) -> None:
        """Test validation rejects missing title."""
        with pytest.raises(ValueError, match="title and description required"):
            ICD(
                icd_id="ICD-001",
                title="",
                description="Test",
            )

    def test_icd_missing_description(self) -> None:
        """Test validation rejects missing description."""
        with pytest.raises(ValueError, match="title and description required"):
            ICD(
                icd_id="ICD-001",
                title="Test",
                description="",
            )

    def test_icd_all_sil_levels(self) -> None:
        """Test ICD accepts all SIL levels."""
        for sil in SILLevel:
            icd = ICD(
                icd_id="ICD-001",
                title="Test",
                description="Test",
                sil_level=sil,
            )
            assert icd.sil_level == sil


class TestICDTraceEntry:
    """Tests for ICDTraceEntry dataclass."""

    def test_trace_entry_creation(self) -> None:
        """Test creation of trace entry."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        assert entry.icd_id == "ICD-001"
        assert entry.claim_ids == []
        assert entry.coverage_status == CoverageStatus.UNCOVERED

    def test_trace_entry_add_claim(self) -> None:
        """Test adding claims to trace entry."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        entry.add_claim("claim-1")
        assert "claim-1" in entry.claim_ids
        assert entry.is_covered()

    def test_trace_entry_no_duplicate_claims(self) -> None:
        """Test that duplicate claims are not added."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        entry.add_claim("claim-1")
        entry.add_claim("claim-1")
        assert entry.claim_ids.count("claim-1") == 1

    def test_trace_entry_multiple_claims(self) -> None:
        """Test adding multiple claims."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        entry.add_claim("claim-1")
        entry.add_claim("claim-2")
        entry.add_claim("claim-3")
        assert len(entry.claim_ids) == 3
        assert entry.is_covered()

    def test_trace_entry_is_covered_empty(self) -> None:
        """Test is_covered returns False for empty claims."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        assert not entry.is_covered()

    def test_trace_entry_is_covered_with_claims(self) -> None:
        """Test is_covered returns True with claims."""
        entry = ICDTraceEntry(icd_id="ICD-001")
        entry.add_claim("claim-1")
        assert entry.is_covered()


class TestICDTraceMatrix:
    """Tests for ICDTraceMatrix construction and validation."""

    def test_matrix_creation(self) -> None:
        """Test creation of empty trace matrix."""
        matrix = ICDTraceMatrix()
        assert len(matrix.icds) == 0
        assert len(matrix.trace_entries) == 0

    def test_matrix_add_icd(self) -> None:
        """Test adding ICDs to matrix."""
        matrix = ICDTraceMatrix()
        icd = ICD(
            icd_id="ICD-001",
            title="Test",
            description="Test",
        )
        matrix.add_icd(icd)
        assert icd.icd_id in matrix.icds
        assert icd.icd_id in matrix.trace_entries

    def test_matrix_duplicate_icd_raises(self) -> None:
        """Test that duplicate ICD ID raises error."""
        matrix = ICDTraceMatrix()
        icd1 = ICD(icd_id="ICD-001", title="Test", description="Test")
        icd2 = ICD(icd_id="ICD-001", title="Other", description="Other")
        matrix.add_icd(icd1)
        with pytest.raises(ValueError, match="Duplicate ICD ID"):
            matrix.add_icd(icd2)

    def test_matrix_add_icd_claim_link(self) -> None:
        """Test linking ICD to claim."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        assert "claim-1" in matrix.trace_entries["ICD-001"].claim_ids

    def test_matrix_link_nonexistent_icd_raises(self) -> None:
        """Test linking to nonexistent ICD raises error."""
        matrix = ICDTraceMatrix()
        with pytest.raises(ValueError, match="ICD .* not found"):
            matrix.add_icd_claim_link("ICD-999", "claim-1")

    def test_matrix_get_icd_coverage(self) -> None:
        """Test retrieving ICD coverage entry."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        entry = matrix.get_icd_coverage("ICD-001")
        assert entry is not None
        assert entry.icd_id == "ICD-001"

    def test_matrix_get_nonexistent_icd_coverage(self) -> None:
        """Test retrieving coverage for nonexistent ICD."""
        matrix = ICDTraceMatrix()
        entry = matrix.get_icd_coverage("ICD-999")
        assert entry is None

    def test_matrix_get_icds_for_claim(self) -> None:
        """Test reverse lookup: claim to ICDs."""
        matrix = ICDTraceMatrix()
        icd1 = ICD(icd_id="ICD-001", title="Test1", description="Test1")
        icd2 = ICD(icd_id="ICD-002", title="Test2", description="Test2")
        matrix.add_icd(icd1)
        matrix.add_icd(icd2)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        matrix.add_icd_claim_link("ICD-002", "claim-1")
        
        icds = matrix.get_icds_for_claim("claim-1")
        assert "ICD-001" in icds
        assert "ICD-002" in icds

    def test_matrix_validate_coverage_complete(self) -> None:
        """Test coverage validation with complete coverage."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        
        report = matrix.validate_coverage()
        assert report.total_icds == 1
        assert report.covered_icds == 1
        assert report.is_complete
        assert len(report.uncovered_icds) == 0

    def test_matrix_validate_coverage_incomplete(self) -> None:
        """Test coverage validation with uncovered ICD."""
        matrix = ICDTraceMatrix()
        icd1 = ICD(icd_id="ICD-001", title="Test1", description="Test1")
        icd2 = ICD(icd_id="ICD-002", title="Test2", description="Test2")
        matrix.add_icd(icd1)
        matrix.add_icd(icd2)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        
        report = matrix.validate_coverage()
        assert report.total_icds == 2
        assert report.covered_icds == 1
        assert not report.is_complete
        assert "ICD-002" in report.uncovered_icds

    def test_matrix_validate_coverage_redundant(self) -> None:
        """Test coverage validation detects redundant ICDs."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        matrix.add_icd_claim_link("ICD-001", "claim-2")
        
        report = matrix.validate_coverage()
        assert "ICD-001" in report.redundant_icds

    def test_matrix_export_trace_matrix(self) -> None:
        """Test exporting trace matrix."""
        matrix = ICDTraceMatrix()
        icd = ICD(
            icd_id="ICD-001",
            title="Test ICD",
            description="Test",
            safety_properties=["prop1"],
            sil_level=SILLevel.SIL2,
        )
        matrix.add_icd(icd)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        
        export = matrix.export_trace_matrix()
        assert "ICD-001" in export
        assert export["ICD-001"]["title"] == "Test ICD"
        assert "claim-1" in export["ICD-001"]["claim_ids"]
        assert export["ICD-001"]["sil_level"] == "SIL2"


class TestCoverageReport:
    """Tests for CoverageReport dataclass."""

    def test_coverage_report_creation(self) -> None:
        """Test creation of coverage report."""
        report = CoverageReport(
            total_icds=10,
            covered_icds=10,
            uncovered_icds=[],
        )
        assert report.total_icds == 10
        assert report.covered_icds == 10
        assert report.is_complete

    def test_coverage_report_percentage(self) -> None:
        """Test coverage percentage calculation."""
        report = CoverageReport(
            total_icds=10,
            covered_icds=8,
            uncovered_icds=["ICD-009", "ICD-010"],
        )
        assert report.coverage_percentage == 0.8

    def test_coverage_report_zero_icds(self) -> None:
        """Test coverage report with zero total ICDs."""
        report = CoverageReport(
            total_icds=0,
            covered_icds=0,
        )
        assert report.coverage_percentage == 0.0


class TestAllICDsConstant:
    """Tests for the ALL_ICDS constant."""

    def test_all_icds_count(self) -> None:
        """Test that ALL_ICDS contains 49 ICDs."""
        assert len(ALL_ICDS) == 49

    def test_all_icds_unique_ids(self) -> None:
        """Test that all ICD IDs are unique."""
        ids = [icd.icd_id for icd in ALL_ICDS]
        assert len(ids) == len(set(ids))

    def test_all_icds_sequential(self) -> None:
        """Test that ICD IDs are sequential ICD-001 through ICD-049."""
        expected = [f"ICD-{i:03d}" for i in range(1, 50)]
        actual = sorted([icd.icd_id for icd in ALL_ICDS])
        assert actual == expected

    def test_all_icds_have_properties(self) -> None:
        """Test that all ICDs have required properties."""
        for icd in ALL_ICDS:
            assert icd.icd_id
            assert icd.title
            assert icd.description
            assert isinstance(icd.sil_level, SILLevel)
            assert icd.protocol
            assert icd.direction


class TestValidateICDCoverage:
    """Tests for validate_icd_coverage function."""

    def test_validate_coverage_complete(self) -> None:
        """Test validation passes with complete coverage."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        matrix.add_icd_claim_link("ICD-001", "claim-1")
        
        report = validate_icd_coverage(matrix)
        assert report.is_complete

    def test_validate_coverage_incomplete_raises(self) -> None:
        """Test validation raises on incomplete coverage."""
        matrix = ICDTraceMatrix()
        icd = ICD(icd_id="ICD-001", title="Test", description="Test")
        matrix.add_icd(icd)
        
        with pytest.raises(ValueError, match="Incomplete ICD coverage"):
            validate_icd_coverage(matrix)

    def test_validate_coverage_multiple_uncovered(self) -> None:
        """Test validation error message lists uncovered ICDs."""
        matrix = ICDTraceMatrix()
        for i in range(1, 4):
            icd = ICD(icd_id=f"ICD-{i:03d}", title=f"Test{i}", description=f"Test{i}")
            matrix.add_icd(icd)
        
        with pytest.raises(ValueError) as exc_info:
            validate_icd_coverage(matrix)
        
        error_msg = str(exc_info.value)
        assert "3 uncovered ICDs" in error_msg
