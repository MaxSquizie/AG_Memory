from __future__ import annotations

from collections import deque

from ah.core import AHCore
from ah.model import Ref, RefKind, SemanticEntity


def taxonomy_path(
    core: AHCore,
    actual: Ref,
    required: Ref,
    *,
    max_depth: int,
) -> tuple[Ref, ...] | None:
    """Return an explicit IS-A proof that ``actual`` satisfies ``required``.

    Role subsumption is permitted only when the requested filler is an explicit
    taxonomy class.  This prevents arbitrary same-name/entity substitutions while
    allowing facts about a textbook to satisfy a query about a book.
    """
    if actual == required:
        return ()
    if actual.kind is not RefKind.M or required.kind is not RefKind.M:
        return None
    try:
        target = core.store.get_element_any_domain(required.uid)
    except KeyError:
        return None
    if not isinstance(target, SemanticEntity):
        return None
    if not (
        target.meta.get("taxonomy_class") is True
        or core.store.incoming_links(required.uid, "IS-A")
        or core.store.outgoing_links(required.uid, "IS-A")
    ):
        return None

    queue = deque([(actual, ())])
    seen = {actual.uid}
    while queue:
        current, proof = queue.popleft()
        if len(proof) // 2 >= max_depth:
            continue
        for link in sorted(
            core.store.outgoing_links(current.uid, "IS-A"),
            key=lambda item: item.uid,
        ):
            target_ref = link.target
            if target_ref.uid in seen:
                continue
            next_proof = (*proof, core.ref(link.uid), target_ref)
            if target_ref == required:
                return (actual, *next_proof)
            seen.add(target_ref.uid)
            queue.append((target_ref, next_proof))
    return None
