from __future__ import annotations

from collections import deque

from ah.config import InferenceSettings
from ah.core import AHCore
from ah.model import FunctionSymbol, Hypernode, Ref, RefKind

from .contracts import (
    CauseEntailmentGoal,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    ExistsGoal,
    InferenceGoal,
    InferenceOutcome,
    LogicalStatus,
    MultiRoleBindingConclusion,
    MultiRoleFillGoal,
    RelationGoal,
    RoleBindingConclusion,
    RoleFillGoal,
    StopReason,
)
from .domain import domain_from_premises


_TRANSITIVE_RELATIONS = frozenset({"IS-A", "FOLLOW"})


class InferenceEngine:
    """Deterministic MVP reasoner.

    Search is read-only. It emits a semantic conclusion plus exact canonical UID
    trace; canonical writes are delegated to InferenceMaterializer.
    """

    def __init__(self, core: AHCore, settings: InferenceSettings) -> None:
        self.core = core
        self.settings = settings

    def solve(self, goal: InferenceGoal, workspace_refs: tuple[Ref, ...] = ()) -> InferenceOutcome:
        if isinstance(goal, RoleFillGoal):
            return self._role_fill(goal)
        if isinstance(goal, MultiRoleFillGoal):
            return self._multi_role_fill(goal)
        if isinstance(goal, ExistsGoal):
            return self._exists(goal)
        if isinstance(goal, RelationGoal):
            return self._relation(goal)
        if isinstance(goal, CauseEntailmentGoal):
            return self._cause(goal, workspace_refs)
        raise TypeError(f"Unsupported inference goal: {type(goal).__name__}")

    def _false_wrapper(self, node_uid: str) -> Ref | None:
        for element in self.core.store.all_elements():
            if not isinstance(element, FunctionSymbol):
                continue
            if element.function_id.upper() not in {"FALSE", "NOT"}:
                continue
            if len(element.operands) == 1 and element.operands[0].uid == node_uid:
                return self.core.ref(element.uid)
        return None

    def _is_refuted(self, ref: Ref) -> bool:
        return ref.kind is RefKind.N and self._false_wrapper(ref.uid) is not None

    def _matching_hypernodes(self, template_uid: str, known_roles) -> list[Hypernode]:
        out: list[Hypernode] = []
        for element in self.core.store.all_elements():
            if not isinstance(element, Hypernode) or element.template.uid != template_uid:
                continue
            # Scoped propositions are operands of canonical semantic operators
            # (currently IF).  Their presence represents proposition content, not
            # an asserted world fact, so ordinary EXISTS/ROLE_FILL must ignore them.
            if element.meta.get("semantic_scope"):
                continue
            if all(element.actants.get(role) == ref for role, ref in known_roles.items()):
                out.append(element)
        out.sort(key=lambda n: n.uid)
        return out

    def _role_fill(self, goal: RoleFillGoal) -> InferenceOutcome:
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles)
        for node in matches:
            if self._false_wrapper(node.uid) is not None:
                continue
            value = node.actants.get(goal.requested_role)
            if value is None:
                continue
            fact_ref = self.core.ref(node.uid)
            premises = (fact_ref,)
            return InferenceOutcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                RoleBindingConclusion(goal.requested_role, value, fact_ref),
                premises,
                (fact_ref, value),
                domain_from_premises(self.core, premises),
                1,
            )
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            len(matches),
        )

    def _multi_role_fill(self, goal: MultiRoleFillGoal) -> InferenceOutcome:
        """Bind every requested WH role from one canonical fact.

        Running one RoleFillGoal per WH slot would allow answers to be assembled
        from different N instances. A multi-WH query denotes one predicate
        realization, so all bindings are taken atomically from the same match.
        """
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles)
        for node in matches:
            if self._false_wrapper(node.uid) is not None:
                continue
            bindings: list[tuple] = []
            missing = False
            for role in goal.requested_roles:
                value = node.actants.get(role)
                if value is None:
                    missing = True
                    break
                bindings.append((role, value))
            if missing:
                continue
            fact_ref = self.core.ref(node.uid)
            premises = (fact_ref,)
            trace = (fact_ref, *(value for _role, value in bindings))
            return InferenceOutcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                MultiRoleBindingConclusion(tuple(bindings), fact_ref),
                premises,
                trace,
                domain_from_premises(self.core, premises),
                1,
            )
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            len(matches),
        )

    def _exists(self, goal: ExistsGoal) -> InferenceOutcome:
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles)
        for node in matches:
            ref = self.core.ref(node.uid)
            false_ref = self._false_wrapper(node.uid)
            if false_ref is None:
                premises = (ref,)
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ExistingRefConclusion(ref),
                    premises,
                    (ref,),
                    domain_from_premises(self.core, premises),
                    1,
                )
            # A precise negated proposition is an explicit negative proof. Partial
            # EXISTS goals remain open-world UNKNOWN because FALSE of one completion
            # does not disprove every possible completion.
            if dict(node.actants) == dict(goal.known_roles):
                premises = (false_ref, ref)
                return InferenceOutcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_SATISFIED,
                    ExistingRefConclusion(false_ref),
                    premises,
                    (false_ref, ref),
                    domain_from_premises(self.core, premises),
                    1,
                    ("Explicit FALSE(N) proof",),
                )
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            0,
        )

    def _relation(self, goal: RelationGoal) -> InferenceOutcome:
        relation = goal.relation_id.upper()
        direct = self.core.store.find_link(relation, goal.source.uid, goal.target.uid)
        if direct is not None:
            link_ref = self.core.ref(direct.uid)
            premises = (goal.source, link_ref, goal.target)
            return InferenceOutcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                ExistingRefConclusion(link_ref),
                premises,
                premises,
                domain_from_premises(self.core, premises),
                1,
            )

        if relation not in _TRANSITIVE_RELATIONS:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None, (), (), None, 0,
                (f"No transitive rule registered for {relation}",),
            )

        # BFS stores exact alternating node/link trace. Depth counts logical edges.
        queue = deque([(goal.source, (goal.source,), 0)])
        visited = {goal.source.uid}
        expanded = 0
        budget = self.settings.max_expanded_states
        max_depth = self.settings.max_depth

        while queue:
            current, trace, depth = queue.popleft()
            if expanded >= budget:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.BUDGET_EXHAUSTED,
                    None, (), trace, None, expanded,
                )
            expanded += 1
            if depth >= max_depth:
                continue

            links = sorted(
                self.core.store.outgoing_links(current.uid, relation),
                key=lambda l: l.uid,
            )
            for link in links:
                target = link.target
                link_ref = self.core.ref(link.uid)
                new_trace = trace + (link_ref, target)
                if target == goal.target:
                    premises = new_trace
                    return InferenceOutcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        DerivedLinkConclusion(relation, goal.source, goal.target),
                        premises,
                        new_trace,
                        domain_from_premises(self.core, premises),
                        expanded,
                    )
                if target.uid not in visited:
                    visited.add(target.uid)
                    queue.append((target, new_trace, depth + 1))

        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None, (), (), None, expanded,
        )

    def _cause(self, goal: CauseEntailmentGoal, workspace_refs: tuple[Ref, ...]) -> InferenceOutcome:
        # MP-like rule: A exists as a canonical proposition and A --CAUSE--> B.
        # Workspace only affects deterministic candidate priority, not validity.
        workspace = {r.uid for r in workspace_refs}
        incoming = list(self.core.store.incoming_links(goal.effect.uid, "CAUSE"))
        incoming.sort(key=lambda l: (0 if l.source.uid in workspace else 1, l.uid))
        if not incoming:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None, (), (), None, 0,
            )
        link = next(
            (candidate for candidate in incoming if not self._is_refuted(candidate.source)),
            None,
        )
        if link is None:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None, (), (), None, len(incoming),
                ("All CAUSE premises are explicitly refuted",),
            )
        source = link.source
        link_ref = self.core.ref(link.uid)
        premises = (source, link_ref)
        trace = (source, link_ref, goal.effect)
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            ExistingRefConclusion(goal.effect),
            premises,
            trace,
            domain_from_premises(self.core, premises),
            1,
        )
