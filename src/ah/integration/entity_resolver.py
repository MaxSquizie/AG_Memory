from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import Domain, Ref
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
        preferred_domain: Domain | None = None,
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

        # `normalized_hint` is an indexing aid, not a new canonical identity field.
        # Prefer it for deterministic lookup/creation so inflectional variants of
        # the same nominal do not become separate m nodes merely because their
        # surface case differs.  Evidence/mention still preserves the source text.
        lookup_forms: list[str] = []
        for value in (candidate.normalized_hint, candidate.mention):
            if value and value.strip() and value.strip() not in lookup_forms:
                lookup_forms.append(value.strip())

        for lookup in lookup_forms:
            # Name/alias is a retrieval index, never a cross-domain identity key.
            # Once Integration has provenance evidence for the current assertion,
            # lexical resolution stays inside that semantic domain.  This prevents
            # a prior generic C entity with the same surface name from hijacking a
            # newly introduced personalized P entity.  Stronger identity evidence
            # (deixis, candidate_ref, turn-local entity_ref) is resolved before this
            # lookup and may still route the assertion to P.
            entities = self.core.store.find_entities_by_name(lookup, preferred_domain)
            if len(entities) == 1:
                return ExistingEntity(self.core.ref(entities[0].uid))
            if len(entities) > 1:
                return AmbiguousEntityPlan(
                    tuple(self.core.ref(entity.uid) for entity in entities),
                    lookup,
                )

        canonical_name = lookup_forms[0] if lookup_forms else text
        return NewEntityPlan(canonical_name, candidate.semantic_hint)
