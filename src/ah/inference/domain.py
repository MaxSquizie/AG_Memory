from __future__ import annotations

from ah.core import AHCore
from ah.model import Domain, Ref, RefKind


_DOMAIN_RANK = {Domain.C: 0, Domain.P: 1, Domain.H: 2}


def effective_domain(core: AHCore, ref: Ref, _seen: frozenset[str] = frozenset()) -> Domain | None:
    if ref.uid in _seen:
        return None
    direct = core.store.domain_of(ref.uid)
    if direct is not None:
        return direct
    if ref.kind is not RefKind.L:
        return None
    link = core.store.get_link(ref.uid)
    domains = [
        effective_domain(core, link.source, _seen | {ref.uid}),
        effective_domain(core, link.target, _seen | {ref.uid}),
    ]
    concrete = [d for d in domains if d is not None]
    return max(concrete, key=_DOMAIN_RANK.__getitem__) if concrete else None


def domain_from_premises(core: AHCore, refs: tuple[Ref, ...]) -> Domain | None:
    domains = [effective_domain(core, ref) for ref in refs]
    concrete = [d for d in domains if d is not None]
    return max(concrete, key=_DOMAIN_RANK.__getitem__) if concrete else None
