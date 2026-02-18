"""Tests for holly.kernel.icd_models - Task 5.5.

Coverage:
    - All 49 ICD models validate example payloads (AC)
    - Invalid payloads rejected for representative ICDs
    - register_all_icd_models() registers all 49
    - Property-based: arbitrary valid payloads roundtrip
    - Enum constraints enforced
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from holly.kernel.icd_models import (
    ICD_MODEL_MAP,
    APSTier,
    GoalSpec,
    ICD001Request,
    ICD006Request,
    ICD008Request,
    ICD008Response,
    ICD022Request,
    ICD023Event,
    ICD030Request,
    IntentType,
    LaneType,
    MemoryType,
    SandboxLanguage,
    Severity,
    register_all_icd_models,
)
from holly.kernel.icd_schema_registry import ICDSchemaRegistry


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    ICDSchemaRegistry.clear()
    yield
    ICDSchemaRegistry.clear()


# ── Example payloads for all 49 ICDs ─────────────────────

EXAMPLE_PAYLOADS: dict[str, dict[str, Any]] = {
    "ICD-001": {"method": "POST", "path": "/chat", "content_type": "application/json"},
    "ICD-002": {"method": "POST", "path": "/chat", "headers": {"Authorization": "Bearer tok"}, "source_ip": "10.0.0.1", "request_id": "r1", "tenant_id": "t1"},
    "ICD-003": {"method": "POST", "path": "/chat", "validated_claims": {"sub": "u1", "tenant_id": "t1", "roles": ["user"], "exp": 9999999999}},
    "ICD-004": {"client_id": "holly", "redirect_uri": "https://app/cb", "state": "s1", "code_challenge": "ch"},
    "ICD-005": {"code": "abc", "client_id": "holly", "client_secret": "sec", "redirect_uri": "https://app/cb", "code_verifier": "ver"},
    "ICD-006": {"boundary_id": "b1", "tenant_id": "t1", "user_id": "u1", "operation": "read"},
    "ICD-007": {"boundary_id": "b1", "tenant_id": "t1", "user_id": "u1", "operation": "dispatch"},
    "ICD-008": {"message": "hello", "user_id": "u1", "tenant_id": "t1"},
    "ICD-009": {"intent": "direct_solve", "original_message": "hello", "user_id": "u1", "tenant_id": "t1"},
    "ICD-010": {"goals": [{"level": 5, "predicate": "done"}]},
    "ICD-011": {"tier": "T0", "goals": [{"level": 5}]},
    "ICD-012": {"topology_id": "top1", "goals": []},
    "ICD-013": {"task_id": "task1", "scheduled_time": 0},
    "ICD-014": {"task_id": "task1", "scheduled_time": 1700000000},
    "ICD-015": {"agent_binding": {"agent_id": "a1", "agent_type": "worker", "role": "exec"}},
    "ICD-016": {"max_concurrency": 10},
    "ICD-017": {"max_concurrency": 5},
    "ICD-018": {"max_concurrency": 8},
    "ICD-019": {"tool_name": "code_exec"},
    "ICD-020": {"tool_name": "web_search"},
    "ICD-021": {"task_graph_id": "g1", "node_id": "n1", "tool_name": "t1"},
    "ICD-022": {"code": "print(1)", "language": "python"},
    "ICD-023": {"event_type": "task_started", "source": "engine"},
    "ICD-024": {"event_type": "intent_classified", "source": "core"},
    "ICD-025": {"channel": "agent_trace"},
    "ICD-026": {"message": "request completed"},
    "ICD-027": {"action": "subscribe", "channel": "metrics"},
    "ICD-028": {"prompt": "Summarize this"},
    "ICD-029": {"prompt": "Agent task"},
    "ICD-030": {"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "hi"}]},
    "ICD-031": {"model": "mistral:latest"},
    "ICD-032": {"goal_id": "g1", "tenant_id": "t1", "user_id": "u1"},
    "ICD-033": {"key": "cache:k1"},
    "ICD-034": {"id": "doc1"},
    "ICD-035": {"queue_name": "main_queue_t1", "task_id": "task1"},
    "ICD-036": {"tenant_id": "t1", "message": "log entry"},
    "ICD-037": {"tenant_id": "t1"},
    "ICD-038": {"tenant_id": "t1", "boundary_id": "b1", "operation": "read"},
    "ICD-039": {"workflow_id": "w1", "node_id": "n1"},
    "ICD-040": {"task_id": "t1", "execution_id": "e1"},
    "ICD-041": {"key": "mem:k1"},
    "ICD-042": {"content": "remembered fact"},
    "ICD-043": {"id": "mem_emb_1"},
    "ICD-044": {"secret": "sk-ant-xxx"},
    "ICD-045": {"user": "holly_core", "password": "pw", "host": "localhost"},
    "ICD-046": {"api_key": "key1"},
    "ICD-047": {"keys": [{"kid": "k1", "n": "abc", "e": "AQAB"}]},
    "ICD-048": {"client_id": "holly", "client_secret": "sec", "issuer_url": "https://auth"},
    "ICD-049": {"jti": "j1", "exp": 9999999999},
}


# ── TestAllModelsValidateExamplePayloads ─────────────────


class TestAllModelsValidateExamplePayloads:
    """AC: Models validate example payloads for all 49 ICDs."""

    @pytest.mark.parametrize("icd_id", sorted(ICD_MODEL_MAP.keys()))
    def test_example_payload_validates(self, icd_id: str) -> None:
        model_cls = ICD_MODEL_MAP[icd_id]
        payload = EXAMPLE_PAYLOADS[icd_id]
        instance = model_cls.model_validate(payload)
        assert isinstance(instance, BaseModel)

    def test_all_49_icds_have_models(self) -> None:
        assert len(ICD_MODEL_MAP) == 49

    def test_all_49_icds_have_example_payloads(self) -> None:
        for icd_id in ICD_MODEL_MAP:
            assert icd_id in EXAMPLE_PAYLOADS, f"Missing example for {icd_id}"


# ── TestInvalidPayloadsRejected ──────────────────────────


class TestInvalidPayloadsRejected:
    """Negative tests: invalid payloads must be rejected."""

    def test_icd001_missing_method(self) -> None:
        with pytest.raises(ValidationError):
            ICD001Request.model_validate({"path": "/chat"})

    def test_icd008_missing_message(self) -> None:
        with pytest.raises(ValidationError):
            ICD008Request.model_validate({"user_id": "u1", "tenant_id": "t1"})

    def test_icd008_response_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ICD008Response.model_validate({
                "intent": "direct_solve",
                "confidence": 1.5,
            })

    def test_icd022_invalid_language(self) -> None:
        with pytest.raises(ValidationError):
            ICD022Request.model_validate({
                "code": "x",
                "language": "cobol",
            })

    def test_icd030_missing_model(self) -> None:
        with pytest.raises(ValidationError):
            ICD030Request.model_validate({
                "messages": [{"role": "user", "content": "hi"}],
            })

    def test_goal_spec_level_too_high(self) -> None:
        with pytest.raises(ValidationError):
            GoalSpec.model_validate({"level": 7})

    def test_goal_spec_level_negative(self) -> None:
        with pytest.raises(ValidationError):
            GoalSpec.model_validate({"level": -1})


# ── TestEnumConstraints ──────────────────────────────────


class TestEnumConstraints:
    """Verify enum types enforce valid values."""

    def test_intent_type_values(self) -> None:
        assert set(IntentType) == {IntentType.DIRECT_SOLVE, IntentType.TEAM_SPAWN, IntentType.CLARIFY}

    def test_aps_tier_values(self) -> None:
        assert set(APSTier) == {APSTier.T0, APSTier.T1, APSTier.T2, APSTier.T3}

    def test_lane_type_values(self) -> None:
        assert set(LaneType) == {LaneType.MAIN, LaneType.CRON, LaneType.SUBAGENT}

    def test_severity_values(self) -> None:
        assert len(Severity) == 4

    def test_sandbox_language_values(self) -> None:
        assert set(SandboxLanguage) == {SandboxLanguage.PYTHON, SandboxLanguage.JAVASCRIPT, SandboxLanguage.BASH}

    def test_memory_type_values(self) -> None:
        assert set(MemoryType) == {MemoryType.CONVERSATION, MemoryType.DECISION, MemoryType.FACT}


# ── TestRegisterAllICDModels ─────────────────────────────


class TestRegisterAllICDModels:
    """register_all_icd_models() populates ICDSchemaRegistry."""

    def test_registers_49_models(self) -> None:
        count = register_all_icd_models()
        assert count == 49
        assert len(ICDSchemaRegistry.registered_ids()) == 49

    def test_idempotent_registration(self) -> None:
        register_all_icd_models()
        count2 = register_all_icd_models()
        assert count2 == 0  # already registered

    def test_resolve_after_registration(self) -> None:
        register_all_icd_models()
        for icd_id, model_cls in ICD_MODEL_MAP.items():
            resolved = ICDSchemaRegistry.resolve(icd_id)
            assert resolved is model_cls

    def test_validate_via_registry(self) -> None:
        register_all_icd_models()
        result = ICDSchemaRegistry.validate("ICD-006", {
            "boundary_id": "b1",
            "tenant_id": "t1",
            "user_id": "u1",
            "operation": "read",
        })
        assert isinstance(result, ICD006Request)


# ── TestModelSerialization ───────────────────────────────


class TestModelSerialization:
    """Roundtrip: dict -> model -> dict preserves data."""

    @pytest.mark.parametrize("icd_id", sorted(ICD_MODEL_MAP.keys()))
    def test_roundtrip(self, icd_id: str) -> None:
        model_cls = ICD_MODEL_MAP[icd_id]
        payload = EXAMPLE_PAYLOADS[icd_id]
        instance = model_cls.model_validate(payload)
        dumped = instance.model_dump()
        instance2 = model_cls.model_validate(dumped)
        assert instance == instance2


# ── TestPropertyBased ────────────────────────────────────


class TestPropertyBased:
    """Hypothesis property-based tests."""

    @given(
        method=st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
        path=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=30)
    def test_icd001_arbitrary_methods(self, method: str, path: str) -> None:
        instance = ICD001Request(method=method, path=path)
        assert instance.method == method
        assert instance.path == path

    @given(
        event_type=st.text(min_size=1, max_size=30),
        source=st.text(min_size=1, max_size=30),
        severity=st.sampled_from(list(Severity)),
    )
    @settings(max_examples=30)
    def test_icd023_arbitrary_events(self, event_type: str, source: str, severity: Severity) -> None:
        event = ICD023Event(event_type=event_type, source=source, severity=severity)
        dumped = event.model_dump()
        restored = ICD023Event.model_validate(dumped)
        assert restored.event_type == event_type

    @given(
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        intent=st.sampled_from(list(IntentType)),
    )
    @settings(max_examples=30)
    def test_icd008_response_confidence_range(self, confidence: float, intent: IntentType) -> None:
        resp = ICD008Response(intent=intent, confidence=confidence)
        assert 0.0 <= resp.confidence <= 1.0
