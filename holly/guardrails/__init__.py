"""Holly Grace Guardrails Module.

Implements input sanitization, output redaction, and injection detection per
Task 28.3. All boundary crossings must pass through the guardrails pipeline.

Public API:
- GuardrailsEngine: Main guardrails implementation
- GuardrailsResult: Combined result type
- create_default_engine: Factory for production instances
"""

from __future__ import annotations

from holly.guardrails.core import (
    GuardrailsEngine,
    GuardrailsEngineProtocol,
    GuardrailsError,
    GuardrailsResult,
    InjectionDetectionResult,
    InputSanitizationResult,
    OutputRedactionResult,
    create_default_engine,
)

__all__ = [
    "GuardrailsEngine",
    "GuardrailsEngineProtocol",
    "GuardrailsError",
    "GuardrailsResult",
    "InjectionDetectionResult",
    "InputSanitizationResult",
    "OutputRedactionResult",
    "create_default_engine",
]
