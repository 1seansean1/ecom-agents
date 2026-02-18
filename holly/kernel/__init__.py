"""L1 Kernel — invariant enforcement at every boundary crossing.

Public API:
    - k1_validate        — standalone K1 schema validation gate
    - SchemaRegistry     — ICD schema resolution singleton
    - ValidationError    — raised on schema violation
    - SchemaNotFoundError — raised when schema_id is unknown
    - PayloadTooLargeError — raised on oversized payload
    - KernelError        — base exception for blanket catch
"""

from __future__ import annotations

from holly.kernel.exceptions import (
    KernelError,
    PayloadTooLargeError,
    SchemaNotFoundError,
    SchemaParseError,
    ValidationError,
)
from holly.kernel.k1 import k1_validate
from holly.kernel.schema_registry import SchemaRegistry

__all__ = [
    "KernelError",
    "PayloadTooLargeError",
    "SchemaNotFoundError",
    "SchemaParseError",
    "SchemaRegistry",
    "ValidationError",
    "k1_validate",
]
