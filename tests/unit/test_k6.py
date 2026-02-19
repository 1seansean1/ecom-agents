"""Tests for K6 - Durability / WAL (Write-Ahead Log) gate (Task 17.4).

Covers Behavior Spec §1.7 acceptance criteria:

1. Every boundary crossing produces a WAL entry.
2. WAL is append-only (InMemoryWALBackend preserves insertion order; no delete).
3. Sensitive data redacted before write (email, API key, CC, SSN, phone).
4. WAL entries ordered by timestamp.
5. Tenant isolation: entry.tenant_id matches context tenant.
6. Correlation ID link: entry.correlation_id == ctx.corr_id.
7. Failure handling: backend failure raises WALWriteError.

Also tests:
- WALEntry dataclass structure and defaults.
- WALBackend protocol conformance.
- redact() function: each rule fires correctly, keeps last-4 CC digits.
- k6_write_entry() validation (WALFormatError on empty required fields).
- k6_gate() factory integration with KernelContext.
- Property-based tests via hypothesis.
"""

from __future__ import annotations

import itertools
import re
import uuid
from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.kernel.context import KernelContext
from holly.kernel.exceptions import (
    WALFormatError,
    WALWriteError,
)
from holly.kernel.k4 import k4_gate
from holly.kernel.k6 import (
    InMemoryWALBackend,
    WALBackend,
    WALEntry,
    _detect_pii,
    k6_gate,
    k6_write_entry,
    redact,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_CLAIMS = {
    "sub": "user-abc123",
    "tenant_id": "tenant-test",
    "roles": ["viewer", "editor"],
    "exp": 9_999_999_999,
}


def _make_entry(
    *,
    tenant_id: str = "t-001",
    correlation_id: str = "c-001",
    boundary_crossing: str = "core::test",
    caller_user_id: str = "u-001",
    operation_result: str | None = None,
) -> WALEntry:
    """Build a minimal valid WALEntry for use in tests."""
    return WALEntry(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        boundary_crossing=boundary_crossing,
        caller_user_id=caller_user_id,
        caller_roles=["viewer"],
        exit_code=0,
        k1_valid=True,
        k2_authorized=True,
        k3_within_budget=True,
        operation_result=operation_result,
    )


# ---------------------------------------------------------------------------
# TestWALEntryStructure
# ---------------------------------------------------------------------------


class TestWALEntryStructure:
    """WALEntry dataclass: fields, defaults, mutability."""

    def test_required_fields_populated(self) -> None:
        """WALEntry with all required fields stores them correctly."""
        now = datetime.now(UTC)
        entry = WALEntry(
            id="test-id",
            tenant_id="t1",
            correlation_id="c1",
            timestamp=now,
            boundary_crossing="a::b",
            caller_user_id="u1",
            caller_roles=["admin"],
            exit_code=0,
            k1_valid=True,
            k2_authorized=True,
            k3_within_budget=True,
        )
        assert entry.id == "test-id"
        assert entry.tenant_id == "t1"
        assert entry.correlation_id == "c1"
        assert entry.timestamp is now
        assert entry.boundary_crossing == "a::b"
        assert entry.caller_user_id == "u1"
        assert entry.caller_roles == ["admin"]
        assert entry.exit_code == 0

    def test_optional_fields_default_none(self) -> None:
        """Optional K-gate fields default to None."""
        entry = _make_entry()
        assert entry.k1_schema_id is None
        assert entry.k2_required_permissions is None
        assert entry.k2_granted_permissions is None
        assert entry.k3_resource_type is None
        assert entry.k5_idempotency_key is None
        assert entry.k7_confidence_score is None
        assert entry.k7_human_approved is None
        assert entry.k8_eval_passed is None
        assert entry.operation_result is None

    def test_redaction_metadata_defaults(self) -> None:
        """redaction_rules_applied defaults to [] and contains_pii to False."""
        entry = _make_entry()
        assert entry.redaction_rules_applied == []
        assert entry.contains_pii_before_redaction is False

    def test_entry_is_mutable(self) -> None:
        """WALEntry fields can be updated (needed by k6_write_entry redaction phase)."""
        entry = _make_entry(operation_result="original")
        entry.operation_result = "redacted"
        entry.redaction_rules_applied = ["email"]
        entry.contains_pii_before_redaction = True
        assert entry.operation_result == "redacted"
        assert entry.redaction_rules_applied == ["email"]
        assert entry.contains_pii_before_redaction is True

    def test_has_slots(self) -> None:
        """WALEntry uses __slots__ (no __dict__ attribute)."""
        entry = _make_entry()
        assert not hasattr(entry, "__dict__")

    def test_k_gate_optional_fields_stored(self) -> None:
        """Optional K-gate fields are stored when provided."""
        entry = WALEntry(
            id="x",
            tenant_id="t",
            correlation_id="c",
            timestamp=datetime.now(UTC),
            boundary_crossing="b",
            caller_user_id="u",
            caller_roles=[],
            exit_code=1,
            k1_valid=False,
            k2_authorized=False,
            k3_within_budget=False,
            k1_schema_id="icd-007",
            k2_required_permissions=["read"],
            k3_resource_type="tokens",
            k3_budget_limit=1000,
            k5_idempotency_key="abc" * 21,
            k7_confidence_score=0.95,
            k7_human_approved=True,
            k8_eval_passed=False,
            operation_result="some result",
        )
        assert entry.k1_schema_id == "icd-007"
        assert entry.k2_required_permissions == ["read"]
        assert entry.k3_resource_type == "tokens"
        assert entry.k3_budget_limit == 1000
        assert entry.k7_confidence_score == pytest.approx(0.95)
        assert entry.k7_human_approved is True
        assert entry.k8_eval_passed is False


# ---------------------------------------------------------------------------
# TestWALBackend
# ---------------------------------------------------------------------------


class TestWALBackend:
    """WALBackend protocol and InMemoryWALBackend behaviour."""

    def test_protocol_conformance(self) -> None:
        """InMemoryWALBackend satisfies the WALBackend protocol."""
        backend = InMemoryWALBackend()
        assert isinstance(backend, WALBackend)

    def test_append_stores_entry(self) -> None:
        """append() adds the entry to internal list."""
        backend = InMemoryWALBackend()
        entry = _make_entry()
        backend.append(entry)
        assert len(backend.entries) == 1
        assert backend.entries[0] is entry

    def test_entries_ordered_by_insertion(self) -> None:
        """entries property returns entries in insertion order."""
        backend = InMemoryWALBackend()
        e1 = _make_entry(boundary_crossing="step-1")
        e2 = _make_entry(boundary_crossing="step-2")
        e3 = _make_entry(boundary_crossing="step-3")
        backend.append(e1)
        backend.append(e2)
        backend.append(e3)
        names = [e.boundary_crossing for e in backend.entries]
        assert names == ["step-1", "step-2", "step-3"]

    def test_fail_mode_raises_wal_write_error(self) -> None:
        """When _fail is True, append raises WALWriteError."""
        backend = InMemoryWALBackend()
        backend._fail = True
        entry = _make_entry()
        with pytest.raises(WALWriteError):
            backend.append(entry)

    def test_entries_snapshot_not_reference(self) -> None:
        """entries property returns a copy; mutating it does not affect backend."""
        backend = InMemoryWALBackend()
        entry = _make_entry()
        backend.append(entry)
        snapshot = backend.entries
        snapshot.clear()
        assert len(backend.entries) == 1


# ---------------------------------------------------------------------------
# TestRedactionEmail
# ---------------------------------------------------------------------------


class TestRedactionEmail:
    """redact() — email address rule."""

    def test_email_replaced(self) -> None:
        """Standard email address is redacted."""
        result, rules = redact("Contact user@example.com for info.")
        assert "user@example.com" not in result
        assert "[email hidden]" in result
        assert "email" in rules

    def test_email_subdomain(self) -> None:
        """Email with subdomain is redacted."""
        result, rules = redact("alice@mail.corp.internal is the contact.")
        assert "[email hidden]" in result
        assert "email" in rules

    def test_no_email_no_rule(self) -> None:
        """Text without email does not trigger email rule."""
        _, rules = redact("No sensitive data here.")
        assert "email" not in rules

    def test_multiple_emails(self) -> None:
        """Multiple email addresses in same string are all redacted."""
        result, rules = redact("From a@x.com to b@y.org")
        assert "a@x.com" not in result
        assert "b@y.org" not in result
        assert result.count("[email hidden]") == 2
        assert "email" in rules


# ---------------------------------------------------------------------------
# TestRedactionAPIKey
# ---------------------------------------------------------------------------


class TestRedactionAPIKey:
    """redact() — API key / token rule."""

    def test_openai_style_key(self) -> None:
        """sk-... key is redacted."""
        text = "Using key sk-AbCdEfGhIjKlMnOpQrStUvWxYz012345 for auth."
        result, rules = redact(text)
        assert "sk-AbCd" not in result
        assert "[secret redacted]" in result
        assert "api_key" in rules

    def test_bearer_token(self) -> None:
        """Bearer token is redacted."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        text = f"Authorization: Bearer {token}"
        result, rules = redact(text)
        assert token not in result
        assert "[secret redacted]" in result
        assert "api_key" in rules

    def test_generic_api_key_equals(self) -> None:
        """api_key=<value> pattern is redacted."""
        result, rules = redact("config api_key=supersecretvalue123 done")
        assert "supersecretvalue123" not in result
        assert "[secret redacted]" in result
        assert "api_key" in rules

    def test_access_token_pattern(self) -> None:
        """access_token=<value> is redacted."""
        result, rules = redact("access_token=abcdefghijklmnop")
        assert "abcdefghijklmnop" not in result
        assert "api_key" in rules

    def test_no_api_key_no_rule(self) -> None:
        """Text without API key does not trigger api_key rule."""
        _, rules = redact("Normal text without secrets.")
        assert "api_key" not in rules


# ---------------------------------------------------------------------------
# TestRedactionCreditCard
# ---------------------------------------------------------------------------


class TestRedactionCreditCard:
    """redact() — credit card rule (keeps last 4 digits)."""

    def test_cc_hyphen_separated(self) -> None:
        """16-digit hyphen-separated CC is redacted; last 4 preserved."""
        result, rules = redact("Card: 4111-1111-1111-1234")
        assert "4111-1111-1111-1234" not in result
        assert "****-****-****-1234" in result
        assert "credit_card" in rules

    def test_cc_space_separated(self) -> None:
        """16-digit space-separated CC is redacted; last 4 preserved."""
        result, rules = redact("Card 4111 1111 1111 5678 used.")
        assert "****-****-****-5678" in result
        assert "credit_card" in rules

    def test_cc_no_separator(self) -> None:
        """16-digit unseparated CC is redacted."""
        result, rules = redact("4111111111119999")
        assert "****-****-****-9999" in result
        assert "credit_card" in rules

    def test_no_cc_no_rule(self) -> None:
        """Text without CC pattern does not trigger credit_card rule."""
        _, rules = redact("Invoice #1234 paid.")
        assert "credit_card" not in rules


# ---------------------------------------------------------------------------
# TestRedactionPII
# ---------------------------------------------------------------------------


class TestRedactionPII:
    """redact() — SSN and phone number rules."""

    def test_ssn_redacted(self) -> None:
        """SSN pattern NNN-NN-NNNN is redacted."""
        result, rules = redact("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[pii redacted]" in result
        assert "ssn" in rules

    def test_phone_redacted(self) -> None:
        """US phone number is redacted."""
        result, rules = redact("Call 555 123-4567 now.")
        assert "555 123-4567" not in result
        assert "[pii redacted]" in result
        assert "phone" in rules

    def test_phone_with_country_code(self) -> None:
        """Phone with +1 prefix is redacted."""
        result, rules = redact("+1 (800) 555-0199")
        assert "[pii redacted]" in result
        assert "phone" in rules

    def test_no_pii_no_rule(self) -> None:
        """Text without SSN or phone does not trigger pii rules."""
        _, rules = redact("All good here.")
        assert "ssn" not in rules
        assert "phone" not in rules


# ---------------------------------------------------------------------------
# TestRedactionMultiple
# ---------------------------------------------------------------------------


class TestRedactionMultiple:
    """redact() — multiple rules fire in same call."""

    def test_email_and_ssn(self) -> None:
        """Email and SSN both redacted in same string."""
        text = "User bob@example.com has SSN 111-22-3333."
        result, rules = redact(text)
        assert "bob@example.com" not in result
        assert "111-22-3333" not in result
        assert "email" in rules
        assert "ssn" in rules

    def test_all_rules_fire(self) -> None:
        """All five rules fire when all patterns present."""
        text = (
            "Email: a@b.com "
            "Key: sk-AbCdEfGhIjKlMnOpQrStUvWxYz012345 "
            "CC: 4111-1111-1111-0000 "
            "SSN: 987-65-4321 "
            "Phone: 555 123-4567"
        )
        result, rules = redact(text)
        assert "a@b.com" not in result
        assert "sk-AbCd" not in result
        assert "4111-1111-1111-0000" not in result
        assert "987-65-4321" not in result
        assert "555 123-4567" not in result
        assert set(rules) >= {"email", "api_key", "credit_card", "ssn", "phone"}

    def test_clean_text_no_rules(self) -> None:
        """Plaintext with no sensitive data returns unchanged with no rules."""
        text = "The quick brown fox jumps over the lazy dog."
        result, rules = redact(text)
        assert result == text
        assert rules == []


# ---------------------------------------------------------------------------
# TestDetectPII
# ---------------------------------------------------------------------------


class TestDetectPII:
    """_detect_pii() returns True/False correctly."""

    def test_email_detected(self) -> None:
        assert _detect_pii("contact user@example.com") is True

    def test_api_key_detected(self) -> None:
        assert _detect_pii("sk-AbCdEfGhIjKlMnOpQrStUvWxYz012345") is True

    def test_credit_card_detected(self) -> None:
        assert _detect_pii("4111-1111-1111-1234") is True

    def test_ssn_detected(self) -> None:
        assert _detect_pii("SSN: 123-45-6789") is True

    def test_clean_text_not_detected(self) -> None:
        assert _detect_pii("Nothing sensitive here.") is False


# ---------------------------------------------------------------------------
# TestK6WriteEntry
# ---------------------------------------------------------------------------


class TestK6WriteEntry:
    """k6_write_entry() validates, redacts, and appends correctly."""

    def test_valid_entry_appended(self) -> None:
        """Valid entry with no sensitive data is appended to backend."""
        backend = InMemoryWALBackend()
        entry = _make_entry()
        k6_write_entry(entry, backend)
        assert len(backend.entries) == 1
        assert backend.entries[0] is entry

    def test_empty_tenant_id_raises_format_error(self) -> None:
        """Empty tenant_id raises WALFormatError."""
        backend = InMemoryWALBackend()
        entry = _make_entry(tenant_id="")
        with pytest.raises(WALFormatError) as exc_info:
            k6_write_entry(entry, backend)
        assert "tenant_id" in exc_info.value.detail

    def test_empty_correlation_id_raises_format_error(self) -> None:
        """Empty correlation_id raises WALFormatError."""
        backend = InMemoryWALBackend()
        entry = _make_entry(correlation_id="")
        with pytest.raises(WALFormatError) as exc_info:
            k6_write_entry(entry, backend)
        assert "correlation_id" in exc_info.value.detail

    def test_empty_boundary_crossing_raises_format_error(self) -> None:
        """Empty boundary_crossing raises WALFormatError."""
        backend = InMemoryWALBackend()
        entry = _make_entry(boundary_crossing="")
        with pytest.raises(WALFormatError) as exc_info:
            k6_write_entry(entry, backend)
        assert "boundary_crossing" in exc_info.value.detail

    def test_empty_caller_user_id_raises_format_error(self) -> None:
        """Empty caller_user_id raises WALFormatError."""
        backend = InMemoryWALBackend()
        entry = _make_entry(caller_user_id="")
        with pytest.raises(WALFormatError) as exc_info:
            k6_write_entry(entry, backend)
        assert "caller_user_id" in exc_info.value.detail

    def test_operation_result_redacted(self) -> None:
        """Email in operation_result is redacted before append."""
        backend = InMemoryWALBackend()
        entry = _make_entry(operation_result="Error from user@secret.com")
        k6_write_entry(entry, backend)
        persisted = backend.entries[0]
        assert "user@secret.com" not in persisted.operation_result  # type: ignore[operator]
        assert "[email hidden]" in persisted.operation_result  # type: ignore[operator]
        assert "email" in persisted.redaction_rules_applied

    def test_contains_pii_flag_set_before_redaction(self) -> None:
        """contains_pii_before_redaction is True when original had PII."""
        backend = InMemoryWALBackend()
        entry = _make_entry(operation_result="Call 555 123-4567 for help.")
        k6_write_entry(entry, backend)
        assert backend.entries[0].contains_pii_before_redaction is True

    def test_backend_failure_raises_wal_write_error(self) -> None:
        """Backend failure raises WALWriteError."""
        backend = InMemoryWALBackend()
        backend._fail = True
        entry = _make_entry()
        with pytest.raises(WALWriteError):
            k6_write_entry(entry, backend)


# ---------------------------------------------------------------------------
# TestK6Gate
# ---------------------------------------------------------------------------


class TestK6Gate:
    """k6_gate() factory integration with KernelContext."""

    @pytest.mark.asyncio
    async def test_gate_is_callable(self) -> None:
        """k6_gate returns an async callable."""
        import inspect

        backend = InMemoryWALBackend()
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
        )
        assert callable(gate)
        assert inspect.iscoroutinefunction(gate)

    @pytest.mark.asyncio
    async def test_gate_creates_entry_in_backend(self) -> None:
        """Gate appends one entry to backend when fired."""
        backend = InMemoryWALBackend()
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
        )
        async with KernelContext(gates=[k4_gate(_CLAIMS), gate]) as _ctx:
            pass
        assert len(backend.entries) == 1

    @pytest.mark.asyncio
    async def test_gate_stamps_corr_id_from_context(self) -> None:
        """entry.correlation_id == ctx.corr_id after gate fires."""
        backend = InMemoryWALBackend()
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
        )
        async with KernelContext(gates=[k4_gate(_CLAIMS), gate]) as ctx:
            ctx_corr_id = ctx.corr_id
        entry = backend.entries[0]
        assert entry.correlation_id == ctx_corr_id

    @pytest.mark.asyncio
    async def test_gate_stamps_tenant_id_from_context(self) -> None:
        """entry.tenant_id == ctx.tenant_id after gate fires."""
        backend = InMemoryWALBackend()
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
        )
        async with KernelContext(gates=[k4_gate(_CLAIMS), gate]) as ctx:
            ctx_tenant_id = ctx.tenant_id
        entry = backend.entries[0]
        assert entry.tenant_id == ctx_tenant_id

    @pytest.mark.asyncio
    async def test_gate_redacts_operation_result(self) -> None:
        """Gate redacts email in operation_result before persisting."""
        backend = InMemoryWALBackend()
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
            operation_result="Sent to admin@example.com",
        )
        async with KernelContext(gates=[k4_gate(_CLAIMS), gate]):
            pass
        entry = backend.entries[0]
        assert "admin@example.com" not in (entry.operation_result or "")
        assert "[email hidden]" in (entry.operation_result or "")

    @pytest.mark.asyncio
    async def test_gate_backend_failure_raises_wal_write_error(self) -> None:
        """Backend failure during gate raises WALWriteError."""
        backend = InMemoryWALBackend()
        backend._fail = True
        gate = k6_gate(
            boundary_crossing="core::test",
            claims=_CLAIMS,
            backend=backend,
        )
        with pytest.raises(WALWriteError):
            async with KernelContext(gates=[k4_gate(_CLAIMS), gate]):
                pass


# ---------------------------------------------------------------------------
# TestTimestampOrdering
# ---------------------------------------------------------------------------


class TestTimestampOrdering:
    """WAL entries are ordered by timestamp (insertion order)."""

    def test_sequential_entries_ordered(self) -> None:
        """Multiple entries appended in sequence appear in that order."""
        backend = InMemoryWALBackend()
        for i in range(5):
            entry = _make_entry(boundary_crossing=f"step-{i}")
            k6_write_entry(entry, backend)
        crossings = [e.boundary_crossing for e in backend.entries]
        assert crossings == [f"step-{i}" for i in range(5)]

    def test_timestamps_non_decreasing(self) -> None:
        """Entry timestamps are non-decreasing (wall clock monotonic)."""
        backend = InMemoryWALBackend()
        for _ in range(10):
            entry = _make_entry()
            k6_write_entry(entry, backend)
        timestamps = [e.timestamp for e in backend.entries]
        for t1, t2 in itertools.pairwise(timestamps):
            assert t1 <= t2

    def test_correlation_id_links_entry_to_context(self) -> None:
        """correlation_id in entry matches the correlation_id used to build it."""
        backend = InMemoryWALBackend()
        corr_id = str(uuid.uuid4())
        entry = _make_entry(correlation_id=corr_id)
        k6_write_entry(entry, backend)
        assert backend.entries[0].correlation_id == corr_id


# ---------------------------------------------------------------------------
# TestPropertyBased
# ---------------------------------------------------------------------------


class TestPropertyBased:
    """Property-based tests using hypothesis."""

    @given(
        local=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=1,
            max_size=20,
        ),
        domain=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=2,
            max_size=15,
        ),
        tld=st.sampled_from(["com", "org", "net", "io", "co"]),
    )
    @settings(max_examples=30)
    def test_email_always_redacted(self, local: str, domain: str, tld: str) -> None:
        """Emails matching our RFC 5322-simplified pattern are always removed."""
        email = f"{local}@{domain}.{tld}"
        result, rules = redact(f"user is {email} thanks")
        assert email not in result
        assert "email" in rules

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters="@",
            ),
            min_size=1,
            max_size=200,
        ).filter(
            lambda t: not re.search(
                r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", t
            )
        )
    )
    @settings(max_examples=30)
    def test_clean_text_unchanged(self, text: str) -> None:
        """Text with no sensitive patterns is returned unchanged."""
        result, rules = redact(text)
        assert result == text
        assert rules == []

    @given(
        tenant_id=st.text(min_size=1, max_size=40),
        correlation_id=st.text(min_size=1, max_size=40),
        boundary=st.text(min_size=1, max_size=40),
        user_id=st.text(min_size=1, max_size=40),
    )
    @settings(max_examples=30)
    def test_write_entry_populates_backend(
        self,
        tenant_id: str,
        correlation_id: str,
        boundary: str,
        user_id: str,
    ) -> None:
        """k6_write_entry always results in exactly one appended entry."""
        backend = InMemoryWALBackend()
        entry = _make_entry(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            boundary_crossing=boundary,
            caller_user_id=user_id,
        )
        k6_write_entry(entry, backend)
        assert len(backend.entries) == 1

    @given(st.uuids())
    @settings(max_examples=20)
    def test_entry_id_is_valid_uuid4(self, _dummy: object) -> None:
        """Every WALEntry built with uuid.uuid4() has a valid UUID4 id."""
        entry = _make_entry()
        assert _UUID_RE.match(entry.id) is not None
