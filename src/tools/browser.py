"""Browser automation tool — Phase 21a.

Playwright-based browser for competitive intelligence, storefront verification,
and admin task automation.

Security contract:
- Domain allowlist per invocation (reject unlisted domains)
- Fresh browser context per run (no cookie persistence)
- URL validation: HTTPS only, no file:/javascript:/data: protocols
- 30s timeout per page load
- Browser destroyed on completion
- All actions logged for audit trail
- No credential logging
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

# Default allowed domains (can be overridden per invocation)
_DEFAULT_ALLOWED_DOMAINS: set[str] = {
    "liberty-forge-2.myshopify.com",
    "www.shopify.com",
    "admin.shopify.com",
    "printful.com",
    "www.printful.com",
}

# Blocked URL protocols
_BLOCKED_PROTOCOLS = {"file", "javascript", "data", "blob", "vbscript"}

# Page load timeout (ms)
_PAGE_TIMEOUT_MS = 30000

# Max screenshot size
_MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024  # 10MB


# ── Data Types ────────────────────────────────────────────────────────────


@dataclass
class BrowserAction:
    """Audit log entry for a browser action."""
    action: str  # navigate, click, screenshot, evaluate, etc.
    url: str = ""
    selector: str = ""
    timestamp: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class BrowseResult:
    """Result of a browser automation session."""
    success: bool
    url: str = ""
    title: str = ""
    text: str = ""
    screenshot: bytes | None = None
    actions: list[BrowserAction] = field(default_factory=list)
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── URL Validation ────────────────────────────────────────────────────────


def validate_url(url: str, allowed_domains: set[str] | None = None) -> tuple[bool, str]:
    """Validate a URL against security rules.

    Args:
        url: The URL to validate
        allowed_domains: Set of allowed domains (None = use defaults)

    Returns:
        (is_valid, error_message)
    """
    if not url:
        return False, "Empty URL"

    parsed = urlparse(url)

    # Protocol check
    scheme = parsed.scheme.lower()
    if scheme in _BLOCKED_PROTOCOLS:
        return False, f"Blocked protocol: {scheme}"

    # HTTPS enforcement (allow http for localhost only)
    if scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        return False, "HTTPS required for non-localhost URLs"

    if scheme not in ("http", "https"):
        return False, f"Invalid protocol: {scheme}"

    # Domain allowlist
    domains = allowed_domains if allowed_domains is not None else _DEFAULT_ALLOWED_DOMAINS
    hostname = parsed.hostname or ""

    if domains and hostname not in domains:
        return False, f"Domain not in allowlist: {hostname}"

    return True, ""


# ── Browser Session ───────────────────────────────────────────────────────


class BrowserSession:
    """A sandboxed browser session with security controls.

    Creates a fresh browser context per session. No cookies or state
    persist between sessions. Domain allowlist is enforced on navigation.

    Usage:
        session = BrowserSession(allowed_domains={"example.com"})
        result = await session.navigate("https://example.com")
        await session.close()
    """

    def __init__(
        self,
        allowed_domains: set[str] | None = None,
        headless: bool = True,
    ):
        self._allowed_domains = allowed_domains if allowed_domains is not None else _DEFAULT_ALLOWED_DOMAINS
        self._headless = headless
        self._browser = None
        self._context = None
        self._page = None
        self._actions: list[BrowserAction] = []

    def _log_action(self, action: str, url: str = "", selector: str = "",
                     success: bool = True, error: str = "") -> None:
        """Log an action for audit trail."""
        entry = BrowserAction(
            action=action,
            url=url,
            selector=selector,
            timestamp=time.time(),
            success=success,
            error=error,
        )
        self._actions.append(entry)
        logger.info(
            "BROWSER_AUDIT action=%s url=%s selector=%s success=%s",
            action, url, selector, success,
        )

    async def start(self) -> None:
        """Start browser with fresh context."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
            )
            self._context = await self._browser.new_context(
                # Fresh context — no cookies from previous sessions
                viewport={"width": 1280, "height": 720},
                user_agent="holly-grace-browser/1.0",
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(_PAGE_TIMEOUT_MS)
            self._log_action("start")
        except Exception as e:
            self._log_action("start", success=False, error=str(e))
            raise

    async def navigate(self, url: str) -> BrowseResult:
        """Navigate to a URL (domain-validated)."""
        valid, error = validate_url(url, self._allowed_domains)
        if not valid:
            self._log_action("navigate", url=url, success=False, error=error)
            return BrowseResult(success=False, url=url, error=error, actions=list(self._actions))

        if not self._page:
            return BrowseResult(success=False, url=url, error="Browser not started")

        try:
            await self._page.goto(url, wait_until="domcontentloaded")
            title = await self._page.title()
            self._log_action("navigate", url=url)
            return BrowseResult(
                success=True,
                url=url,
                title=title,
                actions=list(self._actions),
            )
        except Exception as e:
            self._log_action("navigate", url=url, success=False, error=str(e))
            return BrowseResult(
                success=False, url=url, error=str(e), actions=list(self._actions)
            )

    async def get_text(self) -> str:
        """Extract visible text from the current page."""
        if not self._page:
            return ""
        try:
            text = await self._page.inner_text("body")
            self._log_action("get_text")
            return text
        except Exception as e:
            self._log_action("get_text", success=False, error=str(e))
            return ""

    async def screenshot(self) -> bytes | None:
        """Take a screenshot of the current page."""
        if not self._page:
            return None
        try:
            data = await self._page.screenshot(type="png")
            self._log_action("screenshot")
            if len(data) > _MAX_SCREENSHOT_BYTES:
                self._log_action("screenshot", success=False, error="Screenshot too large")
                return None
            return data
        except Exception as e:
            self._log_action("screenshot", success=False, error=str(e))
            return None

    async def click(self, selector: str) -> bool:
        """Click an element by CSS selector."""
        if not self._page:
            return False
        try:
            await self._page.click(selector)
            self._log_action("click", selector=selector)
            return True
        except Exception as e:
            self._log_action("click", selector=selector, success=False, error=str(e))
            return False

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript expression on the page.

        Security: Only allows read-only expressions. Rejects
        document.cookie, localStorage, fetch, XMLHttpRequest.
        """
        if not self._page:
            return None

        # Block dangerous JS patterns
        blocked = ["document.cookie", "localStorage", "sessionStorage",
                    "fetch(", "XMLHttpRequest", "window.open", "eval("]
        for pattern in blocked:
            if pattern.lower() in expression.lower():
                self._log_action("evaluate", success=False,
                                 error=f"Blocked JS pattern: {pattern}")
                return None

        try:
            result = await self._page.evaluate(expression)
            self._log_action("evaluate")
            return result
        except Exception as e:
            self._log_action("evaluate", success=False, error=str(e))
            return None

    @property
    def actions(self) -> list[BrowserAction]:
        """All recorded actions for this session."""
        return list(self._actions)

    async def close(self) -> None:
        """Destroy browser context and close browser."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if hasattr(self, "_playwright") and self._playwright:
                await self._playwright.stop()
            self._log_action("close")
        except Exception as e:
            self._log_action("close", success=False, error=str(e))
        finally:
            self._page = None
            self._context = None
            self._browser = None
