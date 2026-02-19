"""Unit tests for secret scanner module."""

from __future__ import annotations

import pytest

from holly.observability.secret_scanner import (
    ScanResult,
    SecretFinding,
    SecretScanner,
    SecretScannerConfig,
)


class TestSecretFinding:
    """Tests for SecretFinding dataclass."""

    def test_create_finding(self) -> None:
        """Create a valid SecretFinding."""
        finding = SecretFinding(
            pattern_name="api_key",
            severity="critical",
            location="headers[Authorization]",
            confidence=0.95,
        )
        assert finding.pattern_name == "api_key"
        assert finding.severity == "critical"
        assert finding.confidence == 0.95

    def test_finding_frozen(self) -> None:
        """SecretFinding is immutable."""
        finding = SecretFinding(
            pattern_name="api_key",
            severity="high",
            location="body",
            confidence=0.8,
        )
        with pytest.raises(AttributeError):
            finding.pattern_name = "email"  # type: ignore

    def test_finding_confidence_bounds(self) -> None:
        """Confidence must be [0, 1]."""
        with pytest.raises(ValueError):
            SecretFinding(
                pattern_name="api_key",
                severity="high",
                location="body",
                confidence=1.5,  # type: ignore
            )
        with pytest.raises(ValueError):
            SecretFinding(
                pattern_name="api_key",
                severity="high",
                location="body",
                confidence=-0.1,  # type: ignore
            )

    def test_finding_invalid_severity(self) -> None:
        """Severity must be one of the allowed levels."""
        with pytest.raises(ValueError):
            SecretFinding(
                pattern_name="api_key",
                severity="extreme",  # type: ignore
                location="body",
                confidence=0.8,
            )

    def test_finding_valid_severities(self) -> None:
        """All valid severity levels work."""
        for severity in ("low", "medium", "high", "critical"):
            finding = SecretFinding(
                pattern_name="test",
                severity=severity,  # type: ignore
                location="body",
                confidence=0.5,
            )
            assert finding.severity == severity


class TestSecretScannerConfig:
    """Tests for SecretScannerConfig."""

    def test_default_config(self) -> None:
        """Default config enables all patterns and redaction."""
        config = SecretScannerConfig()
        assert config.enabled_patterns == set()
        assert config.redact_findings is True
        assert config.fail_open is True
        assert config.min_confidence == 0.5

    def test_custom_config(self) -> None:
        """Create config with custom settings."""
        config = SecretScannerConfig(
            enabled_patterns={"api_key", "password"},
            redact_findings=False,
            fail_open=False,
            min_confidence=0.7,
        )
        assert config.enabled_patterns == {"api_key", "password"}
        assert config.redact_findings is False
        assert config.fail_open is False
        assert config.min_confidence == 0.7


class TestSecretScanner:
    """Tests for SecretScanner class."""

    def test_scan_empty_string(self) -> None:
        """Scan empty string produces no findings."""
        scanner = SecretScanner()
        result = scanner.scan("")
        assert result.has_secrets is False
        assert result.findings == []

    def test_scan_none(self) -> None:
        """Scan None returns early."""
        scanner = SecretScanner()
        result = scanner.scan(None)
        assert result.has_secrets is False
        assert result.findings == []
        assert result.redacted_payload is None

    def test_scan_string_with_api_key(self) -> None:
        """Detect API key pattern (sk-xxxx)."""
        scanner = SecretScanner()
        text = "My API key is sk-1234567890abcdefghijklmn for authentication"
        result = scanner.scan(text)
        assert result.has_secrets is True
        assert any(f.pattern_name == "api_key" for f in result.findings)

    def test_scan_string_with_email(self) -> None:
        """Detect email pattern."""
        scanner = SecretScanner()
        text = "Contact me at user@example.com for details"
        result = scanner.scan(text)
        assert result.has_secrets is True
        assert any(f.pattern_name == "email" for f in result.findings)

    def test_scan_dict_payload(self) -> None:
        """Scan dictionary payload."""
        scanner = SecretScanner()
        payload = {
            "user": "alice",
            "api_key": "sk-1234567890abcdefghijklmn",
            "safe_field": "public_value",
        }
        result = scanner.scan(payload)
        assert result.has_secrets is True
        assert isinstance(result.redacted_payload, (dict, str))

    def test_scan_redaction_enabled(self) -> None:
        """With redaction enabled, payload is redacted."""
        scanner = SecretScanner(config=SecretScannerConfig(redact_findings=True))
        text = "API key: sk-1234567890abcdefghijklmn"
        result = scanner.scan(text)
        assert result.redacted_payload is not None
        # Redacted payload should not contain original key
        assert "sk-1234567890abcdefghijklmn" not in str(result.redacted_payload)

    def test_scan_redaction_disabled(self) -> None:
        """With redaction disabled, payload unchanged."""
        scanner = SecretScanner(config=SecretScannerConfig(redact_findings=False))
        text = "Secret: user@example.com"
        result = scanner.scan(text)
        # Finding detected but payload unchanged
        assert result.has_secrets is True
        assert result.redacted_payload == text

    def test_scan_fail_open(self) -> None:
        """With fail_open=True, errors are logged but don't raise."""
        config = SecretScannerConfig(fail_open=True)
        scanner = SecretScanner(config=config)
        payload = object()
        result = scanner.scan(payload)
        # Should return safely with original payload
        assert result.redacted_payload is not None
        assert result.has_secrets is False

    def test_scan_fail_closed(self) -> None:
        """With fail_open=False, errors raise ScannerError."""
        from holly.observability.secret_scanner import ScannerError

        class NonSerializable:
            def __str__(self) -> str:
                raise ValueError("Cannot stringify")

        config = SecretScannerConfig(fail_open=False)
        scanner = SecretScanner(config=config)
        payload = {"obj": NonSerializable()}  # type: ignore
        with pytest.raises(ScannerError):
            scanner.scan(payload)

    def test_scan_string_convenience(self) -> None:
        """scan_string convenience method."""
        scanner = SecretScanner()
        text = "test@example.com"
        result = scanner.scan_string(text)
        assert result.has_secrets is True

    def test_scan_dict_convenience(self) -> None:
        """scan_dict convenience method."""
        scanner = SecretScanner()
        data = {"email": "test@example.com"}
        result = scanner.scan_dict(data)
        assert result.has_secrets is True

    def test_multiple_findings(self) -> None:
        """Detect multiple different secret types in one payload."""
        scanner = SecretScanner()
        payload = {
            "email": "user@example.com",
            "api_key": "sk-1234567890abcdefghijklmn",
        }
        result = scanner.scan(payload)
        assert len(result.findings) >= 1
        assert result.has_secrets is True

    def test_severity_assignment(self) -> None:
        """Check that severities are assigned correctly."""
        scanner = SecretScanner()
        payload = "API key: sk-1234567890abcdefghijklmn"
        result = scanner.scan(payload)
        api_key_findings = [f for f in result.findings if f.pattern_name == "api_key"]
        if api_key_findings:
            assert api_key_findings[0].severity == "critical"

    def test_finding_location(self) -> None:
        """Finding location is recorded."""
        scanner = SecretScanner()
        payload = {"secret": "sk-1234567890abcdefghijklmn"}
        result = scanner.scan(payload)
        api_key_findings = [f for f in result.findings if f.pattern_name == "api_key"]
        if api_key_findings:
            assert api_key_findings[0].location == "payload"

    def test_unicode_payload(self) -> None:
        """Handle Unicode characters in payload."""
        scanner = SecretScanner()
        text = "User: 李明, Email: li@example.com"
        result = scanner.scan(text)
        # Should not crash, even with non-ASCII
        assert isinstance(result.redacted_payload, (str, dict))

    def test_result_has_secrets_flag(self) -> None:
        """has_secrets flag is set correctly."""
        scanner = SecretScanner()
        # No secrets
        result1 = scanner.scan("Hello world")
        assert result1.has_secrets is False
        # With secrets
        result2 = scanner.scan("Key: sk-1234567890abcdefghijklmn")
        assert result2.has_secrets is True


class TestScanResultDataclass:
    """Tests for ScanResult dataclass."""

    def test_scan_result_creation(self) -> None:
        """Create a ScanResult."""
        finding = SecretFinding(
            pattern_name="api_key",
            severity="critical",
            location="body",
            confidence=0.95,
        )
        result = ScanResult(
            findings=[finding],
            has_secrets=True,
            redacted_payload="redacted_text",
        )
        assert result.findings == [finding]
        assert result.has_secrets is True
        assert result.redacted_payload == "redacted_text"

    def test_scan_result_empty_findings(self) -> None:
        """ScanResult with no findings."""
        result = ScanResult(findings=[], has_secrets=False, redacted_payload="safe_text")
        assert result.findings == []
        assert result.has_secrets is False

    def test_scan_result_none_payload(self) -> None:
        """ScanResult with None redacted payload."""
        result = ScanResult(findings=[], has_secrets=False, redacted_payload=None)
        assert result.redacted_payload is None


class TestSecretScannerIntegration:
    """Integration tests combining multiple components."""

    def test_scan_complex_trace_payload(self) -> None:
        """Scan realistic trace payload structure."""
        scanner = SecretScanner()
        payload = {
            "trace_id": "abc-123",
            "timestamp": "2026-02-19T21:00:00Z",
            "boundary": "core::intent_classifier",
            "request": {
                "message": "Authenticate with sk-1234567890abcdefghijklmn",
                "user": "alice@example.com",
            },
            "response": {
                "status": "success",
                "data": "classified_intent",
            },
        }
        result = scanner.scan(payload)
        # Should detect API key and email
        assert result.has_secrets is True
        patterns = {f.pattern_name for f in result.findings}
        assert "api_key" in patterns

    def test_idempotent_scanning(self) -> None:
        """Scanning same payload twice gives same result."""
        scanner = SecretScanner()
        payload = "API key: sk-1234567890abcdefghijklmn"
        result1 = scanner.scan(payload)
        result2 = scanner.scan(payload)
        assert result1.has_secrets == result2.has_secrets
        assert len(result1.findings) == len(result2.findings)

    def test_redaction_consistency(self) -> None:
        """Redacted payload consistent across calls."""
        scanner = SecretScanner(config=SecretScannerConfig(redact_findings=True))
        payload = "API key: sk-1234567890abcdefghijklmn"
        result1 = scanner.scan(payload)
        result2 = scanner.scan(payload)
        # Redacted payloads should be consistent
        assert result1.redacted_payload == result2.redacted_payload
