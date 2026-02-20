"""Unit tests for Phase E gate report (Task 40.5)."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from holly.test_harness.phase_e_gate import GateItem, GateReport, evaluate_phase_e_gate, render_report, write_report


class TestPhaseEGate:
    """Test Phase E gate evaluation."""

    def test_evaluate_phase_e_gate(self) -> None:
        """Test that evaluate_phase_e_gate returns a report."""
        report = evaluate_phase_e_gate()

        assert report is not None
        assert report.slice_id == 6
        assert "Phase E Gate" in report.gate_name

    def test_all_items_pass(self) -> None:
        """Test that all gate items pass."""
        report = evaluate_phase_e_gate()

        for item in report.items:
            assert item.verdict == "PASS"

    def test_gate_passes(self) -> None:
        """Test that overall gate passes."""
        report = evaluate_phase_e_gate()

        assert report.all_pass is True

    def test_item_count(self) -> None:
        """Test that we have comprehensive items."""
        report = evaluate_phase_e_gate()

        # Should cover Steps 34-40
        assert len(report.items) >= 10

    def test_step_34_conversation(self) -> None:
        """Test Step 34 gate items."""
        report = evaluate_phase_e_gate()

        step_34_items = [i for i in report.items if i.task_id.startswith("34")]
        assert len(step_34_items) >= 1
        assert all(i.verdict == "PASS" for i in step_34_items)

    def test_step_35_intent(self) -> None:
        """Test Step 35 gate items."""
        report = evaluate_phase_e_gate()

        step_35_items = [i for i in report.items if i.task_id.startswith("35")]
        assert len(step_35_items) >= 1
        assert all(i.verdict == "PASS" for i in step_35_items)

    def test_step_36_goal(self) -> None:
        """Test Step 36 gate items."""
        report = evaluate_phase_e_gate()

        step_36_items = [i for i in report.items if i.task_id.startswith("36")]
        assert len(step_36_items) >= 4
        assert all(i.verdict == "PASS" for i in step_36_items)

    def test_step_37_aps(self) -> None:
        """Test Step 37 gate items."""
        report = evaluate_phase_e_gate()

        step_37_items = [i for i in report.items if i.task_id.startswith("37")]
        assert len(step_37_items) >= 2
        assert all(i.verdict == "PASS" for i in step_37_items)

    def test_step_38_topology(self) -> None:
        """Test Step 38 gate items."""
        report = evaluate_phase_e_gate()

        step_38_items = [i for i in report.items if i.task_id.startswith("38")]
        assert len(step_38_items) >= 3
        assert all(i.verdict == "PASS" for i in step_38_items)

    def test_step_39_memory(self) -> None:
        """Test Step 39 gate items."""
        report = evaluate_phase_e_gate()

        step_39_items = [i for i in report.items if i.task_id.startswith("39")]
        assert len(step_39_items) >= 1
        assert all(i.verdict == "PASS" for i in step_39_items)

    def test_step_40_core_tests(self) -> None:
        """Test Step 40 gate items."""
        report = evaluate_phase_e_gate()

        step_40_items = [i for i in report.items if i.task_id.startswith("40")]
        assert len(step_40_items) >= 3
        assert all(i.verdict == "PASS" for i in step_40_items)

    def test_gate_item_structure(self) -> None:
        """Test GateItem data structure."""
        item = GateItem(
            task_id="test.1",
            name="Test gate item",
            acceptance_criteria="Test passes",
            verdict="PASS",
            evidence="Evidence provided",
        )

        assert item.task_id == "test.1"
        assert item.name == "Test gate item"
        assert item.acceptance_criteria == "Test passes"
        assert item.verdict == "PASS"
        assert item.evidence == "Evidence provided"

    def test_gate_report_properties(self) -> None:
        """Test GateReport properties."""
        report = evaluate_phase_e_gate()

        assert report.passed > 0
        assert report.failed == 0
        assert report.passed == len(report.items)

    def test_render_report(self) -> None:
        """Test that render_report produces markdown."""
        report = evaluate_phase_e_gate()
        markdown = render_report(report)

        assert "# Phase E Gate Report" in markdown
        assert "Phase E Overview" in markdown
        assert "Gate Items" in markdown
        assert "Phase F unlocked" in markdown
        assert "✓" in markdown

    def test_report_contains_critical_path(self) -> None:
        """Test that report documents critical path."""
        report = evaluate_phase_e_gate()
        markdown = render_report(report)

        assert "36.8 → 36.9 → 36.4" in markdown

    def test_report_contains_safety_case_summary(self) -> None:
        """Test that report includes safety case summary."""
        report = evaluate_phase_e_gate()
        markdown = render_report(report)

        assert "Safety Case Summary" in markdown
        assert "E.G1" in markdown or "Conversation" in markdown
        assert "E.G2" in markdown or "Intent" in markdown

    def test_write_report(self) -> None:
        """Test that write_report writes to file."""
        report = evaluate_phase_e_gate()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "phase_e_gate.md"
            write_report(report, path)

            assert path.exists()
            content = path.read_text()
            assert "Phase E Gate Report" in content

    def test_evidence_fields_populated(self) -> None:
        """Test that all items have evidence."""
        report = evaluate_phase_e_gate()

        for item in report.items:
            assert len(item.evidence) > 0

    def test_acceptance_criteria_populated(self) -> None:
        """Test that all items have acceptance criteria."""
        report = evaluate_phase_e_gate()

        for item in report.items:
            assert len(item.acceptance_criteria) > 0

    def test_celestial_predicates_referenced(self) -> None:
        """Test that L0-L4 predicates are referenced."""
        report = evaluate_phase_e_gate()
        all_text = " ".join(i.evidence for i in report.items) + " ".join(i.name for i in report.items)

        assert "L0" in all_text or "safety" in all_text
        assert "L1" in all_text or "legal" in all_text
        assert "L2" in all_text or "ethical" in all_text
        assert "L3" in all_text or "permissions" in all_text
        assert "L4" in all_text or "constitutional" in all_text

    def test_icd_references(self) -> None:
        """Test that ICDs are referenced appropriately."""
        report = evaluate_phase_e_gate()
        all_text = " ".join(i.evidence for i in report.items) + " ".join(i.name for i in report.items)

        assert "ICD-008" in all_text  # Conversation
        assert "ICD-009" in all_text  # Intent
        assert "ICD-010" in all_text  # Goal
        assert "ICD-011" in all_text  # APS

    def test_gate_verdict_in_markdown(self) -> None:
        """Test that gate verdict is clear in markdown."""
        report = evaluate_phase_e_gate()
        markdown = render_report(report)

        # Should declare Phase F unlocked
        assert "Phase F is unlocked" in markdown or "unlocked" in markdown
