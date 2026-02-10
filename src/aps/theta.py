"""Theta configurations: the expanded control tuple theta = (partition, model, protocol).

21 configurations: 7 channels x 3 levels (nominal, degraded, critical).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from src.llm.config import ModelID

logger = logging.getLogger(__name__)


class ProtocolLevel(str, Enum):
    PASSIVE = "passive"         # No regeneration. Run and log.
    CONFIRM = "confirm"         # On failure, retry once with clarified prompt.
    CROSSCHECK = "crosscheck"   # After LLM output, run deterministic validator.


@dataclass
class ThetaConfig:
    """Complete control configuration for one channel under APS.

    theta = (partition, model, protocol) per the paper.
    """

    theta_id: str
    channel_id: str
    level: int                             # 0=nominal, 1=degraded, 2=critical
    partition_id: str
    model_override: ModelID | None
    protocol_level: ProtocolLevel
    description: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THETA_REGISTRY: dict[str, ThetaConfig] = {}
_ACTIVE_THETA: dict[str, str] = {}  # channel_id -> theta_id


def get_active_theta(channel_id: str) -> ThetaConfig:
    tid = _ACTIVE_THETA.get(channel_id)
    if tid is None:
        raise KeyError(f"No active theta for channel {channel_id}")
    return THETA_REGISTRY[tid]


def set_active_theta(channel_id: str, theta_id: str) -> None:
    if theta_id not in THETA_REGISTRY:
        raise KeyError(f"Unknown theta: {theta_id}")
    _ACTIVE_THETA[channel_id] = theta_id
    # Also update the active partition to match
    from src.aps.partitions import set_active_partition
    theta = THETA_REGISTRY[theta_id]
    set_active_partition(channel_id, theta.partition_id)


def get_theta_by_channel_and_level(channel_id: str, level: int) -> ThetaConfig | None:
    for t in THETA_REGISTRY.values():
        if t.channel_id == channel_id and t.level == level:
            return t
    return None


def get_all_theta_states() -> dict[str, dict]:
    result = {}
    for ch_id, theta_id in _ACTIVE_THETA.items():
        t = THETA_REGISTRY[theta_id]
        result[ch_id] = {
            "theta_id": t.theta_id,
            "level": t.level,
            "partition_id": t.partition_id,
            "model_override": t.model_override.value if t.model_override else None,
            "protocol_level": t.protocol_level.value,
            "description": t.description,
        }
    return result


# ---------------------------------------------------------------------------
# 21 Theta Configurations
# ---------------------------------------------------------------------------

_ALL_THETAS: list[ThetaConfig] = [
    # K1 — Orchestrator
    ThetaConfig("theta_K1_nominal", "K1", 0, "theta_K1_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine partition, Ollama, passive"),
    ThetaConfig("theta_K1_degraded", "K1", 1, "theta_K1_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, Ollama, retry on misclassification"),
    ThetaConfig("theta_K1_critical", "K1", 2, "theta_K1_coarse",
                ModelID.GPT4O_MINI, ProtocolLevel.PASSIVE,
                "Critical: coarse, escalate to GPT-4o-mini, passive (stronger model)"),
    # K2 — Sales/Marketing
    ThetaConfig("theta_K2_nominal", "K2", 0, "theta_K2_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine partition, GPT-4o, passive"),
    ThetaConfig("theta_K2_degraded", "K2", 1, "theta_K2_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, GPT-4o, retry on failure"),
    ThetaConfig("theta_K2_critical", "K2", 2, "theta_K2_coarse",
                None, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, GPT-4o, crosscheck JSON structure"),
    # K3 — Operations
    ThetaConfig("theta_K3_nominal", "K3", 0, "theta_K3_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine partition, GPT-4o-mini, passive"),
    ThetaConfig("theta_K3_degraded", "K3", 1, "theta_K3_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, GPT-4o-mini, retry on failure"),
    ThetaConfig("theta_K3_critical", "K3", 2, "theta_K3_coarse",
                ModelID.GPT4O, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, escalate to GPT-4o, crosscheck order IDs"),
    # K4 — Revenue Analytics
    ThetaConfig("theta_K4_nominal", "K4", 0, "theta_K4_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine, Opus, passive"),
    ThetaConfig("theta_K4_degraded", "K4", 1, "theta_K4_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, Opus, retry on failure"),
    ThetaConfig("theta_K4_critical", "K4", 2, "theta_K4_coarse",
                None, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, Opus, crosscheck revenue figures"),
    # K5 — Content Writer
    ThetaConfig("theta_K5_nominal", "K5", 0, "theta_K5_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine, GPT-4o, passive"),
    ThetaConfig("theta_K5_degraded", "K5", 1, "theta_K5_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, GPT-4o, retry with JSON schema"),
    ThetaConfig("theta_K5_critical", "K5", 2, "theta_K5_coarse",
                None, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, GPT-4o, crosscheck caption + hashtags"),
    # K6 — Campaign Analyzer
    ThetaConfig("theta_K6_nominal", "K6", 0, "theta_K6_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine, Opus, passive"),
    ThetaConfig("theta_K6_degraded", "K6", 1, "theta_K6_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, Opus, retry with scoring rubric"),
    ThetaConfig("theta_K6_critical", "K6", 2, "theta_K6_coarse",
                None, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, Opus, crosscheck engagement score ranges"),
    # K7 — Tool Calls
    ThetaConfig("theta_K7_nominal", "K7", 0, "theta_K7_fine",
                None, ProtocolLevel.PASSIVE, "Nominal: fine, tools, passive"),
    ThetaConfig("theta_K7_degraded", "K7", 1, "theta_K7_coarse",
                None, ProtocolLevel.CONFIRM, "Degraded: coarse, retry failed API calls"),
    ThetaConfig("theta_K7_critical", "K7", 2, "theta_K7_coarse",
                None, ProtocolLevel.CROSSCHECK,
                "Critical: coarse, crosscheck response schema + idempotency"),
]


def register_all_thetas() -> None:
    """Register all 21 theta configs and set nominal (level 0) as defaults."""
    for t in _ALL_THETAS:
        THETA_REGISTRY[t.theta_id] = t

    # Default: all channels start at level 0 (nominal)
    for ch in ("K1", "K2", "K3", "K4", "K5", "K6", "K7"):
        nominal = get_theta_by_channel_and_level(ch, 0)
        if nominal:
            _ACTIVE_THETA[ch] = nominal.theta_id

    logger.info("Registered %d theta configurations", len(THETA_REGISTRY))
