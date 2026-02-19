"""Observability module: tracing, metrics, and secret scanning."""

from holly.observability.secret_scanner import (
    ScanResult,
    SecretFinding,
    SecretScanner,
    SecretScannerConfig,
    SeverityLevel,
)

__all__ = [
    "ScanResult",
    "SecretFinding",
    "SecretScanner",
    "SecretScannerConfig",
    "SeverityLevel",
]
