"""Plugin registry — manages plugin lifecycle and capability enforcement.

Security contract:
- Plugins must pass manifest validation before registration
- Capabilities are enforced at runtime (undeclared capabilities blocked)
- Admin-only capabilities require explicit admin approval
- Auto-enable is off by default; admin must opt in
- All plugin actions are audit-logged
- Plugins can be disabled at runtime without unregistering
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from src.plugins.manifest import (
    ADMIN_ONLY_CAPABILITIES,
    ManifestValidationResult,
    PluginCapability,
    PluginManifest,
    validate_manifest,
)

logger = logging.getLogger(__name__)


class PluginStatus(str, Enum):
    """Plugin lifecycle states."""
    REGISTERED = "registered"     # Manifest validated, not yet enabled
    ENABLED = "enabled"           # Active and dispatching hooks
    DISABLED = "disabled"         # Manually disabled by admin
    ERROR = "error"               # Crashed too many times, auto-disabled


@runtime_checkable
class Plugin(Protocol):
    """Plugin protocol — what a plugin module must implement."""

    @property
    def manifest(self) -> PluginManifest: ...

    def on_enable(self, config: dict[str, Any]) -> None:
        """Called when the plugin is enabled. Receives plugin config."""
        ...

    def on_disable(self) -> None:
        """Called when the plugin is disabled."""
        ...


@dataclass
class PluginEntry:
    """Registry entry for a plugin."""
    plugin: Plugin
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.REGISTERED
    config: dict[str, Any] = field(default_factory=dict)
    error_count: int = 0
    last_error: str = ""
    enabled_at: float = 0.0
    registered_at: float = field(default_factory=time.time)
    # Runtime-registered resources
    registered_tools: list[str] = field(default_factory=list)
    registered_channels: list[str] = field(default_factory=list)


# Auto-disable threshold
_MAX_ERRORS = 10


class PluginRegistry:
    """Singleton registry for all plugins.

    Lifecycle: register → validate → enable → dispatch hooks
    """

    _instance: PluginRegistry | None = None

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, PluginEntry] = {}
            cls._instance._audit_log: list[dict[str, Any]] = []
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None

    @property
    def plugins(self) -> dict[str, PluginEntry]:
        return dict(self._plugins)

    @property
    def enabled_plugins(self) -> dict[str, PluginEntry]:
        return {
            name: entry
            for name, entry in self._plugins.items()
            if entry.status == PluginStatus.ENABLED
        }

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def _audit(self, action: str, plugin_name: str, **details: Any) -> None:
        """Record an audit event."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "plugin": plugin_name,
            **details,
        }
        self._audit_log.append(entry)
        logger.info("Plugin audit: %s %s %s", action, plugin_name, details)

    # ── Registration ─────────────────────────────────────────────────────

    def register(self, plugin: Plugin) -> ManifestValidationResult:
        """Register a plugin. Validates manifest before accepting.

        Returns validation result. Plugin is NOT enabled automatically
        unless manifest.auto_enable is True.
        """
        manifest = plugin.manifest

        # Validate manifest
        result = validate_manifest(manifest)
        if not result.valid:
            self._audit("register_rejected", manifest.name, errors=result.errors)
            return result

        # Check for duplicate
        if manifest.name in self._plugins:
            result = ManifestValidationResult(
                valid=False,
                errors=[f"Plugin '{manifest.name}' is already registered"],
            )
            self._audit("register_duplicate", manifest.name)
            return result

        # Register
        entry = PluginEntry(
            plugin=plugin,
            manifest=manifest,
        )
        self._plugins[manifest.name] = entry
        self._audit("registered", manifest.name, version=manifest.version)

        # Auto-enable if manifest allows (and no admin-only capabilities)
        if manifest.auto_enable and not any(
            cap in ADMIN_ONLY_CAPABILITIES for cap in manifest.capabilities
        ):
            self.enable(manifest.name)

        return result

    def unregister(self, plugin_name: str) -> bool:
        """Unregister a plugin. Disables first if enabled."""
        entry = self._plugins.get(plugin_name)
        if entry is None:
            return False

        if entry.status == PluginStatus.ENABLED:
            self.disable(plugin_name)

        del self._plugins[plugin_name]
        self._audit("unregistered", plugin_name)
        return True

    # ── Enable / Disable ─────────────────────────────────────────────────

    def enable(self, plugin_name: str, config: dict[str, Any] | None = None) -> bool:
        """Enable a registered plugin. Admin action."""
        entry = self._plugins.get(plugin_name)
        if entry is None:
            return False

        if entry.status == PluginStatus.ENABLED:
            return True  # Already enabled

        try:
            entry.plugin.on_enable(config or entry.config)
            entry.status = PluginStatus.ENABLED
            entry.config = config or entry.config
            entry.enabled_at = time.time()
            entry.error_count = 0
            self._audit("enabled", plugin_name)
            return True
        except Exception as e:
            entry.last_error = str(e)
            entry.error_count += 1
            self._audit("enable_failed", plugin_name, error=str(e))
            return False

    def disable(self, plugin_name: str) -> bool:
        """Disable an enabled plugin. Admin action."""
        entry = self._plugins.get(plugin_name)
        if entry is None:
            return False

        if entry.status not in (PluginStatus.ENABLED, PluginStatus.ERROR):
            return True  # Already disabled or just registered

        try:
            entry.plugin.on_disable()
        except Exception as e:
            logger.warning("Plugin %s on_disable error: %s", plugin_name, e)

        entry.status = PluginStatus.DISABLED
        entry.registered_tools.clear()
        entry.registered_channels.clear()
        self._audit("disabled", plugin_name)
        return True

    # ── Capability Enforcement ───────────────────────────────────────────

    def check_capability(self, plugin_name: str, capability: PluginCapability) -> bool:
        """Check if a plugin has declared a specific capability.

        Returns True only if:
        1. Plugin is registered
        2. Plugin is enabled
        3. Capability was declared in manifest
        """
        entry = self._plugins.get(plugin_name)
        if entry is None:
            return False
        if entry.status != PluginStatus.ENABLED:
            return False
        return capability in entry.manifest.capabilities

    def require_capability(
        self, plugin_name: str, capability: PluginCapability
    ) -> None:
        """Assert a capability or raise PermissionError."""
        if not self.check_capability(plugin_name, capability):
            self._audit(
                "capability_denied",
                plugin_name,
                capability=capability.value,
            )
            raise PermissionError(
                f"Plugin '{plugin_name}' does not have capability '{capability.value}'"
            )

    # ── Hook Dispatch ────────────────────────────────────────────────────

    def dispatch_hook(
        self,
        hook: str,
        *,
        capability: PluginCapability,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a hook to all enabled plugins with the required capability.

        Returns dict of {plugin_name: result} for plugins that handled the hook.
        Plugins that crash are error-counted and auto-disabled after threshold.
        """
        results: dict[str, Any] = {}

        for name, entry in list(self._plugins.items()):
            if entry.status != PluginStatus.ENABLED:
                continue
            if capability not in entry.manifest.capabilities:
                continue

            # Check if plugin has the hook handler
            handler = getattr(entry.plugin, hook, None)
            if handler is None or not callable(handler):
                continue

            try:
                result = handler(payload or {})
                results[name] = result
                self._audit("hook_dispatched", name, hook=hook)
            except Exception as e:
                entry.error_count += 1
                entry.last_error = str(e)
                self._audit(
                    "hook_error", name, hook=hook, error=str(e),
                    error_count=entry.error_count,
                )
                if entry.error_count >= _MAX_ERRORS:
                    entry.status = PluginStatus.ERROR
                    self._audit("auto_disabled", name, reason="too_many_errors")

        return results

    # ── Resource Registration ────────────────────────────────────────────

    def register_tool(self, plugin_name: str, tool_name: str) -> bool:
        """Register a tool from a plugin. Requires REGISTER_TOOLS capability."""
        try:
            self.require_capability(plugin_name, PluginCapability.REGISTER_TOOLS)
        except PermissionError:
            return False

        entry = self._plugins[plugin_name]
        if tool_name not in entry.registered_tools:
            entry.registered_tools.append(tool_name)
            self._audit("tool_registered", plugin_name, tool=tool_name)
        return True

    def register_channel(self, plugin_name: str, channel_id: str) -> bool:
        """Register a channel from a plugin. Requires REGISTER_CHANNELS capability."""
        try:
            self.require_capability(plugin_name, PluginCapability.REGISTER_CHANNELS)
        except PermissionError:
            return False

        entry = self._plugins[plugin_name]
        if channel_id not in entry.registered_channels:
            entry.registered_channels.append(channel_id)
            self._audit("channel_registered", plugin_name, channel=channel_id)
        return True

    # ── Status ───────────────────────────────────────────────────────────

    def get_plugin(self, plugin_name: str) -> PluginEntry | None:
        """Get a plugin entry by name."""
        return self._plugins.get(plugin_name)

    def status(self) -> dict[str, Any]:
        """Get registry status summary."""
        return {
            "total": len(self._plugins),
            "enabled": len(self.enabled_plugins),
            "plugins": {
                name: {
                    "status": entry.status.value,
                    "version": entry.manifest.version,
                    "capabilities": [c.value for c in entry.manifest.capabilities],
                    "error_count": entry.error_count,
                    "tools": entry.registered_tools,
                    "channels": entry.registered_channels,
                }
                for name, entry in self._plugins.items()
            },
        }
