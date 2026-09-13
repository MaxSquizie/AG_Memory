from __future__ import annotations

from dataclasses import replace

from ah.agent import InteractionContext
from ah.model import Domain, Property, RefKind, SemanticEntity
from ah.perception.naming_semantics import NamingAssertionCandidate

from .entity_resolver import EntityResolver, ExistingEntity
from .errors import CandidateValidationError
from .naming_service import NamingAwareIntegrationService


class CanonicalNamingIntegrationService(NamingAwareIntegrationService):
    """Normalize a source name before indexing it as an entity alias.

    ``NamingAssertionCandidate`` intentionally keeps both the source realization
    (``name_value``) and a morphology-normalized lookup form
    (``name_normalized_hint``).  The source form belongs to diagnostics/M1; entity
    retrieval must use the normalized form so case-inflected naming statements such
    as ``Я являюсь Ильёй`` can later resolve the ordinary nominative ``Илья``.

    No identity decision happens here: Perception has already classified the source
    as naming, and EntityResolver still deterministically resolves the named owner.
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

            if not changed:
                continue
            domain = core.store.domain_of(entity.uid)
            if domain is None:
                raise CandidateValidationError("Naming owner has no semantic domain")
            core.edit_element(
                domain,
                replace(entity, properties=properties, meta=meta),
            )
