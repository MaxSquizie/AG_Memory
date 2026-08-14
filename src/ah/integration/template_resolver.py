from __future__ import annotations

from dataclasses import dataclass

from ah.core import AHCore
from ah.model import ActantRole, Domain, Template
from ah.perception import PredicateCandidate

from .errors import TemplateResolutionError


@dataclass(frozen=True, slots=True)
class TemplateResolution:
    template: Template
    created: bool


class TemplateResolver:
    """Resolve a semantic predicate to one canonical T or create it.

    `PredicateCandidate.surface` is source-language evidence. When a normalized
    predicate hint exists, only that normalized symbol is used as the predicate S
    referenced by T. This deliberately keeps Russian sensory/lexical S separate
    from English semantic predicate S (for adaptive_v1 the normalized hint is a
    validated lowercase English snake_case symbol).

    This does not introduce a new canonical field into S: the English symbol is
    still an ordinary S form, preserving the architecture's `<UID, R>` model.
    """

    def __init__(self, core: AHCore, template_domain: Domain = Domain.C) -> None:
        self.core = core
        self.template_domain = template_domain

    def resolve(
        self,
        predicate: PredicateCandidate,
        filled_roles: tuple[ActantRole, ...],
    ) -> TemplateResolution:
        lookup = predicate.lookup_form
        symbol = self.core.store.find_symbol_by_form(lookup)

        # Legacy/manual candidates may omit normalized_hint. In that case surface
        # itself remains the only available symbol. Adaptive parser always supplies
        # an English normalized_hint, so source-language surface is never merged
        # into the semantic predicate S.
        if symbol is not None:
            if lookup:
                symbol = self.core.add_symbol_form(symbol.uid, lookup)
            candidates = [
                t
                for t in self.core.store.find_templates_by_predicate(symbol.uid)
                if set(filled_roles).issubset(set(t.roles))
            ]
            if candidates:
                candidates.sort(key=lambda t: (len(t.roles), t.uid))
                best_size = len(candidates[0].roles)
                best = [t for t in candidates if len(t.roles) == best_size]
                if len(best) != 1:
                    raise TemplateResolutionError(
                        f"Ambiguous template for predicate {lookup!r} and roles "
                        f"{[r.value for r in filled_roles]}"
                    )
                return TemplateResolution(best[0], False)
        else:
            symbol = self.core.add_abstract_symbol({lookup})

        template = self.core.add_template(
            self.template_domain,
            self.core.ref(symbol.uid),
            tuple(dict.fromkeys(filled_roles)),
        )
        return TemplateResolution(template, True)
