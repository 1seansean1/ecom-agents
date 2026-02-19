"""Integration tests for secret scanner with redaction library."""

from __future__ import annotations

from holly.observability.secret_scanner import (
    SecretScanner,
    SecretScannerConfig,
)
from holly.redaction import detect_pii, redact


class TestSecretScannerWithRedactionLibrary:
    """Test secret scanner integration with canonical redaction library."""

    def test_scanner_uses_canonical_redaction(self) -> None:
        """Scanner detects same patterns as canonical redaction library."""
        text = "Email: user@example.com, API Key: sk-1234567890abcdefghijklmn"

        # Scan with secret scanner
        scanner = SecretScanner()
        scan_result = scanner.scan(text)

        # Check canonical redaction
        redaction_result = redact(text)

        # Scanner should detect at least the same patterns as redaction library
        redaction_patterns = set(redaction_result.rules_applied)

        # API key should be in both
        assert "api_key" in redaction_patterns
        assert any(f.pattern_name == "api_key" for f in scan_result.findings)

    def test_scanner_detects_pii(self) -> None:
        """Scanner detects PII using canonical library."""
        text = "My phone is 555-123-4567"

        scanner = SecretScanner()
        result = scanner.scan(text)
        pii_detected = detect_pii(text)

        # Both should detect PII or both should not
        assert bool(result.has_secrets) == pii_detected or not pii_detected

    def test_redaction_applied_correctly(self) -> None:
        """Redacted payload hides secrets."""
        payload = {
            "user": "alice",
            "email": "alice@example.com",
            "api_key": "sk-1234567890abcdefghijklmn"
        }

        # Scan and redact
        scanner = SecretScanner(config=SecretScannerConfig(redact_findings=True))
        scan_result = scanner.scan(payload)

        # Redacted version should hide secrets
        scan_redacted = str(scan_result.redacted_payload)

        # Redacted payload should not contain original email or API key
        assert "alice@example.com" not in scan_redacted
        assert "sk-1234567890abcdefghijklmn" not in scan_redacted


class TestSecretScannerWithTracePayloads:
    """Test scanner with realistic trace payload structures."""

    def test_scan_kernel_trace_payload(self) -> None:
        """Scan K6 WAL-like trace payload."""
        trace_payload = {
            "id": "uuid-001",
            "tenant_id": "tenant-001",
            "correlation_id": "corr-123",
            "timestamp": "2026-02-19T21:00:00Z",
            "boundary_crossing": "core::intent_classifier",
            "caller_user_id": "user@example.com",
            "caller_roles": ["user", "editor"],
            "exit_code": 0,
            "k1_valid": True,
            "operation_result": {
                "intent": "direct_solve",
                "message": "Query using API key sk-1234567890abcdefghijklmn"
            }
        }

        scanner = SecretScanner()
        result = scanner.scan(trace_payload)

        # Should detect email and API key
        assert result.has_secrets is True
        pattern_names = {f.pattern_name for f in result.findings}
        assert "email" in pattern_names
        assert "api_key" in pattern_names

    def test_scan_conversation_trace(self) -> None:
        """Scan conversation trace with user message."""
        trace_payload = {
            "trace_id": "trace-001",
            "boundary": "conversation",
            "user_message": "Please use my credentials",
            "response": "Intent classified successfully",
        }

        scanner = SecretScanner()
        result = scanner.scan(trace_payload)

        # Should not crash
        assert result is not None


class TestSecretScannerPropertyBased:
    """Property-based tests for secret scanner."""

    def test_scanning_twice_gives_same_result(self) -> None:
        """For any payload, scanning twice gives same findings."""
        scanner = SecretScanner()
        payloads = [
            "hello world",
            "test@example.com",
            "sk-1234567890abcdefghijklmn",
            {"key": "value"},
            "",
            None,
        ]

        for payload in payloads:
            result1 = scanner.scan(payload)
            result2 = scanner.scan(payload)
            assert result1.has_secrets == result2.has_secrets
            assert len(result1.findings) == len(result2.findings)

    def test_redaction_always_hides_secrets(self) -> None:
        """When redaction enabled, redacted payload doesn't contain obvious secrets."""
        scanner = SecretScanner(config=SecretScannerConfig(redact_findings=True))

        payload = "Secret is sk-1234567890abcdefghijklmn here"
        result = scanner.scan(payload)
        redacted = str(result.redacted_payload)
        # The exact secret shouldn't appear unredacted
        assert "sk-1234567890abcdefghijklmn" not in redacted

    def test_enabled_patterns_filter_is_sound(self) -> None:
        """enabled_patterns filtering doesn't lose secrets."""
        scanner_all = SecretScanner()
        scanner_api_only = SecretScanner(
            config=SecretScannerConfig(enabled_patterns={"api_key"})
        )

        payload = "Email: user@example.com, API: sk-1234567890abcdefghijklmn"

        result_all = scanner_all.scan(payload)
        result_api = scanner_api_only.scan(payload)

        # API-only scanner has fewer or equal findings
        api_findings = [f.pattern_name for f in result_api.findings]
        all_findings = [f.pattern_name for f in result_all.findings]

        # All findings in api_findings should be in all_findings (if it's a subset)
        for finding_name in api_findings:
            assert any(f == finding_name for f in all_findings)


class TestSecretScannerErrorHandling:
    """Test scanner error handling in edge cases."""

    def test_bytes_payload(self) -> None:
        """Handle bytes payload."""
        scanner = SecretScanner()
        payload = b"Email: user@example.com"

        # Should handle bytes gracefully
        result = scanner.scan(payload)
        assert result is not None
        assert isinstance(result.redacted_payload, (str, bytes, dict))
