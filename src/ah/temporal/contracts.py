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


class TemporalModeProbeDecision(str, Enum):
    """Closed output protocol for occurrence-level temporal classification."""

    STATE = "STATE"
    EVENT = "EVENT"
    PROCESS = "PROCESS"
    AMBIGUOUS = "AMBIGUOUS"


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
        # A timezone is semantically part of identity only when the normalized
        # value contains a clock coordinate.  Relative calendar expressions such
        # as ``вчера`` need the utterance timezone to *resolve* which date is meant,
        # but after resolution ``2026-09-12`` and an explicitly written
        # ``12.09.2026`` denote the same DAY.  Keeping ``+03:00`` in the identity
        # key for the former created two canonical time entities for one date.
        has_clock_coordinate = any(
            value is not None and "T" in value
            for value in (self.start, self.end)
        )
        identity_timezone = self.timezone if has_clock_coordinate else None
        return "|".join(
            (
                self.kind.value,
                self.start or "",
                self.end or "",
                self.precision.value,
                identity_timezone or "",
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
