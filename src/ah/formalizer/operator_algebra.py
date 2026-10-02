# -*- coding: utf-8 -*-
"""WP3.1 — Operator algebra table + FunctionRegistry v2 (V7 §6.2/§15): commutativity, argument order, inference rules, prohibitions.

The eight structural operators are declared once with their logical properties; a new operator is a resource declaration, never core
code. ``FunctionRegistryV2`` enforces the write-boundary invariant (an unknown function name is rejected) and produces a *canonical key*
for an application: commutative operators canonicalize by sorting their arguments, while non-commutative ones (IMPLIES) preserve argument
order — so ``AND(a,b) == AND(b,a)`` but ``IMPLIES(p,q) != IMPLIES(q,p)``. Each operator carries its admissible inference rules and its
prohibited inferences; the inference engine (WP3.3) consults this table rather than hard-coding per-operator behavior.

Pure module; no store dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class RegistryReject(Exception):
    """Raised at the write boundary for an unknown function or an arity violation."""


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    arity_min: int
    arity_max: int | None            # None = unbounded
    commutative: bool
    associative: bool = False
    inference_rules: frozenset = field(default_factory=frozenset)
    prohibitions: frozenset = field(default_factory=frozenset)

    @property
    def arg_order_matters(self) -> bool:
        return not self.commutative


# The full operator algebra table (§6.2). Quantifiers (EVERY/SOME/NONE/numeric) are a separate layer — see WP3.2.
OPERATORS: dict[str, OperatorSpec] = {
    "NOT": OperatorSpec("NOT", 1, 1, False, False,
                        inference_rules=frozenset({"DOUBLE_NEGATION"}),
                        prohibitions=frozenset()),
    "AND": OperatorSpec("AND", 2, None, True, True,
                        inference_rules=frozenset({"AND_ELIMINATION", "AND_INTRODUCTION"}),
                        prohibitions=frozenset()),
    "OR": OperatorSpec("OR", 2, None, True, True,
                       inference_rules=frozenset({"OR_ELIMINATION", "OR_INTRODUCTION"}),
                       prohibitions=frozenset()),
    "XOR": OperatorSpec("XOR", 2, None, True, True,
                        inference_rules=frozenset({"XOR_ELIMINATION"}),
                        prohibitions=frozenset()),
    # IMPLIES is NOT commutative: the antecedent/consequent order is semantically load-bearing.
    "IMPLIES": OperatorSpec("IMPLIES", 2, 2, False, False,
                            inference_rules=frozenset({"MODUS_PONENS"}),
                            prohibitions=frozenset({"AFFIRMING_CONSEQUENT", "DENYING_ANTecedent".upper()})),
    "POSSIBLE": OperatorSpec("POSSIBLE", 1, 1, False, False,
                             inference_rules=frozenset({"POSSIBLE_INTRODUCTION"}),
                             prohibitions=frozenset({"POSSIBILITY_TO_NECESSITY"})),
    "NECESSARY": OperatorSpec("NECESSARY", 1, 1, False, False,
                              inference_rules=frozenset({"NECESSARY_ELIMINATION"}),
                              prohibitions=frozenset()),
    # A counterfactual is a distinct modality: it must not be reduced to a material implication.
    "COUNTERFACTUAL": OperatorSpec("COUNTERFACTUAL", 2, 2, False, False,
                                   inference_rules=frozenset(),
                                   prohibitions=frozenset({"TREAT_AS_IMPLIES"})),
    # Association is symmetric (a relation between two terms).
    "ASSOCIATION": OperatorSpec("ASSOCIATION", 2, None, True, True,
                                inference_rules=frozenset({"ASSOCIATION_SYMMETRY"}),
                                prohibitions=frozenset()),
}


class FunctionRegistryV2:
    def __init__(self, operators: dict[str, OperatorSpec] | None = None):
        self.ops = dict(operators) if operators is not None else dict(OPERATORS)

    def register(self, spec: OperatorSpec) -> None:
        """A new operator is a resource declaration; it must name itself and declare its properties."""
        if not spec.name or spec.arity_min < 1:
            raise RegistryReject(f"invalid operator spec {spec!r}")
        self.ops[spec.name] = spec

    def has(self, name: str) -> bool:
        return name in self.ops

    def _check_arity(self, spec: OperatorSpec, n_args: int) -> None:
        if n_args < spec.arity_min or (spec.arity_max is not None and n_args > spec.arity_max):
            raise RegistryReject(f"{spec.name} expects {spec.arity_min}..{spec.arity_max} args, got {n_args}")

    def canonical_key(self, name: str, args) -> tuple:
        """Canonical representation of an application; rejects unknown functions at the write boundary."""
        if name not in self.ops:
            raise RegistryReject(f"unknown function '{name}'")
        spec = self.ops[name]
        a = list(args)
        self._check_arity(spec, len(a))
        if spec.commutative:
            a = sorted(a, key=repr)          # commutative -> order-insensitive canonical form
        return (name, tuple(a))             # non-commutative preserves argument order

    def inferable(self, name: str, rule: str) -> bool:
        if name not in self.ops:
            raise RegistryReject(f"unknown function '{name}'")
        return rule in self.ops[name].inference_rules

    def prohibited(self, name: str, inference: str) -> bool:
        if name not in self.ops:
            raise RegistryReject(f"unknown function '{name}'")
        return inference in self.ops[name].prohibitions


if __name__ == "__main__":  # pragma: no cover - quick sanity
    r = FunctionRegistryV2()
    print(r.canonical_key("AND", ["b", "a"]))
    print(r.canonical_key("IMPLIES", ["p", "q"]))
