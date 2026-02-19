from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "API_KEY_PATTERNS",
    "CREDIT_CARD_PATTERN",
    "EMAIL_PATTERN",
    "PHONE_PATTERN",
    "SSN_PATTERN",
    "RedactionError",
    "RedactionResult",
    "RedactionRule",
    "canonicalize_redaction_rules",
    "detect_pii",
    "redact",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RedactionError(Exception):
    """Raised when redaction cannot be applied safely."""

    pass


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------


class RedactionRule:
    """Immutable redaction rule definition.

    A redaction rule matches a pattern in text and replaces matched portions
    with a placeholder. Rules are applied in a deterministic order, with support
    for custom replacements (e.g., credit cards preserve last 4 digits).

    Attributes
    ----------
    name : str
        Canonical rule name (e.g., "email", "api_key"). Must be unique.
    pattern : re.Pattern[str]
        Compiled regex. If the pattern matches, the rule fires.
    replacement : str | Callable[[re.Match[str]], str]
        Static replacement string or callback function that computes the
        replacement for a given match.
    """

    __slots__ = ("name", "pattern", "replacement")

    def __init__(
        self,
        name: str,
        pattern: re.Pattern[str],
        replacement: str | Callable[[re.Match[str]], str],
    ) -> None:
        """Initialize rule.

        Parameters
        ----------
        name:
            Canonical rule identifier.
        pattern:
            Compiled regex to match.
        replacement:
            String or callable to replace matched text.
        """
        self.name: str = name
        self.pattern: re.Pattern[str] = pattern
        self.replacement: str | Callable[[re.Match[str]], str] = replacement


class RedactionResult:
    """Result of a redaction operation.

    Attributes
    ----------
    redacted_text : str
        Text after applying all active redaction rules.
    rules_applied : list[str]
        Sorted list of rule names that fired (empty if no matches).
    """

    __slots__ = ("redacted_text", "rules_applied")

    def __init__(self, redacted_text: str, rules_applied: list[str]) -> None:
        """Initialize result.

        Parameters
        ----------
        redacted_text:
            Text after redaction.
        rules_applied:
            Rules that matched and were applied.
        """
        self.redacted_text: str = redacted_text
        self.rules_applied: list[str] = sorted(rules_applied)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RedactionResult):
            return NotImplemented
        return (
            self.redacted_text == other.redacted_text
            and self.rules_applied == other.rules_applied
        )

    def __repr__(self) -> str:
        return (
            f"RedactionResult("
            f"redacted_text={self.redacted_text!r}, "
            f"rules_applied={self.rules_applied})"
        )


# ---------------------------------------------------------------------------
# Canonical Redaction Patterns
# ---------------------------------------------------------------------------

# Email: RFC 5322-simplified local-part + @ + domain + TLD
EMAIL_PATTERN: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# API keys: three patterns
#   1. OpenAI format: sk-xxxx (24+ chars)
#   2. Bearer token format: Bearer <long_string>
#   3. Generic patterns: {api_key,key,secret,token}=<string>
#      (refined to avoid matching credit cards by requiring specific keywords)
_API_KEY_OPENAI_PAT: re.Pattern[str] = re.compile(r"sk-[A-Za-z0-9\-]{20,}", re.IGNORECASE)
_API_KEY_BEARER_PAT: re.Pattern[str] = re.compile(
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE
)
_API_KEY_GENERIC_PAT: re.Pattern[str] = re.compile(
    r"(?:api_key|api-key|apikey|key|secret|token|passwd|password)[=:\s\"']+[A-Za-z0-9._\-=+/]{8,}",
    re.IGNORECASE,
)
API_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    _API_KEY_OPENAI_PAT,
    _API_KEY_BEARER_PAT,
    _API_KEY_GENERIC_PAT,
)

# Credit card: 16 digits in 4 groups (hyphen or space separators optional)
# Capture groups: (1) = digits 1-4, (2) = 5-8, (3) = 9-12, (4) = 13-16 (last 4)
CREDIT_CARD_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})\b"
)

# SSN: NNN-NN-NNNN
SSN_PATTERN: re.Pattern[str] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Phone: optional country code, optional parentheses, various separators
PHONE_PATTERN: re.Pattern[str] = re.compile(
    r"\b\+?1?[\s\-]?\(?(\d{3})\)?[\s\-]?\d{3}[\s\-]\d{4}\b"
)


# ---------------------------------------------------------------------------
# Canonical Redaction Rules
# ---------------------------------------------------------------------------


def _credit_card_replacement(m: re.Match[str]) -> str:
    """Preserve last 4 digits of credit card."""
    return f"****-****-****-{m.group(4)}"


_CANONICAL_RULES: tuple[RedactionRule, ...] = (
    RedactionRule("email", EMAIL_PATTERN, "[email hidden]"),
    RedactionRule("credit_card", CREDIT_CARD_PATTERN, _credit_card_replacement),
    RedactionRule("api_key", _API_KEY_OPENAI_PAT, "[secret redacted]"),
    RedactionRule("api_key", _API_KEY_BEARER_PAT, "[secret redacted]"),
    RedactionRule("api_key", _API_KEY_GENERIC_PAT, "[secret redacted]"),
    RedactionRule("ssn", SSN_PATTERN, "[pii redacted]"),
    RedactionRule("phone", PHONE_PATTERN, "[pii redacted]"),
)


def canonicalize_redaction_rules() -> tuple[RedactionRule, ...]:
    """Return the canonical set of ICD v0.1 redaction rules.

    Rules are applied in order (email → credit_card → api_key → ssn → phone).
    Per ICD v0.1, all interfaces must apply these rules before logging,
    transmitting to external services, or persisting sensitive data.

    Returns
    -------
    tuple[RedactionRule, ...]
        Immutable tuple of redaction rules in application order.
    """
    return _CANONICAL_RULES


# ---------------------------------------------------------------------------
# Redaction API
# ---------------------------------------------------------------------------


def redact(
    text: str,
    rules: tuple[RedactionRule, ...] | None = None,
) -> RedactionResult:
    """Apply redaction rules to *text*.

    Rules are applied in order. Each rule's pattern is applied, and if a match
    is found, the matched text is replaced (statefully). The function returns
    both the redacted text and a sorted list of rule names that fired.

    Per ICD v0.1 Redaction Policy, this function is the single source of truth
    for redaction across all Holly interfaces. It is called by:

    - K6 gate (audit WAL before append)
    - Event channels (before publishing)
    - Trace store (before persistence)
    - Egress gateway (before transmitting to Claude API)
    - Guardrails (before sending prompts to LLM)

    Parameters
    ----------
    text:
        Raw input string (typically user input, API response, or audit entry).
    rules:
        Tuple of RedactionRule objects. If ``None``, uses canonical rules from
        ``canonicalize_redaction_rules()``.

    Returns
    -------
    RedactionResult
        Contains ``redacted_text`` (text after all rules) and ``rules_applied``
        (sorted rule names that matched).

    Raises
    ------
    RedactionError
        If a rule's replacement callback raises an exception.

    Examples
    --------
    >>> result = redact("Email: alice@example.com and credit card 4111-1111-1111-1111")
    >>> result.redacted_text
    'Email: [email hidden] and credit card ****-****-****-1111'
    >>> result.rules_applied
    ['credit_card', 'email']
    """
    if rules is None:
        rules = canonicalize_redaction_rules()

    current_text = text
    rules_applied: set[str] = set()

    for rule in rules:
        try:
            if callable(rule.replacement):
                redacted_text, n = rule.pattern.subn(rule.replacement, current_text)
            else:
                redacted_text, n = rule.pattern.subn(rule.replacement, current_text)

            if n > 0:
                current_text = redacted_text
                rules_applied.add(rule.name)
        except Exception as e:
            raise RedactionError(
                f"Redaction rule {rule.name!r} failed: {e}"
            ) from e

    return RedactionResult(current_text, sorted(rules_applied))


def detect_pii(
    text: str,
    rules: tuple[RedactionRule, ...] | None = None,
) -> bool:
    """Return ``True`` if *text* contains any pattern matched by redaction rules.

    This function is called BEFORE redaction to determine if a value contains
    sensitive data (PII/secrets), which is then tracked in audit entries via
    the ``contains_pii_before_redaction`` flag per ICD-025 (Audit Events).

    Parameters
    ----------
    text:
        Raw input string to check.
    rules:
        Tuple of RedactionRule objects. If ``None``, uses canonical rules.

    Returns
    -------
    bool
        ``True`` if any rule's pattern matches.

    Examples
    --------
    >>> detect_pii("user email is alice@example.com")
    True
    >>> detect_pii("hello world")
    False
    """
    if rules is None:
        rules = canonicalize_redaction_rules()

    return any(rule.pattern.search(text) for rule in rules)
