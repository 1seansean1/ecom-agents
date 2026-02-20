"""Test harness for SIL-2 verification and gate reporting.

Tasks 40.2, 40.3, 40.5 — Core test suite, eval suite, and Phase E gate.
"""

from __future__ import annotations

from holly.test_harness.core_eval_suite import CoreEvalSuite, EvalMetric, EvalResult
from holly.test_harness.core_test_suite import CoreTestSuite, TestCase, TestResult, TestSuiteResult
from holly.test_harness.phase_e_gate import GateItem, GateReport, evaluate_phase_e_gate, render_report, write_report

__all__ = [
    "CoreTestSuite",
    "CoreEvalSuite",
    "TestCase",
    "TestResult",
    "TestSuiteResult",
    "EvalMetric",
    "EvalResult",
    "GateItem",
    "GateReport",
    "evaluate_phase_e_gate",
    "render_report",
    "write_report",
]
