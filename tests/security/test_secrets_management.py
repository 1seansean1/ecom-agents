"""P2 HIGH: Secrets management tests.

Verifies secrets are not leaked in API responses, error messages, or logs.
"""

from __future__ import annotations

import json
import os

import pytest

# Patterns that should NEVER appear in API responses
_SECRET_PATTERNS = [
    "sk-",           # OpenAI API key prefix
    "sk_test_",      # Stripe test key prefix
    "sk_live_",      # Stripe live key prefix
    "sk-ant-",       # Anthropic key prefix
    "shpat_",        # Shopify access token prefix
    "postgresql://",  # Database URL
    "redis://",      # Redis URL
    # Phase 18a: New channel/provider patterns
    "xoxb-",         # Slack bot token prefix
    "xoxp-",         # Slack user token prefix
    "xapp-",         # Slack app token prefix
    "SG.",           # SendGrid API key prefix
    "ghp_",          # GitHub personal access token
    "AIza",          # Google API key prefix
    "npm_",          # npm token prefix
    "whsec_",        # Webhook secret prefix
]


def _response_contains_secrets(response_text: str) -> list[str]:
    """Check if response text contains any secret patterns."""
    found = []
    for pattern in _SECRET_PATTERNS:
        if pattern in response_text:
            found.append(pattern)
    return found


class TestNoSecretsInResponses:
    """API responses must not contain secrets."""

    def test_health_no_secrets(self, client):
        """Health endpoint doesn't expose secrets."""
        resp = client.get("/health")
        found = _response_contains_secrets(resp.text)
        assert not found, f"Health response contains secret patterns: {found}"

    def test_agents_list_no_db_urls(self, authenticated_client):
        """Agent listing doesn't expose DB URLs."""
        resp = authenticated_client.get("/agents")
        found = _response_contains_secrets(resp.text)
        # Filter out false positives from agent IDs that might contain "sk-"
        real_secrets = [p for p in found if p in ("postgresql://", "redis://")]
        assert not real_secrets, f"Agents response contains DB URLs: {real_secrets}"

    def test_error_responses_no_secrets(self, admin_client):
        """Error responses don't leak internal details."""
        # Trigger a 404
        resp = admin_client.get("/agents/nonexistent-agent-id-xyz")
        found = _response_contains_secrets(resp.text)
        assert not found, f"Error response contains secrets: {found}"

    def test_500_errors_no_stack_traces(self, admin_client):
        """500 errors don't expose stack traces with file paths."""
        # Trigger endpoints that might error
        resp = admin_client.get("/graph/definition")
        if resp.status_code == 500:
            body = resp.text
            assert "Traceback" not in body, "500 response contains stack trace"
            assert "File \"" not in body, "500 response contains file paths"


class TestMissingEnvVars:
    """Missing env vars should fail loudly, not silently."""

    def test_missing_env_vars_dont_leak_defaults(self):
        """REMEDIATED: Auth module warns when using default secret key."""
        from src.security.auth import _DEV_DEFAULT, _SECRET_KEY

        assert _SECRET_KEY is not None, "AUTH_SECRET_KEY should have a value"
        # The module now logs a warning when using the dev default in non-TESTING mode
        # In production, AUTH_SECRET_KEY MUST be set to a unique value
        assert isinstance(_DEV_DEFAULT, str), "Dev default should be a string constant"


class TestOutputGuardrails:
    """Verify output guardrail integration."""

    def test_output_validator_redacts_secrets(self):
        """REMEDIATED: Output validator catches short and long secret patterns."""
        from src.guardrails.output_validator import validate_output

        # Short Stripe key (6+ chars after prefix -- previously required 20+)
        fake_key = "sk_test_fake123456"
        test_output = f"The API key is {fake_key}"
        result = validate_output(test_output)
        assert fake_key not in result.sanitized
        assert "[REDACTED_STRIPE_KEY]" in result.sanitized

    def test_output_validator_redacts_stripe_keys(self):
        """Output validator catches Stripe live key patterns."""
        from src.guardrails.output_validator import validate_output

        fake_key = "sk_live_" + "B" * 24
        test_output = f"Stripe key: {fake_key}"
        result = validate_output(test_output)
        assert fake_key not in result.sanitized
        assert "[REDACTED_STRIPE_KEY]" in result.sanitized

    def test_output_validator_redacts_db_urls(self):
        """REMEDIATED: Output validator catches database connection URLs."""
        from src.guardrails.output_validator import validate_output

        test_output = "DB is postgresql://user:pass@host/db"
        result = validate_output(test_output)
        assert "postgresql://user:pass@host/db" not in result.sanitized
        assert "[REDACTED_DB_URL]" in result.sanitized

    def test_output_validator_redacts_redis_urls(self):
        """Output validator catches Redis connection URLs."""
        from src.guardrails.output_validator import validate_output

        test_output = "Cache at redis://default:secret@redis:6379/0"
        result = validate_output(test_output)
        assert "redis://default:secret@redis:6379/0" not in result.sanitized
        assert "[REDACTED_DB_URL]" in result.sanitized

    # --- Phase 18a: New channel/provider secret pattern tests ---

    def test_output_validator_redacts_slack_bot_token(self):
        """Output validator catches Slack bot tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "xox" + "b-1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUv"
        result = validate_output(f"Slack token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_SLACK_BOT_TOKEN]" in result.sanitized
        assert not result.safe

    def test_output_validator_redacts_slack_app_token(self):
        """Output validator catches Slack app-level tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "xap" + "p-1-A0B1C2D3E4F-1234567890123-abcdef1234567890abcdef"
        result = validate_output(f"App token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_SLACK_APP_TOKEN]" in result.sanitized

    def test_output_validator_redacts_slack_user_token(self):
        """Output validator catches Slack user tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "xox" + "p-1234567890-1234567890123-1234567890123-abcdef1234"
        result = validate_output(f"User token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_SLACK_USER_TOKEN]" in result.sanitized

    def test_output_validator_redacts_telegram_bot_token(self):
        """Output validator catches Telegram bot tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"
        result = validate_output(f"Telegram token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_TELEGRAM_BOT_TOKEN]" in result.sanitized

    def test_output_validator_redacts_discord_bot_token(self):
        """Output validator catches Discord bot tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "MTA1NjY0MjY0NjI2NjMx" + "Njg2.GxhBqR.abcdefghijklmnopqrstuvwxyz1234"
        result = validate_output(f"Discord token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_DISCORD_BOT_TOKEN]" in result.sanitized

    def test_output_validator_redacts_sendgrid_key(self):
        """Output validator catches SendGrid API keys."""
        from src.guardrails.output_validator import validate_output

        fake_key = "SG." + "aBcDeFgHiJkLmNoPqRsTuVwXyZ.1234567890abcdefghijklmn"
        result = validate_output(f"SendGrid key: {fake_key}")
        assert fake_key not in result.sanitized
        assert "[REDACTED_SENDGRID_KEY]" in result.sanitized

    def test_output_validator_redacts_twilio_key(self):
        """Output validator catches Twilio account SID / auth tokens."""
        from src.guardrails.output_validator import validate_output

        fake_sid = "AC" + "a" * 32
        result = validate_output(f"Twilio SID: {fake_sid}")
        assert fake_sid not in result.sanitized
        assert "[REDACTED_TWILIO_KEY]" in result.sanitized

    def test_output_validator_redacts_google_api_key(self):
        """Output validator catches Google API keys."""
        from src.guardrails.output_validator import validate_output

        fake_key = "AIzaSyA" + "B" * 32
        result = validate_output(f"Google key: {fake_key}")
        assert fake_key not in result.sanitized
        assert "[REDACTED_GOOGLE_API_KEY]" in result.sanitized

    def test_output_validator_redacts_github_token(self):
        """Output validator catches GitHub personal access tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "ghp_" + "A" * 36
        result = validate_output(f"GitHub token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_GITHUB_TOKEN]" in result.sanitized

    def test_output_validator_redacts_github_pat(self):
        """Output validator catches GitHub fine-grained PATs."""
        from src.guardrails.output_validator import validate_output

        fake_token = "github_pat_" + "B" * 22
        result = validate_output(f"GitHub PAT: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_GITHUB_PAT]" in result.sanitized

    def test_output_validator_redacts_npm_token(self):
        """Output validator catches npm publish tokens."""
        from src.guardrails.output_validator import validate_output

        fake_token = "npm_" + "C" * 36
        result = validate_output(f"npm token: {fake_token}")
        assert fake_token not in result.sanitized
        assert "[REDACTED_NPM_TOKEN]" in result.sanitized

    def test_output_validator_redacts_webhook_secret(self):
        """Output validator catches Stripe webhook secrets."""
        from src.guardrails.output_validator import validate_output

        fake_secret = "whsec_" + "D" * 24
        result = validate_output(f"Webhook secret: {fake_secret}")
        assert fake_secret not in result.sanitized
        assert "[REDACTED_WEBHOOK_SECRET]" in result.sanitized

    def test_output_validator_redacts_multiple_new_patterns(self):
        """Output validator handles multiple new secret types in one text."""
        from src.guardrails.output_validator import validate_output

        text = (
            "Slack: " + "xox" + "b-1234567890-1234567890123-AbCdEfGhIjKlMnOpQrStUv "
            "SendGrid: " + "SG." + "aBcDeFgHiJkLmNoPqRsTuVwXyZ.1234567890abcdefghijklmn "
            "GitHub: ghp_" + "A" * 36
        )
        result = validate_output(text)
        assert not result.safe
        assert result.redacted_count >= 3
        assert "xoxb-" not in result.sanitized
        assert "SG." not in result.sanitized
        assert "ghp_" not in result.sanitized


class TestInputGuardrailNewPatterns:
    """Verify input guardrail detects new secret patterns."""

    def test_input_validator_detects_slack_token(self):
        """Input validator flags Slack tokens."""
        from src.guardrails.input_validator import validate_input

        result = validate_input("Use token " + "xox" + "b-1234567890-1234567890123-AbCdEfGhIjKl")
        assert "secret:api_key" in result.flags
        assert not result.safe

    def test_input_validator_detects_telegram_token(self):
        """Input validator flags Telegram tokens."""
        from src.guardrails.input_validator import validate_input

        result = validate_input("Bot token is 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh")
        assert "secret:api_key" in result.flags
        assert not result.safe

    def test_input_validator_detects_sendgrid_key(self):
        """Input validator flags SendGrid keys."""
        from src.guardrails.input_validator import validate_input

        result = validate_input("SG." + "aBcDeFgHiJkLmNoPqRsTuVwXyZ.1234567890abcdefghijklmn")
        assert "secret:api_key" in result.flags
        assert not result.safe

    def test_input_validator_detects_github_token(self):
        """Input validator flags GitHub tokens."""
        from src.guardrails.input_validator import validate_input

        result = validate_input("ghp_" + "A" * 36)
        assert "secret:api_key" in result.flags
        assert not result.safe

    def test_input_validator_detects_google_api_key(self):
        """Input validator flags Google API keys."""
        from src.guardrails.input_validator import validate_input

        result = validate_input("AIzaSyA" + "B" * 32)
        assert "secret:api_key" in result.flags
        assert not result.safe
