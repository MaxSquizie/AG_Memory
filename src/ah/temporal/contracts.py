from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TemporalKind(str, Enum):
    POINT = "POINT"
    INTERVAL = "INTERVAL"


class TemporalPrecision(str, Enum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"
    MINUTE = "MINUTE"
    SECOND = "SECOND"
    UNKNOWN = "UNKNOWN"


class TemporalMode(str, Enum):
    STATE = "STATE"
    EVENT = "EVENT"
    PROCESS = "PROCESS"
    TRANSITION = "TRANSITION"


class TransitionOperator(str, Enum):
    START = "START"
    STOP = "STOP"
    CONTINUE = "CONTINUE"
    AGAIN = "AGAIN"
    NO_LONGER = "NO_LONGER"


class TemporalRelation(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    OVERLAP = "OVERLAP"
    CONTAINS = "CONTAINS"


@dataclass(frozen=True, slots=True)
class TemporalValue:
    """Runtime normalized semantic time.

    ``start``/``end`` use an ISO-like *partial* representation and deliberately
    preserve missing components instead of inventing them. Examples:

    - ``2026``
    - ``2026-09``
    - ``--09`` (September, year unknown)
    - ``2026-09-05``
    - ``T12:30`` (time of day, date unknown)
    - ``2026-09-05T12:30:00+03:00``

    The object is staging/runtime data. Canonically time remains an ordinary ``m``
    with the properties required by architecture v4.
    """

    kind: TemporalKind
    start: str | None
    end: str | None
    precision: TemporalPrecision
    timezone: str | None = None
    source_text: str | None = None

    def __post_init__(self) -> None:
        if self.kind is TemporalKind.POINT:
            if self.start is None or self.end is not None:
                raise ValueError("POINT requires start and forbids end")
        elif self.start is None and self.end is None:
            raise ValueError("INTERVAL requires at least one bound")
        if self.source_text is not None and not self.source_text.strip():
            raise ValueError("source_text must be non-empty when provided")

    @property
    def canonical_key(self) -> str:
        return "|".join(
            (
                self.kind.value,
                self.start or "",
                self.end or "",
                self.precision.value,
                self.timezone or "",
            )
        )


@dataclass(frozen=True, slots=True)
class TemporalAnchorContext:
    """Priority-ordered runtime anchors for relative-time resolution."""

    explicit_anchor: datetime | None = None
    source_timestamp: datetime | None = None
    experience_timestamp: datetime | None = None

    def preferred(self) -> datetime | None:
        return self.explicit_anchor or self.source_timestamp or self.experience_timestamp


@dataclass(frozen=True, slots=True)
class TemporalCandidate:
    """Result of deterministic TIME normalization attached to one actant."""

    value: TemporalValue | None
    relative: bool = False
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        if self.value is None and not self.unresolved_reason:
            raise ValueError("Unresolved TemporalCandidate requires unresolved_reason")
        if self.value is not None and self.unresolved_reason is not None:
            raise ValueError("Resolved TemporalCandidate cannot carry unresolved_reason")

    @property
    def resolved(self) -> bool:
        return self.value is not None
