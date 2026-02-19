"""Tests for contract fixture generator (Task 8.3).

Property-based and parametric tests verifying that the fixture
generator produces valid/invalid payloads for all 49 ICD contracts.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from holly.kernel.contract_fixtures import (
    ContractFixtureGenerator,
    generate_invalid_payloads,
    generate_valid_payload,
    hypothesis_strategy,
)
from holly.kernel.icd_models import ICD_MODEL_MAP

# ── Shared fixtures ─────────────────────────────────────────

ALL_ICD_IDS = sorted(ICD_MODEL_MAP.keys())

generator = ContractFixtureGenerator()


# ── TestMinimalValidPayloads ────────────────────────────────


class TestMinimalValidPayloads:
    """Minimal (required-only) payloads must validate for all 49 ICDs."""

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_minimal_payload_validates(self, icd_id: str) -> None:
        payload = generate_valid_payload(icd_id, full=False)
        model_cls = ICD_MODEL_MAP[icd_id]
        instance = model_cls.model_validate(payload)
        assert isinstance(instance, BaseModel)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_minimal_payload_roundtrips(self, icd_id: str) -> None:
        payload = generate_valid_payload(icd_id, full=False)
        model_cls = ICD_MODEL_MAP[icd_id]
        instance = model_cls.model_validate(payload)
        dumped = instance.model_dump()
        instance2 = model_cls.model_validate(dumped)
        assert instance == instance2


# ── TestFullValidPayloads ───────────────────────────────────


class TestFullValidPayloads:
    """Fully-populated payloads must validate for all 49 ICDs."""

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_full_payload_validates(self, icd_id: str) -> None:
        payload = generate_valid_payload(icd_id, full=True)
        model_cls = ICD_MODEL_MAP[icd_id]
        instance = model_cls.model_validate(payload)
        assert isinstance(instance, BaseModel)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_full_payload_populates_optional_fields(self, icd_id: str) -> None:
        """Full payload should have more keys than minimal."""
        minimal = generate_valid_payload(icd_id, full=False)
        full = generate_valid_payload(icd_id, full=True)
        # Full should have at least as many keys.
        assert len(full) >= len(minimal)


# ── TestInvalidPayloads ─────────────────────────────────────


class TestInvalidPayloads:
    """Invalid payloads must be rejected by the model."""

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_has_invalid_payloads(self, icd_id: str) -> None:
        """Every ICD must produce at least one invalid payload."""
        invalids = generate_invalid_payloads(icd_id)
        assert len(invalids) > 0, f"{icd_id} produced no invalid payloads"

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_missing_required_rejected(self, icd_id: str) -> None:
        """Payloads missing required fields must raise ValidationError."""
        model_cls = ICD_MODEL_MAP[icd_id]
        invalids = generate_invalid_payloads(icd_id)
        missing_cases = [
            (desc, p) for desc, p in invalids if desc.startswith("missing_required_")
        ]
        for _desc, payload in missing_cases:
            with pytest.raises(ValidationError, match=r"Field required|field required"):
                model_cls.model_validate(payload)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_constraint_violations_rejected(self, icd_id: str) -> None:
        """Payloads violating ge/le constraints must raise ValidationError."""
        model_cls = ICD_MODEL_MAP[icd_id]
        invalids = generate_invalid_payloads(icd_id)
        constraint_cases = [
            (desc, p)
            for desc, p in invalids
            if desc.startswith("below_min_") or desc.startswith("above_max_")
        ]
        for _desc, payload in constraint_cases:
            with pytest.raises(ValidationError):
                model_cls.model_validate(payload)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_invalid_enum_rejected(self, icd_id: str) -> None:
        """Payloads with invalid enum values must raise ValidationError."""
        model_cls = ICD_MODEL_MAP[icd_id]
        invalids = generate_invalid_payloads(icd_id)
        enum_cases = [
            (desc, p) for desc, p in invalids if desc.startswith("invalid_enum_")
        ]
        for _desc, payload in enum_cases:
            with pytest.raises(ValidationError):
                model_cls.model_validate(payload)


# ── TestHypothesisStrategies ────────────────────────────────


class TestHypothesisStrategies:
    """Hypothesis strategies must produce valid payloads."""

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=5000,
    )
    @given(data=st.data())
    def test_strategy_produces_valid_payloads(
        self, icd_id: str, data: Any,
    ) -> None:
        strat = hypothesis_strategy(icd_id)
        payload = data.draw(strat)
        model_cls = ICD_MODEL_MAP[icd_id]
        instance = model_cls.model_validate(payload)
        assert isinstance(instance, BaseModel)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=5000,
    )
    @given(data=st.data())
    def test_strategy_payloads_roundtrip(
        self, icd_id: str, data: Any,
    ) -> None:
        strat = hypothesis_strategy(icd_id)
        payload = data.draw(strat)
        model_cls = ICD_MODEL_MAP[icd_id]
        instance = model_cls.model_validate(payload)
        dumped = instance.model_dump()
        instance2 = model_cls.model_validate(dumped)
        assert instance == instance2


# ── TestContractFixtureGenerator ────────────────────────────


class TestContractFixtureGenerator:
    """Test the ContractFixtureGenerator class API."""

    def test_icd_count(self) -> None:
        assert generator.icd_count == 49

    def test_all_icd_ids_sorted(self) -> None:
        ids = generator.all_icd_ids
        assert ids == sorted(ids)
        assert len(ids) == 49

    def test_model_for_returns_basemodel_subclass(self) -> None:
        model = generator.model_for("ICD-001")
        assert issubclass(model, BaseModel)

    def test_model_for_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            generator.model_for("ICD-999")

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_validate_payload_accepts_valid(self, icd_id: str) -> None:
        payload = generator.valid_payload(icd_id, full=True)
        instance = generator.validate_payload(icd_id, payload)
        assert isinstance(instance, BaseModel)

    @pytest.mark.parametrize("icd_id", ALL_ICD_IDS)
    def test_validate_payload_rejects_empty(self, icd_id: str) -> None:
        model_cls = generator.model_for(icd_id)
        required_fields = [
            name
            for name, fi in model_cls.model_fields.items()
            if fi.is_required()
        ]
        if required_fields:
            with pytest.raises(ValidationError):
                generator.validate_payload(icd_id, {})


# ── TestCoverage ────────────────────────────────────────────


class TestCoverage:
    """Ensure full ICD catalogue coverage."""

    def test_all_49_icds_covered(self) -> None:
        """Fixture generator must cover exactly 49 ICDs."""
        assert generator.icd_count == 49

    def test_valid_payload_for_every_icd(self) -> None:
        """Every ICD must produce a validating minimal payload."""
        for icd_id in ALL_ICD_IDS:
            payload = generator.valid_payload(icd_id)
            instance = generator.validate_payload(icd_id, payload)
            assert instance is not None

    def test_invalid_payloads_for_every_icd(self) -> None:
        """Every ICD must produce at least one invalid payload."""
        for icd_id in ALL_ICD_IDS:
            invalids = generator.invalid_payloads(icd_id)
            assert len(invalids) > 0, f"{icd_id}: no invalid payloads"

    def test_strategy_for_every_icd(self) -> None:
        """Every ICD must have a buildable Hypothesis strategy."""
        for icd_id in ALL_ICD_IDS:
            strat = generator.strategy(icd_id)
            assert strat is not None

    def test_total_invalid_payload_count(self) -> None:
        """Sanity-check: 49 ICDs should produce many invalid payloads."""
        total = sum(
            len(generator.invalid_payloads(icd_id)) for icd_id in ALL_ICD_IDS
        )
        # At minimum each ICD has at least 1 required field → 1 missing case.
        assert total >= 49, f"Only {total} invalid payloads across 49 ICDs"
