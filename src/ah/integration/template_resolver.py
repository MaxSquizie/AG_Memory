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
    predicate hint exists, that stable lexical form is used as the predicate S
    referenced by T. adaptive_v3 derives it deterministically from source-language
    morphology instead of asking the LLM to invent a semantic label.

    This introduces no new canonical field into S: the normalized lexical form is
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
        proposed = predicate.template_candidate
        if proposed is not None and not set(filled_roles).issubset(set(proposed.roles)):
            raise TemplateResolutionError(
                f"TemplateCandidate for predicate {lookup!r} does not cover filled roles "
                f"{[r.value for r in filled_roles]}"
            )
        required_roles = proposed.roles if proposed is not None else filled_roles
        symbol = self.core.store.find_symbol_by_form(lookup)
        if symbol is None and predicate.surface.strip():
            symbol = self.core.store.find_symbol_by_form(predicate.surface.strip())
            if symbol is not None and lookup:
                symbol = self.core.add_symbol_form(symbol.uid, lookup)

        # S is one lexical/paradigmatic symbol.  Whichever form found it, register
        # both the deterministic normal form and the observed predicate surface on
        # that same <UID,R> object.  No separate lemma field is introduced.
        if symbol is not None:
            for form in (lookup, predicate.surface.strip()):
                if form and form not in symbol.forms:
                    symbol = self.core.add_symbol_form(symbol.uid, form)
            candidates = [
                t
                for t in self.core.store.find_templates_by_predicate(symbol.uid)
                if set(required_roles).issubset(set(t.roles))
            ]
            if candidates:
                candidates.sort(key=lambda t: (len(t.roles), t.uid))
                best_size = len(candidates[0].roles)
                best = [t for t in candidates if len(t.roles) == best_size]
                if len(best) != 1:
                    raise TemplateResolutionError(
                        f"Ambiguous template for predicate {lookup!r} and role schema "
                        f"{[r.value for r in required_roles]}"
                    )
                return TemplateResolution(best[0], False)
        if proposed is None:
            raise TemplateResolutionError(
                f"Cannot create template for predicate {lookup!r} without TemplateCandidate"
            )

        if symbol is None:
            forms = {lookup}
            if predicate.surface.strip():
                forms.add(predicate.surface.strip())
            symbol = self.core.add_abstract_symbol(forms)

        template = self.core.add_template(
            self.template_domain,
            self.core.ref(symbol.uid),
            proposed.roles,
        )
        return TemplateResolution(template, True)
