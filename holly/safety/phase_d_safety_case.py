"""Phase D Safety Case: Complete Integration of ICDs and Safety Argument.

Combines the SafetyArgumentGraph from Task 33.2 with ICD specifications
from Task 33.5 to produce a complete Phase D safety case document with
full ICD→Claim traceability and 100% coverage validation.

References:
  - Task 33.2: Build Structured Safety Argument
  - Task 33.5: Integrate all 49 ICDs into Phase D Safety Case
  - ISO/IEC 42010:2011 (Architecture description)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Optional

from holly.safety.argument import SafetyArgumentGraph
from holly.safety.icd_integration import (
    ALL_ICDS,
    CoverageReport,
    ICDTraceMatrix,
    build_icd_trace_matrix,
    validate_icd_coverage,
)


@dataclasses.dataclass(slots=True)
class PhaseDSafetyCase:
    """Complete Phase D Safety Case with ICD integration.

    Combines:
    1. SafetyArgumentGraph: Structured GSN-based safety argument
    2. ICDTraceMatrix: Bidirectional ICD↔Claim traceability
    3. CoverageReport: Validation that all 49 ICDs are covered

    Attributes:
        argument_graph: The underlying safety argument
        icd_trace_matrix: ICD→Claim mapping
        coverage_report: Coverage validation report
        exported_at: Timestamp of export
        version: Safety case version
    """

    argument_graph: SafetyArgumentGraph
    icd_trace_matrix: ICDTraceMatrix
    coverage_report: CoverageReport
    exported_at: datetime = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    version: str = "D"

    def __post_init__(self) -> None:
        """Validate safety case completeness."""
        if not self.coverage_report.is_complete:
            raise ValueError(
                f"Phase D Safety Case incomplete: {len(self.coverage_report.uncovered_icds)} uncovered ICDs"
            )

    @property
    def total_claims(self) -> int:
        """Total number of safety claims in the argument."""
        return len(self.argument_graph.claims)

    @property
    def total_icds(self) -> int:
        """Total number of ICDs in the safety case."""
        return self.coverage_report.total_icds

    @property
    def coverage_percentage(self) -> float:
        """ICD coverage percentage (0.0–1.0)."""
        return self.coverage_report.coverage_percentage

    def get_icd_summary(self, icd_id: str) -> Optional[dict]:
        """Get summary information for an ICD.

        Args:
            icd_id: ICD identifier

        Returns:
            Dictionary with ICD details or None if not found
        """
        trace = self.icd_trace_matrix.get_icd_coverage(icd_id)
        if not trace or icd_id not in self.icd_trace_matrix.icds:
            return None

        icd = self.icd_trace_matrix.icds[icd_id]
        return {
            "icd_id": icd_id,
            "title": icd.title,
            "description": icd.description,
            "safety_properties": icd.safety_properties,
            "sil_level": icd.sil_level.name,
            "protocol": icd.protocol,
            "direction": icd.direction,
            "claim_ids": trace.claim_ids,
            "claim_count": len(trace.claim_ids),
        }

    def export_json(self) -> dict:
        """Export Phase D Safety Case as JSON-serializable dictionary.

        Returns:
            Dictionary representation of the complete safety case
        """
        return {
            "version": self.version,
            "exported_at": self.exported_at.isoformat(),
            "coverage": {
                "total_icds": self.coverage_report.total_icds,
                "covered_icds": self.coverage_report.covered_icds,
                "uncovered_icds": self.coverage_report.uncovered_icds,
                "coverage_percentage": self.coverage_report.coverage_percentage,
                "is_complete": self.coverage_report.is_complete,
            },
            "argument_stats": {
                "total_claims": self.total_claims,
                "total_goals": len(self.argument_graph.goals),
                "total_strategies": len(self.argument_graph.strategies),
                "total_evidence": len(self.argument_graph.evidence),
                "total_nodes": self.argument_graph.node_count(),
                "total_edges": self.argument_graph.edge_count(),
            },
            "trace_matrix": self.icd_trace_matrix.export_trace_matrix(),
        }

    def export_markdown(self) -> str:
        """Export Phase D Safety Case as Markdown document.

        Returns:
            Markdown formatted safety case document
        """
        lines = [
            "# Phase D Safety Case: ICD Integration",
            "",
            f"**Generated**: {self.exported_at.isoformat()}",
            f"**Version**: {self.version}",
            "",
            "## Executive Summary",
            "",
            f"- **Total ICDs**: {self.coverage_report.total_icds}",
            f"- **Covered ICDs**: {self.coverage_report.covered_icds}",
            f"- **Coverage**: {self.coverage_report.coverage_percentage * 100:.1f}%",
            f"- **Status**: {'✓ COMPLETE' if self.coverage_report.is_complete else '✗ INCOMPLETE'}",
            "",
            "## ICD Coverage Matrix",
            "",
            "| ICD | Title | Claims | SIL | Status |",
            "|-----|-------|--------|-----|--------|",
        ]

        for icd_id, icd in sorted(self.icd_trace_matrix.icds.items()):
            entry = self.icd_trace_matrix.get_icd_coverage(icd_id)
            claim_count = len(entry.claim_ids) if entry else 0
            status = "✓" if entry and entry.is_covered() else "✗"
            lines.append(
                f"| {icd_id} | {icd.title} | {claim_count} | {icd.sil_level.name} | {status} |"
            )

        lines.extend(
            [
                "",
                "## Argument Graph Statistics",
                "",
                f"- **Total Claims**: {self.total_claims}",
                f"- **Total Goals**: {len(self.argument_graph.goals)}",
                f"- **Total Strategies**: {len(self.argument_graph.strategies)}",
                f"- **Total Evidence**: {len(self.argument_graph.evidence)}",
                f"- **Total Nodes**: {self.argument_graph.node_count()}",
                f"- **Total Edges**: {self.argument_graph.edge_count()}",
                "",
            ]
        )

        if self.coverage_report.uncovered_icds:
            lines.extend(
                [
                    "## Uncovered ICDs (GAPS)",
                    "",
                ]
            )
            for icd_id in sorted(self.coverage_report.uncovered_icds):
                lines.append(f"- {icd_id}")
            lines.append("")

        if self.coverage_report.redundant_icds:
            lines.extend(
                [
                    "## Redundant ICDs (Multiple Claims)",
                    "",
                ]
            )
            for icd_id in sorted(self.coverage_report.redundant_icds):
                entry = self.icd_trace_matrix.get_icd_coverage(icd_id)
                if entry:
                    lines.append(f"- {icd_id}: {len(entry.claim_ids)} claims")
            lines.append("")

        lines.append("## Validation Result")
        lines.append("")
        if self.coverage_report.is_complete:
            lines.append("✓ **All 49 ICDs are covered by safety claims**")
        else:
            lines.append("✗ **INCOMPLETE: Uncovered ICDs present**")

        return "\n".join(lines)


def build_phase_d_safety_case(
    argument_graph: SafetyArgumentGraph,
) -> PhaseDSafetyCase:
    """Construct complete Phase D Safety Case from argument graph.

    Integrates all 49 ICDs with the safety argument, validates 100% coverage,
    and produces the final Phase D safety case document.

    Args:
        argument_graph: SafetyArgumentGraph from Task 33.2

    Returns:
        Complete PhaseDSafetyCase with ICD integration

    Raises:
        ValueError: If coverage validation fails (uncovered ICDs)
    """
    # Build trace matrix
    matrix = build_icd_trace_matrix(argument_graph, ALL_ICDS)

    # Validate coverage
    report = validate_icd_coverage(matrix)

    # Construct Phase D safety case
    safety_case = PhaseDSafetyCase(
        argument_graph=argument_graph,
        icd_trace_matrix=matrix,
        coverage_report=report,
    )

    return safety_case
