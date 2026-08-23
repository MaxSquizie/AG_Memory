from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ah.model import ActantRole
from ah.perception import (
    PerceptionParseError,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    TemplateSelection,
)


class TemplatePerception(Protocol):
    def propose_template_candidate(self, source_text, predicate, filled_roles, role_bindings=()) -> TemplateCandidate: ...
    def resolve_template_sense(self, source_text, predicate, filled_roles, role_bindings, options) -> str | None: ...


class TemplateCompletionService:
    """Public occurrence-local T/sense completion shared by live turns and imports."""
    def __init__(self, integration, perception: TemplatePerception) -> None:
        self.integration = integration
        self.perception = perception

    @staticmethod
    def apply_resolutions(
        result: PerceptionResult,
        candidates: dict[PredicateCandidate, TemplateCandidate],
        selections: dict[PredicateCandidate, TemplateSelection],
    ) -> PerceptionResult:
        def resolve_predicate(predicate: PredicateCandidate) -> PredicateCandidate:
            candidate = candidates.get(predicate, predicate.template_candidate)
            selection = selections.get(predicate, predicate.template_selection)
            if candidate is predicate.template_candidate and selection is predicate.template_selection:
                return predicate
            return replace(predicate, template_candidate=candidate, template_selection=selection)

        def resolve_assertion(assertion):
            return replace(
                assertion,
                predicate=resolve_predicate(assertion.predicate),
                alternatives=tuple(resolve_assertion(item) for item in assertion.alternatives),
            )

        return replace(
            result,
            assertions=tuple(resolve_assertion(item) for item in result.assertions),
            queries=tuple(replace(item, predicate=resolve_predicate(item.predicate)) for item in result.queries),
            commands=tuple(replace(item, predicate=resolve_predicate(item.predicate)) for item in result.commands),
        )

    def _reconcile_selected_query_roles(self, result: PerceptionResult) -> PerceptionResult:
        """Constrain known query fillers by the already-selected canonical T.

        A query is not evidence that an arbitrary model-labelled known filler adds
        a new irreversible valency to an existing template.  When a known query
        filler was assigned a role outside the selected T, deterministic schema
        knowledge first narrows replacement roles to unused slots of that T.  If
        several remain, Perception performs one tiny UID-free semantic decision.
        Requested WH roles are excluded from replacement candidates because they
        denote the missing slot, not a known filler.
        """
        reconcile = getattr(self.perception, "resolve_actant_role", None)
        changed = False
        queries = []
        for query in result.queries:
            selection = query.predicate.template_selection
            if selection is None or selection.existing_template_uid is None:
                queries.append(query)
                continue
            try:
                template = self.integration.core.store.get_template(
                    selection.existing_template_uid
                )
            except (AttributeError, KeyError):
                queries.append(query)
                continue
            schema_roles = set(template.roles)
            requested = set(query.requested_roles)
            used = {
                actant.role for actant in query.actants
                if actant.role in schema_roles
            }
            new_actants = list(query.actants)
            query_changed = False
            for index, actant in enumerate(tuple(new_actants)):
                if actant.role in schema_roles:
                    continue
                candidates = tuple(
                    role for role in ActantRole
                    if role in schema_roles and role not in requested and role not in used
                )
                if not candidates:
                    # Fail closed later in QueryGoalBuilder; never mutate T merely
                    # to accommodate an unconstrained query-side role label.
                    continue
                if len(candidates) == 1:
                    resolved_role = candidates[0]
                else:
                    if not callable(reconcile):
                        continue
                    target = actant.lookup_text or actant.mention or ""
                    if not target.strip():
                        continue
                    resolved_role = reconcile(
                        result.source_text, query.predicate, target, candidates
                    )
                    if resolved_role not in candidates:
                        raise PerceptionParseError(
                            "Query actant role reconciliation escaped selected T roles"
                        )
                new_actants[index] = replace(actant, role=resolved_role)
                used.add(resolved_role)
                query_changed = True
            if query_changed:
                query = replace(query, actants=tuple(new_actants))
                changed = True
            queries.append(query)
        if not changed:
            return result
        return replace(result, queries=tuple(queries))

    def complete(self, result: PerceptionResult) -> PerceptionResult:
        requests = self.integration.template_requests(result)
        if not requests:
            return self._reconcile_selected_query_roles(result)
        proposer = getattr(self.perception, "propose_template_candidate", None)
        sense_resolver = getattr(self.perception, "resolve_template_sense", None)
        candidates: dict[PredicateCandidate, TemplateCandidate] = {}
        selections: dict[PredicateCandidate, TemplateSelection] = {}
        for request in requests:
            predicate = request.predicate
            if request.sense_options:
                # Once deterministic role narrowing leaves one existing T, no
                # semantic model call is needed. Preserve the same local-label ->
                # canonical-UID mapping contract while making the common polar-query
                # path deterministic.
                if len(request.sense_options) == 1:
                    decision = request.sense_options[0].label
                else:
                    if sense_resolver is None:
                        raise PerceptionParseError(f"Predicate {predicate.lookup_form!r} requires lexical-sense resolution")
                    decision = sense_resolver(
                        request.source_context,
                        predicate,
                        request.filled_roles,
                        request.role_bindings,
                        tuple((option.label, option.description) for option in request.sense_options),
                    )
                if decision is None:
                    raise PerceptionParseError(f"Lexical sense is explicitly ambiguous for predicate {predicate.lookup_form!r}")
                if decision == "NEW":
                    candidate = predicate.template_candidate
                    if candidate is None:
                        if proposer is None:
                            raise PerceptionParseError(f"New lexical sense for {predicate.lookup_form!r} requires TemplateCandidate proposal")
                        candidate = proposer(request.source_context, predicate, request.filled_roles, request.role_bindings)
                    if not isinstance(candidate, TemplateCandidate):
                        raise PerceptionParseError("Perception template proposer returned an invalid result")
                    candidates[predicate] = candidate
                    selections[predicate] = TemplateSelection(create_new=True)
                    continue
                option = next((item for item in request.sense_options if item.label == decision), None)
                if option is None:
                    raise PerceptionParseError(f"Template sense resolver returned invalid local label {decision!r}")
                selections[predicate] = TemplateSelection(existing_template_uid=option.template_uid)
                continue
            if predicate.template_candidate is not None:
                continue
            if proposer is None:
                raise PerceptionParseError(f"Unknown predicate {predicate.lookup_form!r} requires TemplateCandidate proposal")
            candidate = proposer(request.source_context, predicate, request.filled_roles, request.role_bindings)
            if not isinstance(candidate, TemplateCandidate):
                raise PerceptionParseError("Perception template proposer returned an invalid result")
            candidates[predicate] = candidate
        completed = self.apply_resolutions(result, candidates, selections)
        return self._reconcile_selected_query_roles(completed)
