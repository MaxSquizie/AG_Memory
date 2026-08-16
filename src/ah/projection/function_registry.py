from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    function_id: str
    min_operands: int
    max_operands: int | None
    renderer: Callable[[tuple[str, ...]], str]

    def validate_arity(self, count: int) -> None:
        if count < self.min_operands:
            raise ValueError(f"{self.function_id} expects at least {self.min_operands} operand(s)")
        if self.max_operands is not None and count > self.max_operands:
            raise ValueError(f"{self.function_id} expects at most {self.max_operands} operand(s)")


class FunctionRegistry:
    """Deterministic semantics for g.ID.

    The LLM never has to guess what a raw function enum means. The registry is a
    program-owned mapping from canonical g.ID to a stable semantic projection.
    """

    def __init__(self) -> None:
        self._specs: dict[str, FunctionSpec] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self.register(FunctionSpec("AND", 2, None, lambda xs: " AND ".join(f"({x})" for x in xs)))
        self.register(FunctionSpec("OR", 2, None, lambda xs: " OR ".join(f"({x})" for x in xs)))
        self.register(FunctionSpec("FALSE", 1, 1, lambda xs: f"NOT ({xs[0]})"))
        self.register(FunctionSpec("NOT", 1, 1, lambda xs: f"NOT ({xs[0]})"))
        self.register(FunctionSpec("IF", 2, 2, lambda xs: f"IF ({xs[0]}) THEN ({xs[1]})"))

    def register(self, spec: FunctionSpec) -> None:
        key = spec.function_id.strip().upper()
        if not key:
            raise ValueError("function_id must be non-empty")
        if key in self._specs:
            raise ValueError(f"Function already registered: {key}")
        self._specs[key] = FunctionSpec(key, spec.min_operands, spec.max_operands, spec.renderer)

    def get(self, function_id: str) -> FunctionSpec:
        key = function_id.strip().upper()
        try:
            return self._specs[key]
        except KeyError as exc:
            raise KeyError(f"No deterministic FunctionRegistry handler for {function_id!r}") from exc

    def render(self, function_id: str, operands: tuple[str, ...]) -> str:
        spec = self.get(function_id)
        spec.validate_arity(len(operands))
        return spec.renderer(operands)
