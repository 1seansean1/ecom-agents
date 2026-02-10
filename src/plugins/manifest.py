"""Plugin manifest — defines what a plugin can do.

Security contract:
- Manifest declares capabilities upfront (tools, channels, hooks)
- Capabilities are validated against a whitelist at registration
- Undeclared capabilities are blocked at runtime
- Manifest schema is strictly validated
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PluginCapability(str, Enum):
    """Allowed plugin capabilities."""
    REGISTER_TOOLS = "register_tools"       # Register agent tools
    REGISTER_CHANNELS = "register_channels"  # Register notification channels
    ON_EVENT = "on_event"                    # Subscribe to events
    ON_WEBHOOK = "on_webhook"               # Handle webhook events
    REGISTER_AGENTS = "register_agents"     # Register custom agents
    SCHEDULE_JOBS = "schedule_jobs"          # Schedule periodic tasks


# Capabilities that require admin approval to enable
ADMIN_ONLY_CAPABILITIES: set[PluginCapability] = {
    PluginCapability.REGISTER_TOOLS,
    PluginCapability.REGISTER_AGENTS,
    PluginCapability.SCHEDULE_JOBS,
}

# All valid capabilities
VALID_CAPABILITIES: set[str] = {c.value for c in PluginCapability}


@dataclass
class PluginManifest:
    """Plugin manifest — describes a plugin's identity and capabilities."""
    name: str                                    # Unique plugin name (slug)
    version: str                                 # SemVer
    description: str                             # Human-readable description
    author: str                                  # Plugin author
    capabilities: list[PluginCapability]          # Declared capabilities
    # Optional
    homepage: str = ""
    min_system_version: str = "0.1.0"
    config_schema: dict[str, Any] = field(default_factory=dict)  # JSON Schema for plugin config
    # Security
    required_role: str = "admin"                 # Minimum role to enable this plugin
    auto_enable: bool = False                    # Whether to auto-enable (admin must opt in)


@dataclass
class ManifestValidationResult:
    """Result of manifest validation."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_manifest(manifest: PluginManifest) -> ManifestValidationResult:
    """Validate a plugin manifest against security rules.

    Checks:
    - Required fields are present and non-empty
    - Capabilities are valid
    - No capability escalation (admin-only capabilities flagged)
    """
    errors = []
    warnings = []

    # Required fields
    if not manifest.name:
        errors.append("Plugin name is required")
    elif not manifest.name.replace("-", "").replace("_", "").isalnum():
        errors.append("Plugin name must be alphanumeric (with - or _)")

    if not manifest.version:
        errors.append("Plugin version is required")

    if not manifest.description:
        errors.append("Plugin description is required")

    if not manifest.author:
        errors.append("Plugin author is required")

    # Capability validation
    if not manifest.capabilities:
        errors.append("Plugin must declare at least one capability")
    else:
        for cap in manifest.capabilities:
            if cap.value not in VALID_CAPABILITIES:
                errors.append(f"Invalid capability: {cap}")
            if cap in ADMIN_ONLY_CAPABILITIES:
                warnings.append(
                    f"Capability '{cap.value}' requires admin approval"
                )

    return ManifestValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def parse_manifest(data: dict[str, Any]) -> PluginManifest | None:
    """Parse a manifest dict into a PluginManifest object.

    Returns None if required fields are missing.
    """
    try:
        capabilities = []
        for cap_str in data.get("capabilities", []):
            try:
                capabilities.append(PluginCapability(cap_str))
            except ValueError:
                logger.warning("Unknown capability in manifest: %s", cap_str)

        return PluginManifest(
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            capabilities=capabilities,
            homepage=data.get("homepage", ""),
            min_system_version=data.get("min_system_version", "0.1.0"),
            config_schema=data.get("config_schema", {}),
            required_role=data.get("required_role", "admin"),
            auto_enable=data.get("auto_enable", False),
        )
    except Exception as e:
        logger.error("Failed to parse manifest: %s", e)
        return None
