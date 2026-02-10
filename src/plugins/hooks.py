"""Plugin hook definitions — declares all available hook points.

Each hook maps to a PluginCapability. Plugins can only receive hooks
for capabilities they declared in their manifest.

Security contract:
- Hook payloads are sanitized before dispatch (no raw credentials)
- Plugins cannot modify the payload — they receive a copy
- Hook results are validated before being used by the system
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from src.plugins.manifest import PluginCapability
from src.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


# ── Hook Definitions ─────────────────────────────────────────────────────

# Maps hook name → required capability
HOOK_CAPABILITY_MAP: dict[str, PluginCapability] = {
    # Tool hooks
    "on_tools_register": PluginCapability.REGISTER_TOOLS,
    "on_tool_before_invoke": PluginCapability.REGISTER_TOOLS,
    "on_tool_after_invoke": PluginCapability.REGISTER_TOOLS,
    # Channel hooks
    "on_channels_register": PluginCapability.REGISTER_CHANNELS,
    "on_notification_before_send": PluginCapability.REGISTER_CHANNELS,
    # Event hooks
    "on_event": PluginCapability.ON_EVENT,
    "on_agent_start": PluginCapability.ON_EVENT,
    "on_agent_end": PluginCapability.ON_EVENT,
    "on_agent_error": PluginCapability.ON_EVENT,
    # Webhook hooks
    "on_webhook_received": PluginCapability.ON_WEBHOOK,
    "on_webhook_verified": PluginCapability.ON_WEBHOOK,
    # Agent hooks
    "on_agents_register": PluginCapability.REGISTER_AGENTS,
    # Schedule hooks
    "on_schedules_register": PluginCapability.SCHEDULE_JOBS,
}


def get_hook_capability(hook: str) -> PluginCapability | None:
    """Get the capability required for a hook."""
    return HOOK_CAPABILITY_MAP.get(hook)


def list_hooks() -> list[dict[str, str]]:
    """List all available hooks with their required capabilities."""
    return [
        {"hook": hook, "capability": cap.value}
        for hook, cap in HOOK_CAPABILITY_MAP.items()
    ]


# ── Hook Dispatch Functions ──────────────────────────────────────────────


def dispatch_hook(hook: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a hook to all plugins that declared the required capability.

    Payload is deep-copied before dispatch so plugins cannot mutate shared state.
    Returns {plugin_name: result} for all plugins that handled the hook.
    """
    capability = get_hook_capability(hook)
    if capability is None:
        logger.warning("Unknown hook: %s", hook)
        return {}

    # Deep-copy payload to prevent mutation
    safe_payload = copy.deepcopy(payload) if payload else {}

    registry = PluginRegistry()
    return registry.dispatch_hook(hook, capability=capability, payload=safe_payload)


def dispatch_event(event: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an event to all plugins with ON_EVENT capability.

    Convenience wrapper for the on_event hook.
    """
    return dispatch_hook("on_event", payload=event)


def dispatch_webhook(webhook_data: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a webhook event to all plugins with ON_WEBHOOK capability."""
    return dispatch_hook("on_webhook_received", payload=webhook_data)
