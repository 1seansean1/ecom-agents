"""L1 Kernel — invariant enforcement at every boundary crossing.

Public API:
    - k1_validate           — standalone K1 schema validation gate
    - k1_gate               — Gate-compatible K1 factory for KernelContext
    - k2_check_permissions  — standalone K2 RBAC permission check
    - k2_gate               — Gate-compatible K2 factory for KernelContext
    - k3_check_bounds       — standalone K3 resource bounds check
    - k3_gate               — Gate-compatible K3 factory for KernelContext
    - k4_inject_trace       — standalone K4 trace injection
    - k4_gate               — Gate-compatible K4 factory for KernelContext
    - k5_generate_key       — standalone K5 RFC 8785 idempotency key generation
    - k5_gate               — Gate-compatible K5 factory for KernelContext
    - k6_write_entry        — standalone K6 WAL entry write (validate + redact + append)
    - k6_gate               — Gate-compatible K6 factory for KernelContext
    - k8_evaluate           — standalone K8 eval gate
    - IdempotencyStore      — K5 deduplication store protocol
    - InMemoryIdempotencyStore — K5 in-memory store for testing/single-process
    - WALBackend            — K6 append-only WAL storage protocol
    - InMemoryWALBackend    — K6 in-memory WAL for testing/single-process
    - WALEntry              — K6 audit record dataclass
    - redact                — K6 ICD v0.1 redaction engine
    - SchemaRegistry        — ICD JSON Schema resolution singleton
    - ICDSchemaRegistry     — ICD Pydantic model resolution with TTL cache
    - PredicateRegistry     — K8 predicate resolution singleton
    - PermissionRegistry    — K2 role-to-permission mapping singleton
    - BudgetRegistry        — K3 per-tenant resource budget singleton
    - ValidationError       — raised on schema violation
    - SchemaNotFoundError   — raised when schema_id is unknown
    - PayloadTooLargeError  — raised on oversized payload
    - PredicateNotFoundError — raised when predicate_id is unknown
    - TenantContextError    — raised when JWT claims lack tenant_id
    - CanonicalizeError     — raised when RFC 8785 canonicalization fails
    - DuplicateRequestError — raised when an idempotency key has been seen before
    - WALWriteError         — raised when WAL backend write fails
    - WALFormatError        — raised when WALEntry is malformed
    - RedactionError        — raised when redaction engine fails
    - EvalGateFailure       — raised when output violates K8 predicate
    - EvalError             — raised when predicate evaluation fails
    - ICDValidationError    — raised on Pydantic model validation failure
    - ICDModelAlreadyRegisteredError — raised on duplicate ICD model registration
    - KernelError           — base exception for blanket catch
    - JWTError              — raised on missing/malformed JWT claims
    - ExpiredTokenError     — raised when JWT exp is in the past
    - RevokedTokenError     — raised when JWT jti is revoked
    - PermissionDeniedError — raised when required permissions are not granted
    - RoleNotFoundError     — raised when role is not in PermissionRegistry
    - RevocationCacheError  — raised when revocation cache is unavailable
    - BoundsExceeded        — raised when resource request exceeds budget
    - BudgetNotFoundError   — raised when no budget for (tenant, resource_type)
    - InvalidBudgetError    — raised when budget limit is negative
    - UsageTrackingError    — raised when usage tracker is unavailable
"""

from __future__ import annotations

from holly.kernel.budget_registry import BudgetRegistry
from holly.kernel.exceptions import (
    BoundsExceeded,
    BudgetNotFoundError,
    CanonicalizeError,
    DuplicateRequestError,
    EvalError,
    EvalGateFailure,
    ExpiredTokenError,
    InvalidBudgetError,
    JWTError,
    KernelError,
    PayloadTooLargeError,
    PermissionDeniedError,
    PredicateAlreadyRegisteredError,
    PredicateNotFoundError,
    RedactionError,
    RevocationCacheError,
    RevokedTokenError,
    RoleNotFoundError,
    SchemaNotFoundError,
    SchemaParseError,
    TenantContextError,
    UsageTrackingError,
    ValidationError,
    WALFormatError,
    WALWriteError,
)
from holly.kernel.icd_schema_registry import (
    ICDModelAlreadyRegisteredError,
    ICDSchemaRegistry,
    ICDValidationError,
)
from holly.kernel.k1 import k1_gate, k1_validate
from holly.kernel.k2 import k2_check_permissions, k2_gate
from holly.kernel.k3 import k3_check_bounds, k3_gate
from holly.kernel.k4 import k4_gate, k4_inject_trace
from holly.kernel.k5 import IdempotencyStore, InMemoryIdempotencyStore, k5_gate, k5_generate_key
from holly.kernel.k6 import (
    InMemoryWALBackend,
    WALBackend,
    WALEntry,
    k6_gate,
    k6_write_entry,
    redact,
)
from holly.kernel.k8 import k8_evaluate
from holly.kernel.permission_registry import PermissionRegistry
from holly.kernel.predicate_registry import PredicateRegistry
from holly.kernel.schema_registry import SchemaRegistry

__all__ = [
    "BoundsExceeded",
    "BudgetNotFoundError",
    "BudgetRegistry",
    "CanonicalizeError",
    "DuplicateRequestError",
    "EvalError",
    "EvalGateFailure",
    "ExpiredTokenError",
    "ICDModelAlreadyRegisteredError",
    "ICDSchemaRegistry",
    "ICDValidationError",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "InMemoryWALBackend",
    "InvalidBudgetError",
    "JWTError",
    "KernelError",
    "PayloadTooLargeError",
    "PermissionDeniedError",
    "PermissionRegistry",
    "PredicateAlreadyRegisteredError",
    "PredicateNotFoundError",
    "PredicateRegistry",
    "RedactionError",
    "RevocationCacheError",
    "RevokedTokenError",
    "RoleNotFoundError",
    "SchemaNotFoundError",
    "SchemaParseError",
    "SchemaRegistry",
    "TenantContextError",
    "UsageTrackingError",
    "ValidationError",
    "WALBackend",
    "WALEntry",
    "WALFormatError",
    "WALWriteError",
    "k1_gate",
    "k1_validate",
    "k2_check_permissions",
    "k2_gate",
    "k3_check_bounds",
    "k3_gate",
    "k4_gate",
    "k4_inject_trace",
    "k5_gate",
    "k5_generate_key",
    "k6_gate",
    "k6_write_entry",
    "k8_evaluate",
    "redact",
]
