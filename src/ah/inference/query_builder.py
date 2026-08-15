from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import Ref
from ah.perception import QueryCandidate, QueryMode

from ah.integration.entity_resolver import EntityResolver, ExistingEntity

from .contracts import ExistsGoal, InferenceGoal, RoleFillGoal


@dataclass(frozen=True, slots=True)
class QueryBuildResult:
    goal: InferenceGoal | None
    diagnostics: tuple[str, ...] = ()


class QueryGoalBuilder:
    """Read-only QueryCandidate -> inference goal normalization for role/exists QA."""

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def build(self, query: QueryCandidate, context: InteractionContext) -> QueryBuildResult:
        symbol = self.core.store.find_symbol_by_form(query.predicate.lookup_form)
        if symbol is None:
            return QueryBuildResult(None, ("predicate_not_found",))
        required_roles = {a.role for a in query.actants}
        if query.requested_role is not None:
            required_roles.add(query.requested_role)
        templates = [
            t for t in self.core.store.find_templates_by_predicate(symbol.uid)
            if required_roles.issubset(set(t.roles))
        ]
        if len(templates) != 1:
            return QueryBuildResult(None, ("template_not_unique",))
        template = templates[0]

        resolver = EntityResolver(self.core)
        known: dict = {}
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

        tref = self.core.ref(template.uid)
        if query.query_mode is QueryMode.FILL_ROLE:
            if query.requested_role is None:
                return QueryBuildResult(None, ("requested_role_missing",))
            return QueryBuildResult(RoleFillGoal(tref, known, query.requested_role))
        return QueryBuildResult(ExistsGoal(tref, known))
