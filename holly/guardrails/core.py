"""Guardrails module for Holly Grace.

Implements input sanitization, output redaction, and injection detection
per Task 28.3 and ICD v0.1 specifications. All boundary crossings that process
user input or model outputs must pass through GuardrailsEngine.

This module provides:
- Input sanitization: strip/normalize dangerous input patterns
- Output redaction: apply canonical redaction rules to LLM outputs
- Injection detection: detect prompt injection, SQL injection, command injection patterns
- GuardrailsEngine: unified pipeline tying sanitization, detection, and redaction together
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from holly.redaction.core import (
    RedactionResult,
    RedactionRule,
    canonicalize_redaction_rules,
    redact,
)

log = logging.getLogger(__name__)

__all__ = [
    "GuardrailsEngine",
    "GuardrailsEngineProtocol",
    "GuardrailsError",
    "GuardrailsResult",
    "InjectionDetectionResult",
    "InputSanitizationResult",
    "OutputRedactionResult",
    "create_default_engine",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GuardrailsError(Exception):
    """Raised when guardrails check fails or cannot be applied safely."""

    pass


# ---------------------------------------------------------------------------
# Detection and Sanitization Patterns
# ---------------------------------------------------------------------------

# Prompt injection patterns: common attacks that try to override system prompts
PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Ignore/discard instructions
    re.compile(
        r"(?:ignore|disregard|forget|delete|discard)\s+(?:the\s+)?(?:above|previous|earlier|original|prior|given)\s+(?:instructions?|prompt|directions?|requests?|system|constraints?|guidelines?)",
        re.IGNORECASE,
    ),
    # Jailbreak attempts: "Pretend you are X", "Act as X", "Play role of X"
    re.compile(
        r"(?:pretend|act|assume|imagine|roleplay|play\s+the\s+role\s+of)"
        r"\s+(?:you\s+)?(?:are\s+)?",
        re.IGNORECASE,
    ),
    # "System prompt is X" or "override" attacks
    re.compile(
        r"(?:system|initial|original|base)\s+(?:prompt|instructions?|guidelines?)"
        r"\s+(?:is|was|should\s+be|override)",
        re.IGNORECASE,
    ),
)

# SQL injection patterns: common SQL attack vectors
SQL_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Basic SQL keywords followed by dangerous commands
    re.compile(r";\s*(?:DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC|EXECUTE)\s+", re.IGNORECASE),
    # UNION-based injection
    re.compile(r"(?:UNION|INTERSECT|EXCEPT)\s+(?:ALL\s+)?SELECT", re.IGNORECASE),
    # Boolean-based injection: 1=1, 1=2, 'a'='a', etc.
    re.compile(r"(?:\bOR\b|\bAND\b)\s+(?:1\s*=\s*1|\d+\s*=\s*\d+|'[^']*'\s*=\s*'[^']*')", re.IGNORECASE),
    # Comment-based injection (-- or /**/  to close queries)
    re.compile(r"(?:--|#|\/\*)\s*(?:DROP|DELETE|SELECT|INSERT|UPDATE)", re.IGNORECASE),
)

# Command injection patterns: shell metacharacters in suspicious context
COMMAND_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Pipe and double-pipe with shell commands
    re.compile(r"[|&]{1,2}\s*(?:cat|ls|rm|touch|curl|wget|nc|bash|sh|cmd|powershell)(?:\s|$|\.exe)"),
    # Command substitution with backticks or $()
    re.compile(r"[\$`]\(.*\)"),
    # Backtick substitution
    re.compile(r"`[^`]+`"),
    # Semicolon followed by shell command keywords
    re.compile(r";\s*(?:cat|ls|rm|touch|curl|wget|nc|bash|sh|cmd|powershell)"),
)

# Unicode normalization attacks: homoglyph attacks and homophone tricks
# (e.g., Cyrillic "a" looks like Latin "a")
UNICODE_NORMALIZATION_ATTACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Detect mixed Latin and Cyrillic
    re.compile(r"[a-zA-Z].*[\u0400-\u04ff]|[\u0400-\u04ff].*[a-zA-Z]"),
    # Detect mixed Latin and Greek
    re.compile(r"[a-zA-Z].*[α-ωΑ-Ω]|[α-ωΑ-Ω].*[a-zA-Z]"),  # noqa: RUF001
)

# ---------------------------------------------------------------------------
# Input Normalization Rules
# ---------------------------------------------------------------------------

# Whitespace normalization: collapse multiple spaces/tabs
_WHITESPACE_NORMALIZER: re.Pattern[str] = re.compile(r"\s+")

# Null byte removal (C-string attack)
_NULL_BYTE_PATTERN: re.Pattern[str] = re.compile(r"\x00")

# ---------------------------------------------------------------------------
# Result Types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class InjectionDetectionResult:
    """Result of injection detection analysis.

    Attributes
    ----------
    is_injection_detected : bool
        True if one or more injection patterns matched.
    injection_types : list[str]
        Sorted list of injection types detected (e.g., "prompt_injection", "sql_injection").
    injection_patterns_matched : dict[str, int]
        Map of injection type to count of matches found.
    """

    is_injection_detected: bool
    injection_types: list[str]
    injection_patterns_matched: dict[str, int]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InjectionDetectionResult):
            return NotImplemented
        return (
            self.is_injection_detected == other.is_injection_detected
            and self.injection_types == other.injection_types
            and self.injection_patterns_matched == other.injection_patterns_matched
        )

    def __repr__(self) -> str:
        return (
            f"InjectionDetectionResult("
            f"is_injection_detected={self.is_injection_detected}, "
            f"injection_types={self.injection_types}, "
            f"injection_patterns_matched={self.injection_patterns_matched})"
        )


@dataclass(slots=True)
class InputSanitizationResult:
    """Result of input sanitization.

    Attributes
    ----------
    sanitized_input : str
        Input after normalization and dangerous pattern removal.
    transformations_applied : list[str]
        Sorted list of transformations applied (e.g., "null_byte_removal", "whitespace_normalization").
    """

    sanitized_input: str
    transformations_applied: list[str] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InputSanitizationResult):
            return NotImplemented
        return (
            self.sanitized_input == other.sanitized_input
            and self.transformations_applied == other.transformations_applied
        )

    def __repr__(self) -> str:
        return (
            f"InputSanitizationResult("
            f"sanitized_input={self.sanitized_input!r}, "
            f"transformations_applied={self.transformations_applied})"
        )


@dataclass(slots=True)
class OutputRedactionResult:
    """Result of output redaction.

    Attributes
    ----------
    redacted_output : str
        Output after applying canonical redaction rules.
    rules_applied : list[str]
        Sorted list of redaction rule names that fired.
    """

    redacted_output: str
    rules_applied: list[str] = field(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OutputRedactionResult):
            return NotImplemented
        return (
            self.redacted_output == other.redacted_output
            and self.rules_applied == other.rules_applied
        )

    def __repr__(self) -> str:
        return (
            f"OutputRedactionResult("
            f"redacted_output={self.redacted_output!r}, "
            f"rules_applied={self.rules_applied})"
        )


@dataclass(slots=True)
class GuardrailsResult:
    """Complete result of guardrails pipeline execution.

    Attributes
    ----------
    passed : bool
        True if input is clean and injection-free; False if injection detected.
    input_sanitization : InputSanitizationResult
        Result of input sanitization step.
    injection_detection : InjectionDetectionResult
        Result of injection detection step.
    output_redaction : OutputRedactionResult | None
        Result of output redaction (None if not applied).
    error : str | None
        Error message if guardrails check failed.
    """

    passed: bool
    input_sanitization: InputSanitizationResult
    injection_detection: InjectionDetectionResult
    output_redaction: OutputRedactionResult | None = None
    error: str | None = None

    def __repr__(self) -> str:
        return (
            f"GuardrailsResult("
            f"passed={self.passed}, "
            f"input_sanitization={self.input_sanitization}, "
            f"injection_detection={self.injection_detection}, "
            f"output_redaction={self.output_redaction}, "
            f"error={self.error})"
        )


# ---------------------------------------------------------------------------
# GuardrailsEngine Protocol (for external dependency injection)
# ---------------------------------------------------------------------------


class GuardrailsEngineProtocol(Protocol):
    """Protocol for guardrails engine implementations."""

    def sanitize_input(self, raw_input: str) -> InputSanitizationResult:
        """Sanitize raw input, removing dangerous patterns."""
        ...

    def detect_injections(
        self,
        text: str,
        check_prompt_injection: bool = True,
        check_sql_injection: bool = True,
        check_command_injection: bool = True,
        check_unicode_attacks: bool = True,
    ) -> InjectionDetectionResult:
        """Detect injection patterns in text."""
        ...

    def redact_output(self, raw_output: str) -> OutputRedactionResult:
        """Redact PII and secrets from output."""
        ...

    def guard_input(self, raw_input: str) -> GuardrailsResult:
        """Apply full guardrails pipeline to input (sanitize + detect)."""
        ...

    def guard_output(self, raw_output: str) -> GuardrailsResult:
        """Apply output redaction guardrails (redact only)."""
        ...

    def guard_roundtrip(self, raw_input: str, raw_output: str) -> GuardrailsResult:
        """Apply full pipeline to both input and output."""
        ...


# ---------------------------------------------------------------------------
# GuardrailsEngine Implementation
# ---------------------------------------------------------------------------


class GuardrailsEngine:
    """Default implementation of guardrails pipeline.

    This engine provides:
    - Input sanitization (null byte removal, whitespace normalization)
    - Injection detection (prompt, SQL, command, unicode attacks)
    - Output redaction (applies canonical redaction rules)

    All methods are deterministic and thread-safe (no shared state).

    Attributes
    ----------
    redaction_rules : tuple[RedactionRule, ...]
        Rules to apply for output redaction.
    """

    __slots__ = ("redaction_rules",)

    def __init__(
        self,
        redaction_rules: tuple[RedactionRule, ...] | None = None,
    ) -> None:
        """Initialize guardrails engine.

        Parameters
        ----------
        redaction_rules:
            Tuple of RedactionRule objects. If None, uses canonical rules.
        """
        self.redaction_rules: tuple[RedactionRule, ...] = (
            redaction_rules or canonicalize_redaction_rules()
        )

    def sanitize_input(self, raw_input: str) -> InputSanitizationResult:
        """Sanitize input by removing null bytes and normalizing whitespace.

        Per Task 28.3, sanitization must normalize dangerous input patterns:
        - Remove null bytes (C-string attacks)
        - Collapse consecutive whitespace
        - Preserve semantic meaning

        Parameters
        ----------
        raw_input:
            Raw user input.

        Returns
        -------
        InputSanitizationResult
            Sanitized input and list of transformations applied.
        """
        current_text = raw_input
        transformations: set[str] = set()

        # Remove null bytes
        if "\x00" in current_text:
            current_text = _NULL_BYTE_PATTERN.sub("", current_text)
            transformations.add("null_byte_removal")

        # Normalize whitespace: collapse consecutive spaces/tabs to single space
        original_len = len(current_text)
        current_text = _WHITESPACE_NORMALIZER.sub(" ", current_text).strip()
        if len(current_text) != original_len:
            transformations.add("whitespace_normalization")

        return InputSanitizationResult(
            sanitized_input=current_text,
            transformations_applied=sorted(transformations),
        )

    def detect_injections(
        self,
        text: str,
        check_prompt_injection: bool = True,
        check_sql_injection: bool = True,
        check_command_injection: bool = True,
        check_unicode_attacks: bool = True,
    ) -> InjectionDetectionResult:
        """Detect injection patterns in input.

        Per Task 28.3, injection detection must identify:
        - Prompt injection (ignore instructions, roleplay, jailbreak)
        - SQL injection (UNION, boolean blind, comment-based)
        - Command injection (pipe operators, shell substitution)
        - Unicode normalization attacks (homoglyph mixing)

        Parameters
        ----------
        text:
            Text to analyze.
        check_prompt_injection:
            If True, check for prompt injection patterns.
        check_sql_injection:
            If True, check for SQL injection patterns.
        check_command_injection:
            If True, check for command injection patterns.
        check_unicode_attacks:
            If True, check for unicode normalization attacks.

        Returns
        -------
        InjectionDetectionResult
            Detection result with injection types and match counts.
        """
        injection_patterns_matched: dict[str, int] = {}
        injection_types: set[str] = set()

        # Prompt injection detection
        if check_prompt_injection:
            for pattern in PROMPT_INJECTION_PATTERNS:
                matches = len(pattern.findall(text))
                if matches > 0:
                    injection_patterns_matched["prompt_injection"] = (
                        injection_patterns_matched.get("prompt_injection", 0) + matches
                    )
                    injection_types.add("prompt_injection")

        # SQL injection detection
        if check_sql_injection:
            for pattern in SQL_INJECTION_PATTERNS:
                matches = len(pattern.findall(text))
                if matches > 0:
                    injection_patterns_matched["sql_injection"] = (
                        injection_patterns_matched.get("sql_injection", 0) + matches
                    )
                    injection_types.add("sql_injection")

        # Command injection detection
        if check_command_injection:
            for pattern in COMMAND_INJECTION_PATTERNS:
                matches = len(pattern.findall(text))
                if matches > 0:
                    injection_patterns_matched["command_injection"] = (
                        injection_patterns_matched.get("command_injection", 0) + matches
                    )
                    injection_types.add("command_injection")

        # Unicode normalization attack detection
        if check_unicode_attacks:
            for pattern in UNICODE_NORMALIZATION_ATTACK_PATTERNS:
                matches = len(pattern.findall(text))
                if matches > 0:
                    injection_patterns_matched["unicode_attack"] = (
                        injection_patterns_matched.get("unicode_attack", 0) + matches
                    )
                    injection_types.add("unicode_attack")

        return InjectionDetectionResult(
            is_injection_detected=len(injection_types) > 0,
            injection_types=sorted(injection_types),
            injection_patterns_matched=injection_patterns_matched,
        )

    def redact_output(self, raw_output: str) -> OutputRedactionResult:
        """Redact PII and secrets from output using canonical rules.

        Per ICD v0.1 Redaction Policy, this applies canonical redaction rules
        before sending output to external services or logging.

        Parameters
        ----------
        raw_output:
            Raw output from LLM or internal service.

        Returns
        -------
        OutputRedactionResult
            Redacted output and list of rules applied.

        Raises
        ------
        GuardrailsError
            If redaction fails.
        """
        try:
            result: RedactionResult = redact(raw_output, self.redaction_rules)
            return OutputRedactionResult(
                redacted_output=result.redacted_text,
                rules_applied=result.rules_applied,
            )
        except Exception as e:
            raise GuardrailsError(f"Output redaction failed: {e}") from e

    def guard_input(self, raw_input: str) -> GuardrailsResult:
        """Apply full guardrails pipeline to input (sanitize + detect).

        Parameters
        ----------
        raw_input:
            Raw user input.

        Returns
        -------
        GuardrailsResult
            Result with passed=True if input is clean, False if injection detected.
        """
        try:
            # Step 1: Sanitize input
            sanitization_result = self.sanitize_input(raw_input)
            sanitized_input = sanitization_result.sanitized_input

            # Step 2: Detect injections in sanitized input
            injection_result = self.detect_injections(sanitized_input)

            # Step 3: Return result (passed=True if no injections)
            passed = not injection_result.is_injection_detected

            return GuardrailsResult(
                passed=passed,
                input_sanitization=sanitization_result,
                injection_detection=injection_result,
                output_redaction=None,
                error=None if passed else "Injection patterns detected",
            )
        except GuardrailsError as e:
            return GuardrailsResult(
                passed=False,
                input_sanitization=InputSanitizationResult(""),
                injection_detection=InjectionDetectionResult(
                    is_injection_detected=False,
                    injection_types=[],
                    injection_patterns_matched={},
                ),
                output_redaction=None,
                error=str(e),
            )

    def guard_output(self, raw_output: str) -> GuardrailsResult:
        """Apply output redaction guardrails (redact only).

        Parameters
        ----------
        raw_output:
            Raw output from LLM or service.

        Returns
        -------
        GuardrailsResult
            Result with redacted output and rules applied.
        """
        try:
            redaction_result = self.redact_output(raw_output)
            return GuardrailsResult(
                passed=True,
                input_sanitization=InputSanitizationResult(raw_output),
                injection_detection=InjectionDetectionResult(
                    is_injection_detected=False,
                    injection_types=[],
                    injection_patterns_matched={},
                ),
                output_redaction=redaction_result,
                error=None,
            )
        except GuardrailsError as e:
            return GuardrailsResult(
                passed=False,
                input_sanitization=InputSanitizationResult(raw_output),
                injection_detection=InjectionDetectionResult(
                    is_injection_detected=False,
                    injection_types=[],
                    injection_patterns_matched={},
                ),
                output_redaction=None,
                error=str(e),
            )

    def guard_roundtrip(self, raw_input: str, raw_output: str) -> GuardrailsResult:
        """Apply full pipeline to both input and output.

        This is the highest-assurance guardrails check, typically used for
        sensitive operations where both input and output must be validated.

        Parameters
        ----------
        raw_input:
            Raw user input.
        raw_output:
            Raw model output.

        Returns
        -------
        GuardrailsResult
            Result combining input and output checks. passed=True only if:
            - Input is clean (no injections detected)
            - Output is redacted (no PII/secrets remain unredacted)
        """
        # Step 1: Guard input (sanitize + detect injections)
        input_result = self.guard_input(raw_input)

        # If input fails, return early
        if not input_result.passed:
            return input_result

        # Step 2: Guard output (redact PII/secrets)
        output_result = self.guard_output(raw_output)

        # Step 3: Combine results
        return GuardrailsResult(
            passed=input_result.passed and output_result.passed,
            input_sanitization=input_result.input_sanitization,
            injection_detection=input_result.injection_detection,
            output_redaction=output_result.output_redaction,
            error=input_result.error or output_result.error,
        )


# ---------------------------------------------------------------------------
# Factory Functions
# ---------------------------------------------------------------------------


def create_default_engine() -> GuardrailsEngine:
    """Create a default GuardrailsEngine with canonical settings.

    This is the recommended way to instantiate the guardrails engine for
    production use.

    Returns
    -------
    GuardrailsEngine
        Engine with canonical redaction rules.
    """
    return GuardrailsEngine(redaction_rules=canonicalize_redaction_rules())
