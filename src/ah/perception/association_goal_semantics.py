from __future__ import annotations

from dataclasses import replace

from .association_semantics import (
    AssociationActRelationCandidate,
    AssociationProbeError,
)
from .contracts import CommandCandidate, PerceptionResult, QueryCandidate
from .goal_semantics import GoalSemanticService as _BaseGoalSemanticService
from .llm_parser import PerceptionParseError


class AssociationGoalSemanticService(_BaseGoalSemanticService):
    """Add one typed association-intent decision after ordinary relation typing.

    Structural parsing owns endpoint structure. A bounded semantic micro-probe only
    decides whether the current act requests associative convergence and, if so,
    which parser-local endpoints participate. Canonical refs remain unavailable at
    this layer.

    Association classification is an optional semantic overlay on an already parsed
    query/command. If the bounded probe explicitly returns UNKNOWN, fail closed only
    for the association operation: do not attach an ASSOCIATION marker, but preserve
    the completed ordinary speech act. Transport/protocol failures still propagate.
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

    @staticmethod
    def _explicit_unknown(exc: BaseException) -> bool:
        probe_error: AssociationProbeError | None = None
        if isinstance(exc, AssociationProbeError):
            probe_error = exc
        elif isinstance(exc, PerceptionParseError) and isinstance(
            exc.__cause__, AssociationProbeError
        ):
            probe_error = exc.__cause__
        if probe_error is None or not probe_error.attempts:
            return False
        return probe_error.attempts[-1].normalized_answer == "UNKNOWN"

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
            try:
                decision = classify(completed.source_text, root)
            except (AssociationProbeError, PerceptionParseError) as exc:
                # UNKNOWN is uncertainty about the optional association overlay, not
                # evidence that an already well-formed ordinary query is invalid.
                # Keeping no ASSOCIATION marker is the conservative/fail-closed
                # outcome. Backend/protocol failures are not semantic uncertainty
                # and must remain visible to the caller.
                if self._explicit_unknown(exc):
                    continue
                raise
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
