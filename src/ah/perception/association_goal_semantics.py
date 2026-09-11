from __future__ import annotations

from dataclasses import replace

from .association_semantics import AssociationActRelationCandidate
from .contracts import CommandCandidate, PerceptionResult, QueryCandidate
from .goal_semantics import GoalSemanticService as _BaseGoalSemanticService


class AssociationGoalSemanticService(_BaseGoalSemanticService):
    """Add one typed association-intent decision after ordinary relation typing.

    Structural parsing owns endpoint structure. A bounded semantic micro-probe only
    decides whether the current act requests associative convergence and, if so,
    which parser-local endpoints participate. Canonical refs remain unavailable at
    this layer.
    """

    @staticmethod
    def _eligible(root: QueryCandidate | CommandCandidate) -> bool:
        if root.local_id is None or root.quoted:
            return False
        if isinstance(root, QueryCandidate) and root.quantified is not None:
            return False
        if isinstance(root, CommandCandidate) and root.negated:
            return False
        return bool(root.actants)

    def complete(self, result: PerceptionResult) -> PerceptionResult:
        completed = super().complete(result)
        classify = getattr(self.classifier, "classify_association_query", None)
        if not callable(classify):
            return completed

        relations = list(completed.act_relations)
        # IS-A or another future intra-act relation does not consume association
        # intent. Only an already typed ASSOCIATION marker suppresses a duplicate.
        covered = {
            item.act_ref
            for item in relations
            if item.canonical_relation_id == "ASSOCIATION"
        }
        changed = False
        for root in (*completed.queries, *completed.commands):
            if not self._eligible(root) or root.local_id in covered:
                continue
            decision = classify(completed.source_text, root)
            if decision is None:
                continue

            relation = AssociationActRelationCandidate(
                "ASSOCIATION",
                root.local_id,
                decision.left.role,
                decision.right.role,
                source_member_index=decision.left.member_index,
                target_member_index=decision.right.member_index,
            )
            relations.append(relation)
            covered.add(root.local_id)
            changed = True

        if not changed:
            return completed
        return replace(completed, act_relations=tuple(relations))
