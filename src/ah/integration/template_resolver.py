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

    def _symbol_candidates(self, predicate: PredicateCandidate):
        """Resolve lexical candidates without using a homographic surface as identity.

        When Perception supplied a distinct normalized lexeme, that form is the
        lexical key.  If no S owns it yet we return no candidate and let canonical
        creation make a new S containing both the normalized and observed forms.
        Falling back to an existing surface-only homograph here is precisely the
        merge bug this boundary must prevent.
        """
        lookup = predicate.lookup_form.strip()
        matches = self.core.store.find_symbols_by_form(lookup)
        if matches:
            return matches
        surface = predicate.surface.strip()
        if not surface:
            return ()
        if predicate.normalized_hint is not None and surface.casefold() != lookup.casefold():
            return ()
        return self.core.store.find_symbols_by_form(surface)

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

        Several T may legitimately belong to one lexical S, including distinct
        lexical senses with the same role schema. ``PredicateCandidate.sense_hint``
        is resolved by Perception against local UID-free T profiles; deterministic
        orchestration records that bounded decision as ``template_selection``.
        Without such a selection this resolver never guesses among several T.
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

        selection = predicate.template_selection
        if selection is not None and selection.existing_template_uid is not None:
            # The UID was not chosen by the LLM: Perception selected a local Cn
            # label and deterministic orchestration mapped that label to this T.
            # Validate the mapping again at the canonical write boundary.
            try:
                selected = self.core.store.get_template(selection.existing_template_uid)
            except KeyError as exc:
                raise TemplateResolutionError(
                    f"Selected template no longer exists for predicate {lookup!r}"
                ) from exc
            symbol = self.core.store.get_symbol(selected.predicate.uid)
            known_forms = {form.casefold() for form in symbol.forms}
            surface = predicate.surface.strip()
            normalized_is_distinct = (
                predicate.normalized_hint is not None
                and surface
                and surface.casefold() != lookup.casefold()
            )
            if normalized_is_distinct:
                selection_matches = lookup.casefold() in known_forms
            else:
                incoming_forms = {
                    form.casefold()
                    for form in (lookup, surface)
                    if form
                }
                selection_matches = bool(known_forms & incoming_forms)
            if not selection_matches:
                raise TemplateResolutionError(
                    f"Selected T does not belong to predicate forms for {lookup!r}"
                )
            for form in (lookup, predicate.surface.strip()):
                if form and form not in symbol.forms:
                    symbol = self.core.add_symbol_form(symbol.uid, form)
            if explicit_set.issubset(set(selected.roles)):
                return TemplateResolution(selected, False)
            expanded = self.core.expand_template_roles(selected.uid, explicit_roles)
            return TemplateResolution(expanded, False)

        force_new_sense = bool(selection is not None and selection.create_new)
        if force_new_sense and proposed is None:
            raise TemplateResolutionError(
                f"Distinct lexical sense for predicate {lookup!r} requires TemplateCandidate"
            )

        symbols = self._symbol_candidates(predicate)
        if len(symbols) > 1:
            raise TemplateResolutionError(
                f"Ambiguous lexical S for predicate {lookup!r}; "
                "an occurrence-local template/lexical selection is required"
            )
        symbol = symbols[0] if symbols else None

        # S is one lexical/paradigmatic symbol.  Once the lexical identity is
        # unambiguous, register both the resolved normal form and observed surface.
        # Overlapping surface forms are legal and therefore do not merge S nodes.
        if symbol is not None:
            for form in (lookup, predicate.surface.strip()):
                if form and form not in symbol.forms:
                    symbol = self.core.add_symbol_form(symbol.uid, form)

            existing = list(self.core.store.find_templates_by_predicate(symbol.uid))
            if existing and not force_new_sense:
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
