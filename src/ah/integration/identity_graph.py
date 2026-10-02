from __future__ import annotations

from ah.model import Domain, Property, Ref, RefKind, SemanticEntity


IDENTITY_NAME_RELATION = "IDENTITY_NAME"
IDENTITY_NAME_META_KEY = "identity_name_label"


def is_identity_name_entity(entity: object) -> bool:
    return isinstance(entity, SemanticEntity) and bool(
        entity.meta.get(IDENTITY_NAME_META_KEY, False)
    )


def identity_name_text(entity: SemanticEntity) -> str | None:
    if not is_identity_name_entity(entity):
        return None
    prop = entity.properties.get("name")
    if prop is None:
        return None
    value = str(prop.value).strip()
    return value or None


def ensure_identity_name_entity(core, name: str) -> Ref:
    """Return one canonical excitable M representing a conventional name label.

    Name labels live in C because the same conventional name may identify several
    P-domain persons.  The M is therefore a reusable semantic name object, while an
    ``IDENTITY_NAME`` L carries the owner-specific assertion.  Exact name lookup is
    index-bounded; no whole-AH scan is used.
    """
    value = name.strip()
    if not value:
        raise ValueError("identity name must be non-empty")

    matches = tuple(
        entity
        for entity in core.store.find_entities_by_name(value, Domain.C)
        if is_identity_name_entity(entity)
    )
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous canonical identity-name label {value!r}: "
            + ", ".join(item.uid for item in matches)
        )
    if matches:
        return core.ref(matches[0].uid)

    entity = core.add_entity(
        Domain.C,
        {"name": Property("name", value, "str")},
        {
            IDENTITY_NAME_META_KEY: True,
            "grammatical_number": "sing",
        },
    )
    return core.ref(entity.uid)


def identity_name_refs_for_owner(core, owner: Ref) -> tuple[Ref, ...]:
    if owner.kind is not RefKind.M:
        return ()
    refs: list[Ref] = []
    seen: set[str] = set()
    for link in core.store.outgoing_links(owner.uid, IDENTITY_NAME_RELATION):
        target = link.target
        if target.kind is not RefKind.M or target.uid in seen:
            continue
        try:
            entity = core.store.get_element_any_domain(target.uid)
        except KeyError:
            continue
        if not is_identity_name_entity(entity):
            continue
        seen.add(target.uid)
        refs.append(target)
    return tuple(refs)


def identity_owners_for_name_ref(core, name_ref: Ref) -> tuple[Ref, ...]:
    if name_ref.kind is not RefKind.M:
        return ()
    try:
        entity = core.store.get_element_any_domain(name_ref.uid)
    except KeyError:
        return ()
    if not is_identity_name_entity(entity):
        return ()

    refs: list[Ref] = []
    seen: set[str] = set()
    for link in core.store.incoming_links(name_ref.uid, IDENTITY_NAME_RELATION):
        source = link.source
        if source.kind is not RefKind.M or source.uid in seen:
            continue
        try:
            owner = core.store.get_element_any_domain(source.uid)
        except KeyError:
            continue
        if not isinstance(owner, SemanticEntity):
            continue
        seen.add(source.uid)
        refs.append(source)
    return tuple(refs)
