from __future__ import annotations

from dataclasses import replace

from ah.agent import InteractionContext
from ah.model import Domain, Property, RefKind, SemanticEntity
from ah.perception.naming_semantics import NamingAssertionCandidate

from .entity_resolver import EntityResolver, ExistingEntity
from .errors import CandidateValidationError
from .identity_graph import IDENTITY_NAME_RELATION, ensure_identity_name_entity
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

            alias = (
                assertion.name_normalized_hint
                or assertion.name_value
            ).strip()
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

            # Graph identity is explicit even when the lexical alias was already
            # present from an older memory. This also upgrades such memories on the
            # next naming assertion instead of silently keeping alias-only state.
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
