from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import Ref, RefKind


@dataclass(frozen=True, slots=True)
class ExistentialDiscourseAnchor:
    """Runtime handle for one still-unidentified discourse participant.

    The anchor is deliberately not a canonical AH node.  It points at an asserted
    existential formula and the quantified proposition members that currently
    describe the same unknown participant.  ``variable_id`` is meaningful only
    inside that existential scope.

    v0.25 keeps the cross-turn contract intentionally narrow: one anchor describes
    one-variable existential scopes only.  Multi-variable scopes remain explicit
    canonical formulae but are not silently guessed by nominative pronouns in the
    next turn.
    """

    existential_ref: Ref
    member_refs: tuple[Ref, ...]
    variable_id: int

    def __post_init__(self) -> None:
        if self.existential_ref.kind is not RefKind.G:
            raise ValueError("ExistentialDiscourseAnchor.existential_ref must be G")
        if not self.member_refs:
            raise ValueError("ExistentialDiscourseAnchor requires member_refs")
        if self.variable_id < 0:
            raise ValueError("ExistentialDiscourseAnchor.variable_id must be >= 0")


@dataclass(slots=True)
class InteractionContext:
    """Runtime interaction context; not part of canonical AH state."""

    self_ref: Ref | None = None
    user_ref: Ref | None = None
    now_ref: Ref | None = None
    active_location_ref: Ref | None = None
    pronoun_refs: dict[str, Ref] = field(default_factory=dict)
    existential_pronoun_anchors: dict[str, ExistentialDiscourseAnchor] = field(default_factory=dict)
    last_experience_ref: Ref | None = None
    pending_clarification_refs: list[Ref] = field(default_factory=list)

    def resolve_pronoun(self, text: str) -> Ref | None:
        return self.pronoun_refs.get(text.casefold())

    def resolve_existential_pronoun(self, text: str) -> ExistentialDiscourseAnchor | None:
        return self.existential_pronoun_anchors.get(text.casefold())
