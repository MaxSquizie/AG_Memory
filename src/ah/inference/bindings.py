from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import Ref
from ah.model.operands import BoundVar, VariableSort


@dataclass(slots=True)
class BindingEnvironment:
    """Runtime-only scoped substitution environment.

    ``local_id`` is interpreted inside the current logical scope. A quantifier
    declares its variable in a child environment; declaration shadows any parent
    variable with the same local id, even before the child receives a concrete
    binding. This is required for nested scopes such as ``FORALL $0 ... EXISTS
    $0 ...``.

    Bindings never become AH nodes, never receive activation and disappear with
    the proof scope.
    """

    parent: "BindingEnvironment | None" = None
    _values: dict[int, Ref] = field(default_factory=dict)
    _declared_sorts: dict[int, VariableSort] = field(default_factory=dict)

    @staticmethod
    def _validate_sort(variable: BoundVar, value: Ref) -> None:
        sort = variable.sort
        if sort is VariableSort.UNKNOWN:
            return
        if sort is VariableSort.ENTITY and value.kind.value != "M":
            raise ValueError("ENTITY BoundVar must bind to M")
        if sort in {VariableSort.PROPOSITION, VariableSort.EVENT} and value.kind.value not in {"N", "G"}:
            raise ValueError(f"{sort.value} BoundVar must bind to N or G")
        # TIME is represented canonically by ordinary m. VALUE may also be an m
        # under the current formalism; richer literal values are intentionally not
        # introduced as new AH node kinds here.
        if sort in {VariableSort.TIME, VariableSort.VALUE} and value.kind.value != "M":
            raise ValueError(f"{sort.value} BoundVar must bind to M")

    def declare(self, variable: BoundVar) -> None:
        existing = self._declared_sorts.get(variable.local_id)
        if existing is not None and existing is not variable.sort:
            raise ValueError(
                f"BoundVar ${variable.local_id} already declared as {existing.value}"
            )
        self._declared_sorts[variable.local_id] = variable.sort

    def bind(self, variable: BoundVar, value: Ref) -> None:
        self.declare(variable)
        self._validate_sort(variable, value)
        existing = self._values.get(variable.local_id)
        if existing is not None and existing != value:
            raise ValueError(
                f"BoundVar ${variable.local_id} already bound to {existing.uid}"
            )
        self._values[variable.local_id] = value

    def resolve(self, variable: BoundVar) -> Ref | None:
        value = self._values.get(variable.local_id)
        if value is not None:
            return value
        # A declaration is a lexical scope barrier: an unbound child variable
        # must not accidentally fall through to an outer variable with the same id.
        if variable.local_id in self._declared_sorts:
            return None
        return self.parent.resolve(variable) if self.parent is not None else None

    def is_declared_here(self, variable: BoundVar) -> bool:
        return variable.local_id in self._declared_sorts

    def child(self, *declared: BoundVar) -> "BindingEnvironment":
        env = BindingEnvironment(parent=self)
        for variable in declared:
            env.declare(variable)
        return env

    def copy(self) -> "BindingEnvironment":
        parent_copy = self.parent.copy() if self.parent is not None else None
        return BindingEnvironment(
            parent_copy,
            dict(self._values),
            dict(self._declared_sorts),
        )

    def items(self) -> tuple[tuple[int, Ref], ...]:
        merged: dict[int, Ref] = {}
        if self.parent is not None:
            merged.update(dict(self.parent.items()))
        # Shadowed-but-unbound variables intentionally remove an outer binding.
        for local_id in self._declared_sorts:
            merged.pop(local_id, None)
        merged.update(self._values)
        return tuple(sorted(merged.items()))
