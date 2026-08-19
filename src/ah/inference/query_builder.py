from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import Ref
from ah.perception import QueryCandidate, QueryMode

from ah.integration.entity_resolver import EntityResolver, ExistingEntity

from .contracts import ExistsGoal, GoalSpec, InferenceQuery, MultiRoleFillGoal, RoleFillGoal


@dataclass(frozen=True, slots=True)
class QueryBuildResult:
    goal: InferenceQuery | None
    diagnostics: tuple[str, ...] = ()
    # Runtime attention anchors discovered while resolving the query. This may
    # include the resolved referent and canonical supporting facts used by a
    # relational description (e.g. USER + ДРУГ -> N_ЕСТЬ -> МИША).
    attention_refs: tuple[Ref, ...] = ()


class QueryGoalBuilder:
    """Read-only QueryCandidate -> inference goal normalization for role/exists QA."""

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def _predicate_symbol_candidates(self, query: QueryCandidate):
        predicate = query.predicate
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

    def build(self, query: QueryCandidate, context: InteractionContext) -> QueryBuildResult:
        required_roles = {a.role for a in query.actants}
        required_roles.update(query.requested_roles)
        selection = query.predicate.template_selection
        if selection is not None and selection.existing_template_uid is not None:
            # Sense resolution already happened against local UID-free options.
            # Trust the deterministic mapping, not another form->S->roles guess.
            try:
                template = self.core.store.get_template(selection.existing_template_uid)
                symbol = self.core.store.get_symbol(template.predicate.uid)
            except KeyError:
                return QueryBuildResult(None, ("selected_template_not_found",))
            lookup_forms = {item.casefold() for item in symbol.forms}
            surface = query.predicate.surface.strip()
            lookup = query.predicate.lookup_form.casefold()
            normalized_is_distinct = (
                query.predicate.normalized_hint is not None
                and surface
                and surface.casefold() != lookup
            )
            if normalized_is_distinct:
                predicate_matches = lookup in lookup_forms
            else:
                predicate_matches = (
                    lookup in lookup_forms
                    or surface.casefold() in lookup_forms
                )
            if not predicate_matches:
                return QueryBuildResult(None, ("selected_template_predicate_mismatch",))
            if not required_roles.issubset(set(template.roles)):
                return QueryBuildResult(None, ("selected_template_role_mismatch",))
        else:
            symbols = self._predicate_symbol_candidates(query)
            if not symbols:
                return QueryBuildResult(None, ("predicate_not_found",))
            templates = [
                t
                for symbol in symbols
                for t in self.core.store.find_templates_by_predicate(symbol.uid)
                if required_roles.issubset(set(t.roles))
            ]
            if len(templates) != 1:
                return QueryBuildResult(None, ("template_not_unique",))
            template = templates[0]

        resolver = EntityResolver(self.core)
        known: dict = {}
        attention_refs: list[Ref] = []
        for actant in query.actants:
            if actant.candidate_ref is not None:
                return QueryBuildResult(None, ("query_candidate_ref_not_supported_here",))
            resolution = resolver.resolve(
                actant,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
            )
            if not isinstance(resolution, ExistingEntity):
                return QueryBuildResult(None, (f"unresolved_actant:{actant.role.value}",))
            known[actant.role] = resolution.ref
            for ref in (resolution.ref, *resolution.support_refs):
                if all(existing.uid != ref.uid for existing in attention_refs):
                    attention_refs.append(ref)

        tref = self.core.ref(template.uid)
        if query.query_mode is QueryMode.FILL_ROLE:
            if not query.requested_roles:
                return QueryBuildResult(None, ("requested_roles_missing",))
            if len(query.requested_roles) == 1:
                return QueryBuildResult(InferenceQuery(GoalSpec(RoleFillGoal(tref, known, query.requested_roles[0]))), attention_refs=tuple(attention_refs))
            return QueryBuildResult(InferenceQuery(GoalSpec(MultiRoleFillGoal(tref, known, query.requested_roles))), attention_refs=tuple(attention_refs))
        return QueryBuildResult(InferenceQuery(GoalSpec(ExistsGoal(tref, known))), attention_refs=tuple(attention_refs))
