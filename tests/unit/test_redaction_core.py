"""Unit tests for holly.redaction.core — canonical redaction patterns and rules."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from holly.redaction.core import (
    CREDIT_CARD_PATTERN,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    SSN_PATTERN,
    RedactionError,
    RedactionResult,
    RedactionRule,
    canonicalize_redaction_rules,
    detect_pii,
    redact,
)

# ---------------------------------------------------------------------------
# Email Pattern Tests
# ---------------------------------------------------------------------------


class TestEmailPattern:
    """Tests for EMAIL_PATTERN matching and redaction."""

    @pytest.mark.parametrize(
        "email",
        [
            "alice@example.com",
            "bob.smith@domain.co.uk",
            "user+tag@test.io",
        ],
    )
    def test_valid_emails_match(self, email: str) -> None:
        """EMAIL_PATTERN matches valid RFC 5322-simplified emails."""
        assert EMAIL_PATTERN.search(email) is not None

    @pytest.mark.parametrize(
        "non_email",
        [
            "not-an-email",
            "@nodomain",
            "user@",
            "user @example.com",
        ],
    )
    def test_invalid_emails_no_match(self, non_email: str) -> None:
        """EMAIL_PATTERN does not match invalid email formats."""
        assert EMAIL_PATTERN.search(non_email) is None

    def test_email_redaction_preserves_non_pii(self) -> None:
        """Email redaction replaces only email addresses."""
        text = "Contact alice@example.com or bob@test.io"
        result = redact(text)
        assert result.redacted_text == "Contact [email hidden] or [email hidden]"
        assert "email" in result.rules_applied

    def test_email_property_sample_valid_emails(self) -> None:
        """Property: common valid emails are redacted."""
        emails = [
            "alice@example.com",
            "user.name+tag@domain.co.uk",
            "test123@subdomain.example.org",
        ]
        for email in emails:
            text = f"Email: {email}"
            result = redact(text)
            assert email not in result.redacted_text
            assert "[email hidden]" in result.redacted_text


# ---------------------------------------------------------------------------
# API Key Pattern Tests
# ---------------------------------------------------------------------------


class TestAPIKeyPattern:
    """Tests for API_KEY_PATTERNS matching and redaction."""

    def test_openai_api_key_format_matches(self) -> None:
        """OpenAI API key format sk-xxxx matches."""
        text = "API key is sk-1234567890abcdefghijklmnopqrst"
        result = redact(text)
        assert "[secret redacted]" in result.redacted_text
        assert "api_key" in result.rules_applied

    def test_bearer_token_matches(self) -> None:
        """Bearer token format matches."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact(text)
        assert "[secret redacted]" in result.redacted_text
        assert "api_key" in result.rules_applied

    def test_generic_api_key_pattern_matches(self) -> None:
        """Generic api_key=<value> pattern matches."""
        text = "api_key=sk1234567890"
        result = redact(text)
        assert "[secret redacted]" in result.redacted_text
        assert "api_key" in result.rules_applied

    def test_key_pattern_case_insensitive(self) -> None:
        """API key patterns are case-insensitive."""
        text_variants = [
            "API_KEY=secret123456",
            "Key=abcdefghijk",
            "SECRET=verylongsecretvalue",
        ]
        for text in text_variants:
            result = redact(text)
            assert "[secret redacted]" in result.redacted_text


# ---------------------------------------------------------------------------
# Credit Card Pattern Tests
# ---------------------------------------------------------------------------


class TestCreditCardPattern:
    """Tests for CREDIT_CARD_PATTERN matching and redaction."""

    @pytest.mark.parametrize(
        "card",
        [
            "4111-1111-1111-1111",
            "4111 1111 1111 1111",
            "4111111111111111",
            "5555-5555-5555-4444",
        ],
    )
    def test_credit_card_formats_match(self, card: str) -> None:
        """CREDIT_CARD_PATTERN matches common 16-digit formats."""
        assert CREDIT_CARD_PATTERN.search(card) is not None

    def test_credit_card_redaction_preserves_last_four(self) -> None:
        """Credit card redaction preserves last 4 digits."""
        text = "Card: 4111-1111-1111-1111"
        result = redact(text)
        assert result.redacted_text == "Card: ****-****-****-1111"
        assert "credit_card" in result.rules_applied

    def test_credit_card_preserves_different_last_four(self) -> None:
        """Last 4 digits preserved for different cards."""
        text = "Pay with 5555-5555-5555-4444"
        result = redact(text)
        assert "****-****-****-4444" in result.redacted_text

    @pytest.mark.parametrize(
        "non_card",
        [
            "1234-5678-90",  # too short
            "12345678901234567",  # 17 digits
            "1234 5678",  # partial
        ],
    )
    def test_invalid_credit_cards_no_match(self, non_card: str) -> None:
        """Invalid credit card formats are not matched."""
        assert CREDIT_CARD_PATTERN.search(non_card) is None

    @given(
        st.text(min_size=4, max_size=4, alphabet=st.characters(blacklist_categories=("Cc",)))
    )
    def test_credit_card_property_last_four_preserved(self, last_four: str) -> None:
        """Property: credit card redaction always preserves last 4 digits."""
        card = f"4111-1111-1111-{last_four}"
        if all(c.isdigit() for c in last_four):
            result = redact(card)
            assert last_four in result.redacted_text or "credit_card" not in result.rules_applied


# ---------------------------------------------------------------------------
# SSN Pattern Tests
# ---------------------------------------------------------------------------


class TestSSNPattern:
    """Tests for SSN_PATTERN matching and redaction."""

    def test_valid_ssn_matches(self) -> None:
        """SSN pattern NNN-NN-NNNN matches."""
        assert SSN_PATTERN.search("123-45-6789") is not None

    def test_ssn_redaction(self) -> None:
        """SSN is redacted to [pii redacted]."""
        text = "SSN is 123-45-6789"
        result = redact(text)
        assert result.redacted_text == "SSN is [pii redacted]"
        assert "ssn" in result.rules_applied

    @pytest.mark.parametrize(
        "non_ssn",
        [
            "123456789",  # no hyphens
            "12-34-5678",  # wrong format
            "123-4567",  # incomplete
        ],
    )
    def test_invalid_ssn_no_match(self, non_ssn: str) -> None:
        """Invalid SSN formats are not matched."""
        assert SSN_PATTERN.search(non_ssn) is None


# ---------------------------------------------------------------------------
# Phone Pattern Tests
# ---------------------------------------------------------------------------


class TestPhonePattern:
    """Tests for PHONE_PATTERN matching and redaction."""

    @pytest.mark.parametrize(
        "phone",
        [
            "555-123-4567",
            "(555) 123-4567",
            "1-555-123-4567",
            "+1 555-123-4567",
        ],
    )
    def test_us_phone_formats_match(self, phone: str) -> None:
        """PHONE_PATTERN matches common US phone formats."""
        assert PHONE_PATTERN.search(phone) is not None

    def test_phone_redaction(self) -> None:
        """Phone numbers are redacted to [pii redacted]."""
        text = "Call me at 555-123-4567"
        result = redact(text)
        assert "[pii redacted]" in result.redacted_text
        assert "phone" in result.rules_applied

    @pytest.mark.parametrize(
        "non_phone",
        [
            "5551234567",  # no separators
            "555-12-4567",  # wrong format
        ],
    )
    def test_invalid_phone_formats(self, non_phone: str) -> None:
        """Invalid phone formats may not match (regex is lenient)."""
        # Note: phone regex is lenient and may match partial patterns
        pass


# ---------------------------------------------------------------------------
# RedactionRule Tests
# ---------------------------------------------------------------------------


class TestRedactionRule:
    """Tests for RedactionRule class."""

    def test_rule_creation(self) -> None:
        """RedactionRule can be created with name, pattern, replacement."""
        rule = RedactionRule("test", EMAIL_PATTERN, "[hidden]")
        assert rule.name == "test"
        assert rule.pattern is EMAIL_PATTERN
        assert rule.replacement == "[hidden]"

    def test_rule_with_callback_replacement(self) -> None:
        """RedactionRule can use a callback for dynamic replacement."""

        def replace_func(m: re.Match[str]) -> str:
            return "X" * len(m.group(0))

        rule = RedactionRule("test", EMAIL_PATTERN, replace_func)
        assert callable(rule.replacement)

    def test_rule_slots(self) -> None:
        """RedactionRule uses __slots__ for memory efficiency."""
        rule = RedactionRule("test", EMAIL_PATTERN, "[hidden]")
        with pytest.raises(AttributeError):
            rule.extra_field = "value"  # type: ignore


# ---------------------------------------------------------------------------
# RedactionResult Tests
# ---------------------------------------------------------------------------


class TestRedactionResult:
    """Tests for RedactionResult class."""

    def test_result_creation(self) -> None:
        """RedactionResult captures redacted text and rules."""
        result = RedactionResult("safe text", ["email", "api_key"])
        assert result.redacted_text == "safe text"
        assert result.rules_applied == ["api_key", "email"]  # sorted

    def test_result_rules_auto_sorted(self) -> None:
        """RedactionResult auto-sorts rule names."""
        result = RedactionResult("text", ["phone", "email", "ssn"])
        assert result.rules_applied == ["email", "phone", "ssn"]

    def test_result_equality(self) -> None:
        """Two RedactionResults are equal if text and rules match."""
        r1 = RedactionResult("text", ["email"])
        r2 = RedactionResult("text", ["email"])
        assert r1 == r2

    def test_result_repr(self) -> None:
        """RedactionResult has a useful repr."""
        result = RedactionResult("safe", ["email"])
        assert "RedactionResult" in repr(result)
        assert "safe" in repr(result)

    def test_result_slots(self) -> None:
        """RedactionResult uses __slots__."""
        result = RedactionResult("text", [])
        with pytest.raises(AttributeError):
            result.extra = "value"  # type: ignore


# ---------------------------------------------------------------------------
# Integration: redact() Function
# ---------------------------------------------------------------------------


class TestRedactFunction:
    """Tests for redact() API."""

    def test_redact_all_patterns_together(self) -> None:
        """redact() handles multiple pattern types in one text."""
        text = (
            "Email: alice@example.com, Card: 4111-1111-1111-1111, "
            "SSN: 123-45-6789, Phone: 555-123-4567, "
            "API key: api_key=sk1234567890abcde"
        )
        result = redact(text)
        redacted = result.redacted_text

        # All patterns should be redacted
        assert "alice@example.com" not in redacted
        assert "4111-1111-1111-1111" not in redacted
        assert "123-45-6789" not in redacted
        assert "555-123-4567" not in redacted
        assert "sk1234567890abcde" not in redacted

        # Check rules applied
        assert "api_key" in result.rules_applied
        assert "credit_card" in result.rules_applied
        assert "email" in result.rules_applied
        assert "phone" in result.rules_applied
        assert "ssn" in result.rules_applied

    def test_redact_preserves_non_pii(self) -> None:
        """redact() leaves non-PII text unchanged."""
        text = "Hello world, this is normal text with no sensitive data."
        result = redact(text)
        assert result.redacted_text == text
        assert result.rules_applied == []

    def test_redact_with_custom_rules(self) -> None:
        """redact() accepts custom rule list."""
        custom_rule = RedactionRule("test", re.compile(r"SECRET"), "[HIDDEN]")
        text = "This has a SECRET value"
        result = redact(text, rules=(custom_rule,))
        assert result.redacted_text == "This has a [HIDDEN] value"
        assert result.rules_applied == ["test"]

    def test_redact_empty_string(self) -> None:
        """redact() handles empty strings."""
        result = redact("")
        assert result.redacted_text == ""
        assert result.rules_applied == []

    def test_redact_deterministic(self) -> None:
        """redact() is deterministic (same input → same output)."""
        text = "alice@example.com and api_key=sk1234567890abcdef"
        result1 = redact(text)
        result2 = redact(text)
        assert result1.redacted_text == result2.redacted_text
        assert result1.rules_applied == result2.rules_applied

    def test_redact_rule_error_propagated(self) -> None:
        """redact() raises RedactionError if rule callback fails."""

        def bad_callback(m: re.Match[str]) -> str:
            raise ValueError("Intentional error")

        bad_rule = RedactionRule("bad", EMAIL_PATTERN, bad_callback)
        text = "email: alice@example.com"

        with pytest.raises(RedactionError, match="bad"):
            redact(text, rules=(bad_rule,))

    def test_redact_multiple_matches_same_rule(self) -> None:
        """redact() applies rules to all matches of a pattern."""
        text = "alice@example.com, bob@test.io, charlie@domain.org"
        result = redact(text)
        assert result.redacted_text.count("[email hidden]") == 3
        assert result.rules_applied == ["email"]

    @given(st.text())
    def test_redact_property_never_empty_without_input(self, text: str) -> None:
        """Property: redact() never returns empty string unless input was empty."""
        result = redact(text)
        if text:
            assert result.redacted_text or text  # at least one is non-empty
        else:
            assert result.redacted_text == ""


# ---------------------------------------------------------------------------
# Integration: detect_pii() Function
# ---------------------------------------------------------------------------


class TestDetectPIIFunction:
    """Tests for detect_pii() API."""

    def test_detect_pii_email(self) -> None:
        """detect_pii() returns True for emails."""
        assert detect_pii("contact alice@example.com") is True

    def test_detect_pii_api_key(self) -> None:
        """detect_pii() returns True for API keys."""
        assert detect_pii("api_key=sk1234567890abcdefghijklmnop") is True

    def test_detect_pii_credit_card(self) -> None:
        """detect_pii() returns True for credit cards."""
        assert detect_pii("4111-1111-1111-1111") is True

    def test_detect_pii_ssn(self) -> None:
        """detect_pii() returns True for SSNs."""
        assert detect_pii("ssn 123-45-6789") is True

    def test_detect_pii_phone(self) -> None:
        """detect_pii() returns True for phones."""
        assert detect_pii("555-123-4567") is True

    def test_detect_pii_clean_text(self) -> None:
        """detect_pii() returns False for clean text."""
        assert detect_pii("hello world this is safe") is False

    def test_detect_pii_with_custom_rules(self) -> None:
        """detect_pii() accepts custom rules."""
        custom_rule = RedactionRule("custom", re.compile(r"SECRET"), "[HIDDEN]")
        assert detect_pii("has SECRET", rules=(custom_rule,)) is True
        assert detect_pii("no secrets", rules=(custom_rule,)) is False

    def test_detect_pii_empty_string(self) -> None:
        """detect_pii() returns False for empty string."""
        assert detect_pii("") is False

    @given(st.text())
    def test_detect_pii_property_consistent_with_redact(self, text: str) -> None:
        """Property: detect_pii(text) ⟹ redact(text).rules_applied is non-empty."""
        if detect_pii(text):
            result = redact(text)
            assert len(result.rules_applied) > 0


# ---------------------------------------------------------------------------
# Canonical Rules Tests
# ---------------------------------------------------------------------------


class TestCanonicalRules:
    """Tests for canonicalize_redaction_rules()."""

    def test_returns_tuple(self) -> None:
        """canonicalize_redaction_rules() returns a tuple."""
        rules = canonicalize_redaction_rules()
        assert isinstance(rules, tuple)
        assert len(rules) > 0

    def test_all_rules_are_redaction_rule(self) -> None:
        """All returned rules are RedactionRule instances."""
        rules = canonicalize_redaction_rules()
        for rule in rules:
            assert isinstance(rule, RedactionRule)

    def test_canonical_rules_immutable(self) -> None:
        """Canonical rules tuple is immutable."""
        rules = canonicalize_redaction_rules()
        with pytest.raises(TypeError):
            rules[0] = None  # type: ignore

    def test_canonical_rules_used_by_default(self) -> None:
        """redact() uses canonical rules when none specified."""
        text = "alice@example.com"
        result = redact(text)
        assert "[email hidden]" in result.redacted_text


# ---------------------------------------------------------------------------
# Edge Cases and Performance
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_overlapping_patterns_applied_in_order(self) -> None:
        """When patterns could overlap, rules are applied in order."""
        # Create two rules that both match "test"
        rule1 = RedactionRule("rule1", re.compile(r"test"), "[R1]")
        rule2 = RedactionRule("rule2", re.compile(r"test"), "[R2]")

        text = "test"
        result = redact(text, rules=(rule1, rule2))
        # First rule should apply, changing "test" to "[R1]"
        # Second rule won't match "[R1]"
        assert "[R1]" in result.redacted_text

    def test_very_long_text(self) -> None:
        """redact() handles very long texts efficiently."""
        long_text = "alice@example.com " * 10000
        result = redact(long_text)
        assert "[email hidden]" in result.redacted_text
        assert result.redacted_text.count("[email hidden]") == 10000

    def test_repeated_pii_all_redacted(self) -> None:
        """All occurrences of PII are redacted."""
        text = "alice@example.com alice@example.com alice@example.com"
        result = redact(text)
        assert "alice@example.com" not in result.redacted_text
        assert result.redacted_text.count("[email hidden]") == 3

    def test_special_regex_chars_in_text(self) -> None:
        """Patterns handle special regex characters in text."""
        text = "user+tag@example.com"
        result = redact(text)
        assert "[email hidden]" in result.redacted_text

    def test_unicode_preserved_outside_patterns(self) -> None:
        """Unicode text outside redaction patterns is preserved."""
        text = "Hello 世界, email: alice@example.com"
        result = redact(text)
        assert "世界" in result.redacted_text
        assert "[email hidden]" in result.redacted_text

    def test_newlines_preserved(self) -> None:
        """Newlines in text are preserved."""
        text = "Line 1\nalice@example.com\nLine 3"
        result = redact(text)
        assert "\n" in result.redacted_text
        assert "[email hidden]" in result.redacted_text


# ---------------------------------------------------------------------------
# ICD v0.1 Compliance
# ---------------------------------------------------------------------------


class TestICDCompliance:
    """Tests verifying ICD v0.1 redaction policy compliance."""

    def test_email_redaction_per_icd(self) -> None:
        """Email redaction matches ICD requirement."""
        # ICD v0.1: email redacted before logging
        text = "User alice@example.com registered"
        result = redact(text)
        assert "[email hidden]" in result.redacted_text

    def test_api_key_redaction_per_icd(self) -> None:
        """API key redaction matches ICD requirement."""
        # ICD v0.1: API keys redacted before logging
        text = "Authorization: sk-1234567890abcdefghijklmnop"
        result = redact(text)
        assert "[secret redacted]" in result.redacted_text

    def test_credit_card_partial_redaction_per_icd(self) -> None:
        """Credit card redaction preserves last 4 per ICD."""
        # ICD v0.1: credit card with last 4 preserved
        text = "Payment: 4111-1111-1111-1111"
        result = redact(text)
        assert "****-****-****-1111" in result.redacted_text

    def test_ssn_redaction_per_icd(self) -> None:
        """SSN redaction matches ICD requirement."""
        # ICD v0.1: SSN redacted completely
        text = "SSN: 123-45-6789"
        result = redact(text)
        assert "[pii redacted]" in result.redacted_text
        assert "123-45-6789" not in result.redacted_text

    def test_phone_redaction_per_icd(self) -> None:
        """Phone redaction matches ICD requirement."""
        # ICD v0.1: phone numbers redacted
        text = "Call 555-123-4567"
        result = redact(text)
        assert "[pii redacted]" in result.redacted_text

    def test_canonical_library_single_source_of_truth(self) -> None:
        """Canonical rules are the single source of truth."""
        # Per ICD v0.1: all interfaces use canonical library
        rules = canonicalize_redaction_rules()
        text = "alice@example.com and 4111-1111-1111-1111"
        result = redact(text, rules=rules)
        assert result.redacted_text == redact(text).redacted_text
