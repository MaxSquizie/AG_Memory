from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ah.model import BoundVar, Operand, Ref, RefKind


OperandValidator = Callable[[tuple[Operand, ...]], None]
Renderer = Callable[[tuple[str, ...]], str]


def _refs_only(operands: tuple[Operand, ...]) -> None:
    if any(not isinstance(item, Ref) for item in operands):
        raise ValueError("Function expects canonical AH references as operands")


def _proposition_refs(operands: tuple[Operand, ...]) -> None:
    _refs_only(operands)
    invalid = [item for item in operands if isinstance(item, Ref) and item.kind not in {RefKind.N, RefKind.G}]
    if invalid:
        kinds = ", ".join(item.kind.value for item in invalid)
        raise ValueError(f"Function expects proposition refs (N/G), got: {kinds}")


def _quantifier(operands: tuple[Operand, ...]) -> None:
    # v0.12.98 progress builds could persist a declaration-only quantifier as
    # ``(BoundVar,)`` while the body representation was still being designed.
    # Keep that shape loadable, but only the two-operand form is executable.
    if len(operands) not in {1, 2}:
        raise ValueError("Quantifier expects BoundVar or (BoundVar, body_ref)")
    variable = operands[0]
    if not isinstance(variable, BoundVar):
        raise ValueError("Quantifier first operand must be BoundVar")
    if len(operands) == 1:
        return
    body = operands[1]
    if not isinstance(body, Ref) or body.kind not in {RefKind.N, RefKind.G}:
        raise ValueError("Quantifier body must reference a proposition/formula (N/G)")


def _render_quantifier(name: str, operands: tuple[str, ...]) -> str:
    # A one-operand form is legacy-loadable only. Rendering it must nevertheless
    # stay total so old snapshots can be inspected without crashing diagnostics.
    if len(operands) == 1:
        return f"{name} {operands[0]}: <UNRESOLVED_BODY>"
    return f"{name} {operands[0]}: ({operands[1]})"


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """Deterministic code contract for one canonical ``g.ID``.

    Registries are machine semantics, not AH memory.  ``aliases`` exist only for
    backward compatibility with already persisted canonical data (notably ``IF``
    from the pre-v4 implementation).  New code should use ``function_id``.
    """

    function_id: str
    min_operands: int
    max_operands: int | None
    renderer: Renderer
    reasoner_handler: str | None = None
    aliases: tuple[str, ...] = ()
    operand_validator: OperandValidator | None = None

    def validate_arity(self, count: int) -> None:
        if count < self.min_operands:
            raise ValueError(f"{self.function_id} expects at least {self.min_operands} operand(s)")
        if self.max_operands is not None and count > self.max_operands:
            raise ValueError(f"{self.function_id} expects at most {self.max_operands} operand(s)")

    def validate_operands(self, operands: tuple[Operand, ...]) -> None:
        self.validate_arity(len(operands))
        if self.operand_validator is not None:
            self.operand_validator(operands)


class FunctionRegistry:
    """Explicit conservative registry for functional/logical ``g`` semantics.

    Unknown function ids are rejected.  This is the code-level counterpart of the
    v4 invariant that a new ``g.ID`` is legal only together with deterministic
    machine semantics; the registry is not a knowledge store and does not carry
    activation or truth values.
    """

    def __init__(self) -> None:
        self._specs: dict[str, FunctionSpec] = {}
        self._aliases: dict[str, str] = {}
        self._register_builtins()

    @staticmethod
    def _key(value: str) -> str:
        key = value.strip().upper()
        if not key:
            raise ValueError("function_id must be non-empty")
        return key

    def _register_builtins(self) -> None:
        # AND/OR are also used by the existing canonical representation of
        # coordinated entity-valued actants.  Therefore their core validator only
        # requires Ref operands; the reasoner applies propositional semantics only
        # when those refs denote N/G expressions.
        self.register(
            FunctionSpec(
                "AND", 2, None,
                lambda xs: " AND ".join(f"({x})" for x in xs),
                reasoner_handler="AND",
                operand_validator=_refs_only,
            )
        )
        self.register(
            FunctionSpec(
                "OR", 2, None,
                lambda xs: " OR ".join(f"({x})" for x in xs),
                reasoner_handler="OR",
                operand_validator=_refs_only,
            )
        )
        # Propositional n-ary XOR means exactly one true alternative.  It is
        # deliberately not parity XOR, matching natural-language exclusive choice.
        self.register(
            FunctionSpec(
                "XOR", 2, None,
                lambda xs: " XOR ".join(f"({x})" for x in xs),
                reasoner_handler="XOR",
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "NOT", 1, 1,
                lambda xs: f"NOT ({xs[0]})",
                reasoner_handler="NOT",
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "FALSE", 1, 1,
                lambda xs: f"FALSE ({xs[0]})",
                reasoner_handler="FALSE",
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "CONTRADICTS", 2, 2,
                lambda xs: f"CONTRADICTS ({xs[0]}, {xs[1]})",
                reasoner_handler="CONTRADICTS",
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "CORRECTS", 2, 2,
                lambda xs: f"CORRECTS ({xs[0]} -> {xs[1]})",
                reasoner_handler="CORRECTS",
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "IMPLIES", 2, 2,
                lambda xs: f"IF ({xs[0]}) THEN ({xs[1]})",
                reasoner_handler="IMPLIES",
                aliases=("IF",),
                operand_validator=_proposition_refs,
            )
        )
        self.register(
            FunctionSpec(
                "FORALL", 1, 2,
                lambda xs: _render_quantifier("FORALL", xs),
                reasoner_handler="FORALL",
                operand_validator=_quantifier,
            )
        )
        self.register(
            FunctionSpec(
                "EXISTS", 1, 2,
                lambda xs: _render_quantifier("EXISTS", xs),
                reasoner_handler="EXISTS",
                operand_validator=_quantifier,
            )
        )
        for temporal_id in ("START", "STOP", "CONTINUE", "AGAIN", "NO_LONGER"):
            self.register(
                FunctionSpec(
                    temporal_id, 1, 1,
                    lambda xs, name=temporal_id: f"{name} ({xs[0]})",
                    reasoner_handler=temporal_id,
                    operand_validator=_proposition_refs,
                )
            )

    def register(self, spec: FunctionSpec) -> None:
        canonical = self._key(spec.function_id)
        if canonical in self._specs or canonical in self._aliases:
            raise ValueError(f"Function already registered: {canonical}")
        aliases = tuple(self._key(item) for item in spec.aliases)
        if len(set(aliases)) != len(aliases):
            raise ValueError(f"Duplicate alias in FunctionSpec {canonical}")
        for alias in aliases:
            if alias in self._specs or alias in self._aliases or alias == canonical:
                raise ValueError(f"Function alias already registered: {alias}")
        normalized = FunctionSpec(
            canonical,
            spec.min_operands,
            spec.max_operands,
            spec.renderer,
            reasoner_handler=(spec.reasoner_handler.upper() if spec.reasoner_handler else None),
            aliases=aliases,
            operand_validator=spec.operand_validator,
        )
        self._specs[canonical] = normalized
        for alias in aliases:
            self._aliases[alias] = canonical

    def canonical_id(self, function_id: str) -> str:
        key = self._key(function_id)
        if key in self._specs:
            return key
        try:
            return self._aliases[key]
        except KeyError as exc:
            raise KeyError(f"No deterministic FunctionRegistry handler for {function_id!r}") from exc

    def get(self, function_id: str) -> FunctionSpec:
        return self._specs[self.canonical_id(function_id)]

    def validate(self, function_id: str, operands: tuple[Operand, ...]) -> FunctionSpec:
        spec = self.get(function_id)
        spec.validate_operands(operands)
        return spec

    def render(self, function_id: str, operands: tuple[str, ...]) -> str:
        spec = self.get(function_id)
        spec.validate_arity(len(operands))
        return spec.renderer(operands)

    def reasoner_handler(self, function_id: str) -> str | None:
        return self.get(function_id).reasoner_handler

    def items(self) -> tuple[FunctionSpec, ...]:
        return tuple(self._specs[key] for key in sorted(self._specs))
