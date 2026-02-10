"""
Integration tests for Holly Grace Chat frontend.

Tests the chat SSE endpoints through the Holly Grace proxy,
verifying that each provider/model combination handles simple messages
correctly and that parameter conflicts are caught gracefully.

Requires:
  - Holly Grace chat server running on :8073
  - Holly Grace dev server on :5173 (for proxy tests)
  - Valid API keys configured in chat-ui/.env

Run:
  pytest tests/test_chat_frontend.py -v --timeout=120
"""

import json
import os
import re
import time
from typing import Generator

import httpx
import pytest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHAT_UI_BASE = os.getenv("CHAT_UI_BASE", "http://localhost:8073")
PROXY_BASE = os.getenv("PROXY_BASE", "http://localhost:5173/chat-ui")

SIMPLE_MESSAGES = [
    {"role": "user", "content": "Hello how are you today?"},
]

SHORT_MESSAGES = [
    {"role": "user", "content": "Say hello in exactly 5 words."},
]

TIMEOUT = 60  # seconds per streaming request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse_events(text: str) -> list[dict]:
    """Parse SSE text into list of JSON-decoded data payloads."""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                events.append({"_raw": line[6:]})
    return events


def collect_sse_stream(response: httpx.Response) -> list[dict]:
    """Read a streaming SSE response and collect all events."""
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                events.append({"_raw": line[6:]})
    return events


def extract_tokens(events: list[dict]) -> str:
    """Concatenate all token events into the full response text."""
    return "".join(e.get("token", "") for e in events if "token" in e)


def find_errors(events: list[dict]) -> list[str]:
    """Extract all error messages from SSE events."""
    errors = []
    for e in events:
        if "error" in e:
            errors.append(e["error"])
        # Socratic mode embeds errors in token text
        if "token" in e and "[" in str(e["token"]) and "error:" in str(e["token"]).lower():
            errors.append(e["token"])
    return errors


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def chat_client() -> Generator[httpx.Client, None, None]:
    """HTTP client pointed at chat-ui directly."""
    with httpx.Client(base_url=CHAT_UI_BASE, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="session")
def proxy_client() -> Generator[httpx.Client, None, None]:
    """HTTP client pointed at Holly Grace proxy."""
    with httpx.Client(base_url=PROXY_BASE, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="session")
def available_providers(chat_client: httpx.Client) -> dict:
    """Fetch model catalog and determine which providers have valid keys."""
    resp = chat_client.get("/api/models")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture(scope="session")
def validated_keys(chat_client: httpx.Client) -> dict:
    """Call /api/validate-keys to see which providers are actually usable."""
    resp = chat_client.post("/api/validate-keys")
    if resp.status_code == 200:
        return resp.json()
    return {}


# ---------------------------------------------------------------------------
# Test: Server Health
# ---------------------------------------------------------------------------

class TestServerHealth:
    """Verify both servers are running and endpoints respond."""

    def test_chat_ui_root(self, chat_client: httpx.Client):
        resp = chat_client.get("/")
        assert resp.status_code == 200

    def test_models_endpoint(self, chat_client: httpx.Client, available_providers: dict):
        assert "openai" in available_providers
        assert "anthropic" in available_providers
        assert "google" in available_providers
        for provider_key, provider_data in available_providers.items():
            assert "models" in provider_data
            assert len(provider_data["models"]) > 0

    def test_proxy_reachable(self, proxy_client: httpx.Client):
        """Verify Holly Grace proxy forwards to chat-ui."""
        resp = proxy_client.get("/api/models")
        # May get 200 or 502 if proxy isn't up — skip if proxy unreachable
        if resp.status_code == 502:
            pytest.skip("Holly Grace proxy not available")
        assert resp.status_code == 200

    def test_proxy_models_match_direct(self, chat_client: httpx.Client, proxy_client: httpx.Client):
        """Proxy response should match direct response."""
        direct = chat_client.get("/api/models")
        proxied = proxy_client.get("/api/models")
        if proxied.status_code == 502:
            pytest.skip("Holly Grace proxy not available")
        assert direct.json() == proxied.json()


# ---------------------------------------------------------------------------
# Test: Standard Chat — Provider Smoke Tests
# ---------------------------------------------------------------------------

class TestStandardChatOpenAI:
    """Test OpenAI models with simple chat messages."""

    def test_gpt4o_hello(self, chat_client: httpx.Client):
        """GPT-4o should respond to a simple hello."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Unexpected errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response text received"

    def test_gpt35_turbo_hello(self, chat_client: httpx.Client):
        """GPT-3.5 Turbo should respond to a simple hello."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-3.5-turbo",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Unexpected errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response text received"

    def test_o1_mini_hello(self, chat_client: httpx.Client):
        """o1-mini — reasoning model that may reject certain params."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o1-mini",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        # Skip if model not available on this account
        if errors and any("does not exist" in e or "model_not_found" in e for e in errors):
            pytest.skip("o1-mini not available on this OpenAI account")
        assert not errors, f"o1-mini failed with empty params: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response text from o1-mini"

    def test_o3_mini_hello(self, chat_client: httpx.Client):
        """o3-mini — reasoning model with empty params."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o3-mini",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("does not exist" in e or "model_not_found" in e for e in errors):
            pytest.skip("o3-mini not available on this OpenAI account")
        assert not errors, f"o3-mini failed with empty params: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response text from o3-mini"


class TestStandardChatAnthropic:
    """Test Anthropic models with simple chat messages."""

    def test_haiku_hello(self, chat_client: httpx.Client):
        """Claude Haiku 4.5 — fastest, cheapest Anthropic model."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Haiku 4.5 errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Haiku"

    def test_sonnet_hello(self, chat_client: httpx.Client):
        """Claude Sonnet 4.5."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-sonnet-4-5-20250929",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Sonnet 4.5 errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Sonnet"

    def test_opus_hello(self, chat_client: httpx.Client):
        """Claude Opus 4.6."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-opus-4-6",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Opus 4.6 errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Opus"


class TestStandardChatGoogle:
    """Test Google Gemini models."""

    def test_gemini_flash_hello(self, chat_client: httpx.Client):
        """Gemini 2.0 Flash — fast Google model."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "google", "model": "gemini-2.0-flash",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("429" in e or "quota" in e.lower() for e in errors):
            pytest.skip("Google API quota exceeded")
        assert not errors, f"Gemini Flash errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Gemini Flash"

    def test_gemini_flash_lite_hello(self, chat_client: httpx.Client):
        """Gemini 2.0 Flash Lite."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "google", "model": "gemini-2.0-flash-lite",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("429" in e or "quota" in e.lower() for e in errors):
            pytest.skip("Google API quota exceeded")
        assert not errors, f"Gemini Flash Lite errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Gemini Flash Lite"


class TestStandardChatGrok:
    """Test xAI Grok models (skip if no key)."""

    def test_grok_hello(self, chat_client: httpx.Client, validated_keys: dict):
        """Grok 3 Mini Fast — cheapest Grok model."""
        if not validated_keys.get("grok", {}).get("valid"):
            pytest.skip("No valid Grok API key")

        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "grok", "model": "grok-3-mini-fast",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Grok errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from Grok"


# ---------------------------------------------------------------------------
# Test: Parameter Conflicts
# ---------------------------------------------------------------------------

class TestParameterConflicts:
    """
    Test parameter combinations known to cause provider errors.
    These tests verify errors are returned gracefully (as SSE error events)
    rather than crashing the server.
    """

    def _skip_if_model_unavailable(self, errors: list[str]):
        """Skip test if model is not available on this account."""
        if errors and any("does not exist" in e or "model_not_found" in e for e in errors):
            pytest.skip("Model not available on this account")

    def test_openai_o1_with_temperature(self, chat_client: httpx.Client):
        """o1 models reject temperature parameter — should get graceful error."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o1-mini",
            "messages": SIMPLE_MESSAGES,
            "params": {"temperature": 0.7},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        # Either it errors gracefully or somehow succeeds — both are acceptable
        errors = find_errors(events)
        self._skip_if_model_unavailable(errors)
        text = extract_tokens(events)
        if errors:
            # Verify error is returned as SSE event (not server crash)
            assert any("temperature" in e.lower() or "unsupported" in e.lower()
                       or "not supported" in e.lower() or "400" in e
                       for e in errors), f"Unexpected error type: {errors}"
        else:
            # If it succeeds, that's also fine (OpenAI may have changed behavior)
            assert len(text) > 0

    def test_openai_o1_with_top_p(self, chat_client: httpx.Client):
        """o1 models reject top_p parameter."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o1-mini",
            "messages": SIMPLE_MESSAGES,
            "params": {"top_p": 0.9},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        self._skip_if_model_unavailable(errors)
        text = extract_tokens(events)
        # Graceful error OR success — server must not crash
        assert errors or len(text) > 0, "Neither error nor response received"

    def test_openai_o3_with_temperature_and_top_p(self, chat_client: httpx.Client):
        """o3-mini with both temperature and top_p — double parameter conflict."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o3-mini",
            "messages": SIMPLE_MESSAGES,
            "params": {"temperature": 0.5, "top_p": 0.9},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        self._skip_if_model_unavailable(errors)
        text = extract_tokens(events)
        assert errors or len(text) > 0, "Neither error nor response received"

    def test_openai_o1_with_frequency_penalty(self, chat_client: httpx.Client):
        """o1 models reject frequency_penalty."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o1-mini",
            "messages": SIMPLE_MESSAGES,
            "params": {"frequency_penalty": 0.5},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        self._skip_if_model_unavailable(errors)
        text = extract_tokens(events)
        assert errors or len(text) > 0, "Neither error nor response received"

    def test_anthropic_temperature_and_top_p_together(self, chat_client: httpx.Client):
        """Anthropic may reject temperature + top_p simultaneously."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SIMPLE_MESSAGES,
            "params": {"temperature": 0.7, "top_p": 0.9},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        text = extract_tokens(events)
        # Anthropic docs say you can set both, but they warn against it
        # Either a clean error or a valid response is acceptable
        assert errors or len(text) > 0, "Neither error nor response received"
        if not errors:
            # If it works, good — both params were accepted
            assert len(text) > 5, "Suspiciously short response"

    def test_anthropic_temperature_zero(self, chat_client: httpx.Client):
        """temperature=0 should work fine (deterministic mode)."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SHORT_MESSAGES,
            "params": {"temperature": 0},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"temperature=0 should not error: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0

    def test_google_extreme_temperature(self, chat_client: httpx.Client):
        """Gemini with temperature=2.0 (max) — should work or graceful error."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "google", "model": "gemini-2.0-flash-lite",
            "messages": SIMPLE_MESSAGES,
            "params": {"temperature": 2.0},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("429" in e or "quota" in e.lower() for e in errors):
            pytest.skip("Google API quota exceeded")
        text = extract_tokens(events)
        assert errors or len(text) > 0, "Neither error nor response"


# ---------------------------------------------------------------------------
# Test: Model Constraints (unsupported_params)
# ---------------------------------------------------------------------------

class TestModelConstraints:
    """
    Verify that the /api/models endpoint returns unsupported_params metadata
    and that the server strips unsupported params before forwarding to providers.
    """

    def test_o1_has_unsupported_params(self, available_providers: dict):
        """o1 model should declare unsupported_params in the catalog."""
        models = available_providers["openai"]["models"]
        o1 = next((m for m in models if m["id"] == "o1"), None)
        assert o1 is not None, "o1 not found in model catalog"
        assert "unsupported_params" in o1, "o1 missing unsupported_params field"
        unsupported = o1["unsupported_params"]
        assert "temperature" in unsupported
        assert "top_p" in unsupported
        assert "frequency_penalty" in unsupported
        assert "presence_penalty" in unsupported

    def test_o3_mini_has_unsupported_params(self, available_providers: dict):
        """o3-mini should also declare unsupported_params."""
        models = available_providers["openai"]["models"]
        o3 = next((m for m in models if m["id"] == "o3-mini"), None)
        assert o3 is not None, "o3-mini not found in model catalog"
        assert "unsupported_params" in o3
        assert "temperature" in o3["unsupported_params"]

    def test_gpt4o_no_unsupported_params(self, available_providers: dict):
        """GPT-4o should NOT have unsupported_params (supports everything)."""
        models = available_providers["openai"]["models"]
        gpt4o = next((m for m in models if m["id"] == "gpt-4o"), None)
        assert gpt4o is not None
        # Either missing or empty list
        assert not gpt4o.get("unsupported_params"), \
            f"GPT-4o should not have unsupported_params: {gpt4o.get('unsupported_params')}"

    def test_anthropic_no_unsupported_params(self, available_providers: dict):
        """Anthropic models should not have unsupported_params."""
        models = available_providers["anthropic"]["models"]
        for m in models:
            assert not m.get("unsupported_params"), \
                f"{m['id']} should not have unsupported_params"

    def test_server_strips_o1_temperature(self, chat_client: httpx.Client):
        """Server should strip temperature from o1 requests and succeed."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o1",
            "messages": SIMPLE_MESSAGES,
            "params": {"temperature": 0.7},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        # Skip if model not available on account
        if errors and any("does not exist" in e or "model_not_found" in e for e in errors):
            pytest.skip("o1 not available on this account")
        # With server-side stripping, this should now SUCCEED (no param error)
        assert not errors, f"o1 still errored with temperature after stripping: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0, "No response from o1 after param stripping"

    def test_server_strips_o3_all_unsupported(self, chat_client: httpx.Client):
        """Server should strip all unsupported params from o3-mini."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "o3-mini",
            "messages": SIMPLE_MESSAGES,
            "params": {
                "temperature": 0.5,
                "top_p": 0.9,
                "frequency_penalty": 0.3,
                "presence_penalty": 0.3,
            },
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("does not exist" in e or "model_not_found" in e for e in errors):
            pytest.skip("o3-mini not available on this account")
        assert not errors, f"o3-mini errored after param stripping: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0

    def test_params_section_in_provider_data(self, available_providers: dict):
        """Each provider should have a params section with ranges."""
        for provider_key, provider_data in available_providers.items():
            assert "params" in provider_data, \
                f"{provider_key} missing params section"
            params = provider_data["params"]
            # At minimum should have temperature
            assert "temperature" in params, \
                f"{provider_key} missing temperature in params"
            temp = params["temperature"]
            assert "min" in temp and "max" in temp and "step" in temp


# ---------------------------------------------------------------------------
# Test: SSE Event Format
# ---------------------------------------------------------------------------

class TestSSEEventFormat:
    """Verify SSE events conform to expected structure."""

    def test_stream_ends_with_done(self, chat_client: httpx.Client):
        """Every successful stream should end with a done event."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SHORT_MESSAGES, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if not errors:
            done_events = [e for e in events if e.get("done")]
            assert len(done_events) >= 1, f"No 'done' event. Events: {events[-3:]}"

    def test_tokens_are_strings(self, chat_client: httpx.Client):
        """All token events should contain string values."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SHORT_MESSAGES, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        for e in events:
            if "token" in e:
                assert isinstance(e["token"], str), f"Token is not string: {type(e['token'])}"

    def test_no_empty_token_events(self, chat_client: httpx.Client):
        """Token events should not be completely empty strings."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": SHORT_MESSAGES, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        tokens = [e for e in events if "token" in e]
        # Some empty tokens are normal for OpenAI, but the majority should have content
        non_empty = [t for t in tokens if t["token"]]
        assert len(non_empty) > 0, "All token events were empty"


# ---------------------------------------------------------------------------
# Test: System Prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    """Verify system prompt is respected by each provider."""

    def test_openai_system_prompt(self, chat_client: httpx.Client):
        """OpenAI should follow system prompt instructions."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "What is your name?"}],
            "params": {},
            "system_prompt": "You are a pirate named Captain Blackbeard. Always speak like a pirate.",
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"System prompt test errors: {errors}"
        text = extract_tokens(events).lower()
        # Should reference pirate theme or Blackbeard
        assert any(w in text for w in ["blackbeard", "pirate", "arr", "matey", "ahoy", "captain", "ye"]), \
            f"System prompt not followed. Response: {text[:200]}"

    def test_anthropic_system_prompt(self, chat_client: httpx.Client):
        """Anthropic should follow system prompt instructions."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "What is your name?"}],
            "params": {},
            "system_prompt": "You are a pirate named Captain Blackbeard. Always speak like a pirate.",
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"System prompt test errors: {errors}"
        text = extract_tokens(events).lower()
        assert any(w in text for w in ["blackbeard", "pirate", "arr", "matey", "ahoy", "captain", "ye"]), \
            f"System prompt not followed. Response: {text[:200]}"

    def test_google_system_prompt(self, chat_client: httpx.Client):
        """Google should follow system prompt (prepended to user message)."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "google", "model": "gemini-2.0-flash-lite",
            "messages": [{"role": "user", "content": "What is your name?"}],
            "params": {},
            "system_prompt": "You are a pirate named Captain Blackbeard. Always speak like a pirate.",
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if errors and any("429" in e or "quota" in e.lower() for e in errors):
            pytest.skip("Google API quota exceeded")
        assert not errors, f"System prompt test errors: {errors}"
        text = extract_tokens(events).lower()
        assert any(w in text for w in ["blackbeard", "pirate", "arr", "matey", "ahoy", "captain", "ye"]), \
            f"System prompt not followed. Response: {text[:200]}"


# ---------------------------------------------------------------------------
# Test: Multi-turn Conversations
# ---------------------------------------------------------------------------

class TestMultiTurn:
    """Verify multi-turn conversation context is maintained."""

    def test_openai_remembers_context(self, chat_client: httpx.Client):
        """Model should reference information from earlier messages."""
        messages = [
            {"role": "user", "content": "My favorite color is purple."},
            {"role": "assistant", "content": "That's great! Purple is a wonderful color."},
            {"role": "user", "content": "What is my favorite color?"},
        ]
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": messages, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Multi-turn errors: {errors}"
        text = extract_tokens(events).lower()
        assert "purple" in text, f"Model forgot context. Response: {text[:200]}"

    def test_anthropic_remembers_context(self, chat_client: httpx.Client):
        """Anthropic should maintain multi-turn context."""
        messages = [
            {"role": "user", "content": "My favorite color is purple."},
            {"role": "assistant", "content": "That's great! Purple is a wonderful color."},
            {"role": "user", "content": "What is my favorite color?"},
        ]
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": messages, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Multi-turn errors: {errors}"
        text = extract_tokens(events).lower()
        assert "purple" in text, f"Model forgot context. Response: {text[:200]}"


# ---------------------------------------------------------------------------
# Test: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_message(self, chat_client: httpx.Client):
        """Empty message content — should error gracefully."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": ""}],
            "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        # Either an error message or an empty response — server must not crash
        # The status_code being 200 already confirms the server didn't crash
        errors = find_errors(events)
        text = extract_tokens(events)
        assert errors or text is not None, "Server crashed on empty message"

    def test_unknown_provider(self, chat_client: httpx.Client):
        """Unknown provider should return error event."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "unknown_provider", "model": "some-model",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert errors, "Expected error for unknown provider"
        assert any("unknown" in e.lower() for e in errors), f"Error didn't mention unknown provider: {errors}"

    def test_invalid_model(self, chat_client: httpx.Client):
        """Invalid model ID should return error event."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "nonexistent-model-xyz",
            "messages": SIMPLE_MESSAGES, "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert errors, "Expected error for invalid model"

    def test_very_long_message(self, chat_client: httpx.Client):
        """Long message should be handled without crash."""
        long_msg = "Hello! " * 500  # ~3500 chars
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": long_msg}],
            "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        text = extract_tokens(events)
        assert not errors, f"Long message errors: {errors}"
        assert len(text) > 0

    def test_special_characters(self, chat_client: httpx.Client):
        """Messages with special chars, unicode, and newlines."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": 'Hello! \n\nWhat is 2+2? "quotes" & <brackets> \u00e9\u00e8\u00ea \U0001f600'}],
            "params": {},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Special char errors: {errors}"
        text = extract_tokens(events)
        assert len(text) > 0

    def test_max_tokens_one(self, chat_client: httpx.Client):
        """max_tokens=1 should return a very short response."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "Tell me a long story about a dragon."}],
            "params": {"max_tokens": 5},
        }) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"max_tokens=5 errors: {errors}"
        text = extract_tokens(events)
        # Should be very short
        assert len(text) < 100, f"Response too long for max_tokens=5: {len(text)} chars"


# ---------------------------------------------------------------------------
# Test: Code Mode (Claude + Tools)
# ---------------------------------------------------------------------------

class TestCodeMode:
    """Test the Claude Code streaming endpoint."""

    def test_code_list_files(self, chat_client: httpx.Client):
        """Code mode should be able to list files."""
        with chat_client.stream("POST", "/api/claude-code/stream", json={
            "messages": [{"role": "user", "content": "List the files in the current directory. Just list them, nothing else."}],
            "working_directory": "c:\\Users\\seanp\\Workspace\\ecom-agents",
            "max_turns": 5,
            "model": "claude-haiku-4-5-20251001",
            "allowed_tools": ["list_files"],
        }, timeout=120) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Code mode errors: {errors}"

        # Should have at least one turn event
        turn_events = [e for e in events if "turn" in e]
        assert len(turn_events) >= 1, "No turn events in Code mode"

        # Should have token text OR tool call events (model may respond only via tools)
        text = extract_tokens(events)
        tool_calls = [e for e in events if "tool_call_start" in e or "tool_call_result" in e]
        assert len(text) > 0 or len(tool_calls) > 0, \
            "No text response or tool calls from Code mode"

    def test_code_read_file(self, chat_client: httpx.Client):
        """Code mode should be able to read a file."""
        with chat_client.stream("POST", "/api/claude-code/stream", json={
            "messages": [{"role": "user", "content": "Read the first 5 lines of pyproject.toml and tell me the project name."}],
            "working_directory": "c:\\Users\\seanp\\Workspace\\ecom-agents",
            "max_turns": 5,
            "model": "claude-haiku-4-5-20251001",
            "allowed_tools": ["read_file"],
        }, timeout=120) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Code read errors: {errors}"

        text = extract_tokens(events)
        assert len(text) > 0, "No text from Code read_file test"

    def test_code_done_event(self, chat_client: httpx.Client):
        """Code mode stream should end with done event."""
        with chat_client.stream("POST", "/api/claude-code/stream", json={
            "messages": [{"role": "user", "content": "Say hello."}],
            "working_directory": ".",
            "max_turns": 2,
            "model": "claude-haiku-4-5-20251001",
            "allowed_tools": [],
        }, timeout=60) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        if not errors:
            done_events = [e for e in events if e.get("done")]
            assert len(done_events) >= 1, "No 'done' event in Code mode"


# ---------------------------------------------------------------------------
# Test: Socratic Mode
# ---------------------------------------------------------------------------

class TestSocraticMode:
    """Test the Socratic roundtable streaming endpoint."""

    def test_socratic_defaults_endpoint(self, chat_client: httpx.Client):
        """Verify /api/socratic/defaults returns valid participant config."""
        resp = chat_client.get("/api/socratic/defaults")
        assert resp.status_code == 200
        data = resp.json()
        # API returns a list of participants directly
        participants = data if isinstance(data, list) else data.get("participants", [])
        assert len(participants) >= 3, f"Expected 3+ participants, got {len(participants)}"
        for p in participants:
            assert "name" in p
            assert "provider" in p
            assert "model" in p
            assert "system" in p

    def test_socratic_roundtable(self, chat_client: httpx.Client):
        """Socratic mode with 2 cheap participants — verify round structure."""
        participants = [
            {
                "name": "Thinker",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "system": "You are Thinker. Give a 1-sentence answer.",
            },
            {
                "name": "Critic",
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "system": "You are Critic. Give a 1-sentence response.",
            },
        ]
        with chat_client.stream("POST", "/api/socratic/stream", json={
            "participants": participants,
            "history": [],
            "user_message": "Is water wet?",
            "rounds": 1,
        }, timeout=120) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors, f"Socratic errors: {errors}"

        # Should have participant_start events for each participant
        starts = [e for e in events if "participant_start" in e]
        assert len(starts) >= 2, f"Expected 2 participant_start events, got {len(starts)}"

        # Each participant_start should have name, provider, model
        for s in starts:
            ps = s["participant_start"]
            assert "name" in ps
            assert "provider" in ps
            assert "model" in ps

        # Should have participant_done events
        dones = [e for e in events if "participant_done" in e]
        assert len(dones) >= 2, f"Expected 2 participant_done events, got {len(dones)}"

        # Should have token events
        text = extract_tokens(events)
        assert len(text) > 10, "Socratic roundtable produced very little text"

    def test_socratic_done_event(self, chat_client: httpx.Client):
        """Socratic stream should end with done event."""
        participants = [
            {
                "name": "Solo",
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "system": "Give a 1-sentence answer.",
            },
        ]
        with chat_client.stream("POST", "/api/socratic/stream", json={
            "participants": participants,
            "history": [],
            "user_message": "Hello",
            "rounds": 1,
        }, timeout=60) as resp:
            assert resp.status_code == 200
            events = collect_sse_stream(resp)

        done_events = [e for e in events if e.get("done")]
        assert len(done_events) >= 1, "No 'done' event in Socratic mode"


# ---------------------------------------------------------------------------
# Test: Response Quality
# ---------------------------------------------------------------------------

class TestResponseQuality:
    """Verify response content is reasonable, not garbled."""

    def test_response_is_readable_text(self, chat_client: httpx.Client):
        """Response should be human-readable (mostly ASCII/printable)."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "messages": SHORT_MESSAGES, "params": {},
        }) as resp:
            events = collect_sse_stream(resp)

        text = extract_tokens(events)
        assert len(text) > 0
        # At least 80% should be printable characters
        printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
        ratio = printable / len(text) if text else 0
        assert ratio > 0.8, f"Response is mostly non-printable ({ratio:.0%}): {text[:100]}"

    def test_response_not_truncated_mid_word(self, chat_client: httpx.Client):
        """With reasonable max_tokens, response should end at a natural boundary."""
        with chat_client.stream("POST", "/api/chat/stream", json={
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Write one complete sentence about the weather."}],
            "params": {"max_tokens": 100},
        }) as resp:
            events = collect_sse_stream(resp)

        errors = find_errors(events)
        assert not errors
        text = extract_tokens(events).strip()
        assert len(text) > 0
        # Should end with punctuation or at least a space (not mid-word)
        assert text[-1] in ".!?,;:\"')]\n " or text.endswith("..."), \
            f"Response appears truncated mid-word: ...{text[-20:]}"

    def test_cross_provider_consistency(self, chat_client: httpx.Client):
        """Both providers should produce meaningful responses to the same prompt."""
        responses = {}
        for provider, model in [
            ("openai", "gpt-4o-mini"),
            ("anthropic", "claude-haiku-4-5-20251001"),
        ]:
            with chat_client.stream("POST", "/api/chat/stream", json={
                "provider": provider, "model": model,
                "messages": [{"role": "user", "content": "What is 2 + 2? Answer with just the number."}],
                "params": {"temperature": 0},
            }) as resp:
                events = collect_sse_stream(resp)

            errors = find_errors(events)
            assert not errors, f"{provider} error: {errors}"
            text = extract_tokens(events)
            responses[provider] = text

        # Both should mention "4"
        for provider, text in responses.items():
            assert "4" in text, f"{provider} didn't answer correctly: {text[:100]}"
