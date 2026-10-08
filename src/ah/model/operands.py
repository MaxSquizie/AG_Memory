from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

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


@dataclass(frozen=True, slots=True)
class TimeLiteral:
    """Closed temporal anchor inside G, with no UID or activation state."""

    bounds: tuple[float, ...]

    def __post_init__(self) -> None:
        try:
            valid=(isinstance(self.bounds,tuple) and len(self.bounds) in {1,2}
                   and all(type(x) in {int,float} and math.isfinite(x) for x in self.bounds)
                   and (len(self.bounds)==1 or self.bounds[0]<=self.bounds[1]))
        except (OverflowError,TypeError):
            valid=False
        if not valid:
            raise ValueError('Temporal anchor requires finite ordered bounds')


Operand = Ref | BoundVar | TimeLiteral
