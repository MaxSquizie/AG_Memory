from __future__ import annotations

from collections import deque
from dataclasses import replace

from ah.config import InferenceSettings
from ah.core import AHCore
from ah.model import FunctionSymbol, Hypernode, Ref, RefKind

from .attention import InferenceAttention
from .contracts import (
    AllOfGoal,
    CauseEntailmentGoal,
    CompositeConclusion,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    ExistsGoal,
    GoalSpec,
    InferenceGoal,
    InferenceOutcome,
    InferenceQuery,
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
    """Deterministic goal-directed MVP reasoner.

    Search is read-only. The goal is explicit before traversal begins and every
    rule-driven search stops as soon as that goal is proved. Canonical writes are
    delegated to InferenceMaterializer; intermediate search states are never
    materialized.
    """

    def __init__(self, core: AHCore, settings: InferenceSettings) -> None:
        self.core = core
        self.settings = settings

    def solve(
        self,
        request: InferenceGoal | InferenceQuery,
        workspace_refs: tuple[Ref, ...] = (),
        *,
        attention: InferenceAttention | None = None,
    ) -> InferenceOutcome:
        query = self._normalize_query(request)
        goal = query.goal.target
        if attention is not None:
            attention.begin()

        outcome = self._solve_goal(goal, query, workspace_refs, attention)

        # The exact runtime target travels with the outcome for diagnostics/M2.
        return replace(outcome, goal_spec=query.goal)

    def _solve_goal(
        self,
        goal: InferenceGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        if isinstance(goal, RoleFillGoal):
            return self._role_fill(goal)
        if isinstance(goal, MultiRoleFillGoal):
            return self._multi_role_fill(goal)
        if isinstance(goal, ExistsGoal):
            return self._exists(goal)
        if isinstance(goal, RelationGoal):
            return self._relation(goal, query, workspace_refs, attention)
        if isinstance(goal, CauseEntailmentGoal):
            return self._cause(goal, query, workspace_refs, attention)
        if isinstance(goal, AllOfGoal):
            return self._all_of(goal, query, workspace_refs, attention)
        raise TypeError(f"Unsupported inference goal: {type(goal).__name__}")

    def _all_of(
        self,
        goal: AllOfGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        """Prove a typed conjunction without turning mixed graph reachability into proof.

        Each child is solved by its registered rule family. Its exact proof trace is
        appended to one composite trace, collapsing a shared boundary ref when the
        next child starts where the previous child ended. Depth and expansion budgets
        are global across the complete proof, not reset for each child.
        """
        max_depth, budget = self._limits(query)
        total_depth = 0
        total_expanded = 0
        merged_trace: tuple[Ref, ...] = ()
        premise_refs: list[Ref] = []
        premise_seen: set[str] = set()
        conclusions = []
        diagnostics: list[str] = []
        current_workspace = workspace_refs

        for index, child in enumerate(goal.goals, 1):
            remaining_depth = max_depth - total_depth
            remaining_budget = budget - total_expanded
            if remaining_depth < 1:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.DEPTH_EXHAUSTED,
                    None,
                    tuple(premise_refs),
                    merged_trace,
                    None,
                    total_expanded,
                    tuple((*diagnostics, f"AllOf child {index} not attempted: global depth exhausted")),
                    logical_depth=total_depth,
                )
            if remaining_budget < 1:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.BUDGET_EXHAUSTED,
                    None,
                    tuple(premise_refs),
                    merged_trace,
                    None,
                    total_expanded,
                    tuple((*diagnostics, f"AllOf child {index} not attempted: global budget exhausted")),
                    logical_depth=total_depth,
                )

            child_query = InferenceQuery(
                GoalSpec(child),
                premise_refs=query.premise_refs,
                max_depth=remaining_depth,
                max_expanded_states=remaining_budget,
            )
            child_outcome = self._solve_goal(child, child_query, current_workspace, attention)
            total_depth += child_outcome.logical_depth
            total_expanded += child_outcome.expanded_states
            diagnostics.extend(f"child[{index}] {item}" for item in child_outcome.diagnostics)

            if child_outcome.uid_trace:
                child_trace = tuple(child_outcome.uid_trace)
                if merged_trace and child_trace and merged_trace[-1] == child_trace[0]:
                    merged_trace += child_trace[1:]
                else:
                    merged_trace += child_trace
            for ref in child_outcome.premise_refs:
                if ref.uid not in premise_seen:
                    premise_seen.add(ref.uid)
                    premise_refs.append(ref)

            if child_outcome.status is LogicalStatus.DISPROVED:
                return InferenceOutcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_SATISFIED,
                    child_outcome.conclusion,
                    tuple(premise_refs),
                    merged_trace,
                    domain_from_premises(self.core, tuple(premise_refs)) if premise_refs else None,
                    total_expanded,
                    tuple((*diagnostics, f"AllOf child {index} explicitly disproved")),
                    logical_depth=total_depth,
                )
            if child_outcome.status is not LogicalStatus.PROVED:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    child_outcome.stop_reason,
                    None,
                    tuple(premise_refs),
                    merged_trace,
                    None,
                    total_expanded,
                    tuple((*diagnostics, f"AllOf child {index} not proved")),
                    logical_depth=total_depth,
                )
            if child_outcome.conclusion is not None:
                conclusions.append(child_outcome.conclusion)

            # Attention changes the real Workspace during a child proof. Read its
            # current view before the next rule family so warm state can influence
            # priority without becoming a truth premise.
            if attention is not None and hasattr(attention, "ignition"):
                try:
                    current_workspace = tuple(attention.ignition.workspace_refs())
                except Exception:
                    current_workspace = current_workspace

        if len(conclusions) < 2:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                tuple(premise_refs),
                merged_trace,
                None,
                total_expanded,
                tuple((*diagnostics, "AllOf did not produce all semantic conclusions")),
                logical_depth=total_depth,
            )

        premises_tuple = tuple(premise_refs)
        return InferenceOutcome(
            LogicalStatus.PROVED,
            StopReason.GOAL_SATISFIED,
            CompositeConclusion(tuple(conclusions)),
            premises_tuple,
            merged_trace,
            domain_from_premises(self.core, premises_tuple) if premises_tuple else None,
            total_expanded,
            tuple(diagnostics),
            logical_depth=total_depth,
        )

    @staticmethod
    def _normalize_query(request: InferenceGoal | InferenceQuery) -> InferenceQuery:
        if isinstance(request, InferenceQuery):
            return request
        return InferenceQuery(GoalSpec(request))

    def _limits(self, query: InferenceQuery) -> tuple[int, int]:
        max_depth = query.max_depth if query.max_depth is not None else self.settings.max_depth
        budget = (
            query.max_expanded_states
            if query.max_expanded_states is not None
            else self.settings.max_expanded_states
        )
        return max_depth, budget

    def _reverse_distances(
        self,
        relation: str,
        target: Ref,
        max_depth: int,
    ) -> dict[str, int]:
        """Bounded structural distance-to-goal map used only for candidate pruning.

        This traverses typed L adjacency, not arbitrary semantic neighborhoods. It
        never proves a proposition by reachability: forward rule application still
        constructs the proof. The map only prevents the search from spending its
        budget on branches that cannot possibly reach the explicit Goal within the
        allowed logical depth.
        """
        relation = relation.upper()
        distances = {target.uid: 0}
        queue = deque((target.uid,))
        while queue:
            current_uid = queue.popleft()
            depth = distances[current_uid]
            if depth >= max_depth:
                continue
            for link in self.core.store.incoming_links(current_uid, relation):
                source_uid = link.source.uid
                new_depth = depth + 1
                old = distances.get(source_uid)
                if old is None or new_depth < old:
                    distances[source_uid] = new_depth
                    queue.append(source_uid)
        return distances

    def _false_wrapper(self, node_uid: str) -> Ref | None:
        # Reverse operand index keeps refutation lookup local even in very large AH.
        for element in self.core.store.function_parents(node_uid):
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
        # Template index is the deterministic candidate generator. Do not scan the
        # entire AH merely because the store is large or the Workspace is noisy.
        for element in self.core.store.find_hypernodes_by_template(template_uid):
            # Scoped propositions are operands of canonical semantic operators
            # (currently IF). Their presence represents proposition content, not
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
        """Bind every requested WH role from one canonical fact."""
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

    def _relation(
        self,
        goal: RelationGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        relation = goal.relation_id.upper()
        workspace = {ref.uid for ref in workspace_refs}

        # Attention is a runtime accessibility mechanism, not a truth criterion.
        # Before the reasoner inspects relation adjacency from a proposition, the
        # proposition is explicitly focused through Ignition. A warm Workspace is
        # therefore useful but never required for correctness.
        if attention is not None:
            workspace = {
                ref.uid for ref in attention.focus(goal.source, logical_depth=0)
            }

        direct = self.core.store.find_link(relation, goal.source.uid, goal.target.uid)
        if direct is not None:
            if attention is not None:
                workspace = {
                    ref.uid for ref in attention.focus(goal.target, logical_depth=1)
                }
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
                logical_depth=1,
            )

        if relation not in _TRANSITIVE_RELATIONS:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                0,
                (f"No transitive rule registered for {relation}",),
            )

        # Rule-driven BFS stores an exact alternating node/link proof trace. Target
        # Refs may be discovered structurally from the current focused node, but a
        # non-root proposition is semantically expanded only after attention has
        # shifted to it. This prevents a global cold-store walk while preserving the
        # architecture rule that x/Workspace affect access/priority, never truth.
        queue = deque([(goal.source, (goal.source,), 0)])
        visited = {goal.source.uid}
        expanded = 0
        max_depth, budget = self._limits(query)
        distance_to_goal = self._reverse_distances(relation, goal.target, max_depth)
        depth_limited = False
        deepest_trace: tuple[Ref, ...] = (goal.source,)
        deepest_depth = 0

        while queue:
            current, trace, depth = queue.popleft()
            if expanded >= budget:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.BUDGET_EXHAUSTED,
                    None,
                    (),
                    trace,
                    None,
                    expanded,
                    logical_depth=depth,
                )
            expanded += 1

            # source was already focused before direct-link lookup above.
            if attention is not None and not (depth == 0 and current == goal.source):
                workspace = {
                    ref.uid for ref in attention.focus(current, logical_depth=depth)
                }

            if depth > deepest_depth:
                deepest_depth = depth
                deepest_trace = trace

            links = list(self.core.store.outgoing_links(current.uid, relation))
            links.sort(
                key=lambda link: (
                    0 if link.target == goal.target else 1,
                    0 if link.target.uid in workspace else 1,
                    -self.core.store.runtime_state(link.target.uid).excitation,
                    link.uid,
                )
            )
            if depth >= max_depth:
                if any(link.target.uid not in visited for link in links):
                    depth_limited = True
                continue

            for link in links:
                target = link.target
                remaining = distance_to_goal.get(target.uid)
                current_goal_feasible = (
                    current.uid in distance_to_goal
                    and depth + distance_to_goal[current.uid] <= max_depth
                )
                if current_goal_feasible and (
                    remaining is None or depth + 1 + remaining > max_depth
                ):
                    continue
                link_ref = self.core.ref(link.uid)
                new_trace = trace + (link_ref, target)
                new_depth = depth + 1
                if target == goal.target:
                    if attention is not None:
                        workspace = {
                            ref.uid
                            for ref in attention.focus(target, logical_depth=new_depth)
                        }
                    premises = new_trace
                    return InferenceOutcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        DerivedLinkConclusion(relation, goal.source, goal.target),
                        premises,
                        new_trace,
                        domain_from_premises(self.core, premises),
                        expanded,
                        logical_depth=new_depth,
                    )
                if target.uid not in visited:
                    visited.add(target.uid)
                    queue.append((target, new_trace, new_depth))

        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.DEPTH_EXHAUSTED if depth_limited else StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            deepest_trace if depth_limited else (),
            None,
            expanded,
            logical_depth=deepest_depth,
        )

    def _cause(
        self,
        goal: CauseEntailmentGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        if query.premise_refs:
            return self._cause_from_explicit_premises(
                goal, query, workspace_refs, attention
            )
        return self._cause_legacy_one_step(goal, workspace_refs, attention)

    def _cause_from_explicit_premises(
        self,
        goal: CauseEntailmentGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        """Goal-directed multi-step modus ponens over canonical CAUSE rules.

        If A is an explicit premise and A --CAUSE--> B, B becomes a derived
        proposition for this search state. The derived B can license the next MP
        step without being materialized. This repeats only until Goal is reached or
        a deterministic depth/state limit is hit.
        """

        workspace = {ref.uid for ref in workspace_refs}
        max_depth, budget = self._limits(query)
        distance_to_goal = self._reverse_distances("CAUSE", goal.effect, max_depth)

        premises: list[Ref] = []
        seen_premises: set[str] = set()
        for ref in query.premise_refs:
            if ref.uid in seen_premises or self._is_refuted(ref):
                continue
            seen_premises.add(ref.uid)
            premises.append(ref)
        premises.sort(
            key=lambda ref: (
                0 if ref.uid in workspace else 1,
                -self.core.store.runtime_state(ref.uid).excitation,
                ref.uid,
            )
        )

        if not premises:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                0,
                ("No non-refuted explicit CAUSE premises",),
            )

        for premise in premises:
            if premise == goal.effect:
                if attention is not None:
                    workspace = {
                        ref.uid for ref in attention.focus(premise, logical_depth=0)
                    }
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ExistingRefConclusion(goal.effect),
                    (premise,),
                    (premise,),
                    domain_from_premises(self.core, (premise,)),
                    0,
                    logical_depth=0,
                )

        # Each queue item carries one valid proof path from one explicit premise.
        queue = deque((premise, (premise,), 0) for premise in premises)
        visited_depth: dict[str, int] = {premise.uid: 0 for premise in premises}
        expanded = 0
        depth_limited = False
        deepest_trace: tuple[Ref, ...] = (premises[0],)
        deepest_depth = 0

        while queue:
            current, trace, depth = queue.popleft()
            if expanded >= budget:
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.BUDGET_EXHAUSTED,
                    None,
                    (),
                    trace,
                    None,
                    expanded,
                    logical_depth=depth,
                )
            expanded += 1

            if attention is not None:
                workspace = {
                    ref.uid for ref in attention.focus(current, logical_depth=depth)
                }

            if depth > deepest_depth:
                deepest_depth = depth
                deepest_trace = trace

            links = list(self.core.store.outgoing_links(current.uid, "CAUSE"))
            links.sort(
                key=lambda link: (
                    0 if link.target == goal.effect else 1,
                    0 if link.target.uid in workspace else 1,
                    -self.core.store.runtime_state(link.target.uid).excitation,
                    link.uid,
                )
            )

            if depth >= max_depth:
                if any(visited_depth.get(link.target.uid, max_depth + 1) > depth for link in links):
                    depth_limited = True
                continue

            for link in links:
                # Rule: current proposition has been established on this proof path;
                # current CAUSE target may therefore be derived by one MP step.
                target = link.target
                remaining = distance_to_goal.get(target.uid)
                current_goal_feasible = (
                    current.uid in distance_to_goal
                    and depth + distance_to_goal[current.uid] <= max_depth
                )
                if current_goal_feasible and (
                    remaining is None or depth + 1 + remaining > max_depth
                ):
                    continue
                link_ref = self.core.ref(link.uid)
                new_trace = trace + (link_ref, target)
                new_depth = depth + 1

                if target == goal.effect:
                    if attention is not None:
                        workspace = {
                            ref.uid
                            for ref in attention.focus(target, logical_depth=new_depth)
                        }
                    return InferenceOutcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        ExistingRefConclusion(goal.effect),
                        new_trace,
                        new_trace,
                        domain_from_premises(self.core, new_trace),
                        expanded,
                        logical_depth=new_depth,
                    )

                previous_depth = visited_depth.get(target.uid)
                if previous_depth is None or new_depth < previous_depth:
                    visited_depth[target.uid] = new_depth
                    queue.append((target, new_trace, new_depth))

        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.DEPTH_EXHAUSTED if depth_limited else StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            deepest_trace if depth_limited else (),
            None,
            expanded,
            logical_depth=deepest_depth,
        )

    def _cause_legacy_one_step(
        self,
        goal: CauseEntailmentGoal,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
    ) -> InferenceOutcome:
        """Compatibility path for pre-v0.38 callers without explicit premises.

        This preserves the previous one-step MP contract. Multi-step CAUSE requires
        InferenceQuery(..., premise_refs=(...)) so intermediate canonical nodes are
        not silently treated as independent starting truths.
        """

        workspace = {ref.uid for ref in workspace_refs}
        if attention is not None:
            workspace = {
                ref.uid for ref in attention.focus(goal.effect, logical_depth=1)
            }
        incoming = list(self.core.store.incoming_links(goal.effect.uid, "CAUSE"))
        incoming.sort(key=lambda link: (0 if link.source.uid in workspace else 1, link.uid))
        if not incoming:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                0,
            )
        link = next(
            (candidate for candidate in incoming if not self._is_refuted(candidate.source)),
            None,
        )
        if link is None:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                None,
                len(incoming),
                ("All CAUSE premises are explicitly refuted",),
            )
        source = link.source
        if attention is not None:
            workspace = {
                ref.uid for ref in attention.focus(source, logical_depth=0)
            }
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
            ("Implicit one-step CAUSE premise compatibility mode",),
            logical_depth=1,
        )
