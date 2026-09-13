from __future__ import annotations

from ah.agent import InteractionContext
from ah.model import Domain, Ref, SemanticEntity
from ah.perception import ActantCandidate

from .entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EntityResolution,
    ExistingEntity,
)
from .identity_graph import identity_owners_for_name_ref, is_identity_name_entity


class IdentityAwareEntityResolver(EntityResolver):
    """Resolve conventional-name M nodes to the entities they explicitly name.

    Ordinary lexical aliases remain a fast retrieval aid, but explicit graph
    semantics are authoritative. Exact name lookup may therefore return both the
    named P entity (through its alias index) and a C-domain identity-name M. The
    latter is never treated as a competing person/entity: it is traversed through
    indexed ``IDENTITY_NAME`` links to its owner(s), then all owner refs are deduped.

    Only genuine grammatical deixis (``я``, ``ты`` and inflected equivalents)
    bypasses that graph. A lexical name such as ``Илья`` must carry its explicit
    name-M as support even if the owner's legacy alias index already points directly
    at USER.
    """

    def _identity_expanded_matches(
        self,
        lookup: str,
        *,
        preferred_domain: Domain | None,
        grammatical_number: str | None,
    ) -> tuple[tuple[SemanticEntity, tuple[Ref, ...]], ...]:
        matches = self.core.store.find_entities_by_name(lookup, preferred_domain)
        label_matches = self.core.store.find_entities_by_name(lookup, Domain.C)
        combined: list[SemanticEntity] = []
        for entity in (*matches, *label_matches):
            if all(old.uid != entity.uid for old in combined):
                combined.append(entity)

        expanded: dict[str, tuple[SemanticEntity, list[Ref]]] = {}
        for entity in combined:
            if is_identity_name_entity(entity):
                label_ref = self.core.ref(entity.uid)
                for owner_ref in identity_owners_for_name_ref(self.core, label_ref):
                    if (
                        preferred_domain is not None
                        and self.core.store.domain_of(owner_ref.uid) is not preferred_domain
                    ):
                        continue
                    try:
                        owner = self.core.store.get_element_any_domain(owner_ref.uid)
                    except KeyError:
                        continue
                    if not isinstance(owner, SemanticEntity):
                        continue
                    old = expanded.get(owner.uid)
                    if old is None:
                        expanded[owner.uid] = (owner, [label_ref])
                    elif all(ref.uid != label_ref.uid for ref in old[1]):
                        old[1].append(label_ref)
                continue

            if preferred_domain is not None and self.core.store.domain_of(entity.uid) is not preferred_domain:
                continue
            expanded.setdefault(entity.uid, (entity, []))

        filtered_entities = self._filter_by_grammatical_number(
            [item[0] for item in expanded.values()], grammatical_number
        )
        allowed = {item.uid for item in filtered_entities}
        return tuple(
            (entity, tuple(supports))
            for uid, (entity, supports) in expanded.items()
            if uid in allowed
        )

    def resolve(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None = None,
        second_person_ref: Ref | None = None,
        preferred_domain: Domain | None = None,
        attention_refs: tuple[Ref, ...] = (),
    ) -> EntityResolution:
        # Deixis is a stronger source-grounded identity signal than any lexical name
        # edge, so preserve the mature direct path for grammatical USER/SELF forms.
        deictic = self.deixis.resolve(
            candidate,
            context,
            first_person_ref=first_person_ref,
            second_person_ref=second_person_ref,
        )
        if deictic is not None:
            return ExistingEntity(deictic)

        # Keep every non-name mature behavior as a fallback (literals, possessive
        # descriptions, ordinary indexed entities, unseen NewEntityPlan, etc.).
        base = super().resolve(
            candidate,
            context,
            first_person_ref=first_person_ref,
            second_person_ref=second_person_ref,
            preferred_domain=preferred_domain,
            attention_refs=attention_refs,
        )

        lookup_forms: list[str] = []
        for value in (candidate.normalized_hint, candidate.mention):
            if value and value.strip() and value.strip() not in lookup_forms:
                lookup_forms.append(value.strip())

        for lookup in lookup_forms:
            expanded = self._identity_expanded_matches(
                lookup,
                preferred_domain=preferred_domain,
                grammatical_number=candidate.grammatical_number,
            )
            if len(expanded) == 1:
                entity, supports = expanded[0]
                return ExistingEntity(self.core.ref(entity.uid), supports)
            if len(expanded) > 1:
                active = {ref.uid for ref in attention_refs}
                active_matches = [item for item in expanded if item[0].uid in active]
                if len(active_matches) == 1:
                    entity, supports = active_matches[0]
                    return ExistingEntity(self.core.ref(entity.uid), supports)
                return AmbiguousEntityPlan(
                    tuple(self.core.ref(entity.uid) for entity, _supports in expanded),
                    lookup,
                )

        return base
