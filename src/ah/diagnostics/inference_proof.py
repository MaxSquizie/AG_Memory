from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference.contracts import (
    AllOfGoal,
    CauseEntailmentGoal,
    CounterfactualGoal,
    CompositeConclusion,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    FormulaGoal,
    ExistsGoal,
    InferenceOutcome,
    MultiRoleBindingConclusion,
    MultiRoleFillGoal,
    RelationGoal,
    RoleBindingConclusion,
    RoleFillGoal,
)
from ah.model import Link, Ref, RefKind
from ah.projection.semantic_projection import SemanticProjector


@dataclass(frozen=True, slots=True)
class ProofCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ProofNodeSnapshot:
    uid: str
    kind: str
    semantic: str
    domain: str | None


@dataclass(frozen=True, slots=True)
class ProofEdgeSnapshot:
    uid: str | None
    relation: str
    source_uid: str
    target_uid: str
    semantic: str


@dataclass(frozen=True, slots=True)
class ProofStepSnapshot:
    index: int
    rule: str
    premise_uid: str | None
    link_uid: str | None
    conclusion_uid: str | None
    explanation: str


@dataclass(frozen=True, slots=True)
class ProofChainSnapshot:
    chain_id: str
    source: str
    title: str
    status: str
    stop_reason: str
    logical_depth: int
    expanded_states: int
    goal_text: str
    conclusion_text: str
    trace_uids: tuple[str, ...]
    nodes: tuple[ProofNodeSnapshot, ...]
    edges: tuple[ProofEdgeSnapshot, ...]
    steps: tuple[ProofStepSnapshot, ...]
    checks: tuple[ProofCheck, ...] = ()
    diagnostics: tuple[str, ...] = ()
    cognitive_events: tuple[str, ...] = ()

    @property
    def node_uids(self) -> tuple[str, ...]:
        return tuple(node.uid for node in self.nodes)

    @property
    def edge_uids(self) -> tuple[str, ...]:
        return tuple(edge.uid for edge in self.edges if edge.uid)

    def semantic_text(self) -> str:
        lines = [
            f"Цель: {self.goal_text}",
            f"Исход: {self.status} / {self.stop_reason}",
            f"Логическая глубина: {self.logical_depth}",
            "",
        ]
        if self.steps:
            lines.append("Ход вывода:")
            lines.extend(f"{step.index}. [{step.rule}] {step.explanation}" for step in self.steps)
        else:
            lines.append("Ход вывода: канонический proof trace пуст.")
        lines.extend(("", f"Заключение: {self.conclusion_text}"))
        if self.cognitive_events:
            lines.append("")
            lines.append("Когнитивный цикл:")
            lines.extend(f"- {item}" for item in self.cognitive_events)
        if self.diagnostics:
            lines.append("")
            lines.append("Диагностика:")
            lines.extend(f"- {item}" for item in self.diagnostics)
        return "\n".join(lines)


class ProofSnapshotBuilder:
    """Freeze a human-readable proof without making it semantic memory.

    The result contains only diagnostic copies of semantics/UIDs already used by
    InferenceOutcome. It is safe to keep after an M2 sandbox is destroyed and does
    not grant the reasoner any new read path into AH.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core
        self.semantic = SemanticProjector(
            core, ContextSettings(include_structural_uids=False)
        )

    def build_unresolved(
        self,
        *,
        chain_id: str,
        source: str,
        title: str,
        diagnostics: Iterable[str] = (),
    ) -> ProofChainSnapshot:
        """Freeze a failed proof obligation so the operator never sees silence.

        Goal compilation failure is not an InferenceOutcome because search never
        started. It is still first-class provenance: a live answer must not look as
        if no proof was requested at all.
        """
        frozen = tuple(str(item) for item in diagnostics)
        return ProofChainSnapshot(
            chain_id=chain_id,
            source=source,
            title=title,
            status="UNRESOLVED",
            stop_reason="GOAL_NOT_COMPILED",
            logical_depth=0,
            expanded_states=0,
            goal_text="GoalSpec не построена",
            conclusion_text="Доказательство не запускалось",
            trace_uids=(),
            nodes=(),
            edges=(),
            steps=(),
            checks=(),
            diagnostics=frozen,
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
        trace = tuple(outcome.uid_trace)
        nodes = self._nodes(trace)
        edges = self._edges(trace)
        steps = self._steps(outcome, trace, edges)
        return ProofChainSnapshot(
            chain_id=chain_id,
            source=source,
            title=title,
            status=outcome.status.value,
            stop_reason=outcome.stop_reason.value,
            logical_depth=outcome.logical_depth,
            expanded_states=outcome.expanded_states,
            goal_text=self._goal_text(outcome),
            conclusion_text=self._conclusion_text(outcome),
            trace_uids=tuple(ref.uid for ref in trace),
            nodes=nodes,
            edges=edges,
            steps=steps,
            checks=tuple(checks),
            diagnostics=tuple(outcome.diagnostics),
            cognitive_events=self._cognitive_events(outcome),
        )

    @staticmethod
    def _cognitive_events(outcome: InferenceOutcome) -> tuple[str, ...]:
        lines: list[str] = []
        for event in outcome.cognitive_trace:
            parts = [f"d={event.logical_depth}", event.kind.value]
            if event.ref is not None:
                parts.append(event.ref.uid)
            if event.query_kind is not None:
                parts.append(event.query_kind)
            if event.query_key is not None:
                parts.append(event.query_key)
            if event.candidate_count is not None:
                parts.append(f"candidates={event.candidate_count}")
            if event.rule_id is not None:
                parts.append(f"rule={event.rule_id}")
            if event.detail:
                parts.append(event.detail)
            if event.workspace_refs:
                parts.append(f"workspace={len(event.workspace_refs)}")
            lines.append(" | ".join(parts))
        return tuple(lines)

    def _text(self, ref: Ref) -> str:
        try:
            text = self.semantic.inference_text_for_ref(ref)
            # Zero-arity M2 propositions are complete statements; diagnostic
            # parentheses add protocol noise without semantic information.
            return text[:-2] if text.endswith("()") else text
        except Exception:
            return f"{ref.kind.value}:{ref.uid}"

    def _nodes(self, trace: tuple[Ref, ...]) -> tuple[ProofNodeSnapshot, ...]:
        seen: set[str] = set()
        out: list[ProofNodeSnapshot] = []
        for ref in trace:
            if ref.kind is RefKind.L or ref.uid in seen:
                continue
            seen.add(ref.uid)
            domain = self.core.store.domain_of(ref.uid)
            out.append(
                ProofNodeSnapshot(
                    uid=ref.uid,
                    kind=ref.kind.value,
                    semantic=self._text(ref),
                    domain=None if domain is None else domain.value,
                )
            )
        return tuple(out)

    def _edges(self, trace: tuple[Ref, ...]) -> tuple[ProofEdgeSnapshot, ...]:
        out: list[ProofEdgeSnapshot] = []
        for ref in trace:
            if ref.kind is not RefKind.L:
                continue
            try:
                link = self.core.store.get_link(ref.uid)
            except Exception:
                continue
            out.append(
                ProofEdgeSnapshot(
                    uid=link.uid,
                    relation=link.relation_id,
                    source_uid=link.source.uid,
                    target_uid=link.target.uid,
                    semantic=(
                        f"{self._text(link.source)} --{link.relation_id}--> {self._text(link.target)}"
                    ),
                )
            )
        return tuple(out)

    def _steps(
        self,
        outcome: InferenceOutcome,
        trace: tuple[Ref, ...],
        edges: tuple[ProofEdgeSnapshot, ...],
    ) -> tuple[ProofStepSnapshot, ...]:
        if edges:
            return self._relation_steps(outcome, edges)

        conclusion = outcome.conclusion
        if isinstance(conclusion, RoleBindingConclusion):
            fact = self._text(conclusion.fact)
            value = self._text(conclusion.value)
            return (
                ProofStepSnapshot(
                    1,
                    "ROLE_MATCH",
                    conclusion.fact.uid,
                    None,
                    conclusion.value.uid,
                    f"В факте «{fact}» роль {conclusion.role.value} заполнена значением «{value}».",
                ),
            )
        if isinstance(conclusion, MultiRoleBindingConclusion):
            fact = self._text(conclusion.fact)
            rendered = ", ".join(
                f"{role.value}=«{self._text(value)}»" for role, value in conclusion.bindings
            )
            return (
                ProofStepSnapshot(
                    1,
                    "ROLE_MATCH",
                    conclusion.fact.uid,
                    None,
                    None,
                    f"В одном каноническом факте «{fact}» найдены запрошенные роли: {rendered}.",
                ),
            )
        if isinstance(conclusion, ExistingRefConclusion) and trace:
            ref = conclusion.ref
            support_rule = next(
                (support.rule_id for support in outcome.proof_support if support.rule_id),
                None,
            )
            # Preserve the established diagnostic contract for direct/retrieval
            # proofs. Only the new branch/counterfactual scopes need a distinct
            # visible rule label here.
            if support_rule == "OR_CASES":
                rule = "OR_CASES"
                explanation = (
                    f"Цель «{self._text(ref)}» доказана разбором всех ветвей asserted OR; "
                    "ветвевые допущения существовали только в BranchContext."
                )
            elif outcome.proof_context is not None and outcome.proof_context.is_counterfactual():
                rule = support_rule or "COUNTERFACTUAL_PROOF"
                explanation = (
                    f"Цель «{self._text(ref)}» доказана внутри CounterfactualContext; "
                    "результат не является factual commit в AH."
                )
            else:
                rule = "DIRECT_FACT"
                explanation = f"Цель непосредственно удовлетворена каноническим фактом «{self._text(ref)}»."
            return (
                ProofStepSnapshot(
                    1,
                    rule,
                    trace[0].uid if trace else ref.uid,
                    None,
                    ref.uid,
                    explanation,
                ),
            )
        if trace:
            return (
                ProofStepSnapshot(
                    1,
                    "TRACE",
                    trace[0].uid,
                    None,
                    trace[-1].uid,
                    "Использован канонический proof trace без типизированного L-перехода.",
                ),
            )
        return ()

    def _relation_steps(
        self,
        outcome: InferenceOutcome,
        edges: tuple[ProofEdgeSnapshot, ...],
    ) -> tuple[ProofStepSnapshot, ...]:
        out: list[ProofStepSnapshot] = []
        segment_relation: str | None = None
        segment_anchor_uid: str | None = None
        segment_index = 0

        for index, edge in enumerate(edges, 1):
            source_ref = self.core.ref(edge.source_uid)
            target_ref = self.core.ref(edge.target_uid)
            source = self._text(source_ref)
            target = self._text(target_ref)
            relation = edge.relation.upper()
            if relation != segment_relation:
                segment_relation = relation
                segment_anchor_uid = edge.source_uid
                segment_index = 1
            else:
                segment_index += 1

            if relation == "CAUSE":
                rule = "CAUSE / MP"
                explanation = (
                    f"«{source}» установлено в текущем proof-state. Каноническое правило "
                    f"«{source} CAUSE {target}» разрешает modus ponens, поэтому устанавливается «{target}»."
                )
            elif relation in {"IS-A", "FOLLOW"}:
                rule = f"{relation} / DIRECT" if segment_index == 1 else f"{relation} / TRANSITIVITY"
                if segment_index == 1:
                    explanation = f"Для текущего подцеля использовано прямое отношение «{source} {relation} {target}»."
                else:
                    anchor_ref = self.core.ref(segment_anchor_uid) if segment_anchor_uid else source_ref
                    anchor = self._text(anchor_ref)
                    explanation = (
                        f"Уже доказано «{anchor} {relation} {source}». Вместе с "
                        f"«{source} {relation} {target}» по транзитивности получаем "
                        f"«{anchor} {relation} {target}»."
                    )
            else:
                rule = relation
                explanation = f"Использовано типизированное отношение «{source} {relation} {target}»."
            out.append(
                ProofStepSnapshot(
                    index=index,
                    rule=rule,
                    premise_uid=edge.source_uid,
                    link_uid=edge.uid,
                    conclusion_uid=edge.target_uid,
                    explanation=explanation,
                )
            )
        return tuple(out)

    def _goal_text(self, outcome: InferenceOutcome) -> str:
        if outcome.goal_spec is None:
            return "цель не зафиксирована в outcome"
        return self._render_goal(outcome.goal_spec.target)

    def _render_goal(self, goal) -> str:
        if isinstance(goal, AllOfGoal):
            parts = [self._render_goal(child) for child in goal.goals]
            return "ALL-OF { " + "; ".join(parts) + " }"
        if isinstance(goal, CounterfactualGoal):
            assumptions = ", ".join(f"«{self._text(ref)}»" for ref in goal.assumptions)
            return f"при допущениях [{assumptions}] {self._render_goal(goal.target)}"
        if isinstance(goal, FormulaGoal):
            return f"доказать формулу «{self._text(goal.expression)}»"
        if isinstance(goal, RelationGoal):
            return f"доказать «{self._text(goal.source)} {goal.relation_id.upper()} {self._text(goal.target)}»"
        if isinstance(goal, CauseEntailmentGoal):
            return f"доказать установленность «{self._text(goal.effect)}» из явной посылки через CAUSE/MP"
        if isinstance(goal, RoleFillGoal):
            known = ", ".join(f"{role.value}=«{self._text(ref)}»" for role, ref in goal.known_roles.items())
            return f"найти роль {goal.requested_role.value}; известные роли: {known or 'нет'}"
        if isinstance(goal, MultiRoleFillGoal):
            roles = ", ".join(role.value for role in goal.requested_roles)
            known = ", ".join(f"{role.value}=«{self._text(ref)}»" for role, ref in goal.known_roles.items())
            return f"найти роли {roles}; известные роли: {known or 'нет'}"
        if isinstance(goal, ExistsGoal):
            known = ", ".join(f"{role.value}=«{self._text(ref)}»" for role, ref in goal.known_roles.items())
            return f"доказать существование факта; известные роли: {known or 'нет'}"
        return repr(goal)

    def _conclusion_text(self, outcome: InferenceOutcome) -> str:
        conclusion = outcome.conclusion
        if conclusion is None:
            return "заключение не доказано"
        if isinstance(conclusion, ExistingRefConclusion):
            return self._text(conclusion.ref)
        if isinstance(conclusion, CompositeConclusion):
            parts = []
            for item in conclusion.conclusions:
                if isinstance(item, ExistingRefConclusion):
                    parts.append(self._text(item.ref))
                elif isinstance(item, DerivedLinkConclusion):
                    parts.append(f"{self._text(item.source)} {item.relation_id} {self._text(item.target)}")
                elif isinstance(item, RoleBindingConclusion):
                    parts.append(f"{item.role.value} = {self._text(item.value)}")
                elif isinstance(item, MultiRoleBindingConclusion):
                    parts.append(", ".join(f"{role.value} = {self._text(value)}" for role, value in item.bindings))
                else:
                    parts.append(repr(item))
            return "ALL-OF: " + " AND ".join(parts)
        if isinstance(conclusion, DerivedLinkConclusion):
            return f"{self._text(conclusion.source)} {conclusion.relation_id} {self._text(conclusion.target)}"
        if isinstance(conclusion, RoleBindingConclusion):
            return f"{conclusion.role.value} = {self._text(conclusion.value)}"
        if isinstance(conclusion, MultiRoleBindingConclusion):
            return ", ".join(
                f"{role.value} = {self._text(value)}" for role, value in conclusion.bindings
            )
        return repr(conclusion)
