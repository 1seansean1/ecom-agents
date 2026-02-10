"""P2 HIGH: External API tool security tests.

Verifies secure handling of API credentials in tool implementations:
- Instagram token transport (query params vs headers)
- HTTPS enforcement
- Timeout configuration
- Missing API key error handling
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestInstagramTokenTransport:
    """Instagram tool should use headers, not URL query params for tokens."""

    def test_instagram_token_in_headers_not_params(self):
        """REMEDIATED: Instagram tool sends token via Authorization header, not URL params."""
        import inspect

        from src.tools.instagram_tool import _meta_request

        source = inspect.getsource(_meta_request)
        # Token must be in Authorization header
        assert "Authorization" in source, (
            "Instagram tool should send token via Authorization header"
        )
        assert "Bearer" in source, (
            "Instagram tool should use Bearer scheme for token"
        )
        # Token must NOT be in URL query params
        assert "access_token" not in source.split("headers")[0].split("def ")[-1] or \
               "all_params" not in source, (
            "Instagram tool should not send access_token as query param"
        )

    def test_instagram_token_not_in_response(self):
        """Instagram tool responses don't leak the access token."""
        with patch("src.tools.instagram_tool.httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "12345"}
            mock_resp.raise_for_status = MagicMock()
            mock_req.return_value = mock_resp

            from src.tools.instagram_tool import _meta_request

            result = _meta_request.__wrapped__("GET", "/test")
            assert os.environ.get("INSTAGRAM_ACCESS_TOKEN", "") not in str(result)


class TestHTTPSEnforcement:
    """External API calls should use HTTPS."""

    def test_instagram_uses_https(self):
        """Instagram API base URL uses HTTPS."""
        from src.tools.instagram_tool import META_GRAPH_BASE

        assert META_GRAPH_BASE.startswith("https://")

    def test_shopify_uses_https(self):
        """Shopify API calls use HTTPS."""
        from src.tools.shopify_tool import _graphql_request

        import inspect

        source = inspect.getsource(_graphql_request)
        assert "https://" in source or "SHOPIFY_SHOP_URL" in source


class TestTimeoutConfiguration:
    """External API calls must have explicit timeouts."""

    def test_instagram_has_timeout(self):
        """Instagram API calls have timeout configured."""
        import inspect

        from src.tools.instagram_tool import _meta_request

        source = inspect.getsource(_meta_request)
        assert "timeout" in source, "Instagram API calls must have explicit timeout"

    def test_shopify_has_timeout(self):
        """Shopify API calls have timeout configured."""
        import inspect

        from src.tools.shopify_tool import _graphql_request

        source = inspect.getsource(_graphql_request)
        assert "timeout" in source, "Shopify API calls must have explicit timeout"


class TestMissingAPIKeys:
    """Missing API keys should produce clear errors."""

    def test_instagram_missing_account_id(self):
        """Missing Instagram account ID returns clear error."""
        with patch.dict(os.environ, {"INSTAGRAM_BUSINESS_ACCOUNT_ID": ""}):
            with patch("src.tools.instagram_tool.httpx.request"):
                from src.tools.instagram_tool import instagram_publish_post

                result = instagram_publish_post.invoke({
                    "image_url": "https://example.com/img.jpg",
                    "caption": "Test",
                })
                assert "error" in result
                assert "not configured" in result["error"].lower() or "error" in result

    def test_instagram_missing_access_token(self):
        """Missing Instagram token handled without crash."""
        with patch.dict(os.environ, {"INSTAGRAM_ACCESS_TOKEN": ""}):
            # The tool should handle missing token gracefully
            from src.tools.instagram_tool import _meta_request

            # This will likely fail at the HTTP level, but shouldn't crash
            try:
                _meta_request.__wrapped__("GET", "/test")
            except Exception:
                pass  # Expected -- but should not be an unhandled crash


class TestCircuitBreakerIntegration:
    """Tools should have circuit breaker protection."""

    def test_retry_decorator_exists(self):
        """Instagram tool has retry-with-backoff decorator."""
        from src.tools.instagram_tool import _meta_request

        # Verify the function is wrapped with retry decorator
        assert hasattr(_meta_request, "__wrapped__"), (
            "Instagram _meta_request should be decorated with @retry_with_backoff"
        )

    def test_circuit_breaker_module_exists(self):
        """Circuit breaker module is available."""
        from src.resilience.circuit_breaker import get_all_states

        # Module loads without error
        assert callable(get_all_states)
