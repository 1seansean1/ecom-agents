"""Tests for Phase B gate evaluation (Task 21.6).

AC-1: All 18 critical-path Phase B tasks done → all_pass True, Phase C unlocked.
AC-2: Any critical-path task not done → verdict FAIL, all_pass False.
AC-3: test_count=0 with 21.2 done → 21.2 FAIL (SIL-3 not confirmed).
AC-4: render_phase_b_report produces correct header, verdict, and gate decision text.
AC-5: GateReport.passed + failed + waived + skipped == len(items).
AC-6: evaluate_phase_b_gate covers all 18 GATE_ITEMS_PHASE_B entries.
"""

from __future__ import annotations

import datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.arch.gate_report import (
    GATE_ITEMS_PHASE_B,
    GateReport,
    evaluate_phase_b_gate,
    render_phase_b_report,
)

# ── Helpers ───────────────────────────────────────────────────────

_CRITICAL_PATH_IDS: frozenset[str] = frozenset(
    task_id for task_id, *_ in GATE_ITEMS_PHASE_B
)

# Minimal done-entry matching what load_status produces
_DONE_NOTE = "test note (99 tests)"


def _all_done_statuses() -> dict[str, dict[str, str]]:
    return {tid: {"status": "done", "note": _DONE_NOTE} for tid in _CRITICAL_PATH_IDS}


# ── AC-1: all done → all_pass ─────────────────────────────────────


class TestEvaluatePhaseBGateAllPass:
    """AC-1: all 18 critical-path tasks done → all_pass True."""

    def test_all_done_returns_all_pass(self) -> None:
        report = evaluate_phase_b_gate(
            _all_done_statuses(), test_count=2200, audit_pass=True
        )
        assert report.all_pass is True

    def test_all_done_zero_failures(self) -> None:
        report = evaluate_phase_b_gate(
            _all_done_statuses(), test_count=2200, audit_pass=True
        )
        assert report.failed == 0

    def test_all_done_passed_count_equals_item_count(self) -> None:
        report = evaluate_phase_b_gate(
            _all_done_statuses(), test_count=2200, audit_pass=True
        )
        assert report.passed == len(GATE_ITEMS_PHASE_B)

    def test_slice_id_is_3(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert report.slice_id == 3

    def test_gate_name(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert "Phase B" in report.gate_name
        assert "13-21" in report.gate_name

    def test_date_is_today(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert report.date == datetime.date.today().isoformat()

    def test_item_count_matches_gate_items(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert len(report.items) == len(GATE_ITEMS_PHASE_B)


# ── AC-2: missing critical task → FAIL ───────────────────────────


class TestEvaluatePhaseBGateFailure:
    """AC-2: any critical-path task not done → FAIL, all_pass False."""

    @pytest.mark.parametrize("missing_id", sorted(_CRITICAL_PATH_IDS))
    def test_missing_critical_task_fails(self, missing_id: str) -> None:
        statuses = _all_done_statuses()
        statuses[missing_id] = {"status": "pending", "note": ""}
        report = evaluate_phase_b_gate(statuses, test_count=2200, audit_pass=True)
        assert report.all_pass is False
        assert report.failed >= 1

    @pytest.mark.parametrize("missing_id", sorted(_CRITICAL_PATH_IDS))
    def test_missing_critical_task_item_verdict_is_fail(self, missing_id: str) -> None:
        statuses = _all_done_statuses()
        statuses[missing_id] = {"status": "pending", "note": ""}
        report = evaluate_phase_b_gate(statuses, test_count=2200, audit_pass=True)
        failed = [i for i in report.items if i.task_id == missing_id]
        assert len(failed) == 1
        assert failed[0].verdict == "FAIL"

    def test_empty_statuses_all_fail(self) -> None:
        report = evaluate_phase_b_gate({}, test_count=0, audit_pass=False)
        assert report.all_pass is False
        assert report.failed == len(GATE_ITEMS_PHASE_B)


# ── AC-3: 21.2 auto check with test_count=0 → FAIL ───────────────


class TestTask212AutoCheck:
    """AC-3: 21.2 requires test_count > 0 to PASS."""

    def test_21_2_done_with_tests_passes(self) -> None:
        statuses = _all_done_statuses()
        report = evaluate_phase_b_gate(statuses, test_count=1, audit_pass=True)
        item = next(i for i in report.items if i.task_id == "21.2")
        assert item.verdict == "PASS"

    def test_21_2_done_without_tests_fails(self) -> None:
        statuses = _all_done_statuses()
        report = evaluate_phase_b_gate(statuses, test_count=0, audit_pass=True)
        item = next(i for i in report.items if i.task_id == "21.2")
        assert item.verdict == "FAIL"

    def test_21_2_pending_always_fails(self) -> None:
        statuses = _all_done_statuses()
        statuses["21.2"] = {"status": "pending", "note": ""}
        report = evaluate_phase_b_gate(statuses, test_count=9999, audit_pass=True)
        item = next(i for i in report.items if i.task_id == "21.2")
        assert item.verdict == "FAIL"

    def test_21_2_pass_evidence_contains_note(self) -> None:
        statuses = _all_done_statuses()
        report = evaluate_phase_b_gate(statuses, test_count=500, audit_pass=True)
        item = next(i for i in report.items if i.task_id == "21.2")
        assert _DONE_NOTE in item.evidence


# ── AC-4: render_phase_b_report structure ────────────────────────


class TestRenderPhaseBReport:
    """AC-4: render_phase_b_report produces correct header, verdict, decision text."""

    def _pass_report(self) -> GateReport:
        return evaluate_phase_b_gate(_all_done_statuses(), test_count=2200, audit_pass=True)

    def _fail_report(self) -> GateReport:
        statuses = _all_done_statuses()
        statuses["13.1"] = {"status": "pending", "note": ""}
        return evaluate_phase_b_gate(statuses, test_count=2200, audit_pass=True)

    def test_pass_report_contains_phase_b_header(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "Phase B Gate Report" in text

    def test_pass_report_verdict_text(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "Phase C unlocked" in text

    def test_fail_report_verdict_text(self) -> None:
        text = render_phase_b_report(self._fail_report())
        assert "Phase C blocked" in text

    def test_pass_report_gate_decision_mentions_phase_c(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "Phase C" in text
        assert "Slice 4" in text

    def test_fail_report_gate_decision_lists_failed_item(self) -> None:
        text = render_phase_b_report(self._fail_report())
        assert "13.1" in text

    def test_report_contains_gate_items_table_header(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "## Gate Items" in text

    def test_report_contains_gate_decision_section(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "## Gate Decision" in text

    def test_report_contains_all_task_ids(self) -> None:
        text = render_phase_b_report(self._pass_report())
        for task_id in _CRITICAL_PATH_IDS:
            assert task_id in text, f"Task {task_id} missing from report"

    def test_report_summary_line_present(self) -> None:
        text = render_phase_b_report(self._pass_report())
        assert "**Summary:**" in text


# ── AC-5: verdict accounting ──────────────────────────────────────


class TestVerdictAccounting:
    """AC-5: passed + failed + waived + skipped == len(items)."""

    def test_verdict_totals_sum_to_item_count_pass(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert (
            report.passed + report.failed + report.waived + report.skipped
            == len(report.items)
        )

    def test_verdict_totals_sum_to_item_count_fail(self) -> None:
        report = evaluate_phase_b_gate({}, test_count=0)
        assert (
            report.passed + report.failed + report.waived + report.skipped
            == len(report.items)
        )

    def test_all_pass_requires_zero_failed(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        assert report.all_pass == (report.failed == 0)


# ── AC-6: coverage of all GATE_ITEMS_PHASE_B entries ─────────────


class TestGateItemsCoverage:
    """AC-6: evaluate_phase_b_gate covers all GATE_ITEMS_PHASE_B entries."""

    def test_all_gate_item_ids_appear_in_report(self) -> None:
        report = evaluate_phase_b_gate(_all_done_statuses(), test_count=1)
        reported_ids = {i.task_id for i in report.items}
        defined_ids = {task_id for task_id, *_ in GATE_ITEMS_PHASE_B}
        assert reported_ids == defined_ids

    def test_gate_items_phase_b_has_18_entries(self) -> None:
        assert len(GATE_ITEMS_PHASE_B) == 18

    def test_gate_items_check_types_are_valid(self) -> None:
        valid_types = {"status", "auto"}
        for task_id, _, _, check_type in GATE_ITEMS_PHASE_B:
            assert check_type in valid_types, f"{task_id}: invalid check_type {check_type!r}"

    def test_21_2_is_auto_check(self) -> None:
        entry = next(e for e in GATE_ITEMS_PHASE_B if e[0] == "21.2")
        assert entry[3] == "auto"

    def test_all_others_are_status_check(self) -> None:
        for task_id, _, _, check_type in GATE_ITEMS_PHASE_B:
            if task_id != "21.2":
                assert check_type == "status", f"{task_id} should be status check"


# ── Property-based tests ──────────────────────────────────────────


class TestPhaseBGateProperties:
    """Property-based invariant checks."""

    @given(
        statuses=st.dictionaries(
            st.sampled_from(sorted(_CRITICAL_PATH_IDS)),
            st.one_of(
                st.just("pending"),
                st.just("done"),
                st.fixed_dictionaries(
                    {"status": st.sampled_from(["pending", "done"]), "note": st.text(max_size=50)}
                ),
            ),
            min_size=0,
            max_size=len(_CRITICAL_PATH_IDS),
        ),
        test_count=st.integers(min_value=0, max_value=10000),
        audit_pass=st.booleans(),
    )
    @settings(max_examples=200)
    def test_verdict_always_valid(
        self,
        statuses: dict,
        test_count: int,
        audit_pass: bool,
    ) -> None:
        """AC: Every GateItem verdict is one of {PASS, FAIL, WAIVED, SKIP}."""
        valid_verdicts = {"PASS", "FAIL", "WAIVED", "SKIP"}
        report = evaluate_phase_b_gate(statuses, test_count=test_count, audit_pass=audit_pass)
        for item in report.items:
            assert item.verdict in valid_verdicts, (
                f"{item.task_id}: invalid verdict {item.verdict!r}"
            )

    @given(
        statuses=st.dictionaries(
            st.sampled_from(sorted(_CRITICAL_PATH_IDS)),
            st.one_of(
                st.just("pending"),
                st.just("done"),
                st.fixed_dictionaries(
                    {"status": st.sampled_from(["pending", "done"]), "note": st.text(max_size=50)}
                ),
            ),
            min_size=0,
            max_size=len(_CRITICAL_PATH_IDS),
        ),
        test_count=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=200)
    def test_all_pass_iff_zero_failed(
        self,
        statuses: dict,
        test_count: int,
    ) -> None:
        """AC: all_pass is True iff failed == 0."""
        report = evaluate_phase_b_gate(statuses, test_count=test_count)
        assert report.all_pass == (report.failed == 0)

    @given(
        statuses=st.dictionaries(
            st.sampled_from(sorted(_CRITICAL_PATH_IDS)),
            st.one_of(
                st.just("pending"),
                st.just("done"),
                st.fixed_dictionaries(
                    {"status": st.sampled_from(["pending", "done"]), "note": st.text(max_size=50)}
                ),
            ),
            min_size=0,
            max_size=len(_CRITICAL_PATH_IDS),
        ),
        test_count=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=200)
    def test_item_count_always_equals_gate_items(
        self,
        statuses: dict,
        test_count: int,
    ) -> None:
        """AC: report always has exactly len(GATE_ITEMS_PHASE_B) items."""
        report = evaluate_phase_b_gate(statuses, test_count=test_count)
        assert len(report.items) == len(GATE_ITEMS_PHASE_B)
