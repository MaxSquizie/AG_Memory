from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ah.model import ActantRole


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    text: str
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        if (self.start is None) != (self.end is None):
            raise ValueError("EvidenceSpan.start/end must be both set or both None")
        if self.start is not None and (self.start < 0 or self.end < self.start):
            raise ValueError("Invalid evidence span")


@dataclass(frozen=True, slots=True)
class PredicateCandidate:
    surface: str
    normalized_hint: str | None = None
    sense_hint: str | None = None
    evidence: EvidenceSpan | None = None

    @property
    def lookup_form(self) -> str:
        value = (self.normalized_hint or self.surface).strip()
        if not value:
            raise ValueError("PredicateCandidate must contain a non-empty form")
        return value


@dataclass(frozen=True, slots=True)
class ActantCandidate:
    role: ActantRole
    mention: str | None = None
    normalized_hint: str | None = None
    semantic_hint: str | None = None
    candidate_ref: str | None = None
    evidence: EvidenceSpan | None = None
    parser_confidence: float | None = None

    def __post_init__(self) -> None:
        if self.candidate_ref is None and not (self.mention or self.normalized_hint):
            raise ValueError("ActantCandidate needs mention/normalized_hint or candidate_ref")
        if self.parser_confidence is not None and not 0.0 <= self.parser_confidence <= 1.0:
            raise ValueError("parser_confidence must be in [0, 1]")

    @property
    def lookup_text(self) -> str | None:
        value = self.normalized_hint or self.mention
        return value.strip() if value else None


@dataclass(frozen=True, slots=True)
class AssertionCandidate:
    local_id: str
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...]
    evidence: EvidenceSpan | None = None
    alternatives: tuple["AssertionCandidate", ...] = ()
    negated: bool = False


class QueryMode(str, Enum):
    FILL_ROLE = "FILL_ROLE"
    EXISTS = "EXISTS"


@dataclass(frozen=True, slots=True)
class QueryCandidate:
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...] = ()
    requested_role: ActantRole | None = None
    query_mode: QueryMode = QueryMode.EXISTS


@dataclass(frozen=True, slots=True)
class CommandCandidate:
    predicate: PredicateCandidate
    actants: tuple[ActantCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    source_text: str
    assertions: tuple[AssertionCandidate, ...] = ()
    queries: tuple[QueryCandidate, ...] = ()
    commands: tuple[CommandCandidate, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def acts_count(self) -> int:
        return len(self.assertions) + len(self.queries) + len(self.commands)
