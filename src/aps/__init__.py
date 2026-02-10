"""Adaptive Partition Selection (APS) — information-theoretic agent monitoring.

Implements the experimental protocol from "Informational Monism" (Allen, 2026).
See APS_IMPLEMENTATION_PLAN_v3.md for full specification.

Modules:
    partitions  — 14 partition schemes (7 channels x 2 granularities)
    theta       — 21 theta configs (7 channels x 3 levels)
    channel     — confusion matrices, mutual information, Blahut-Arimoto, eta
    goals       — mission-critical + operational goal definitions
    regeneration — ConfirmProtocol, CrosscheckProtocol
    instrument  — node wrapper with token accounting + trace/path IDs
    controller  — adaptive escalation/de-escalation with UCB + caching
    store       — PostgreSQL persistence (4 tables)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def init_aps() -> None:
    """Initialize APS subsystem: create tables, register partitions + thetas."""
    from src.aps.partitions import register_all_partitions
    from src.aps.store import init_aps_tables
    from src.aps.theta import register_all_thetas

    await init_aps_tables()
    register_all_partitions()
    register_all_thetas()
    logger.info("APS subsystem initialized: 14 partitions, 21 thetas, 4 tables")
