from __future__ import annotations

from dataclasses import replace

from .contracts import (
    ActRelationCandidate,
    CommandCandidate,
    PerceptionResult,
    QueryCandidate,
)
from .goal_semantics import GoalSemanticService as _BaseGoalSemanticService


class AssociationGoalSemanticService(_BaseGoalSemanticService):
    """Add one typed association-intent decision after ordinary relation typing.

    Structural parsing has already supplied the act, predicate and semantic roles.
    Deterministic narrowing admits only acts with at least two explicit entity-like
    actants. A bounded perception micro-probe then decides whether the user's goal is
    associative convergence between two of those local endpoints. The result is
    represented as runtime-only ActRelationCandidate("ASSOCIATION", ...); it is never
    materialized as an asserted canonical L relation.
    """

    @staticmethod
    def _eligible(root: QueryCandidate | CommandCandidate) -> bool:
        if root.local_id is None or root.quoted:
            return False
        if isinstance(root, QueryCandidate) and root.quantified is not None:
            return False
        if isinstance(root, CommandCandidate) and root.negated:
            return False
        roles = {
            actant.role
            for actant in root.actants
            if (
                actant.proposition is None
                and actant.composition is None
                and actant.candidate_ref is None
                and bool(actant.lookup_text)
            )
        }
        return len(roles) >= 2

    def complete(self, result: PerceptionResult) -> PerceptionResult:
        completed = super().complete(result)
        classify = getattr(self.classifier, "classify_association_query", None)
        if not callable(classify):
            return completed

        relations = list(completed.act_relations)
        covered = {item.act_ref for item in relations}
        changed = False
        for root in (*completed.queries, *completed.commands):
            if not self._eligible(root) or root.local_id in covered:
                continue
            decision = classify(completed.source_text, root)
            if decision is None:
                continue

            eligible_roles = {
                actant.role
                for actant in root.actants
                if (
                    actant.proposition is None
                    and actant.composition is None
                    and actant.candidate_ref is None
                    and bool(actant.lookup_text)
                )
            }
            left_role = getattr(decision, "left_role", None)
            right_role = getattr(decision, "right_role", None)
            if left_role not in eligible_roles or right_role not in eligible_roles:
                raise ValueError(
                    "association semantic decision escaped eligible actant roles"
                )
            relation = ActRelationCandidate(
                "ASSOCIATION",
                root.local_id,
                left_role,
                right_role,
            )
            relations.append(relation)
            covered.add(root.local_id)
            changed = True

        if not changed:
            return completed
        return replace(completed, act_relations=tuple(relations))
