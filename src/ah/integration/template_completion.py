from __future__ import annotations

from dataclasses import replace
from typing import Protocol

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

    def complete(self, result: PerceptionResult) -> PerceptionResult:
        requests = self.integration.template_requests(result)
        if not requests:
            return result
        proposer = getattr(self.perception, "propose_template_candidate", None)
        sense_resolver = getattr(self.perception, "resolve_template_sense", None)
        candidates: dict[PredicateCandidate, TemplateCandidate] = {}
        selections: dict[PredicateCandidate, TemplateSelection] = {}
        for request in requests:
            predicate = request.predicate
            if request.sense_options:
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
        return self.apply_resolutions(result, candidates, selections)
