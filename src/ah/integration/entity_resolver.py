from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import Ref
from ah.perception import ActantCandidate

from .deixis_resolver import DeixisResolver


@dataclass(frozen=True, slots=True)
class ExistingEntity:
    ref: Ref


@dataclass(frozen=True, slots=True)
class NewEntityPlan:
    name: str
    semantic_hint: str | None = None


@dataclass(frozen=True, slots=True)
class AmbiguousEntityPlan:
    candidates: tuple[Ref, ...]
    mention: str


EntityResolution = ExistingEntity | NewEntityPlan | AmbiguousEntityPlan


class EntityResolver:
    def __init__(self, core: AHCore, deixis: DeixisResolver | None = None) -> None:
        self.core = core
        self.deixis = deixis or DeixisResolver()

    def resolve(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None = None,
        second_person_ref: Ref | None = None,
    ) -> EntityResolution:
        deictic = self.deixis.resolve(
            candidate,
            context,
            first_person_ref=first_person_ref,
            second_person_ref=second_person_ref,
        )
        if deictic is not None:
            return ExistingEntity(deictic)

        text = candidate.lookup_text
        if not text:
            raise ValueError("EntityResolver requires text for non-candidate_ref actants")

        entities = self.core.store.find_entities_by_name(text)
        if len(entities) == 1:
            return ExistingEntity(self.core.ref(entities[0].uid))
        if len(entities) > 1:
            return AmbiguousEntityPlan(
                tuple(self.core.ref(entity.uid) for entity in entities),
                text,
            )
        return NewEntityPlan(text, candidate.semantic_hint)
