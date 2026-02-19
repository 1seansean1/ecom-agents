"""Contract fixture generator for ICD boundary payloads.

Task 8.3 — Write contract fixture generator.

Introspects Pydantic model schemas from ``ICD_MODEL_MAP`` to produce:

* **Valid payloads** (minimal and fully-populated)
* **Invalid payloads** (missing required fields, constraint violations)
* **Hypothesis strategies** for property-based testing

Every boundary crossing in the 49-ICD catalogue has a deterministic
valid/invalid fixture set and a composable Hypothesis strategy.
"""

from __future__ import annotations

import string
from enum import StrEnum
from typing import Any, get_args, get_origin

from hypothesis import strategies as st
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from holly.kernel.icd_models import ICD_MODEL_MAP

# ═══════════════════════════════════════════════════════════
# Type introspection helpers
# ═══════════════════════════════════════════════════════════


def _is_optional(annotation: Any) -> bool:
    """Return True if annotation is ``T | None``."""
    origin = get_origin(annotation)
    if origin is not type(int | str):  # types.UnionType
        return False
    args = get_args(annotation)
    return type(None) in args


def _unwrap_optional(annotation: Any) -> Any:
    """Strip ``None`` from a union type, returning the inner type."""
    args = get_args(annotation)
    non_none = [a for a in args if a is not type(None)]
    return non_none[0] if len(non_none) == 1 else annotation


def _is_str_enum(annotation: Any) -> bool:
    """Return True if *annotation* is a StrEnum subclass."""
    try:
        return isinstance(annotation, type) and issubclass(annotation, StrEnum)
    except TypeError:
        return False


def _is_pydantic_model(annotation: Any) -> bool:
    """Return True if *annotation* is a Pydantic BaseModel subclass."""
    try:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)
    except TypeError:
        return False


# ═══════════════════════════════════════════════════════════
# Deterministic payload generation
# ═══════════════════════════════════════════════════════════


def _default_value_for_type(
    annotation: Any,
    field_info: FieldInfo,
    *,
    full: bool = False,
) -> Any:
    """Produce a deterministic valid value for a Pydantic field.

    Parameters
    ----------
    annotation:
        The field's resolved type annotation.
    field_info:
        The Pydantic ``FieldInfo`` for constraint extraction.
    full:
        If True, populate optional/defaulted fields with non-default
        values.
    """
    # Handle Optional[T] — generate inner type value.
    if _is_optional(annotation):
        if not full:
            return None
        inner = _unwrap_optional(annotation)
        return _default_value_for_type(inner, field_info, full=full)

    # StrEnum — first member.
    if _is_str_enum(annotation):
        return next(iter(annotation)).value

    # Nested Pydantic model — recurse.
    if _is_pydantic_model(annotation):
        return generate_valid_payload_from_model(annotation, full=full)

    origin = get_origin(annotation)

    # list[T]
    if origin is list:
        if not full:
            return []
        args = get_args(annotation)
        if args:
            elem = args[0]
            if _is_pydantic_model(elem):
                return [generate_valid_payload_from_model(elem, full=full)]
            if _is_str_enum(elem):
                return [next(iter(elem)).value]
            # list[dict[str, Any]] — common in ICD models.
            elem_origin = get_origin(elem)
            if elem_origin is dict:
                return [{"key": "value"}]
            if elem is str:
                return ["item"]
            if elem is float:
                return [0.5]
            if elem is int:
                return [0]
        return [{"key": "value"}]

    # dict[str, T]
    if origin is dict:
        if not full:
            return {}
        return {"key": "value"}

    # Scalars.
    if annotation is str:
        return "test-value"

    if annotation is int:
        ge = _extract_constraint(field_info, "ge")
        le = _extract_constraint(field_info, "le")
        if ge is not None and le is not None:
            return (ge + le) // 2
        if ge is not None:
            return ge
        return 0

    if annotation is float:
        ge = _extract_constraint(field_info, "ge")
        le = _extract_constraint(field_info, "le")
        if ge is not None and le is not None:
            return (ge + le) / 2.0
        if ge is not None:
            return ge + 0.5
        return 0.0

    if annotation is bool:
        return False

    # Any / unknown — return empty dict.
    return {} if full else None


def _extract_constraint(field_info: FieldInfo, name: str) -> Any:
    """Extract a numeric constraint (ge, le, gt, lt) from FieldInfo metadata."""
    # Direct attribute (Pydantic v1 style).
    val = getattr(field_info, name, None)
    if val is not None:
        return val
    # Metadata annotations (Pydantic v2 style).
    for m in field_info.metadata:
        val = getattr(m, name, None)
        if val is not None:
            return val
    return None


def generate_valid_payload_from_model(
    model_cls: type[BaseModel],
    *,
    full: bool = False,
) -> dict[str, Any]:
    """Generate a deterministic valid payload dict for *model_cls*.

    Parameters
    ----------
    model_cls:
        A Pydantic BaseModel subclass.
    full:
        If False (default), produce minimal payload — only required
        fields.  If True, populate all fields with non-default values.
    """
    payload: dict[str, Any] = {}
    for name, field_info in model_cls.model_fields.items():
        has_default = field_info.default is not None or field_info.default_factory is not None
        is_required = field_info.is_required()

        if not full and not is_required and has_default:
            continue

        annotation = field_info.annotation
        payload[name] = _default_value_for_type(
            annotation, field_info, full=full,
        )
    return payload


def generate_valid_payload(icd_id: str, *, full: bool = False) -> dict[str, Any]:
    """Generate a valid payload for the given ICD ID.

    Parameters
    ----------
    icd_id:
        ICD identifier (e.g. ``"ICD-001"``).
    full:
        If True, populate all fields.

    Raises
    ------
    KeyError:
        If *icd_id* is not in ``ICD_MODEL_MAP``.
    """
    model_cls = ICD_MODEL_MAP[icd_id]
    return generate_valid_payload_from_model(model_cls, full=full)


# ═══════════════════════════════════════════════════════════
# Invalid payload generation
# ═══════════════════════════════════════════════════════════


def generate_invalid_payloads(icd_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Generate a catalogue of invalid payloads for *icd_id*.

    Returns a list of ``(description, payload)`` tuples.  Each payload
    violates exactly one constraint:

    * Missing each required field.
    * Type mismatch (string where int expected).
    * Out-of-range values for constrained fields.

    Raises
    ------
    KeyError:
        If *icd_id* is not in ``ICD_MODEL_MAP``.
    """
    model_cls = ICD_MODEL_MAP[icd_id]
    base = generate_valid_payload_from_model(model_cls, full=True)
    invalids: list[tuple[str, dict[str, Any]]] = []

    for name, field_info in model_cls.model_fields.items():
        annotation = field_info.annotation

        # 1. Missing required field.
        if field_info.is_required():
            without = {k: v for k, v in base.items() if k != name}
            invalids.append((f"missing_required_{name}", without))

        # 2. Type mismatch.
        if annotation is str or (_is_optional(annotation) and _unwrap_optional(annotation) is str):
            wrong = {**base, name: 12345}
            invalids.append((f"type_mismatch_{name}_int_for_str", wrong))
        elif annotation is int or (_is_optional(annotation) and _unwrap_optional(annotation) is int):
            wrong = {**base, name: "not_an_int"}
            invalids.append((f"type_mismatch_{name}_str_for_int", wrong))

        # 3. Constraint violations.
        ge = _extract_constraint(field_info, "ge")
        le = _extract_constraint(field_info, "le")
        if ge is not None:
            # Value below minimum.
            below_val = ge - 1 if isinstance(ge, int) else ge - 0.1
            wrong = {**base, name: below_val}
            invalids.append((f"below_min_{name}", wrong))
        if le is not None:
            # Value above maximum.
            above_val = le + 1 if isinstance(le, int) else le + 0.1
            wrong = {**base, name: above_val}
            invalids.append((f"above_max_{name}", wrong))

        # 4. Wrong enum value.
        if _is_str_enum(annotation):
            wrong = {**base, name: "__INVALID_ENUM_VALUE__"}
            invalids.append((f"invalid_enum_{name}", wrong))

    return invalids


# ═══════════════════════════════════════════════════════════
# Hypothesis strategy generation
# ═══════════════════════════════════════════════════════════

# Alphabet for generated strings — printable ASCII minus problematic chars.
_SAFE_ALPHABET = string.ascii_letters + string.digits + "-_."


_ANY_STRATEGY: st.SearchStrategy[Any] = st.one_of(
    st.none(),
    st.text(_SAFE_ALPHABET, min_size=0, max_size=15),
    st.integers(min_value=-100, max_value=100),
    st.dictionaries(
        st.text(_SAFE_ALPHABET, min_size=1, max_size=5),
        st.text(_SAFE_ALPHABET, min_size=0, max_size=10),
        min_size=0,
        max_size=2,
    ),
)


def _strategy_for_type(
    annotation: Any,
    field_info: FieldInfo,
) -> st.SearchStrategy[Any]:
    """Build a Hypothesis strategy producing valid values for *annotation*."""
    # typing.Any — not a real type, produce mixed values.
    if annotation is Any:
        return _ANY_STRATEGY

    # Optional[T] — either None or inner type.
    if _is_optional(annotation):
        inner = _unwrap_optional(annotation)
        return st.one_of(st.none(), _strategy_for_type(inner, field_info))

    # StrEnum — sample from members.
    if _is_str_enum(annotation):
        return st.sampled_from(list(annotation))

    # Nested Pydantic model — build recursively.
    if _is_pydantic_model(annotation):
        return hypothesis_strategy_for_model(annotation)

    origin = get_origin(annotation)

    # list[T]
    if origin is list:
        args = get_args(annotation)
        if args:
            elem_info = FieldInfo(annotation=args[0])
            elem_strategy = _strategy_for_type(args[0], elem_info)
            return st.lists(elem_strategy, min_size=0, max_size=3)
        return st.just([])

    # dict[str, T]
    if origin is dict:
        args = get_args(annotation)
        if args and len(args) >= 2:
            key_strat = st.text(_SAFE_ALPHABET, min_size=1, max_size=10)
            val_strat = _strategy_for_type(args[1], FieldInfo(annotation=args[1]))
            return st.dictionaries(key_strat, val_strat, min_size=0, max_size=3)
        return st.just({})

    # Scalars.
    if annotation is str:
        return st.text(_SAFE_ALPHABET, min_size=1, max_size=30)

    if annotation is int:
        ge = _extract_constraint(field_info, "ge")
        le = _extract_constraint(field_info, "le")
        min_val = ge if ge is not None else -1_000_000
        max_val = le if le is not None else 1_000_000
        return st.integers(min_value=int(min_val), max_value=int(max_val))

    if annotation is float:
        ge = _extract_constraint(field_info, "ge")
        le = _extract_constraint(field_info, "le")
        min_val = ge if ge is not None else -1e6
        max_val = le if le is not None else 1e6
        return st.floats(
            min_value=float(min_val),
            max_value=float(max_val),
            allow_nan=False,
            allow_infinity=False,
        )

    if annotation is bool:
        return st.booleans()

    # Any / fallback — small text or None.
    return st.one_of(
        st.none(),
        st.text(_SAFE_ALPHABET, min_size=0, max_size=15),
        st.integers(min_value=-100, max_value=100),
    )


def hypothesis_strategy_for_model(
    model_cls: type[BaseModel],
) -> st.SearchStrategy[dict[str, Any]]:
    """Build a Hypothesis strategy producing valid payload dicts.

    The strategy generates dicts that should pass
    ``model_cls.model_validate()``.
    """
    field_strategies: dict[str, st.SearchStrategy[Any]] = {}
    for name, field_info in model_cls.model_fields.items():
        annotation = field_info.annotation
        field_strategies[name] = _strategy_for_type(annotation, field_info)

    return st.fixed_dictionaries(field_strategies)


def hypothesis_strategy(icd_id: str) -> st.SearchStrategy[dict[str, Any]]:
    """Return a Hypothesis strategy for the given ICD ID.

    Raises
    ------
    KeyError:
        If *icd_id* is not in ``ICD_MODEL_MAP``.
    """
    model_cls = ICD_MODEL_MAP[icd_id]
    return hypothesis_strategy_for_model(model_cls)


# ═══════════════════════════════════════════════════════════
# ContractFixtureGenerator — unified API
# ═══════════════════════════════════════════════════════════


class ContractFixtureGenerator:
    """Unified generator for ICD contract test fixtures.

    Wraps the module-level functions with a cached model map and
    provides a convenience ``all_icd_ids`` property.
    """

    __slots__ = ("_model_map",)

    def __init__(
        self,
        model_map: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self._model_map = model_map or ICD_MODEL_MAP

    @property
    def all_icd_ids(self) -> list[str]:
        """Return sorted list of all ICD IDs."""
        return sorted(self._model_map.keys())

    @property
    def icd_count(self) -> int:
        """Number of ICDs covered."""
        return len(self._model_map)

    def model_for(self, icd_id: str) -> type[BaseModel]:
        """Resolve the Pydantic model class for *icd_id*."""
        return self._model_map[icd_id]

    def valid_payload(
        self, icd_id: str, *, full: bool = False,
    ) -> dict[str, Any]:
        """Generate a valid payload for *icd_id*."""
        model_cls = self._model_map[icd_id]
        return generate_valid_payload_from_model(model_cls, full=full)

    def invalid_payloads(
        self, icd_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Generate invalid payloads for *icd_id*."""
        return generate_invalid_payloads(icd_id)

    def strategy(
        self, icd_id: str,
    ) -> st.SearchStrategy[dict[str, Any]]:
        """Return a Hypothesis strategy for *icd_id*."""
        model_cls = self._model_map[icd_id]
        return hypothesis_strategy_for_model(model_cls)

    def validate_payload(
        self, icd_id: str, payload: dict[str, Any],
    ) -> BaseModel:
        """Validate *payload* against the model for *icd_id*.

        Returns the validated model instance.

        Raises
        ------
        pydantic.ValidationError:
            If *payload* is invalid.
        """
        model_cls = self._model_map[icd_id]
        return model_cls.model_validate(payload)
