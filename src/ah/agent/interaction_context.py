from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import ActantRole, Ref, RefKind


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
    restriction_lemma: str | None = None

    def __post_init__(self) -> None:
        if self.existential_ref.kind is not RefKind.G:
            raise ValueError("ExistentialDiscourseAnchor.existential_ref must be G")
        if not self.member_refs:
            raise ValueError("ExistentialDiscourseAnchor requires member_refs")
        if self.variable_id < 0:
            raise ValueError("ExistentialDiscourseAnchor.variable_id must be >= 0")
        if self.restriction_lemma is not None:
            value = self.restriction_lemma.strip().casefold().replace("ё", "е")
            object.__setattr__(self, "restriction_lemma", value or None)


@dataclass(slots=True)
class AssociationDiscourseSession:
    """Runtime-only context for follow-up requests such as ``А ещё?``.

    A comparison stream is identified by both canonical endpoints and its explicit
    typed search restrictions.  ``A vs B`` and ``A vs B at LOCATION=yard`` are
    therefore different discourse goals and must not share result exclusions.
    Constraints are stored as low-level ``(ActantRole, Ref)`` pairs to keep the
    interaction layer independent from inference dataclasses.
    """

    left: Ref
    right: Ref
    # Keep this field in its historical positional slot for compatibility with
    # callers/tests that constructed AssociationDiscourseSession(left, right, rows).
    emitted_signatures: list[str] = field(default_factory=list)
    constraints: tuple[tuple[ActantRole, Ref], ...] = ()

    @staticmethod
    def _constraint_key(constraints) -> tuple[tuple[str, str, str], ...]:
        rows: list[tuple[str, str, str]] = []
        for item in constraints or ():
            role = getattr(item, "role", None)
            value = getattr(item, "value", None)
            if role is None or value is None:
                role, value = item
            rows.append((str(getattr(role, "value", role)), value.kind.value, value.uid))
        rows.sort()
        return tuple(rows)

    def same_pair(self, left: Ref, right: Ref) -> bool:
        return {self.left.uid, self.right.uid} == {left.uid, right.uid}

    def same_goal(self, left: Ref, right: Ref, constraints=()) -> bool:
        return self.same_pair(left, right) and self._constraint_key(self.constraints) == self._constraint_key(constraints)

    def remember(self, signature: str | None) -> None:
        value = (signature or "").strip()
        if value and value not in self.emitted_signatures:
            self.emitted_signatures.append(value)


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
    association_session: AssociationDiscourseSession | None = None

    def resolve_pronoun(self, text: str) -> Ref | None:
        return self.pronoun_refs.get(text.casefold())

    def resolve_existential_pronoun(self, text: str) -> ExistentialDiscourseAnchor | None:
        return self.existential_pronoun_anchors.get(text.casefold())
