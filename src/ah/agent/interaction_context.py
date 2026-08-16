from __future__ import annotations

from dataclasses import dataclass, field

from ah.model import Ref


@dataclass(slots=True)
class InteractionContext:
    """Runtime interaction context; not part of canonical AH state."""

    self_ref: Ref | None = None
    user_ref: Ref | None = None
    now_ref: Ref | None = None
    active_location_ref: Ref | None = None
    pronoun_refs: dict[str, Ref] = field(default_factory=dict)
    last_experience_ref: Ref | None = None
    pending_clarification_refs: list[Ref] = field(default_factory=list)

    def resolve_pronoun(self, text: str) -> Ref | None:
        return self.pronoun_refs.get(text.casefold())
