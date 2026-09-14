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
    """M2 renderer for explicit ASSOCIATION convergence obligations.

    Association search is not semantic entailment. The live orchestrator exposes a
    diagnostic ``InferenceOutcome`` with GoalSpec.mode=ASSOCIATION so the operator
    can audit whether both activation fronts really converged. The ancestry is shown
    as association-search steps, never re-labelled as logical L-rule applications.
    """

    @staticmethod
    def _is_association(outcome: InferenceOutcome) -> bool:
        return (
            outcome.goal_spec is not None
            and outcome.goal_spec.mode is GoalMode.ASSOCIATION
            and isinstance(outcome.goal_spec.target, AssociationGoal)
        )

    def _association_steps(
        self,
        outcome: InferenceOutcome,
        goal: AssociationGoal,
    ) -> tuple[ProofStepSnapshot, ...]:
        steps: list[ProofStepSnapshot] = []
        for event in outcome.cognitive_trace:
            rule_id = event.rule_id or ""
            if not rule_id.startswith("ASSOCIATION:"):
                continue
            relation = rule_id.split(":", 1)[1]
            source_uid = event.query_key
            target = event.ref
            if source_uid is None or target is None:
                continue
            try:
                source_text = self._text(self.core.ref(source_uid))
            except Exception:
                source_text = source_uid
            target_text = self._text(target)
            front = event.detail.split(":", 1)[0] if event.detail else "PATH"
            steps.append(
                ProofStepSnapshot(
                    len(steps) + 1,
                    f"ASSOCIATION / {relation}",
                    source_uid,
                    None,
                    target.uid,
                    f"{front}: «{source_text}» → «{target_text}»; "
                    "это шаг bounded activation/incidence search, не правило логического вывода.",
                )
            )

        if outcome.conclusion is not None and outcome.status.value == "PROVED":
            common_ref = getattr(outcome.conclusion, "ref", None)
            common_uid = None if common_ref is None else common_ref.uid
            common_text = (
                "неизвестная репрезентация"
                if common_ref is None
                else self._text(common_ref)
            )
            steps.append(
                ProofStepSnapshot(
                    len(steps) + 1,
                    "ASSOCIATION / CONVERGENCE",
                    goal.left.uid,
                    None,
                    common_uid,
                    f"Фронты от «{self._text(goal.left)}» и «{self._text(goal.right)}» "
                    f"сошлись на «{common_text}». Ассоциация действительно найдена; "
                    "новый семантический факт этим не утверждается.",
                )
            )
        return tuple(steps)

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
            # Association path hops include reverse/incidence runtime transitions.
            # They are intentionally rendered as steps rather than fake canonical L.
            edges=(),
            steps=self._association_steps(outcome, goal),
            checks=tuple(checks),
            diagnostics=tuple(outcome.diagnostics),
            cognitive_events=self._cognitive_events(outcome),
        )
