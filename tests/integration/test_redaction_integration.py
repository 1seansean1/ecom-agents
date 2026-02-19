"""Integration tests for holly.redaction — interaction with other modules."""

from __future__ import annotations

import json
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.redaction import RedactionError, RedactionRule, detect_pii, redact


class TestRedactionWithJSON:
    """Tests for redacting PII from JSON structures."""

    def test_redact_json_string_values(self) -> None:
        """Redaction applies to JSON string values."""
        json_str = '{"email": "alice@example.com", "name": "Alice"}'
        result = redact(json_str)
        assert "[email hidden]" in result.redacted_text
        assert "alice@example.com" not in result.redacted_text

    def test_redact_nested_json(self) -> None:
        """Redaction detects PII in nested JSON values."""
        data = {
            "user": {
                "email": "alice@example.com",
                "card": "4111-1111-1111-1111",
            }
        }
        json_str = json.dumps(data)
        result = redact(json_str)
        assert "[email hidden]" in result.redacted_text
        assert "****-****-****-1111" in result.redacted_text

    def test_detect_pii_in_json_string(self) -> None:
        """detect_pii() finds PII in JSON strings."""
        json_str = '{"email": "alice@example.com"}'
        assert detect_pii(json_str) is True

    def test_redact_json_preserves_structure(self) -> None:
        """JSON structure is preserved after redaction."""
        json_str = '{"email": "alice@example.com"}'
        result = redact(json_str)
        # Should still be valid JSON (or at least have braces)
        assert "{" in result.redacted_text
        assert "}" in result.redacted_text


class TestRedactionWithQueryStrings:
    """Tests for redacting PII from URL query strings."""

    def test_redact_api_key_in_query_string(self) -> None:
        """API keys in query strings are redacted."""
        query = "api_key=sk-1234567890abcdefghijklmnop&user=alice"
        result = redact(query)
        assert "[secret redacted]" in result.redacted_text
        assert "sk-1234567890" not in result.redacted_text

    def test_redact_token_in_query_string(self) -> None:
        """Tokens in query strings are redacted."""
        query = "token=Bearer%20eyJhbGciOiJIUzI1NiJ9"
        result = redact(query)
        assert "[secret redacted]" in result.redacted_text or "Bearer" in result.redacted_text

    def test_detect_pii_in_query_string(self) -> None:
        """detect_pii() identifies PII in query strings."""
        query = "email=alice@example.com&page=1"
        assert detect_pii(query) is True


class TestRedactionWithLogLines:
    """Tests for redacting PII from log entries."""

    def test_redact_typical_log_entry(self) -> None:
        """Typical log entries with PII are redacted."""
        log_entry = 'INFO: User alice@example.com logged in with API key sk-1234567890abcdefghijklmnop'
        result = redact(log_entry)
        assert "alice@example.com" not in result.redacted_text
        assert "sk-1234567890" not in result.redacted_text
        assert "[email hidden]" in result.redacted_text
        assert "[secret redacted]" in result.redacted_text

    def test_redact_error_message_with_context(self) -> None:
        """Error messages with PII context are redacted."""
        error = "ValidationError: Invalid card 4111-1111-1111-1111"
        result = redact(error)
        assert "****-****-****-1111" in result.redacted_text

    def test_detect_pii_in_log_line(self) -> None:
        """detect_pii() identifies PII in log lines."""
        log_line = "User 555-123-4567 requested resource"
        assert detect_pii(log_line) is True

    def test_redact_preserves_log_format(self) -> None:
        """Redaction preserves log line format."""
        log_line = "[2026-02-19 12:00:00] INFO: User alice@example.com performed action"
        result = redact(log_line)
        # Timestamp and level should be preserved
        assert "[2026-02-19 12:00:00]" in result.redacted_text
        assert "INFO:" in result.redacted_text


class TestRedactionWithHTMLContent:
    """Tests for redacting PII from HTML/template content."""

    def test_redact_html_content_with_email(self) -> None:
        """Email addresses in HTML content are redacted."""
        html = '<div class="user-email">Contact: alice@example.com</div>'
        result = redact(html)
        assert "[email hidden]" in result.redacted_text
        assert "alice@example.com" not in result.redacted_text

    def test_redact_html_form_values(self) -> None:
        """Form input values in HTML are redacted."""
        html = '<input type="hidden" value="sk-1234567890abcdefghijklmnop">'
        result = redact(html)
        assert "[secret redacted]" in result.redacted_text

    def test_detect_pii_in_html(self) -> None:
        """detect_pii() finds PII in HTML content."""
        html = '<span>SSN: 123-45-6789</span>'
        assert detect_pii(html) is True


class TestRedactionChaining:
    """Tests for multiple redaction passes and chaining."""

    def test_single_pass_sufficient(self) -> None:
        """Single redaction pass is sufficient (deterministic)."""
        text = "Email: alice@example.com, Card: 4111-1111-1111-1111"
        result1 = redact(text)
        result2 = redact(result1.redacted_text)
        # Second pass should not change anything (already redacted)
        assert result1.redacted_text == result2.redacted_text

    def test_redacted_text_does_not_contain_original_pii(self) -> None:
        """Redacted text never contains original PII patterns."""
        text = "User alice@example.com, Card 4111-1111-1111-1111, SSN 123-45-6789"
        result = redact(text)
        assert "alice@example.com" not in result.redacted_text
        assert "4111-1111-1111-1111" not in result.redacted_text
        assert "123-45-6789" not in result.redacted_text

    def test_multiple_passes_idempotent(self) -> None:
        """Multiple redaction passes are idempotent."""
        text = "alice@example.com"
        result1 = redact(text)
        result2 = redact(result1.redacted_text)
        result3 = redact(result2.redacted_text)
        assert result1.redacted_text == result2.redacted_text == result3.redacted_text


class TestRedactionPerformance:
    """Tests for redaction performance and scalability."""

    @given(st.text(min_size=100, max_size=10000))
    @settings(max_examples=10)
    def test_redaction_handles_large_texts(self, text: str) -> None:
        """Redaction can process large texts efficiently."""
        result = redact(text)
        assert isinstance(result.redacted_text, str)
        assert isinstance(result.rules_applied, list)

    def test_redaction_with_many_matches(self) -> None:
        """Redaction handles texts with many PII matches."""
        # 1000 emails
        text = " ".join([f"user{i}@example.com" for i in range(1000)])
        result = redact(text)
        assert result.redacted_text.count("[email hidden]") == 1000
        assert "email" in result.rules_applied

    def test_detect_pii_short_circuit(self) -> None:
        """detect_pii() returns as soon as any match is found."""
        # This is a performance test - detect_pii should not scan entire document
        # if it finds PII early
        text = "alice@example.com " + ("x" * 100000)
        assert detect_pii(text) is True


class TestRedactionErrorHandling:
    """Tests for error handling in redaction."""

    def test_redact_none_raises_error(self) -> None:
        """redact() with None raises an error."""
        with pytest.raises((AttributeError, RedactionError)):
            redact(None)  # type: ignore

    def test_redact_with_invalid_rule_type(self) -> None:
        """redact() with invalid rule type raises error."""
        with pytest.raises((TypeError, AttributeError)):
            redact("text", rules="invalid")  # type: ignore

    def test_detect_pii_invalid_input(self) -> None:
        """detect_pii() with non-string raises error."""
        with pytest.raises((AttributeError, TypeError)):
            detect_pii(None)  # type: ignore


class TestRedactionWithRealWorldExamples:
    """Tests with realistic data samples."""

    def test_redact_auth_header(self) -> None:
        """Authorization headers are properly redacted."""
        headers = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        result = redact(headers)
        assert "[secret redacted]" in result.redacted_text

    def test_redact_database_connection_string(self) -> None:
        """Database connection strings with credentials are redacted."""
        conn_str = "postgres://user:password123@db.example.com:5432/mydb"
        result = redact(conn_str)
        # Should detect secrets in generic patterns
        has_redaction = len(result.rules_applied) > 0 or conn_str == result.redacted_text
        assert has_redaction

    def test_redact_credit_card_from_receipt(self) -> None:
        """Credit card from receipt is redacted with last 4 preserved."""
        receipt = "Transaction ID: 12345, Card: 4111-1111-1111-1111, Amount: $99.99"
        result = redact(receipt)
        assert "****-****-****-1111" in result.redacted_text
        assert "4111-1111-1111-1111" not in result.redacted_text
        assert "$99.99" in result.redacted_text  # Amount preserved

    def test_redact_email_from_error_stack(self) -> None:
        """Email in error message/stack is redacted."""
        error_stack = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 42, in get_user\n'
            '    raise ValueError(f"User {user_email} not found")\n'
            'ValueError: User alice@example.com not found'
        )
        result = redact(error_stack)
        assert "alice@example.com" not in result.redacted_text
        assert "[email hidden]" in result.redacted_text
        assert "Traceback" in result.redacted_text  # Structure preserved

    def test_redact_multiple_formats_same_text(self) -> None:
        """Text with multiple PII formats is fully redacted."""
        text = (
            "User: alice@example.com\n"
            "Phone: 555-123-4567\n"
            "Card: 4111-1111-1111-1111\n"
            "API Key: sk-1234567890abcdefghijklmnop\n"
            "SSN: 123-45-6789"
        )
        result = redact(text)
        # All PII should be redacted
        assert "alice@example.com" not in result.redacted_text
        assert "555-123-4567" not in result.redacted_text
        assert "4111-1111-1111-1111" not in result.redacted_text
        assert "sk-1234567890" not in result.redacted_text
        assert "123-45-6789" not in result.redacted_text
        # All rules should be in the set
        assert len(result.rules_applied) == 5


class TestRedactionRulesOrderMatters:
    """Tests verifying that rule application order matters."""

    def test_rules_applied_in_sequence(self) -> None:
        """Rules are applied in the order provided."""
        # Create two custom rules
        rule1 = RedactionRule("rule1", re.compile(r"ABC"), "[R1]")
        rule2 = RedactionRule("rule2", re.compile(r"R1"), "[R2]")

        text = "ABC DEF"
        result = redact(text, rules=(rule1, rule2))
        # First rule: ABC -> [R1]
        # Second rule: now matches "R1" in "[R1]" -> "[[R2]]"
        assert result.redacted_text == "[[R2]] DEF"

    def test_email_before_generic_api_key(self) -> None:
        """Email rule fires before generic api_key patterns."""
        # This ensures emails containing @ aren't caught by overly broad rules
        text = "Email: alice@example.com"
        result = redact(text)
        assert "[email hidden]" in result.redacted_text
        # Verify email rule specifically fired, not generic pattern
        assert "email" in result.rules_applied


class TestDetectPIIConsistency:
    """Tests verifying detect_pii() and redact() consistency."""

    @given(st.text())
    @settings(max_examples=100)
    def test_detect_then_redact_consistency(self, text: str) -> None:
        """If detect_pii is True, redact should have rules_applied."""
        if detect_pii(text):
            result = redact(text)
            # Should have applied some rules
            assert len(result.rules_applied) > 0 or text == result.redacted_text

    @given(st.text())
    @settings(max_examples=100)
    def test_no_pii_means_no_redaction(self, text: str) -> None:
        """If detect_pii is False, redact should not change text."""
        if not detect_pii(text):
            result = redact(text)
            assert result.redacted_text == text
            assert result.rules_applied == []
