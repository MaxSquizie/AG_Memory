from __future__ import annotations

from dataclasses import replace

from ah.core import AHCore
from ah.model import Domain, Property, Ref, SemanticEntity
from ah.perception import PredicateCandidate

from .errors import IntegrationError


def _forms(predicate: PredicateCandidate) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        value.strip()
        for value in (predicate.lookup_form, predicate.surface)
        if value and value.strip()
    ))


def taxonomy_class_candidates(
    core: AHCore, predicate: PredicateCandidate
) -> tuple[Ref, ...]:
    """Find explicit/imported class nodes without treating names as identity."""
    entities: dict[str, SemanticEntity] = {}
    for form in _forms(predicate):
        for entity in core.store.find_entities_by_name(form, Domain.C):
            entities[entity.uid] = entity
    tagged = [
        entity for entity in entities.values()
        if entity.meta.get("taxonomy_class") is True
    ]
    graph_classes = [
        entity for entity in entities.values()
        if core.store.incoming_links(entity.uid, "IS-A")
        or core.store.outgoing_links(entity.uid, "IS-A")
    ]
    selected = tagged or graph_classes
    return tuple(core.ref(entity.uid) for entity in selected)


def ensure_taxonomy_class(
    core: AHCore, predicate: PredicateCandidate
) -> tuple[Ref, bool]:
    """Resolve/create the canonical C-domain class named by a predicate."""
    candidates = taxonomy_class_candidates(core, predicate)
    if len(candidates) > 1:
        raise IntegrationError(
            f"Ambiguous canonical taxonomy class: {predicate.lookup_form!r}"
        )
    if candidates:
        ref = candidates[0]
        entity = core.store.get_element_any_domain(ref.uid)
        if isinstance(entity, SemanticEntity) and entity.meta.get("taxonomy_class") is not True:
            core.edit_element(
                Domain.C,
                replace(entity, meta={**entity.meta, "taxonomy_class": True}),
            )
        return ref, False

    forms = _forms(predicate)
    canonical_name = predicate.lookup_form
    aliases = tuple(
        form for form in forms if form.casefold() != canonical_name.casefold()
    )
    properties = {
        "name": Property("name", canonical_name, "str"),
        "grammatical_number": Property("grammatical_number", "sing", "str"),
    }
    if aliases:
        properties["aliases"] = Property("aliases", aliases, "str[]")
    entity = core.add_entity(
        Domain.C,
        properties=properties,
        meta={
            "taxonomy_class": True,
            "grammatical_number": "sing",
            "gc_auto_created": True,
        },
    )
    return core.ref(entity.uid), True
