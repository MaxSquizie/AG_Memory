from __future__ import annotations

from collections import deque
from typing import Iterable

from ah.inference.contracts import AssociationGoal, GoalMode, InferenceOutcome
from ah.model import FunctionSymbol, Group, Hypernode, Ref, RefKind, Template

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

    The raw runtime fronts can meet at structural hubs such as predicate S/template T.
    For operator diagnostics we additionally reconstruct the shared partial predicate
    frame from the supporting N facts already present in the frozen UID trace. This
    makes the visible result ``HAVE(SUBJECT=_, OBJECT=legs)`` rather than bare
    ``HAVE`` without inventing a canonical partial N.
    """

    @staticmethod
    def _is_association(outcome: InferenceOutcome) -> bool:
        return (
            outcome.goal_spec is not None
            and outcome.goal_spec.mode is GoalMode.ASSOCIATION
            and isinstance(outcome.goal_spec.target, AssociationGoal)
        )

    def _element(self, ref: Ref):
        if ref.kind in {RefKind.S, RefKind.L}:
            return None
        try:
            return self.core.store.get_element_any_domain(ref.uid)
        except Exception:
            return None

    def _contains(self, operand, target: Ref, seen: set[str] | None = None) -> bool:
        if not isinstance(operand, Ref):
            return False
        if operand == target:
            return True
        seen = set() if seen is None else seen
        if operand.uid in seen:
            return False
        seen.add(operand.uid)
        obj = self._element(operand)
        if isinstance(obj, Group):
            return any(self._contains(item, target, seen) for item in obj.members)
        if isinstance(obj, FunctionSymbol):
            return any(
                self._contains(item, target, seen)
                for item in obj.operands
                if isinstance(item, Ref)
            )
        return False

    @staticmethod
    def _relation_key(value: str) -> str:
        return value.upper().replace("_", "-")

    def _ancestors(self, origin: Ref) -> dict[str, tuple[Ref, int]]:
        found: dict[str, tuple[Ref, int]] = {origin.uid: (origin, 0)}
        queue = deque([(origin, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= 6:
                continue
            try:
                links = tuple(self.core.store.outgoing_links(current.uid))
            except Exception:
                links = ()
            for link in links:
                if link.weight <= 0 or self._relation_key(link.relation_id) != "IS-A":
                    continue
                next_depth = depth + 1
                old = found.get(link.target.uid)
                if old is not None and old[1] <= next_depth:
                    continue
                found[link.target.uid] = (link.target, next_depth)
                queue.append((link.target, next_depth))
        return found

    def _common_value(self, left, right) -> tuple[Ref, bool] | None:
        if not isinstance(left, Ref) or not isinstance(right, Ref):
            return None
        if left == right:
            return left, False
        la = self._ancestors(left)
        ra = self._ancestors(right)
        common = set(la) & set(ra)
        if not common:
            return None
        uid = min(
            common,
            key=lambda item: (
                la[item][1] + ra[item][1],
                max(la[item][1], ra[item][1]),
                item,
            ),
        )
        return la[uid][0], True

    def _association_frame_text(
        self,
        outcome: InferenceOutcome,
        goal: AssociationGoal,
    ) -> str | None:
        trace = tuple(outcome.uid_trace)
        indexed = {ref.uid: index for index, ref in enumerate(trace)}
        facts: list[tuple[Ref, Hypernode]] = []
        for ref in trace:
            if ref.kind is not RefKind.N:
                continue
            obj = self._element(ref)
            if isinstance(obj, Hypernode) and obj.weight > 0:
                facts.append((ref, obj))
        left = [
            item
            for item in facts
            if any(self._contains(value, goal.left) for value in item[1].actants.values())
        ]
        right = [
            item
            for item in facts
            if any(self._contains(value, goal.right) for value in item[1].actants.values())
        ]
        candidates: list[tuple[tuple, str]] = []
        for left_ref, left_node in left:
            for right_ref, right_node in right:
                if left_node.template != right_node.template:
                    continue
                template = self._element(left_node.template)
                if not isinstance(template, Template):
                    continue
                variable_roles = []
                for role in template.roles:
                    lv = left_node.actants.get(role)
                    rv = right_node.actants.get(role)
                    if lv is None or rv is None:
                        continue
                    if self._contains(lv, goal.left) and self._contains(rv, goal.right):
                        variable_roles.append(role)
                if not variable_roles:
                    continue
                rows: list[tuple[str, str, bool]] = []
                for role in template.roles:
                    if role in variable_roles:
                        rows.append((role.value, "_", False))
                        continue
                    lv = left_node.actants.get(role)
                    rv = right_node.actants.get(role)
                    if lv is None or rv is None:
                        continue
                    common = self._common_value(lv, rv)
                    if common is None:
                        continue
                    value, generalized = common
                    rendered = self._text(value)
                    rows.append((role.value, rendered, generalized))
                rows.sort(key=lambda row: row[0])
                predicate = self._text(template.predicate)
                rendered_rows = []
                fixed_count = 0
                exact_count = 0
                for role, value, generalized in rows:
                    if value != "_":
                        fixed_count += 1
                        if not generalized:
                            exact_count += 1
                    suffix = " [IS-A]" if generalized and value != "_" else ""
                    rendered_rows.append(f"{role}={value}{suffix}")
                text = f"{predicate}({', '.join(rendered_rows)})"
                distance = indexed.get(left_ref.uid, 10**6) + indexed.get(right_ref.uid, 10**6)
                key = (distance, -fixed_count, -exact_count, text)
                candidates.append((key, text))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

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
            frame_text = self._association_frame_text(outcome, goal)
            detail = (
                f" Структурная сходимость произошла на «{common_text}», но общая "
                f"семантическая схема поддерживающих фактов: «{frame_text}»."
                if frame_text is not None
                else f" Фронты сошлись на «{common_text}»."
            )
            steps.append(
                ProofStepSnapshot(
                    len(steps) + 1,
                    "ASSOCIATION / CONVERGENCE",
                    goal.left.uid,
                    None,
                    common_uid,
                    f"Фронты от «{self._text(goal.left)}» и «{self._text(goal.right)}» сошлись."
                    + detail
                    + " Ассоциация действительно найдена; новый семантический факт этим не утверждается.",
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
        frame_text = self._association_frame_text(outcome, goal)
        conclusion = (
            f"общая семантическая схема: {frame_text}"
            if frame_text is not None and outcome.status.value == "PROVED"
            else self._conclusion_text(outcome)
        )
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
            conclusion_text=conclusion,
            trace_uids=tuple(ref.uid for ref in trace),
            nodes=nodes,
            edges=(),
            steps=self._association_steps(outcome, goal),
            checks=tuple(checks),
            diagnostics=tuple(outcome.diagnostics),
            cognitive_events=self._cognitive_events(outcome),
        )
