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
        """Resolve or monotonically expand one canonical T from explicit roles.

        ``filled_roles`` is validated semantic evidence from the current assertion,
        query or command.  Canonical valency may only grow from that evidence; an
        unfilled role guessed by Perception is never allowed to become irreversible
        schema state.  Existing N remain valid because a concrete N may fill any
        subset of its T roles.

        Legacy memories may contain several T for one lexical S.  We reuse a unique
        compatible T when possible, but we never guess which of several incompatible
        legacy frames should be evolved.
        """
        lookup = predicate.lookup_form
        proposed = predicate.template_candidate
        explicit_roles = tuple(
            role for role in ActantRole if role in set(filled_roles)
        )
        explicit_set = set(explicit_roles)

        if proposed is not None:
            proposed_set = set(proposed.roles)
            if not explicit_set.issubset(proposed_set):
                raise TemplateResolutionError(
                    f"TemplateCandidate for predicate {lookup!r} does not cover filled roles "
                    f"{[r.value for r in explicit_roles]}"
                )

        symbol = self.core.store.find_symbol_by_form(lookup)
        if symbol is None and predicate.surface.strip():
            symbol = self.core.store.find_symbol_by_form(predicate.surface.strip())
            if symbol is not None and lookup:
                symbol = self.core.add_symbol_form(symbol.uid, lookup)

        # S is one lexical/paradigmatic symbol. Whichever form found it, register
        # both the deterministic normal form and the observed predicate surface on
        # that same <UID,R> object. No separate lemma field is introduced.
        if symbol is not None:
            for form in (lookup, predicate.surface.strip()):
                if form and form not in symbol.forms:
                    symbol = self.core.add_symbol_form(symbol.uid, form)

            existing = list(self.core.store.find_templates_by_predicate(symbol.uid))
            if existing:
                compatible = [
                    t for t in existing if explicit_set.issubset(set(t.roles))
                ]
                if compatible:
                    compatible.sort(key=lambda t: (len(t.roles), t.uid))
                    best_size = len(compatible[0].roles)
                    best = [t for t in compatible if len(t.roles) == best_size]
                    if len(best) != 1:
                        raise TemplateResolutionError(
                            f"Ambiguous canonical T for predicate {lookup!r} and filled roles "
                            f"{[r.value for r in explicit_roles]}"
                        )
                    return TemplateResolution(best[0], False)

                # Controlled valency evolution is safe only when there is exactly one
                # canonical frame to evolve.  With several legacy frames this becomes
                # a lexical-sense decision and must fail closed instead of merging them.
                if len(existing) != 1:
                    raise TemplateResolutionError(
                        f"Cannot choose one of {len(existing)} canonical T frames for "
                        f"predicate {lookup!r} to add roles "
                        f"{[r.value for r in explicit_roles]}"
                    )

                current = existing[0]
                expanded = self.core.expand_template_roles(current.uid, explicit_roles)
                return TemplateResolution(expanded, False)

        if proposed is None:
            raise TemplateResolutionError(
                f"Cannot create template for predicate {lookup!r} without TemplateCandidate"
            )

        if symbol is None:
            forms = {lookup}
            if predicate.surface.strip():
                forms.add(predicate.surface.strip())
            symbol = self.core.add_abstract_symbol(forms)

        # The candidate proves Perception acknowledged the explicit schema, but only
        # explicit roles are committed.  Future validated occurrences may expand T.
        template = self.core.add_template(
            self.template_domain,
            self.core.ref(symbol.uid),
            explicit_roles,
        )
        return TemplateResolution(template, True)
