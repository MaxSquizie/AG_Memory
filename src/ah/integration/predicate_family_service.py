from __future__ import annotations

from ah.perception.morphology import material_analyses

from .identity_query_service import IdentityQueryIntegrationService


_VERBAL_POS = {"VERB", "INFN", "PRTF", "PRTS", "GRND"}

# Candidate generation only.  These prefixes are never treated as semantic proof
# that two predicates are equivalent: they merely expose a small family-neighbour
# set to the existing bounded template-sense resolver, which may still choose NEW.
# Longest first prevents e.g. "пере-" from being reduced as "пе-" by accident.
_ASPECTUAL_PREFIXES = tuple(
    sorted(
        {
            "вз", "воз", "вы", "до", "за", "из", "на", "над", "об", "от",
            "пере", "по", "под", "при", "про", "раз", "с", "у",
        },
        key=len,
        reverse=True,
    )
)


def _verbal_profile(morphology, form: str):
    try:
        analyses = material_analyses(tuple(morphology.analyze_all(form)))
    except (AttributeError, TypeError):
        single = morphology.analyze(form)
        analyses = () if single is None else (single,)
    verbal = tuple(item for item in analyses if item.pos in _VERBAL_POS)
    if not verbal:
        return None
    normals = {item.normal_form.casefold() for item in verbal if item.normal_form.strip()}
    if len(normals) != 1:
        return None
    aspects = {
        aspect
        for item in verbal
        for aspect in ("perf", "impf")
        if aspect in item.grammemes
    }
    transitivity = {
        item.transitivity
        for item in verbal
        if item.transitivity in {"tran", "intr"}
    }
    return next(iter(normals)), frozenset(aspects), frozenset(transitivity)


class PredicateFamilyIntegrationService(IdentityQueryIntegrationService):
    """Expose conservative derivational neighbours for predicate-template reuse.

    Canonical S identity remains lexical: ``видеть`` and ``увидеть`` may stay
    different symbols.  This adapter affects only template candidate retrieval.
    When the current predicate has no exact lexical S, a bounded set of dictionary-
    valid aspectual-prefix neighbours already present in memory is returned as sense
    candidates.  TemplateCompletionService then *must* ask the semantic resolver
    before reusing such a cross-lexeme T, so pairs like ``писать``/``подписать`` are
    free to remain different while true aspectual variants may converge to one T.
    """

    def _template_sense_description(self, template) -> str:
        base = super()._template_sense_description(template)
        try:
            symbol = self.core.store.get_symbol(template.predicate.uid)
            form = sorted(
                (str(item).strip() for item in symbol.forms if str(item).strip()),
                key=lambda item: (len(item), item.casefold()),
            )[0]
        except (AttributeError, KeyError, IndexError, ValueError):
            return base
        return f"predicate: {form}; {base}"

    def _predicate_symbol_candidates(self, predicate) -> tuple:
        exact = super()._predicate_symbol_candidates(predicate)
        if exact:
            return exact

        lookup = predicate.lookup_form.strip().casefold()
        if not lookup:
            return ()
        current = _verbal_profile(self._discourse_morphology, lookup)
        if current is None:
            return ()
        current_lemma, current_aspects, current_transitivity = current

        candidate_forms: list[str] = []

        # Perfective-looking form -> possible unprefixed family base.
        for prefix in _ASPECTUAL_PREFIXES:
            if current_lemma.startswith(prefix) and len(current_lemma) - len(prefix) >= 3:
                candidate_forms.append(current_lemma[len(prefix) :])

        # Imperfective/base form -> only prefixed forms that already exist as S are
        # probed; this is an index lookup, not a global vocabulary scan.
        for prefix in _ASPECTUAL_PREFIXES:
            candidate_forms.append(prefix + current_lemma)

        found: dict[str, object] = {}
        seen_forms: set[str] = set()
        for form in candidate_forms:
            folded = form.casefold()
            if folded == current_lemma or folded in seen_forms:
                continue
            seen_forms.add(folded)
            symbols = self.core.store.find_symbols_by_form(form)
            if not symbols:
                continue
            other = _verbal_profile(self._discourse_morphology, form)
            if other is None:
                continue
            _other_lemma, other_aspects, other_transitivity = other

            # The candidate must look like an aspectual contrast rather than just a
            # prefixed homograph.  This still does not assert semantic equivalence.
            if (
                current_aspects
                and other_aspects
                and not current_aspects.isdisjoint(other_aspects)
            ):
                continue
            if (
                current_transitivity
                and other_transitivity
                and current_transitivity.isdisjoint(other_transitivity)
            ):
                continue
            for symbol in symbols:
                found[symbol.uid] = symbol

        return tuple(found[uid] for uid in sorted(found))
