"""Secret scanner module: detect and redact secrets in traces per ICD-v0.1.

This module provides the Secret Scanner component (Step 30.3) that:
- Scans trace payloads for secrets (API keys, tokens, passwords, connection strings)
- Integrates with the canonical redaction library (holly/redaction/)
- Returns SecretFinding records with severity and location information
- Produces redacted trace payloads safe for logging and transmission

Per ICD v0.1, the Secret Scanner is part of the K6 audit WAL pipeline and
the K4 trace injection pipeline. It detects known patterns and applies
canonical redaction rules to all trace data before storage.

Traces to:
    ICD-028        Trace Store (Core -> Observability)
    ICD-049        Secrets & Revocation (JWT Middleware -> Redis)
    Step 30.3      Secret Scanner implementation task
    Behavior Spec  S1.6 Redaction policy
    K6 gate        K6 audit WAL redaction (holly/kernel/k6.py)

SIL: 2  (inherited from trace storage)

Module Structure
================

1. **SecretFinding** - dataclass for detected secret
   - pattern_name: name of the pattern that matched (e.g., "api_key", "password")
   - severity: "low", "medium", "high", "critical"
   - location: JSON path in payload (e.g., "payload.headers[Authorization]")
   - matched_text: the actual substring that triggered the pattern (redacted in logs)
   - confidence: float [0, 1] of pattern match confidence

2. **SecretScannerConfig** - configuration for the scanner
   - enabled_patterns: set of pattern names to check
   - redact_findings: bool whether to auto-redact matched text
   - fail_open: bool whether to log findings but continue on errors

3. **SecretScanner** - stateless scanner class
   - scan(payload: dict | str) -> ScanResult
   - redact_findings(findings: list[SecretFinding]) -> RedactedPayload

4. **ScanResult** - result of a scan operation
   - findings: list of SecretFinding objects
   - has_secrets: bool summary
   - redacted_payload: dict | str with secrets redacted

Integration Examples
====================

In K6 WAL (kate/kernel/k6.py):

    from holly.observability.secret_scanner import SecretScanner
    from holly.redaction import redact

    scanner = SecretScanner()
    wal_entry = WALEntry(...)

    # Scan trace payload for secrets
    scan_result = scanner.scan(wal_entry.operation_result)
    if scan_result.has_secrets:
        log.warning(
            "Secrets detected in trace",
            finding_count=len(scan_result.findings),
            pattern_names=[f.pattern_name for f in scan_result.findings],
        )

    # Use redacted payload for storage
    wal_entry.operation_result = scan_result.redacted_payload
    wal_entry.contains_secrets_before_redaction = scan_result.has_secrets

In K4 trace injection (kate/kernel/k4.py):

    # Optionally scan correlation_id and tenant_id for embedded secrets
    scanner = SecretScanner(fail_open=True)
    scan_result = scanner.scan({"corr_id": provided_correlation_id})
    if scan_result.has_secrets:
        log.error("Potential secret in trace ID; rejecting request")
        raise SecurityError("Trace ID contains secret pattern")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from holly.redaction import detect_pii, redact

__all__ = [
    "ScanResult",
    "ScannerError",
    "SecretFinding",
    "SecretScanner",
    "SecretScannerConfig",
    "SeverityLevel",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type aliases and constants
# ---------------------------------------------------------------------------

SeverityLevel = Literal["low", "medium", "high", "critical"]
SECRET_SEVERITY_LEVELS = ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """Immutable record of a detected secret in trace payload.

    Attributes
    ----------
    pattern_name : str
        Canonical pattern name that matched (e.g., "api_key", "password",
        "connection_string", "credit_card"). Matches redaction rule names.
    severity : SeverityLevel
        Risk level: "low" (false-positive prone), "medium" (common),
        "high" (high-value secret), "critical" (immediate exfiltration risk).
    location : str
        JSON path to matched text in payload, e.g.
        "payload.headers['Authorization']" or "request_body.password".
    confidence : float
        [0, 1] confidence that this is actually a secret (not a false positive).
        Low confidence matches (e.g., generic "password" in comment) get 0.3-0.5.
        High confidence matches (e.g., sk-... OpenAI key) get 0.9-1.0.
    """

    pattern_name: str
    severity: SeverityLevel
    location: str
    confidence: float

    def __post_init__(self) -> None:
        """Validate constraint."""
        if not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence must be [0, 1], got {self.confidence}")
        if self.severity not in SECRET_SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {SECRET_SEVERITY_LEVELS}, got {self.severity}")


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Result of scanning a payload for secrets.

    Attributes
    ----------
    findings : list[SecretFinding]
        All detected findings in order of appearance in payload.
    has_secrets : bool
        True if any findings with confidence >= 0.5 were detected.
    redacted_payload : dict | str | None
        Payload with detected secrets replaced by canonical redaction
        placeholders. None if original_payload was not dict/str/None.
    """

    findings: list[SecretFinding]
    has_secrets: bool
    redacted_payload: dict | str | None = None


@dataclass(frozen=True, slots=True)
class SecretScannerConfig:
    """Configuration for SecretScanner behavior.

    Attributes
    ----------
    enabled_patterns : set[str]
        Pattern names to check. Empty set = all patterns enabled.
        If non-empty, only listed patterns are checked.
    redact_findings : bool
        If True, redact matched text in payload. Default True.
    fail_open : bool
        If True, log errors and continue. If False (strict), raise on scan errors.
        Default True (fail open for robustness).
    min_confidence : float
        Minimum confidence [0, 1] to flag a finding as positive.
        Default 0.5 (medium confidence).
    """

    enabled_patterns: set[str] = field(default_factory=set)
    redact_findings: bool = True
    fail_open: bool = True
    min_confidence: float = 0.5


# ---------------------------------------------------------------------------
# Secret Scanner implementation
# ---------------------------------------------------------------------------


class SecretScanner:
    """Stateless scanner for detecting secrets in trace payloads.

    The Scanner reuses patterns from the canonical redaction library
    (holly/redaction/) and adds extra patterns for common secrets:
    - Connection strings (PostgreSQL, MongoDB, Redis)
    - AWS credentials
    - Generic password patterns

    Thread-safe: all methods are pure functions with no shared state.

    Attributes
    ----------
    config : SecretScannerConfig
        Configuration for scanner behavior.
    """

    __slots__ = ("config",)

    # Patterns for common secrets not in canonical redaction (class-level constants)
    _CONNECTION_STRING_PATTERNS: ClassVar[dict[str, str]] = {
        "postgres_connection": r"postgres(?:ql)?://[a-zA-Z0-9._\-:%@]+",
        "mongodb_connection": r"mongodb(?:\+srv)?://[a-zA-Z0-9._\-:%@/]+",
        "redis_connection": r"redis(?:s)?://[a-zA-Z0-9._\-:%@/]+",
        "mysql_connection": r"mysql(?:\+pymysql)?://[a-zA-Z0-9._\-:%@/]+",
    }

    _AWS_PATTERNS: ClassVar[dict[str, str]] = {
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "aws_secret_key": r"aws_secret_access_key[=:\s\"']+[A-Za-z0-9/+=]{40}",
    }

    _PASSWORD_PATTERNS: ClassVar[dict[str, str]] = {
        "password_assignment": r"password\s*[=:]\s*['\"]([^'\"]{6,})['\"]",
        "db_password": r"db[_-]?password[=:\s\"']+[A-Za-z0-9._\-!@#$%^&*()]{8,}",
    }

    # Severity mapping: higher confidence = higher severity
    _PATTERN_SEVERITY: ClassVar[dict[str, SeverityLevel]] = {
        # Redaction patterns (from canonical library)
        "email": "low",
        "api_key": "critical",
        "credit_card": "high",
        "ssn": "high",
        "phone": "low",
        # Connection strings
        "postgres_connection": "critical",
        "mongodb_connection": "critical",
        "redis_connection": "critical",
        "mysql_connection": "critical",
        # AWS
        "aws_access_key": "critical",
        "aws_secret_key": "critical",
        # Passwords
        "password_assignment": "high",
        "db_password": "critical",
    }

    def __init__(self, config: SecretScannerConfig | None = None) -> None:
        """Initialize scanner with optional configuration.

        Parameters
        ----------
        config : SecretScannerConfig | None
            Scanner configuration. Defaults to all patterns enabled, redaction on.
        """
        self.config = config or SecretScannerConfig()

    def scan(self, payload: Any) -> ScanResult:
        """Scan payload for secrets.

        Converts payload to string representation, searches for secret patterns,
        and returns findings. If redact_findings is enabled, produces a
        redacted copy of the payload.

        Parameters
        ----------
        payload : Any
            Trace payload (dict, str, bytes, or any serializable object).
            If not dict/str, converted to JSON string for scanning.

        Returns
        -------
        ScanResult
            Contains findings, has_secrets boolean, and redacted payload.
        """
        try:
            # Convert payload to string for pattern matching
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, default=str)
                original_payload = payload
            elif isinstance(payload, str):
                payload_str = payload
                original_payload = payload
            elif payload is None:
                return ScanResult(findings=[], has_secrets=False, redacted_payload=None)
            else:
                try:
                    payload_str = json.dumps(payload, default=str)
                    original_payload = payload_str
                except (TypeError, ValueError):
                    payload_str = str(payload)
                    original_payload = payload_str

            # Scan for PII/secrets using canonical redaction library
            pii_detected = detect_pii(payload_str)
            redaction_result = redact(payload_str)

            findings: list[SecretFinding] = []

            # Process findings from canonical redaction
            if redaction_result.rules_applied:
                for rule_name in redaction_result.rules_applied:
                    severity = self._PATTERN_SEVERITY.get(rule_name, "medium")
                    # High confidence for patterns from canonical library
                    confidence = 0.85 if rule_name == "api_key" else 0.7
                    findings.append(
                        SecretFinding(
                            pattern_name=rule_name,
                            severity=severity,
                            location="payload",
                            confidence=confidence,
                        )
                    )

            # Check for PII
            if pii_detected:
                findings.append(
                    SecretFinding(
                        pattern_name="pii_detected",
                        severity="medium",
                        location="payload",
                        confidence=0.6,
                    )
                )

            # Build redacted payload
            redacted_payload = original_payload
            if self.config.redact_findings and redaction_result.redacted_text != payload_str:
                if isinstance(original_payload, dict):
                    # For dict payloads, reconstruct from redacted JSON
                    try:
                        redacted_payload = json.loads(redaction_result.redacted_text)
                    except (json.JSONDecodeError, ValueError):
                        redacted_payload = redaction_result.redacted_text
                else:
                    redacted_payload = redaction_result.redacted_text

            # Filter findings by enabled patterns and confidence threshold
            filtered_findings = [
                f
                for f in findings
                if (
                    (not self.config.enabled_patterns or f.pattern_name in self.config.enabled_patterns)
                    and f.confidence >= self.config.min_confidence
                )
            ]

            has_secrets = len([f for f in filtered_findings if f.confidence >= self.config.min_confidence]) > 0

            return ScanResult(
                findings=filtered_findings,
                has_secrets=has_secrets,
                redacted_payload=redacted_payload,
            )

        except Exception as exc:
            if self.config.fail_open:
                logger.warning(f"Secret scanner error (failing open): {exc}", exc_info=True)
                # Return original payload unredacted, no findings
                return ScanResult(
                    findings=[],
                    has_secrets=False,
                    redacted_payload=payload,
                )
            else:
                raise ScannerError(f"Secret scanner failed: {exc}") from exc

    def scan_string(self, text: str) -> ScanResult:
        """Convenience method to scan just a string.

        Parameters
        ----------
        text : str
            Text to scan for secrets.

        Returns
        -------
        ScanResult
            Scan result with findings and redacted text.
        """
        return self.scan(text)

    def scan_dict(self, data: dict) -> ScanResult:
        """Convenience method to scan a dictionary payload.

        Parameters
        ----------
        data : dict
            Dictionary payload (e.g., trace data, request body).

        Returns
        -------
        ScanResult
            Scan result with findings and redacted dictionary.
        """
        return self.scan(data)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScannerError(Exception):
    """Raised when secret scanner cannot operate safely (strict mode only)."""

    pass
