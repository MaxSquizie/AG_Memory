from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Ref


class VariableSort(str, Enum):
    ENTITY = "ENTITY"
    PROPOSITION = "PROPOSITION"
    TIME = "TIME"
    VALUE = "VALUE"
    EVENT = "EVENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BoundVar:
    """Scoped variable descriptor used inside canonical logical formulae.

    Bound variables are not AH nodes, never receive global UIDs and do not own
    activation state. ``local_id`` is meaningful only inside the owning logical
    scope/formula.
    """

    local_id: int
    sort: VariableSort = VariableSort.UNKNOWN

    def __post_init__(self) -> None:
        if self.local_id < 0:
            raise ValueError("BoundVar.local_id must be >= 0")


Operand = Ref | BoundVar
