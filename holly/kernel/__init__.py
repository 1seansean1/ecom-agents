"""L1 Kernel — invariant enforcement at every boundary crossing.

Public API:
    - k1_validate        — standalone K1 schema validation gate
    - k8_evaluate        — standalone K8 eval gate
    - SchemaRegistry     — ICD schema resolution singleton
    - PredicateRegistry  — K8 predicate resolution singleton
    - ValidationError    — raised on schema violation
    - SchemaNotFoundError — raised when schema_id is unknown
    - PayloadTooLargeError — raised on oversized payload
    - PredicateNotFoundError — raised when predicate_id is unknown
    - EvalGateFailure    — raised when output violates K8 predicate
    - EvalError          — raised when predicate evaluation fails
    - KernelError        — base exception for blanket catch
"""

from __future__ import annotations

from holly.kernel.exceptions import (
    EvalError,
    EvalGateFailure,
    KernelError,
    PayloadTooLargeError,
    PredicateAlreadyRegisteredError,
    PredicateNotFoundError,
    SchemaNotFoundError,
    SchemaParseError,
    ValidationError,
)
from holly.kernel.k1 import k1_validate
from holly.kernel.k8 import k8_evaluate
from holly.kernel.predicate_registry import PredicateRegistry
from holly.kernel.schema_registry import SchemaRegistry

__all__ = [
    "EvalError",
    "EvalGateFailure",
    "KernelError",
    "PayloadTooLargeError",
    "PredicateAlreadyRegisteredError",
    "PredicateNotFoundError",
    "PredicateRegistry",
    "SchemaNotFoundError",
    "SchemaParseError",
    "SchemaRegistry",
    "ValidationError",
    "k1_validate",
    "k8_evaluate",
]
