from __future__ import annotations

from typing import Iterable

from ah.inference.contracts import AssociationGoal, GoalMode, InferenceOutcome

from .inference_proof import (
    ProofCheck,
    ProofChainSnapshot,
    ProofSnapshotBuilder as _BaseProofSnapshotBuilder,
    ProofStepSnapshot,
)


class ProofSnapshotBuilder(_BaseProofSnapshotBuilder):
    """M2 proof renderer with an explicit ASSOCIATION convergence obligation.

    Association search is not semantic entailment.  The live orchestrator nevertheless
    exposes a diagnostic ``InferenceOutcome`` whose GoalSpec has mode ASSOCIATION so
    the operator can audit whether both activation fronts really converged instead of
    seeing an ordinary ``UNRESOLVED`` query.  This renderer keeps that distinction
    visible and deliberately does not reinterpret incidence/activation hops as logical
    L-rule applications.
    """

    @staticmethod
    def _is_association(outcome: InferenceOutcome) -> bool:
        return (
            outcome.goal_spec is not None
            and outcome.goal_spec.mode is GoalMode.ASSOCIATION
            and isinstance(outcome.goal_spec.target, AssociationGoal)
        )

    def build(
        self,
        outcome: InferenceOutcome,
        *,
        chain_id: str,
        source: str,
        title: str,
        checks: Iterable[ProofCheck] = (),
    ) -> ProofChainSnapshot:
        if not self._is_association(outcome):
            return super().build(
                outcome,
                chain_id=chain_id,
                source=source,
                title=title,
                checks=checks,
            )

        assert outcome.goal_spec is not None
        goal = outcome.goal_spec.target
        assert isinstance(goal, AssociationGoal)
        trace = tuple(outcome.uid_trace)
        nodes = self._nodes(trace)
        found = outcome.conclusion is not None and outcome.status.value == "PROVED"

        if found:
            common_ref = getattr(outcome.conclusion, "ref", None)
            common_uid = None if common_ref is None else common_ref.uid
            common_text = (
                "неизвестная репрезентация"
                if common_ref is None
                else self._text(common_ref)
            )
            explanation = (
                f"Два ограниченных фронта активации от «{self._text(goal.left)}» и "
                f"«{self._text(goal.right)}» сошлись на канонической репрезентации "
                f"«{common_text}». Это подтверждает факт найденной ассоциации в "
                "runtime-поиске; это не доказательство нового семантического факта."
            )
            steps = (
                ProofStepSnapshot(
                    1,
                    "ASSOCIATION / CONVERGENCE",
                    goal.left.uid,
                    None,
                    common_uid,
                    explanation,
                ),
            )
        else:
            steps = ()

        return ProofChainSnapshot(
            chain_id=chain_id,
            source=source,
            title=title,
            status=outcome.status.value,
            stop_reason=outcome.stop_reason.value,
            logical_depth=outcome.logical_depth,
            expanded_states=outcome.expanded_states,
            goal_text=(
                "найти ассоциативную сходимость между "
                f"«{self._text(goal.left)}» и «{self._text(goal.right)}»"
            ),
            conclusion_text=self._conclusion_text(outcome),
            trace_uids=tuple(ref.uid for ref in trace),
            nodes=nodes,
            # Incidence/propagation provenance is not a logical L proof.  The UID
            # trace and node overlay remain available without drawing fake rule edges.
            edges=(),
            steps=steps,
            checks=tuple(checks),
            diagnostics=tuple(outcome.diagnostics),
            cognitive_events=self._cognitive_events(outcome),
        )
