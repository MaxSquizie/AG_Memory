from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import Ref

from .bindings import BindingEnvironment


@dataclass(slots=True)
class ProofContext:
    """Runtime-only proof scope.

    Proof contexts are overlays over canonical AH, never a second memory store.
    They may carry temporary assumptions/bindings and local intermediate results,
    but none of those objects receive canonical UIDs merely because they are
    useful during reasoning.
    """

    parent: "ProofContext | None" = None
    bindings: BindingEnvironment = field(default_factory=BindingEnvironment)
    assumptions: tuple[Ref, ...] = ()
    local_derived: tuple[Ref, ...] = ()
    admissibility_filters: tuple[str, ...] = ()

    def child(self) -> "ProofContext":
        return ProofContext(parent=self, bindings=self.bindings.child())

    def visible_assumptions(self) -> tuple[Ref, ...]:
        """Return inherited assumptions in deterministic outer->inner order."""
        inherited = self.parent.visible_assumptions() if self.parent is not None else ()
        out: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for ref in (*inherited, *self.assumptions):
            key = (ref.kind.value, ref.uid)
            if key in seen:
                continue
            seen.add(key)
            out.append(ref)
        return tuple(out)

    def is_counterfactual(self) -> bool:
        if isinstance(self, CounterfactualContext):
            return True
        return self.parent.is_counterfactual() if self.parent is not None else False


@dataclass(slots=True)
class BranchContext(ProofContext):
    """One local proof-by-cases branch.

    ``branch_assumption`` is a scoped premise inherited from an asserted OR. It is
    admissible only in this branch and must never be materialized as an ordinary
    factual assertion.
    """

    branch_assumption: Ref | None = None


@dataclass(slots=True)
class CounterfactualContext(ProofContext):
    """Local counterfactual world overlay.

    Explicit assumptions may suppress incompatible canonical premises/supports
    during this proof only. Canonical AH is neither copied nor mutated.
    ``suppressed_premise_uids`` is a derived runtime cache used to filter
    materialized supports that depend on an overridden premise.
    """

    suppressed_premise_uids: frozenset[str] = frozenset()
    assumed_positive_uids: frozenset[str] = frozenset()
    assumed_negative_refs: tuple[tuple[str, Ref], ...] = ()
