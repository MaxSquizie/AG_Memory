from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from ah.model import ActantRole


@dataclass(frozen=True, slots=True)
class InferenceSchema:
    """Deterministic inference properties for one canonical relation/predicate id.

    The schema is code metadata, not AH content. Absence of a property means the
    reasoner must not infer it from the surface name.
    """

    canonical_id: str
    transitive: bool = False
    symmetric: bool = False
    asymmetric: bool = False
    reflexive: bool = False
    irreflexive: bool = False
    functional: bool = False
    # For predicate T schemas, FUNCTIONAL is only operational when the output
    # slot is explicit.  All other filled roles form the deterministic key.
    # Relation L schemas may keep this None because their endpoint semantics are
    # handled separately by relation-specific reasoners.
    functional_role: ActantRole | None = None
    inverse_of: str | None = None
    rule_handlers: tuple[str, ...] = ()


class InferenceSchemaRegistry:
    """Explicit conservative-by-default registry used by the reasoner.

    Unknown ids receive an empty schema. This deliberately prevents hidden
    semantic guessing from relation names.
    """

    def __init__(self, schemas: Iterable[InferenceSchema] = ()) -> None:
        self._schemas: dict[str, InferenceSchema] = {}
        for schema in schemas:
            self.register(schema)

    @classmethod
    def default(cls) -> "InferenceSchemaRegistry":
        return cls(
            (
                InferenceSchema("IS-A", transitive=True, asymmetric=True, rule_handlers=("TRANSITIVITY",)),
                InferenceSchema("FOLLOW", transitive=True, asymmetric=True, rule_handlers=("TRANSITIVITY",)),
                InferenceSchema("CAUSE", asymmetric=True, rule_handlers=("CAUSE_MP", "CAUSE_PATH")),
                InferenceSchema("BEFORE", transitive=True, asymmetric=True, rule_handlers=("TRANSITIVITY",)),
                InferenceSchema("AFTER", transitive=True, asymmetric=True, rule_handlers=("TRANSITIVITY",)),
                InferenceSchema("OVERLAP", symmetric=True),
                InferenceSchema("CONTAINS", transitive=True, asymmetric=True, rule_handlers=("TRANSITIVITY",)),
            )
        )

    @staticmethod
    def _key(canonical_id: str) -> str:
        value = canonical_id.strip().upper()
        if not value:
            raise ValueError("canonical_id must be non-empty")
        return value

    def register(self, schema: InferenceSchema) -> None:
        key = self._key(schema.canonical_id)
        self._schemas[key] = InferenceSchema(
            canonical_id=key,
            transitive=schema.transitive,
            symmetric=schema.symmetric,
            asymmetric=schema.asymmetric,
            reflexive=schema.reflexive,
            irreflexive=schema.irreflexive,
            functional=schema.functional,
            functional_role=schema.functional_role,
            inverse_of=(schema.inverse_of.upper() if schema.inverse_of else None),
            rule_handlers=tuple(handler.upper() for handler in schema.rule_handlers),
        )

    def get(self, canonical_id: str) -> InferenceSchema:
        key = self._key(canonical_id)
        return self._schemas.get(key, InferenceSchema(key))

    def is_transitive(self, canonical_id: str) -> bool:
        return self.get(canonical_id).transitive

    def is_functional(self, canonical_id: str) -> bool:
        return self.get(canonical_id).functional

    def has_handler(self, canonical_id: str, handler: str) -> bool:
        return handler.strip().upper() in self.get(canonical_id).rule_handlers

    def items(self) -> tuple[InferenceSchema, ...]:
        return tuple(self._schemas[key] for key in sorted(self._schemas))
