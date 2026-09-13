from __future__ import annotations

from dataclasses import dataclass

from .contracts import EvidenceSpan, QueryCandidate, QueryMode


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