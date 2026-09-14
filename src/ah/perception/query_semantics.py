from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import ActantCandidate, EvidenceSpan, QueryCandidate, QueryMode


class IdentityQueryKind(str, Enum):
    """Typed information need carried by an entity-identity question.

    The values describe the requested semantic projection, not Russian surface
    forms.  Perception selects one bounded value from the complete source and the
    already extracted structure; downstream layers never classify question words.
    """

    NAME_LOOKUP = "NAME_LOOKUP"
    ENTITY_DESCRIPTION = "ENTITY_DESCRIPTION"


@dataclass(frozen=True, slots=True)
class EventSetQueryCandidate(QueryCandidate):
    """Runtime query whose unknown is the event/proposition itself.

    Ordinary ``QueryCandidate`` asks either whether one predicate instance exists
    or for a missing role of that predicate. A question such as ``what did X do``
    is different: the source predicate is an interrogative shell describing the
    requested event class, not a canonical predicate constraint. The answer is
    therefore one or more asserted events satisfying the explicit actant
    constraints.

    ``query_operator_evidence`` keeps the already detected interrogative source
    spans (for example the top-level ``Что``).  It is presentation/provenance data,
    not a second classifier: the same structural Ques+clause decision that created
    the query owns these spans.  Keeping them here lets M1 explain every grounded
    operator without re-inferring semantics from surface words.

    This remains perception/runtime data. It has no canonical UID and does not
    mutate AH. ``query_mode`` is kept as EXISTS only for compatibility with code
    that understands the historical two-mode contract; event-set aware goal
    compilation dispatches on this typed subclass before ordinary predicate/T
    resolution.
    """

    event_set: bool = True
    query_operator_evidence: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        # dataclass(slots=True) may synthesize a replacement class object; call the
        # base validator explicitly rather than relying on zero-argument super().
        QueryCandidate.__post_init__(self)
        if self.query_mode is not QueryMode.EXISTS:
            raise ValueError("EventSetQueryCandidate must use compatibility mode EXISTS")
        if self.requested_roles:
            raise ValueError("EventSetQueryCandidate requests events, not actant roles")


@dataclass(frozen=True, slots=True)
class EntityIdentityQueryCandidate(QueryCandidate):
    """Runtime query asking for a supported name/description of one known entity.

    Natural-language copular shells such as ``пользователь кто?`` are not factual
    ``быть(STATE=пользователь, SUBJECT=кто)`` propositions.  Their unknown is an
    name or description of one already grounded entity. The source copula remains
    provenance only; it must not create or select a canonical predicate template.

    ``target`` is the source-grounded entity expression. ``query_operator_evidence``
    records source spans consumed by this query shell. Canonical entity resolution
    and reading matching identity evidence remain deterministic after Perception.
    """

    target: ActantCandidate | None = None
    query_kind: IdentityQueryKind = IdentityQueryKind.ENTITY_DESCRIPTION
    identity_query: bool = True
    query_operator_evidence: tuple[EvidenceSpan, ...] = ()

    def __post_init__(self) -> None:
        QueryCandidate.__post_init__(self)
        if self.query_mode is not QueryMode.EXISTS:
            raise ValueError("EntityIdentityQueryCandidate must use compatibility mode EXISTS")
        if self.requested_roles:
            raise ValueError("EntityIdentityQueryCandidate does not request predicate roles")
        if self.target is None:
            raise ValueError("EntityIdentityQueryCandidate requires a target entity")
        if len(self.actants) != 1 or self.actants[0] != self.target:
            raise ValueError("EntityIdentityQueryCandidate.actants must contain only target")
        if not isinstance(self.query_kind, IdentityQueryKind):
            raise ValueError("EntityIdentityQueryCandidate.query_kind must be IdentityQueryKind")
