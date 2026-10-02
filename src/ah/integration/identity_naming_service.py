from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ah.agent import InteractionContext
from ah.model import Domain, Property, RefKind, SemanticEntity
from ah.perception import PerceptionResult
from ah.perception.naming_semantics import NamingAssertionCandidate

from .contracts import ActivationSeedRequest, IntegrationCommit, SeedReason
from .entity_resolver import EntityResolver, ExistingEntity
from .errors import CandidateValidationError
from .identity_graph import (
    IDENTITY_NAME_RELATION,
    ensure_identity_name_entity,
    is_identity_name_entity,
)
from .naming_service import NamingAwareIntegrationService


class CanonicalNamingIntegrationService(NamingAwareIntegrationService):
    """Materialize naming as explicit graph semantics plus a retrieval alias.

    Perception has already decided that the source is naming rather than ordinary
    predication. Integration therefore performs two distinct operations:

    * keep the morphology-normalized value in the owner's ``aliases`` property as a
      bounded lexical retrieval index, preserving fast ordinary entity resolution;
    * create/reuse an excitable canonical C-domain M for the conventional name and
      connect the named entity to it with ``IDENTITY_NAME``.

    The explicit M/L pair is authoritative graph evidence. The alias is only a
    retrieval aid and must never replace the graph relation. Thus ``Я Илья`` yields
    USER --IDENTITY_NAME--> M("Илья") without manufacturing a generic copular fact,
    while ``Я инженер`` remains ordinary predication and does not enter this path.
    """

    @staticmethod
    def _canonical_name(assertion: NamingAssertionCandidate) -> str:
        return (
            assertion.name_normalized_hint
            or assertion.name_value
        ).strip()

    def _apply_naming_assertions(
        self,
        core,
        naming: tuple[NamingAssertionCandidate, ...],
        context: InteractionContext,
    ) -> None:
        resolver = EntityResolver(core)
        for assertion in naming:
            owner = assertion.owner
            assert owner is not None
            resolved = resolver.resolve(
                owner,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                preferred_domain=Domain.P,
            )
            if not isinstance(resolved, ExistingEntity):
                raise CandidateValidationError(
                    f"Naming owner is not a uniquely existing entity: {assertion.local_id}"
                )
            if resolved.ref.kind is not RefKind.M:
                raise CandidateValidationError("Naming owner must resolve to canonical M")
            entity = core.store.get_element_any_domain(resolved.ref.uid)
            if not isinstance(entity, SemanticEntity):
                raise CandidateValidationError("Naming owner does not reference SemanticEntity")

            alias = self._canonical_name(assertion)
            if not alias:
                raise CandidateValidationError("Naming value must not normalize to empty text")
            alias_key = alias.casefold()
            primary = entity.properties.get("name")
            aliases = self._alias_values(entity)
            properties = dict(entity.properties)
            changed = False

            if not (
                primary is not None
                and str(primary.value).strip().casefold() == alias_key
            ) and alias_key not in {item.casefold() for item in aliases}:
                aliases.append(alias)
                existing_prop = entity.properties.get("aliases")
                properties["aliases"] = Property(
                    "aliases",
                    tuple(aliases),
                    existing_prop.type_name if existing_prop is not None else "str[]",
                    existing_prop.unit if existing_prop is not None else None,
                )
                changed = True

            meta = dict(entity.meta)
            if (
                str(meta.get("identity_role") or "").upper() in {"USER", "SELF"}
                and meta.get("grammatical_number") is None
            ):
                meta["grammatical_number"] = "sing"
                changed = True

            if changed:
                domain = core.store.domain_of(entity.uid)
                if domain is None:
                    raise CandidateValidationError("Naming owner has no semantic domain")
                core.edit_element(
                    domain,
                    replace(entity, properties=properties, meta=meta),
                )

            try:
                name_ref = ensure_identity_name_entity(core, alias)
            except ValueError as exc:
                raise CandidateValidationError(str(exc)) from exc
            core.ensure_link(
                IDENTITY_NAME_RELATION,
                resolved.ref,
                name_ref,
                self.config.nominal_relation_link_weight,
            )

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        source_timestamp: datetime | None = None,
    ) -> IntegrationCommit:
        """Expose newly grounded name M nodes to the same turn's ignition wave."""
        naming = tuple(
            item for item in result.assertions
            if isinstance(item, NamingAssertionCandidate)
        )
        commit = super().integrate_external(
            result,
            context,
            source_timestamp=source_timestamp,
        )
        if not naming:
            return commit

        seeds = list(commit.activation_seeds)
        seen = {(item.ref.kind.value, item.ref.uid) for item in seeds}
        for assertion in naming:
            alias = self._canonical_name(assertion)
            if not alias:
                continue
            matches = tuple(
                entity
                for entity in self.core.store.find_entities_by_name(alias, Domain.C)
                if is_identity_name_entity(entity)
            )
            if len(matches) != 1:
                continue
            ref = self.core.ref(matches[0].uid)
            key = (ref.kind.value, ref.uid)
            if key in seen:
                continue
            seen.add(key)
            seeds.append(ActivationSeedRequest(ref, SeedReason.NEW_FACT))
        return replace(commit, activation_seeds=tuple(seeds))
