"""Tests for plugin system — Phase 22.

Tests:
- Manifest validation (fields, capabilities, admin-only flags)
- Manifest parsing from dict
- Plugin registration (lifecycle, duplicates, validation)
- Plugin enable/disable (lifecycle, error handling)
- Capability enforcement (check, require, undeclared blocking)
- Hook dispatch (routing, error isolation, auto-disable)
- Resource registration (tools, channels, capability gating)
- Registry status and audit logging
- Hook definitions and dispatch functions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.plugins.hooks import (
    HOOK_CAPABILITY_MAP,
    dispatch_event,
    dispatch_hook,
    dispatch_webhook,
    get_hook_capability,
    list_hooks,
)
from src.plugins.manifest import (
    ADMIN_ONLY_CAPABILITIES,
    VALID_CAPABILITIES,
    ManifestValidationResult,
    PluginCapability,
    PluginManifest,
    parse_manifest,
    validate_manifest,
)
from src.plugins.registry import (
    PluginEntry,
    PluginRegistry,
    PluginStatus,
    _MAX_ERRORS,
)


# ── Test Plugin Implementations ──────────────────────────────────────────


class MockPlugin:
    """Minimal mock plugin satisfying the Plugin protocol."""

    def __init__(
        self,
        name: str = "test-plugin",
        version: str = "1.0.0",
        capabilities: list[PluginCapability] | None = None,
        auto_enable: bool = False,
        on_enable_error: str | None = None,
        on_disable_error: str | None = None,
    ):
        self._manifest = PluginManifest(
            name=name,
            version=version,
            description=f"Test plugin {name}",
            author="test-author",
            capabilities=capabilities or [PluginCapability.ON_EVENT],
            auto_enable=auto_enable,
        )
        self._on_enable_error = on_enable_error
        self._on_disable_error = on_disable_error
        self.enabled = False
        self.disabled = False
        self.events: list[dict] = []

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    def on_enable(self, config: dict[str, Any]) -> None:
        if self._on_enable_error:
            raise RuntimeError(self._on_enable_error)
        self.enabled = True

    def on_disable(self) -> None:
        if self._on_disable_error:
            raise RuntimeError(self._on_disable_error)
        self.disabled = True

    def on_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.events.append(payload)
        return {"handled": True, "count": len(self.events)}


class CrashingPlugin(MockPlugin):
    """Plugin that crashes on event hooks."""

    def on_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("plugin crash!")


class ToolPlugin(MockPlugin):
    """Plugin with REGISTER_TOOLS capability."""

    def __init__(self, name: str = "tool-plugin"):
        super().__init__(
            name=name,
            capabilities=[PluginCapability.REGISTER_TOOLS, PluginCapability.ON_EVENT],
        )

    def on_tools_register(self, payload: dict[str, Any]) -> list[str]:
        return ["my_tool_1", "my_tool_2"]


class ChannelPlugin(MockPlugin):
    """Plugin with REGISTER_CHANNELS capability."""

    def __init__(self, name: str = "channel-plugin"):
        super().__init__(
            name=name,
            capabilities=[PluginCapability.REGISTER_CHANNELS, PluginCapability.ON_EVENT],
        )

    def on_channels_register(self, payload: dict[str, Any]) -> list[str]:
        return ["my_channel"]


# ── Manifest Validation ─────────────────────────────────────────────────


class TestManifestValidation:
    """Manifest validation enforces required fields and capability rules."""

    def test_valid_manifest(self):
        manifest = PluginManifest(
            name="my-plugin",
            version="1.0.0",
            description="A test plugin",
            author="tester",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert result.valid
        assert len(result.errors) == 0

    def test_empty_name_rejected(self):
        manifest = PluginManifest(
            name="", version="1.0.0", description="d", author="a",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert not result.valid
        assert any("name" in e.lower() for e in result.errors)

    def test_invalid_name_chars_rejected(self):
        manifest = PluginManifest(
            name="bad plugin!", version="1.0.0", description="d", author="a",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert not result.valid
        assert any("alphanumeric" in e for e in result.errors)

    def test_hyphen_underscore_in_name_allowed(self):
        manifest = PluginManifest(
            name="my-plugin_v2", version="1.0.0", description="d", author="a",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert result.valid

    def test_empty_version_rejected(self):
        manifest = PluginManifest(
            name="p", version="", description="d", author="a",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert not result.valid

    def test_empty_description_rejected(self):
        manifest = PluginManifest(
            name="p", version="1.0.0", description="", author="a",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert not result.valid

    def test_empty_author_rejected(self):
        manifest = PluginManifest(
            name="p", version="1.0.0", description="d", author="",
            capabilities=[PluginCapability.ON_EVENT],
        )
        result = validate_manifest(manifest)
        assert not result.valid

    def test_no_capabilities_rejected(self):
        manifest = PluginManifest(
            name="p", version="1.0.0", description="d", author="a",
            capabilities=[],
        )
        result = validate_manifest(manifest)
        assert not result.valid
        assert any("capability" in e.lower() for e in result.errors)

    def test_admin_only_capability_warns(self):
        manifest = PluginManifest(
            name="p", version="1.0.0", description="d", author="a",
            capabilities=[PluginCapability.REGISTER_TOOLS],
        )
        result = validate_manifest(manifest)
        assert result.valid
        assert len(result.warnings) > 0
        assert any("admin" in w.lower() for w in result.warnings)

    def test_multiple_admin_capabilities_warn(self):
        manifest = PluginManifest(
            name="p", version="1.0.0", description="d", author="a",
            capabilities=[
                PluginCapability.REGISTER_TOOLS,
                PluginCapability.REGISTER_AGENTS,
                PluginCapability.SCHEDULE_JOBS,
            ],
        )
        result = validate_manifest(manifest)
        assert result.valid
        assert len(result.warnings) == 3

    def test_all_capabilities_enum_values(self):
        assert len(PluginCapability) == 6
        assert len(VALID_CAPABILITIES) == 6

    def test_admin_only_set(self):
        assert PluginCapability.REGISTER_TOOLS in ADMIN_ONLY_CAPABILITIES
        assert PluginCapability.REGISTER_AGENTS in ADMIN_ONLY_CAPABILITIES
        assert PluginCapability.SCHEDULE_JOBS in ADMIN_ONLY_CAPABILITIES
        assert PluginCapability.ON_EVENT not in ADMIN_ONLY_CAPABILITIES


# ── Manifest Parsing ─────────────────────────────────────────────────────


class TestManifestParsing:
    """Parse manifest dicts into PluginManifest objects."""

    def test_parse_valid_dict(self):
        data = {
            "name": "my-plugin",
            "version": "1.0.0",
            "description": "A plugin",
            "author": "tester",
            "capabilities": ["on_event", "on_webhook"],
        }
        manifest = parse_manifest(data)
        assert manifest is not None
        assert manifest.name == "my-plugin"
        assert len(manifest.capabilities) == 2

    def test_parse_unknown_capability_skipped(self):
        data = {
            "name": "p", "version": "1.0", "description": "d", "author": "a",
            "capabilities": ["on_event", "unknown_cap"],
        }
        manifest = parse_manifest(data)
        assert manifest is not None
        assert len(manifest.capabilities) == 1

    def test_parse_empty_dict(self):
        manifest = parse_manifest({})
        assert manifest is not None
        assert manifest.name == ""

    def test_parse_with_optional_fields(self):
        data = {
            "name": "p", "version": "1.0", "description": "d", "author": "a",
            "capabilities": ["on_event"],
            "homepage": "https://example.com",
            "min_system_version": "2.0.0",
            "config_schema": {"type": "object"},
            "required_role": "operator",
            "auto_enable": True,
        }
        manifest = parse_manifest(data)
        assert manifest is not None
        assert manifest.homepage == "https://example.com"
        assert manifest.min_system_version == "2.0.0"
        assert manifest.auto_enable is True


# ── Plugin Registration ──────────────────────────────────────────────────


class TestPluginRegistration:
    """Plugin registration lifecycle."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_register_valid_plugin(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        result = registry.register(plugin)
        assert result.valid
        assert "test-plugin" in registry.plugins

    def test_register_returns_validation_result(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        result = registry.register(plugin)
        assert isinstance(result, ManifestValidationResult)

    def test_register_invalid_manifest_rejected(self):
        registry = PluginRegistry()
        plugin = MockPlugin(name="")
        result = registry.register(plugin)
        assert not result.valid
        assert len(registry.plugins) == 0

    def test_register_duplicate_rejected(self):
        registry = PluginRegistry()
        p1 = MockPlugin(name="dupe")
        p2 = MockPlugin(name="dupe")
        registry.register(p1)
        result = registry.register(p2)
        assert not result.valid
        assert "already registered" in result.errors[0]

    def test_registered_plugin_status(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        entry = registry.get_plugin("test-plugin")
        assert entry is not None
        assert entry.status == PluginStatus.REGISTERED

    def test_unregister_removes_plugin(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        result = registry.unregister("test-plugin")
        assert result is True
        assert "test-plugin" not in registry.plugins

    def test_unregister_nonexistent_returns_false(self):
        registry = PluginRegistry()
        assert registry.unregister("nonexistent") is False

    def test_unregister_disables_first(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        registry.unregister("test-plugin")
        assert plugin.disabled is True

    def test_auto_enable_non_admin_caps(self):
        registry = PluginRegistry()
        plugin = MockPlugin(name="auto-plugin", auto_enable=True)
        registry.register(plugin)
        entry = registry.get_plugin("auto-plugin")
        assert entry is not None
        assert entry.status == PluginStatus.ENABLED
        assert plugin.enabled is True

    def test_no_auto_enable_admin_caps(self):
        """Plugins with admin-only capabilities don't auto-enable."""
        registry = PluginRegistry()
        plugin = MockPlugin(name="admin-plugin", auto_enable=True)
        plugin._manifest.capabilities = [PluginCapability.REGISTER_TOOLS]
        registry.register(plugin)
        entry = registry.get_plugin("admin-plugin")
        assert entry is not None
        assert entry.status == PluginStatus.REGISTERED  # NOT enabled


# ── Enable / Disable ─────────────────────────────────────────────────────


class TestPluginEnableDisable:
    """Plugin enable/disable lifecycle."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_enable_plugin(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        result = registry.enable("test-plugin")
        assert result is True
        assert plugin.enabled is True
        entry = registry.get_plugin("test-plugin")
        assert entry.status == PluginStatus.ENABLED

    def test_enable_nonexistent_returns_false(self):
        registry = PluginRegistry()
        assert registry.enable("nonexistent") is False

    def test_enable_already_enabled_returns_true(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        assert registry.enable("test-plugin") is True

    def test_enable_with_config(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin", config={"key": "value"})
        entry = registry.get_plugin("test-plugin")
        assert entry.config == {"key": "value"}

    def test_enable_error_returns_false(self):
        registry = PluginRegistry()
        plugin = MockPlugin(on_enable_error="boom")
        registry.register(plugin)
        result = registry.enable("test-plugin")
        assert result is False
        entry = registry.get_plugin("test-plugin")
        assert entry.error_count == 1
        assert "boom" in entry.last_error

    def test_disable_plugin(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        result = registry.disable("test-plugin")
        assert result is True
        assert plugin.disabled is True
        entry = registry.get_plugin("test-plugin")
        assert entry.status == PluginStatus.DISABLED

    def test_disable_nonexistent_returns_false(self):
        registry = PluginRegistry()
        assert registry.disable("nonexistent") is False

    def test_disable_already_disabled_returns_true(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        # Not enabled, just registered
        assert registry.disable("test-plugin") is True

    def test_disable_clears_registered_resources(self):
        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        registry.enable("tool-plugin")
        registry.register_tool("tool-plugin", "my-tool")
        entry = registry.get_plugin("tool-plugin")
        assert len(entry.registered_tools) == 1

        registry.disable("tool-plugin")
        assert len(entry.registered_tools) == 0

    def test_disable_error_still_disables(self):
        """on_disable error doesn't prevent disable."""
        registry = PluginRegistry()
        plugin = MockPlugin(on_disable_error="cleanup failed")
        registry.register(plugin)
        registry.enable("test-plugin")
        result = registry.disable("test-plugin")
        assert result is True
        entry = registry.get_plugin("test-plugin")
        assert entry.status == PluginStatus.DISABLED

    def test_enabled_plugins_property(self):
        registry = PluginRegistry()
        p1 = MockPlugin(name="p1")
        p2 = MockPlugin(name="p2")
        registry.register(p1)
        registry.register(p2)
        registry.enable("p1")
        enabled = registry.enabled_plugins
        assert "p1" in enabled
        assert "p2" not in enabled


# ── Capability Enforcement ───────────────────────────────────────────────


class TestCapabilityEnforcement:
    """Capability checks and enforcement."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_check_declared_capability(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        assert registry.check_capability("test-plugin", PluginCapability.ON_EVENT) is True

    def test_check_undeclared_capability(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        assert registry.check_capability("test-plugin", PluginCapability.REGISTER_TOOLS) is False

    def test_check_capability_not_enabled(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        # Not enabled
        assert registry.check_capability("test-plugin", PluginCapability.ON_EVENT) is False

    def test_check_capability_nonexistent(self):
        registry = PluginRegistry()
        assert registry.check_capability("nonexistent", PluginCapability.ON_EVENT) is False

    def test_require_capability_passes(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        # Should not raise
        registry.require_capability("test-plugin", PluginCapability.ON_EVENT)

    def test_require_undeclared_raises(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        with pytest.raises(PermissionError, match="does not have capability"):
            registry.require_capability("test-plugin", PluginCapability.REGISTER_TOOLS)

    def test_require_not_enabled_raises(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        with pytest.raises(PermissionError):
            registry.require_capability("test-plugin", PluginCapability.ON_EVENT)


# ── Hook Dispatch ────────────────────────────────────────────────────────


class TestHookDispatch:
    """Hook dispatch routes to enabled plugins with matching capability."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_dispatch_to_matching_plugin(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")

        results = registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        assert "test-plugin" in results
        assert results["test-plugin"]["handled"] is True
        assert len(plugin.events) == 1

    def test_dispatch_skips_disabled(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        # Not enabled

        results = registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        assert len(results) == 0

    def test_dispatch_skips_wrong_capability(self):
        registry = PluginRegistry()
        plugin = MockPlugin()  # Only has ON_EVENT
        registry.register(plugin)
        registry.enable("test-plugin")

        results = registry.dispatch_hook(
            "on_tools_register", capability=PluginCapability.REGISTER_TOOLS,
            payload={},
        )
        assert len(results) == 0

    def test_dispatch_to_multiple_plugins(self):
        registry = PluginRegistry()
        p1 = MockPlugin(name="p1")
        p2 = MockPlugin(name="p2")
        registry.register(p1)
        registry.register(p2)
        registry.enable("p1")
        registry.enable("p2")

        results = registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        assert "p1" in results
        assert "p2" in results

    def test_dispatch_error_isolates_plugin(self):
        """One plugin crashing doesn't affect others."""
        registry = PluginRegistry()
        crasher = CrashingPlugin(name="crasher")
        good = MockPlugin(name="good")
        registry.register(crasher)
        registry.register(good)
        registry.enable("crasher")
        registry.enable("good")

        results = registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        # Good plugin still gets result
        assert "good" in results
        assert "crasher" not in results
        # Crasher gets error counted
        entry = registry.get_plugin("crasher")
        assert entry.error_count == 1

    def test_auto_disable_after_max_errors(self):
        registry = PluginRegistry()
        crasher = CrashingPlugin(name="crasher")
        registry.register(crasher)
        registry.enable("crasher")

        for _ in range(_MAX_ERRORS):
            registry.dispatch_hook(
                "on_event", capability=PluginCapability.ON_EVENT,
                payload={"type": "test"},
            )

        entry = registry.get_plugin("crasher")
        assert entry.status == PluginStatus.ERROR
        assert entry.error_count >= _MAX_ERRORS

    def test_dispatch_skips_missing_handler(self):
        """Plugin without the handler method is silently skipped."""
        registry = PluginRegistry()
        plugin = MockPlugin()  # Has on_event but not on_tools_register
        plugin._manifest.capabilities.append(PluginCapability.REGISTER_TOOLS)
        registry.register(plugin)
        registry.enable("test-plugin")

        results = registry.dispatch_hook(
            "on_tools_register", capability=PluginCapability.REGISTER_TOOLS,
            payload={},
        )
        assert len(results) == 0  # No handler, no result


# ── Resource Registration ────────────────────────────────────────────────


class TestResourceRegistration:
    """Plugin resource registration (tools, channels) with capability gating."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_register_tool_with_capability(self):
        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        registry.enable("tool-plugin")
        result = registry.register_tool("tool-plugin", "my-tool")
        assert result is True
        entry = registry.get_plugin("tool-plugin")
        assert "my-tool" in entry.registered_tools

    def test_register_tool_without_capability(self):
        registry = PluginRegistry()
        plugin = MockPlugin()  # Only ON_EVENT
        registry.register(plugin)
        registry.enable("test-plugin")
        result = registry.register_tool("test-plugin", "my-tool")
        assert result is False

    def test_register_tool_duplicate_ignored(self):
        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        registry.enable("tool-plugin")
        registry.register_tool("tool-plugin", "my-tool")
        registry.register_tool("tool-plugin", "my-tool")
        entry = registry.get_plugin("tool-plugin")
        assert entry.registered_tools.count("my-tool") == 1

    def test_register_channel_with_capability(self):
        registry = PluginRegistry()
        plugin = ChannelPlugin()
        registry.register(plugin)
        registry.enable("channel-plugin")
        result = registry.register_channel("channel-plugin", "my-channel")
        assert result is True
        entry = registry.get_plugin("channel-plugin")
        assert "my-channel" in entry.registered_channels

    def test_register_channel_without_capability(self):
        registry = PluginRegistry()
        plugin = MockPlugin()  # Only ON_EVENT
        registry.register(plugin)
        registry.enable("test-plugin")
        result = registry.register_channel("test-plugin", "my-channel")
        assert result is False


# ── Audit Logging ────────────────────────────────────────────────────────


class TestAuditLogging:
    """Registry audit log captures all plugin actions."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_register_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        log = registry.audit_log
        assert any(e["action"] == "registered" for e in log)

    def test_enable_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        log = registry.audit_log
        assert any(e["action"] == "enabled" for e in log)

    def test_disable_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        registry.disable("test-plugin")
        log = registry.audit_log
        assert any(e["action"] == "disabled" for e in log)

    def test_rejected_registration_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin(name="")
        registry.register(plugin)
        log = registry.audit_log
        assert any(e["action"] == "register_rejected" for e in log)

    def test_capability_denied_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        try:
            registry.require_capability("test-plugin", PluginCapability.REGISTER_TOOLS)
        except PermissionError:
            pass
        log = registry.audit_log
        assert any(e["action"] == "capability_denied" for e in log)

    def test_hook_dispatch_logged(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")
        registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        log = registry.audit_log
        assert any(e["action"] == "hook_dispatched" for e in log)

    def test_hook_error_logged(self):
        registry = PluginRegistry()
        crasher = CrashingPlugin(name="crasher")
        registry.register(crasher)
        registry.enable("crasher")
        registry.dispatch_hook(
            "on_event", capability=PluginCapability.ON_EVENT,
            payload={"type": "test"},
        )
        log = registry.audit_log
        assert any(e["action"] == "hook_error" for e in log)

    def test_auto_disable_logged(self):
        registry = PluginRegistry()
        crasher = CrashingPlugin(name="crasher")
        registry.register(crasher)
        registry.enable("crasher")
        for _ in range(_MAX_ERRORS):
            registry.dispatch_hook(
                "on_event", capability=PluginCapability.ON_EVENT,
                payload={"type": "test"},
            )
        log = registry.audit_log
        assert any(e["action"] == "auto_disabled" for e in log)

    def test_audit_log_has_timestamps(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        log = registry.audit_log
        assert all("timestamp" in e for e in log)


# ── Registry Status ──────────────────────────────────────────────────────


class TestRegistryStatus:
    """Registry status reporting."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_empty_status(self):
        registry = PluginRegistry()
        status = registry.status()
        assert status["total"] == 0
        assert status["enabled"] == 0

    def test_status_with_plugins(self):
        registry = PluginRegistry()
        p1 = MockPlugin(name="p1")
        p2 = MockPlugin(name="p2")
        registry.register(p1)
        registry.register(p2)
        registry.enable("p1")

        status = registry.status()
        assert status["total"] == 2
        assert status["enabled"] == 1
        assert "p1" in status["plugins"]
        assert status["plugins"]["p1"]["status"] == "enabled"
        assert status["plugins"]["p2"]["status"] == "registered"

    def test_status_includes_capabilities(self):
        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        status = registry.status()
        caps = status["plugins"]["tool-plugin"]["capabilities"]
        assert "register_tools" in caps

    def test_status_includes_tools_and_channels(self):
        registry = PluginRegistry()
        plugin = ToolPlugin()
        registry.register(plugin)
        registry.enable("tool-plugin")
        registry.register_tool("tool-plugin", "my-tool")

        status = registry.status()
        assert "my-tool" in status["plugins"]["tool-plugin"]["tools"]


# ── Hook Definitions ─────────────────────────────────────────────────────


class TestHookDefinitions:
    """Hook definitions map hooks to capabilities."""

    def test_all_hooks_have_capabilities(self):
        for hook, cap in HOOK_CAPABILITY_MAP.items():
            assert isinstance(cap, PluginCapability)

    def test_get_hook_capability(self):
        assert get_hook_capability("on_event") == PluginCapability.ON_EVENT
        assert get_hook_capability("on_tools_register") == PluginCapability.REGISTER_TOOLS
        assert get_hook_capability("nonexistent") is None

    def test_list_hooks(self):
        hooks = list_hooks()
        assert len(hooks) == len(HOOK_CAPABILITY_MAP)
        assert all("hook" in h and "capability" in h for h in hooks)

    def test_hook_count(self):
        """Verify we have the expected number of hooks."""
        assert len(HOOK_CAPABILITY_MAP) >= 12  # At least 12 hooks defined


# ── Hook Dispatch Functions ──────────────────────────────────────────────


class TestHookDispatchFunctions:
    """High-level hook dispatch convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_dispatch_hook_routes_correctly(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")

        results = dispatch_hook("on_event", {"type": "test"})
        assert "test-plugin" in results

    def test_dispatch_hook_unknown_returns_empty(self):
        results = dispatch_hook("totally_unknown_hook", {})
        assert len(results) == 0

    def test_dispatch_event_convenience(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        registry.enable("test-plugin")

        results = dispatch_event({"type": "order_created"})
        assert "test-plugin" in results
        assert plugin.events[0]["type"] == "order_created"

    def test_dispatch_webhook_convenience(self):
        registry = PluginRegistry()
        plugin = MockPlugin(
            name="webhook-handler",
            capabilities=[PluginCapability.ON_WEBHOOK],
        )
        # Add on_webhook_received handler
        plugin.on_webhook_received = lambda payload: {"ok": True}
        registry.register(plugin)
        registry.enable("webhook-handler")

        results = dispatch_webhook({"provider": "shopify", "event": "orders/create"})
        assert "webhook-handler" in results

    def test_dispatch_deep_copies_payload(self):
        """Payload mutation by plugin doesn't affect original."""
        registry = PluginRegistry()

        class MutatingPlugin(MockPlugin):
            def on_event(self, payload):
                payload["mutated"] = True
                return {"ok": True}

        plugin = MutatingPlugin(name="mutator")
        registry.register(plugin)
        registry.enable("mutator")

        original = {"type": "test", "data": [1, 2, 3]}
        dispatch_hook("on_event", original)
        assert "mutated" not in original


# ── Singleton Behavior ───────────────────────────────────────────────────


class TestSingletonBehavior:
    """Registry singleton behavior."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        PluginRegistry.reset()
        yield
        PluginRegistry.reset()

    def test_singleton(self):
        r1 = PluginRegistry()
        r2 = PluginRegistry()
        assert r1 is r2

    def test_reset_clears_state(self):
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)
        assert len(registry.plugins) == 1

        PluginRegistry.reset()
        registry = PluginRegistry()
        assert len(registry.plugins) == 0
