from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole

from .association_semantics import (
    AssociationActRelationCandidate,
    AssociationProbeError,
)
from .contracts import ActantCandidate, CommandCandidate, PerceptionResult, QueryCandidate
from .goal_semantics import GoalSemanticService as _BaseGoalSemanticService
from .llm_parser import PerceptionParseError
from .query_semantics import EntityIdentityQueryCandidate


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

    _PARTICIPANT_ROLES = frozenset(
        {
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.RECIPIENT,
            ActantRole.SOURCE,
            ActantRole.ABSENTEE,
            ActantRole.AUXILLIARY,
        }
    )

    @staticmethod
    def _eligible(root: QueryCandidate | CommandCandidate) -> bool:
        if isinstance(root, EntityIdentityQueryCandidate):
            return False
        if root.local_id is None or root.quoted:
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

    @staticmethod
    def _endpoint_count(actants: tuple[ActantCandidate, ...]) -> int:
        count = 0
        for actant in actants:
            if actant.composition is not None:
                count += len(actant.composition.members)
            else:
                count += 1
        return count

    @classmethod
    def _association_probe_view(
        cls, root: QueryCandidate | CommandCandidate
    ) -> QueryCandidate | CommandCandidate:
        """Remove relation-description actants when two endpoint participants exist.

        Commonality questions are often structurally parsed as a copular shell such
        as BE(STATE=common, SUBJECT=A, OBJECT=B).  STATE is the requested relation
        description, not a third association endpoint.  Feeding all three actants to
        the bounded probe needlessly creates three endpoint-pair choices and caused
        obvious ``what do A and B have in common`` turns to be classified ORDINARY.

        This filter is role-structural, not lexical: it applies only when at least two
        participant endpoints are already available.  Otherwise every original
        actant remains visible so association between places/times/states still works.
        """
        participants = tuple(
            item for item in root.actants if item.role in cls._PARTICIPANT_ROLES
        )
        if cls._endpoint_count(participants) < 2:
            return root
        if participants == root.actants:
            return root
        return replace(root, actants=participants)

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
            probe_root = self._association_probe_view(root)
            try:
                decision = classify(completed.source_text, probe_root)
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
