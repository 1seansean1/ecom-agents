"""Regeneration protocols: active restoration of the symbol set.

Paper Section 4: passive transport vs active regeneration.
- ConfirmProtocol: retry with clarified prompt (digital repeater analog)
- CrosscheckProtocol: deterministic validation (error-correcting code analog)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure symbols per channel (triggers ConfirmProtocol)
# ---------------------------------------------------------------------------

FAILURE_SYMBOLS: dict[str, set[str]] = {
    "K1": {"error", "unknown"},
    "K2": {"error"},
    "K3": {"error", "malformed"},
    "K4": {"error"},
    "K5": {"error"},
    "K6": {"analysis_failed"},
    "K7": {"http_error", "timeout", "auth_error", "rate_limited", "failure"},
}


def is_failure(sigma_out: str, channel_id: str) -> bool:
    """Check if sigma_out is a failure symbol for the given channel."""
    return sigma_out in FAILURE_SYMBOLS.get(channel_id, set())


# ---------------------------------------------------------------------------
# ConfirmProtocol
# ---------------------------------------------------------------------------


class ConfirmProtocol:
    """On failure, retry once with a clarified/rephrased prompt.

    Simplest form of active regeneration: re-amplify the signal by
    giving the agent a second chance with more context.
    """

    def execute(
        self,
        channel_id: str,
        state: dict,
        original_result: dict,
        node_fn: Callable,
        partition: Any = None,
    ) -> tuple[dict, str]:
        """Retry the node with augmented prompt.

        Returns (new_result, new_sigma_out).
        """
        try:
            retry_state = dict(state)
            original_messages = list(state.get("messages", []))
            error_context = _extract_error(original_result)
            retry_prompt = (
                f"Previous attempt produced an error or incomplete result. "
                f"Please re-examine the task carefully and try again. "
                f"Original error context: {error_context}"
            )
            original_messages.append(HumanMessage(content=retry_prompt))
            retry_state["messages"] = original_messages

            retry_result = node_fn(retry_state)

            if partition:
                new_sigma_out = partition.classify_output(retry_result)
            else:
                new_sigma_out = "retry_completed"

            logger.info("ConfirmProtocol retry for %s: %s", channel_id, new_sigma_out)
            return retry_result, new_sigma_out
        except Exception:
            logger.warning("ConfirmProtocol retry failed for %s", channel_id, exc_info=True)
            return original_result, "retry_failed"


# ---------------------------------------------------------------------------
# CrosscheckProtocol
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    passed: bool
    reason: str = ""


# Per-channel validators
def _validate_operations_result(result: dict) -> ValidationResult:
    """K3: Check operations result has expected structure."""
    ops = result.get("operations_result", {})
    if not isinstance(ops, dict):
        return ValidationResult(False, "operations_result is not a dict")
    if ops.get("error"):
        return ValidationResult(False, f"operations_result contains error: {ops['error']}")
    return ValidationResult(True)


def _validate_revenue_numbers(result: dict) -> ValidationResult:
    """K4: Check revenue result has numeric values."""
    rev = result.get("revenue_result", {})
    if not isinstance(rev, dict):
        return ValidationResult(False, "revenue_result is not a dict")
    return ValidationResult(True)


def _validate_content_output(result: dict) -> ValidationResult:
    """K5: Check content writer produced valid JSON with caption."""
    sub = result.get("sub_agent_results", {})
    writer = sub.get("content_writer", {}) if isinstance(sub, dict) else {}
    if not isinstance(writer, dict):
        return ValidationResult(False, "content_writer result is not a dict")
    caption = writer.get("caption", "")
    if not caption or len(str(caption)) < 10:
        return ValidationResult(False, f"caption too short: {len(str(caption))} chars")
    return ValidationResult(True)


def _validate_engagement_score(result: dict) -> ValidationResult:
    """K6: Check engagement score is a number in valid range."""
    sub = result.get("sub_agent_results", {})
    analyzer = sub.get("campaign_analyzer", {}) if isinstance(sub, dict) else {}
    if not isinstance(analyzer, dict):
        return ValidationResult(False, "campaign_analyzer result is not a dict")
    rate = analyzer.get("expected_engagement_rate", "")
    try:
        val = float(str(rate).strip("%"))
        if not (0 <= val <= 100):
            return ValidationResult(False, f"engagement rate out of range: {val}")
    except (ValueError, TypeError):
        return ValidationResult(False, f"engagement rate not numeric: {rate}")
    return ValidationResult(True)


def _validate_tool_response(result: dict) -> ValidationResult:
    """K7: Check tool response has expected shape."""
    if result.get("error"):
        return ValidationResult(False, f"tool error: {result['error']}")
    return ValidationResult(True)


VALIDATORS: dict[str, Callable[[dict], ValidationResult]] = {
    "K3": _validate_operations_result,
    "K4": _validate_revenue_numbers,
    "K5": _validate_content_output,
    "K6": _validate_engagement_score,
    "K7": _validate_tool_response,
}


class CrosscheckProtocol:
    """After LLM output, run a deterministic validator.

    Error-detection coding: can't fix the output, but can detect
    when it's wrong and flag it.
    """

    def execute(self, channel_id: str, result: dict) -> tuple[dict, str | None]:
        """Validate the result. Returns (result, override_sigma_out or None)."""
        validator = VALIDATORS.get(channel_id)
        if validator is None:
            return result, None

        try:
            vr = validator(result)
            if vr.passed:
                return result, None
            else:
                result["_crosscheck_failed"] = True
                result["_crosscheck_reason"] = vr.reason
                logger.info("CrosscheckProtocol failed for %s: %s", channel_id, vr.reason)
                return result, "crosscheck_failed"
        except Exception:
            logger.warning("CrosscheckProtocol error for %s", channel_id, exc_info=True)
            return result, None


# Singleton instances
confirm_protocol = ConfirmProtocol()
crosscheck_protocol = CrosscheckProtocol()


def _extract_error(result: dict) -> str:
    """Extract error context from a result dict for retry prompts."""
    if result.get("error"):
        return str(result["error"])[:500]
    if result.get("_crosscheck_reason"):
        return str(result["_crosscheck_reason"])[:500]
    for key in ("operations_result", "sales_result", "revenue_result"):
        sub = result.get(key, {})
        if isinstance(sub, dict) and sub.get("error"):
            return str(sub["error"])[:500]
    return "Unknown error"
