"""Tests for browser automation tool — Phase 21a.

Tests:
- URL validation (domain allowlist, protocol blocking, HTTPS enforcement)
- BrowserSession security controls (JS blocking, action logging)
- Domain allowlist enforcement
- BrowseResult data structure
"""

from __future__ import annotations

import pytest

from src.tools.browser import (
    BrowserAction,
    BrowserSession,
    BrowseResult,
    _BLOCKED_PROTOCOLS,
    _DEFAULT_ALLOWED_DOMAINS,
    validate_url,
)


# ── URL Validation ────────────────────────────────────────────────────────


class TestUrlValidation:
    """URL validation enforces security rules."""

    def test_valid_https_url(self):
        valid, error = validate_url(
            "https://liberty-forge-2.myshopify.com/products",
            allowed_domains={"liberty-forge-2.myshopify.com"},
        )
        assert valid
        assert error == ""

    def test_rejects_empty_url(self):
        valid, error = validate_url("")
        assert not valid
        assert "Empty" in error

    def test_rejects_file_protocol(self):
        valid, error = validate_url("file:///etc/passwd")
        assert not valid
        assert "Blocked" in error

    def test_rejects_javascript_protocol(self):
        valid, error = validate_url("javascript:alert(1)")
        assert not valid
        assert "Blocked" in error

    def test_rejects_data_protocol(self):
        valid, error = validate_url("data:text/html,<h1>XSS</h1>")
        assert not valid
        assert "Blocked" in error

    def test_rejects_http_non_localhost(self):
        valid, error = validate_url(
            "http://example.com",
            allowed_domains={"example.com"},
        )
        assert not valid
        assert "HTTPS" in error

    def test_allows_http_localhost(self):
        valid, error = validate_url(
            "http://localhost:8050/health",
            allowed_domains={"localhost"},
        )
        assert valid

    def test_rejects_unlisted_domain(self):
        valid, error = validate_url(
            "https://evil.com",
            allowed_domains={"good.com"},
        )
        assert not valid
        assert "allowlist" in error

    def test_allows_listed_domain(self):
        valid, error = validate_url(
            "https://good.com/path",
            allowed_domains={"good.com"},
        )
        assert valid

    def test_empty_allowlist_allows_all(self):
        """Empty set means no domain restriction."""
        valid, error = validate_url("https://anything.com", allowed_domains=set())
        assert valid

    def test_default_domains_include_shopify(self):
        assert "liberty-forge-2.myshopify.com" in _DEFAULT_ALLOWED_DOMAINS
        assert "printful.com" in _DEFAULT_ALLOWED_DOMAINS

    def test_all_blocked_protocols(self):
        """All dangerous protocols are blocked."""
        for proto in _BLOCKED_PROTOCOLS:
            valid, _ = validate_url(f"{proto}:something")
            assert not valid, f"{proto}: should be blocked"


# ── BrowserSession Security ───────────────────────────────────────────────


class TestBrowserSessionSecurity:
    """BrowserSession enforces security without needing a real browser."""

    def test_session_has_default_domains(self):
        session = BrowserSession()
        assert session._allowed_domains == _DEFAULT_ALLOWED_DOMAINS

    def test_session_custom_domains(self):
        session = BrowserSession(allowed_domains={"custom.com"})
        assert session._allowed_domains == {"custom.com"}

    def test_action_logging(self):
        session = BrowserSession()
        session._log_action("test_action", url="https://example.com")
        assert len(session.actions) == 1
        assert session.actions[0].action == "test_action"
        assert session.actions[0].url == "https://example.com"
        assert session.actions[0].success is True

    def test_action_failure_logging(self):
        session = BrowserSession()
        session._log_action("failed_action", success=False, error="test error")
        assert len(session.actions) == 1
        assert session.actions[0].success is False
        assert session.actions[0].error == "test error"

    @pytest.mark.asyncio
    async def test_navigate_rejects_blocked_url(self):
        session = BrowserSession(allowed_domains={"safe.com"})
        result = await session.navigate("https://evil.com/steal")
        assert not result.success
        assert "allowlist" in result.error

    @pytest.mark.asyncio
    async def test_navigate_rejects_file_url(self):
        session = BrowserSession()
        result = await session.navigate("file:///etc/passwd")
        assert not result.success
        assert "Blocked" in result.error

    @pytest.mark.asyncio
    async def test_navigate_rejects_javascript_url(self):
        session = BrowserSession()
        result = await session.navigate("javascript:alert(1)")
        assert not result.success

    @pytest.mark.asyncio
    async def test_evaluate_blocks_document_cookie(self):
        session = BrowserSession()
        result = await session.evaluate("document.cookie")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_blocks_localstorage(self):
        session = BrowserSession()
        result = await session.evaluate("localStorage.getItem('key')")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_blocks_fetch(self):
        session = BrowserSession()
        result = await session.evaluate("fetch('https://evil.com')")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_blocks_xmlhttprequest(self):
        session = BrowserSession()
        result = await session.evaluate("new XMLHttpRequest()")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_blocks_window_open(self):
        session = BrowserSession()
        result = await session.evaluate("window.open('https://evil.com')")
        assert result is None

    @pytest.mark.asyncio
    async def test_evaluate_blocks_eval(self):
        session = BrowserSession()
        result = await session.evaluate("eval('alert(1)')")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_text_without_browser(self):
        session = BrowserSession()
        text = await session.get_text()
        assert text == ""

    @pytest.mark.asyncio
    async def test_screenshot_without_browser(self):
        session = BrowserSession()
        data = await session.screenshot()
        assert data is None

    @pytest.mark.asyncio
    async def test_click_without_browser(self):
        session = BrowserSession()
        result = await session.click("#button")
        assert result is False


# ── Data Structures ───────────────────────────────────────────────────────


class TestDataStructures:
    """BrowseResult and BrowserAction data structures."""

    def test_browse_result_defaults(self):
        result = BrowseResult(success=True)
        assert result.url == ""
        assert result.title == ""
        assert result.text == ""
        assert result.screenshot is None
        assert result.actions == []
        assert result.error == ""

    def test_browser_action_defaults(self):
        action = BrowserAction(action="navigate")
        assert action.url == ""
        assert action.selector == ""
        assert action.success is True
        assert action.error == ""

    def test_browse_result_with_data(self):
        result = BrowseResult(
            success=True,
            url="https://example.com",
            title="Example",
            text="Hello World",
            metadata={"status_code": 200},
        )
        assert result.url == "https://example.com"
        assert result.title == "Example"
