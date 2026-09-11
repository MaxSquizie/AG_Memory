from __future__ import annotations

from collections import deque
from dataclasses import replace

from ah.config import InferenceSettings
from ah.conflict import ConflictEngine
from ah.core import AHCore
from ah.model import FunctionSymbol, Hypernode, Ref, RefKind

from .attention import InferenceAttention
from .contracts import (
    AllOfGoal,
    CauseEntailmentGoal,
    CounterfactualGoal,
    CompositeConclusion,
    DerivedLinkConclusion,
    ExistingRefConclusion,
    ExistsGoal,
    FormulaGoal,
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
    ProofSupport,
)
from .domain import domain_from_premises
from .context import CounterfactualContext, ProofContext
from .schema import InferenceSchemaRegistry
from .formula import GroundFormulaReasoner
from .runtime import GoalRuntime


class InferenceEngine:
    """Deterministic goal-directed MVP reasoner.

    Search is read-only. The goal is explicit before traversal begins and every
    rule-driven search stops as soon as that goal is proved. Canonical writes are
    delegated to InferenceMaterializer; intermediate search states are never
    materialized.
    """

    def __init__(
        self,
        core: AHCore,
        settings: InferenceSettings,
        schema_registry: InferenceSchemaRegistry | None = None,
    ) -> None:
        self.core = core
        self.settings = settings
        self.schema_registry = schema_registry or InferenceSchemaRegistry.default()
        self.conflicts = ConflictEngine(core)

    def solve(
        self,
        request: InferenceGoal | InferenceQuery,
        workspace_refs: tuple[Ref, ...] = (),
        *,
        attention: InferenceAttention | None = None,
    ) -> InferenceOutcome:
        query = self._normalize_query(request)
        goal = query.goal.target
        proof_context = query.proof_context or ProofContext()
        runtime = GoalRuntime(query.goal, attention)
        runtime.begin(workspace_refs)

        outcome = self._solve_goal(
            goal, query, workspace_refs, attention, proof_context=proof_context, runtime=runtime
        )
        runtime.finish(outcome.status, outcome.stop_reason, logical_depth=outcome.logical_depth)

        # The exact runtime target and proof scope travel with the outcome for
        # diagnostics/M2. Counterfactual/branch solvers may return a child context;
        # never overwrite it with the initially empty root context. Formula/quantifier
        # solvers may also produce concrete substitutions.
        final_context = outcome.proof_context or proof_context
        if outcome.bindings is not None:
            final_context.bindings = outcome.bindings.copy()
        return replace(
            outcome,
            goal_spec=query.goal,
            bindings=final_context.bindings,
            proof_context=final_context,
            cognitive_trace=runtime.snapshot(),
        )

    def _solve_goal(
        self,
        goal: InferenceGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        if isinstance(goal, RoleFillGoal):
            return self._role_fill(goal, runtime)
        if isinstance(goal, MultiRoleFillGoal):
            return self._multi_role_fill(goal, runtime)
        if isinstance(goal, ExistsGoal):
            return self._exists(goal, runtime)
        if isinstance(goal, RelationGoal):
            return self._relation(goal, query, workspace_refs, attention, runtime)
        if isinstance(goal, CauseEntailmentGoal):
            return self._cause(goal, query, workspace_refs, attention, runtime)
        if isinstance(goal, FormulaGoal):
            return GroundFormulaReasoner(
                self.core, self.settings, query, attention=attention, proof_context=proof_context, runtime=runtime
            ).solve(goal)
        if isinstance(goal, CounterfactualGoal):
            return self._counterfactual(
                goal, query, workspace_refs, attention, proof_context=proof_context, runtime=runtime
            )
        if isinstance(goal, AllOfGoal):
            return self._all_of(
                goal, query, workspace_refs, attention, proof_context=proof_context, runtime=runtime
            )
        raise TypeError(f"Unsupported inference goal: {type(goal).__name__}")

    def _counterfactual(
        self,
        goal: CounterfactualGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        """Evaluate a formula in one non-canonical counterfactual overlay.

        Ground N assumptions are matched against structurally equivalent canonical
        propositions through the existing T index. This is necessary because a
        hypothetical/query proposition may be a scoped N with its own UID while the
        factual world contains an ordinary N with the same T+actants.
        """
        assumptions = tuple(goal.assumptions)
        positive: set[str] = set()
        negative: set[str] = set()
        negative_sources: list[tuple[str, Ref]] = []
        suppressed: set[str] = set()

        def equivalent_uids(ref: Ref) -> set[str]:
            if ref.kind is not RefKind.N:
                return {ref.uid}
            node = self.core.store.get_hypernode(ref.uid)
            return {
                candidate.uid
                for candidate in self.core.store.find_hypernodes_by_template(node.template.uid)
                if dict(candidate.actants) == dict(node.actants)
            } or {ref.uid}

        for assumption in assumptions:
            if not self.core.store.has_uid(assumption.uid):
                return InferenceOutcome(
                    LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), None, 0,
                    (f"Missing counterfactual assumption UID: {assumption.uid}",),
                    logical_depth=0,
                )
            if assumption.kind is RefKind.G:
                obj = self.core.store.get_element_any_domain(assumption.uid)
                if isinstance(obj, FunctionSymbol):
                    try:
                        canonical = self.core.function_registry.canonical_id(obj.function_id)
                    except KeyError:
                        canonical = ""
                    if canonical == "NOT" and len(obj.operands) == 1 and isinstance(obj.operands[0], Ref):
                        operand = obj.operands[0]
                        for uid in equivalent_uids(operand):
                            negative.add(uid)
                            negative_sources.append((uid, assumption))
                            suppressed.add(uid)
                        continue
            positive.update(equivalent_uids(assumption))

        opposed = positive & negative
        if opposed:
            return InferenceOutcome(
                LogicalStatus.UNKNOWN, StopReason.CONFLICTED, None, assumptions, assumptions, None, 0,
                ("Counterfactual assumptions are mutually incompatible: " + ", ".join(sorted(opposed)),),
                logical_depth=0,
            )

        # A positive assumption locally overrides both object-level NOT(P) and an
        # explicit historical FALSE(P). Those meta nodes remain canonical records.
        for uid in positive:
            if not self.core.store.has_uid(uid):
                continue
            ref = self.core.ref(uid)
            for parent in self.core.store.function_parents(uid):
                try:
                    canonical = self.core.function_registry.canonical_id(parent.function_id)
                except KeyError:
                    continue
                if canonical not in {"NOT", "FALSE"}:
                    continue
                if len(parent.operands) == 1 and parent.operands[0] == ref:
                    suppressed.add(parent.uid)

        context = CounterfactualContext(
            parent=proof_context,
            bindings=proof_context.bindings.child(),
            assumptions=assumptions,
            suppressed_premise_uids=frozenset(suppressed),
            assumed_positive_uids=frozenset(positive),
            assumed_negative_refs=tuple(negative_sources),
        )
        child_query = InferenceQuery(
            GoalSpec(goal.target),
            premise_refs=query.premise_refs,
            max_depth=query.max_depth,
            max_expanded_states=query.max_expanded_states,
            proof_context=context,
        )
        runtime.subgoal(
            logical_depth=0,
            ref=goal.target.expression,
            detail=f"counterfactual overlay with {len(assumptions)} explicit assumption(s)",
        )
        outcome = self._solve_goal(
            goal.target, child_query, workspace_refs, attention, proof_context=context, runtime=runtime
        )
        return replace(
            outcome,
            diagnostics=("counterfactual overlay; canonical AH unchanged", *outcome.diagnostics),
            proof_context=context,
        )

    def _all_of(
        self,
        goal: AllOfGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        *,
        proof_context: ProofContext,
        runtime: GoalRuntime,
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
        proof_supports: list[ProofSupport] = []
        current_workspace = workspace_refs

        for index, child in enumerate(goal.goals, 1):
            runtime.subgoal(
                logical_depth=total_depth,
                detail=f"AllOf child {index}/{len(goal.goals)}: {type(child).__name__}",
            )
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
                proof_context=proof_context,
            )
            child_outcome = self._solve_goal(
                child, child_query, current_workspace, attention, proof_context=proof_context, runtime=runtime
            )
            total_depth += child_outcome.logical_depth
            total_expanded += child_outcome.expanded_states
            diagnostics.extend(f"child[{index}] {item}" for item in child_outcome.diagnostics)
            proof_supports.extend(child_outcome.proof_support)

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
        runtime.rule("ALL_OF", logical_depth=total_depth, detail=f"children={len(goal.goals)}")
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
            proof_support=tuple(proof_supports),
        )

    @staticmethod
    def _proof_support(
        premise_refs: tuple[Ref, ...],
        *,
        rule_id: str | None = None,
        relation_id: str | None = None,
    ) -> tuple[ProofSupport, ...]:
        return (
            ProofSupport(
                premise_refs=premise_refs,
                rule_id=rule_id,
                relation_id=(relation_id.upper() if relation_id else None),
            ),
        ) if premise_refs else ()

    def _conflict_outcome(
        self,
        refs: tuple[Ref, ...],
        *,
        expanded: int = 0,
        logical_depth: int = 0,
    ) -> InferenceOutcome | None:
        """Return one localized unresolved-conflict outcome, if any ref depends on it."""
        records = {}
        for ref in refs:
            if not self.core.store.has_uid(ref.uid):
                continue
            for record in self.conflicts.unresolved_for(ref):
                records[record.group_ref.uid] = record
        if not records:
            return None
        record = records[sorted(records)[0]]
        premises = tuple(record.members)
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.CONFLICTED,
            None,
            premises,
            tuple((*premises, record.group_ref)),
            domain_from_premises(self.core, premises) if premises else None,
            expanded,
            (
                f"Unresolved canonical conflict {record.group_ref.uid}: "
                + ", ".join(member.uid for member in record.members),
            ),
            logical_depth=logical_depth,
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
        runtime: GoalRuntime | None = None,
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
        if runtime is not None:
            runtime.memory_query(
                "REVERSE_DISTANCE_HEURISTIC",
                f"relation={relation}|target={target.uid}|max_depth={max_depth}",
                logical_depth=0,
                focus_ref=target,
                candidate_count=max(0, len(distances) - 1),
                detail="ordering/pruning only; never proof",
            )
        return distances

    def _false_wrapper(self, node_uid: str) -> Ref | None:
        # Reverse operand index keeps refutation lookup local even in very large AH.
        for element in self.core.store.function_parents(node_uid):
            if not isinstance(element, FunctionSymbol):
                continue
            if element.function_id.upper() not in {"FALSE", "NOT"}:
                continue
            if (
                len(element.operands) == 1
                and isinstance(element.operands[0], Ref)
                and element.operands[0].uid == node_uid
            ):
                return self.core.ref(element.uid)
        return None

    def _is_refuted(self, ref: Ref) -> bool:
        return ref.kind is RefKind.N and self._false_wrapper(ref.uid) is not None

    def _matching_hypernodes(
        self,
        template_uid: str,
        known_roles,
        runtime: GoalRuntime | None = None,
        *,
        logical_depth: int = 0,
    ) -> list[Hypernode]:
        out: list[Hypernode] = []
        # Template index is the deterministic candidate generator. Do not scan the
        # entire AH merely because the store is large or the Workspace is noisy.
        candidates = tuple(self.core.store.find_hypernodes_by_template(template_uid))
        if runtime is not None:
            role_key = ",".join(
                f"{getattr(role, 'value', role)}={ref.uid}"
                for role, ref in sorted(known_roles.items(), key=lambda item: str(item[0]))
            )
            runtime.memory_query(
                "TEMPLATE_FACTS",
                f"T={template_uid}|{role_key}",
                logical_depth=logical_depth,
                candidate_count=len(candidates),
                detail="goal-derived T index lookup",
            )
        for element in candidates:
            # Scoped propositions are operands of canonical semantic operators
            # (for example IMPLIES/OR/NOT scopes). Their presence represents proposition content, not
            # an asserted world fact, so ordinary EXISTS/ROLE_FILL must ignore them.
            if element.meta.get("semantic_scope"):
                continue
            if all(element.actants.get(role) == ref for role, ref in known_roles.items()):
                out.append(element)
        out.sort(key=lambda n: n.uid)
        return out

    def _role_fill(self, goal: RoleFillGoal, runtime: GoalRuntime) -> InferenceOutcome:
        runtime.focus(goal.template_ref, logical_depth=0, reason="goal-generated template query seed")
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles, runtime)
        conflicted: list[Ref] = []
        for node in matches:
            fact_ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
            if self._false_wrapper(node.uid) is not None:
                continue
            value = node.actants.get(goal.requested_role)
            if value is None:
                continue
            runtime.focus(fact_ref, logical_depth=0, reason="matched factual premise")
            runtime.rule("FACT_MATCH", logical_depth=0, detail=f"requested role={goal.requested_role.value}")
            premises = (fact_ref,)
            return InferenceOutcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                RoleBindingConclusion(goal.requested_role, value, fact_ref),
                premises,
                (fact_ref, value),
                domain_from_premises(self.core, premises),
                1,
                proof_support=self._proof_support(premises, rule_id="FACT_MATCH"),
            )
        conflict = self._conflict_outcome(tuple(conflicted), expanded=len(matches))
        if conflict is not None:
            return conflict
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            len(matches),
        )

    def _multi_role_fill(self, goal: MultiRoleFillGoal, runtime: GoalRuntime) -> InferenceOutcome:
        runtime.focus(goal.template_ref, logical_depth=0, reason="goal-generated template query seed")
        """Bind every requested WH role from one canonical fact."""
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles, runtime)
        conflicted: list[Ref] = []
        for node in matches:
            fact_ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(fact_ref):
                conflicted.append(fact_ref)
                continue
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
            runtime.focus(fact_ref, logical_depth=0, reason="matched factual premise")
            runtime.rule("FACT_MATCH", logical_depth=0, detail="multi-role binding")
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
                proof_support=self._proof_support(premises, rule_id="FACT_MATCH"),
            )
        conflict = self._conflict_outcome(tuple(conflicted), expanded=len(matches))
        if conflict is not None:
            return conflict
        return InferenceOutcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            None,
            len(matches),
        )

    def _exists(self, goal: ExistsGoal, runtime: GoalRuntime) -> InferenceOutcome:
        runtime.focus(goal.template_ref, logical_depth=0, reason="goal-generated template query seed")
        matches = self._matching_hypernodes(goal.template_ref.uid, goal.known_roles, runtime)
        conflicted: list[Ref] = []
        for node in matches:
            ref = self.core.ref(node.uid)
            if self.conflicts.is_conflicted(ref):
                conflicted.append(ref)
                continue
            false_ref = self._false_wrapper(node.uid)
            if false_ref is None:
                runtime.focus(ref, logical_depth=0, reason="EXISTS witness")
                runtime.rule("EXISTS_WITNESS", logical_depth=0, detail="explicit canonical witness")
                premises = (ref,)
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ExistingRefConclusion(ref),
                    premises,
                    (ref,),
                    domain_from_premises(self.core, premises),
                    1,
                    proof_support=self._proof_support(premises, rule_id="EXISTS_WITNESS"),
                )
            # A precise negated proposition is an explicit negative proof. Partial
            # EXISTS goals remain open-world UNKNOWN because FALSE of one completion
            # does not disprove every possible completion.
            if dict(node.actants) == dict(goal.known_roles):
                runtime.focus(false_ref, logical_depth=0, reason="explicit refutation")
                runtime.rule("EXPLICIT_REFUTATION", logical_depth=0, detail="precise FALSE/NOT proof")
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
                    proof_support=self._proof_support(premises, rule_id="EXPLICIT_REFUTATION"),
                )
        conflict = self._conflict_outcome(tuple(conflicted), expanded=len(matches))
        if conflict is not None:
            return conflict
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
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        relation = goal.relation_id.upper()
        conflict = self._conflict_outcome((goal.source, goal.target))
        if conflict is not None:
            return conflict
        workspace = {ref.uid for ref in workspace_refs}

        # Attention is a runtime accessibility mechanism, not a truth criterion.
        # Before the reasoner inspects relation adjacency from a proposition, the
        # proposition is explicitly focused through Ignition. A warm Workspace is
        # therefore useful but never required for correctness.
        workspace = {
            ref.uid for ref in runtime.focus(goal.source, logical_depth=0, reason="relation source focus")
        }

        direct = self.core.store.find_link(relation, goal.source.uid, goal.target.uid)
        runtime.memory_query(
            "DIRECT_RELATION",
            f"{relation}|{goal.source.uid}|{goal.target.uid}",
            logical_depth=0,
            focus_ref=goal.source,
            candidate_count=1 if direct is not None else 0,
            detail="exact typed link lookup derived from GoalSpec",
        )
        if direct is not None:
            runtime.rule("DIRECT_RELATION", logical_depth=1, detail=relation)
            workspace = {
                ref.uid for ref in runtime.focus(goal.target, logical_depth=1, reason="relation goal satisfied")
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
                proof_support=self._proof_support(
                    premises, rule_id="DIRECT_RELATION", relation_id=relation
                ),
            )

        schema = self.schema_registry.get(relation)
        if goal.source == goal.target:
            if schema.irreflexive:
                runtime.rule("IRREFLEXIVE", logical_depth=1, detail=relation)
                return InferenceOutcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_REFUTED,
                    None,
                    (goal.source,),
                    (goal.source,),
                    domain_from_premises(self.core, (goal.source,)),
                    1,
                    (f"{relation} is explicitly registered IRREFLEXIVE",),
                    logical_depth=1,
                    proof_support=self._proof_support(
                        (goal.source,), rule_id="IRREFLEXIVE", relation_id=relation
                    ),
                )
            if schema.reflexive:
                runtime.rule("REFLEXIVE", logical_depth=1, detail=relation)
                premises = (goal.source,)
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    DerivedLinkConclusion(relation, goal.source, goal.target),
                    premises,
                    premises,
                    domain_from_premises(self.core, premises),
                    1,
                    logical_depth=1,
                    proof_support=self._proof_support(
                        premises, rule_id="REFLEXIVE", relation_id=relation
                    ),
                )

        if schema.symmetric:
            reverse = self.core.store.find_link(relation, goal.target.uid, goal.source.uid)
            runtime.memory_query(
                "SYMMETRIC_RELATION",
                f"{relation}|{goal.target.uid}|{goal.source.uid}",
                logical_depth=0,
                focus_ref=goal.source,
                candidate_count=1 if reverse is not None else 0,
                detail="reverse typed link lookup licensed by SYMMETRIC schema",
            )
            if reverse is not None:
                link_ref = self.core.ref(reverse.uid)
                premises = (goal.source, link_ref, goal.target)
                runtime.rule("SYMMETRY", logical_depth=1, detail=relation)
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    DerivedLinkConclusion(relation, goal.source, goal.target),
                    premises,
                    premises,
                    domain_from_premises(self.core, premises),
                    1,
                    logical_depth=1,
                    proof_support=self._proof_support(
                        premises, rule_id="SYMMETRY", relation_id=relation
                    ),
                )

        inverse = self.schema_registry.inverse_for(relation)
        if inverse is not None:
            inverse_link = self.core.store.find_link(inverse, goal.target.uid, goal.source.uid)
            runtime.memory_query(
                "INVERSE_RELATION",
                f"{inverse}|{goal.target.uid}|{goal.source.uid}",
                logical_depth=0,
                focus_ref=goal.source,
                candidate_count=1 if inverse_link is not None else 0,
                detail=f"inverse typed link lookup licensed by {relation}<->{inverse}",
            )
            if inverse_link is not None:
                link_ref = self.core.ref(inverse_link.uid)
                premises = (goal.source, link_ref, goal.target)
                runtime.rule("INVERSE_OF", logical_depth=1, detail=f"{relation}<->{inverse}")
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    DerivedLinkConclusion(relation, goal.source, goal.target),
                    premises,
                    premises,
                    domain_from_premises(self.core, premises),
                    1,
                    logical_depth=1,
                    proof_support=self._proof_support(
                        premises, rule_id="INVERSE_OF", relation_id=relation
                    ),
                )

        if not self.schema_registry.is_transitive(relation):
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
        conflicted_premises: list[Ref] = []
        expanded = 0
        max_depth, budget = self._limits(query)
        distance_to_goal = self._reverse_distances(relation, goal.target, max_depth, runtime)
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
            if not (depth == 0 and current == goal.source):
                workspace = {
                    ref.uid for ref in runtime.focus(current, logical_depth=depth, reason="relation proof frontier")
                }

            if depth > deepest_depth:
                deepest_depth = depth
                deepest_trace = trace

            links = list(self.core.store.outgoing_links(current.uid, relation))
            runtime.memory_query(
                "OUTGOING_RELATION",
                f"{relation}|source={current.uid}",
                logical_depth=depth,
                focus_ref=current,
                candidate_count=len(links),
                detail="typed adjacency from current proof focus",
            )
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
                if self.conflicts.is_conflicted(target):
                    conflicted_premises.append(target)
                    continue
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
                    workspace = {
                        ref.uid
                        for ref in runtime.focus(target, logical_depth=new_depth, reason="relation goal satisfied")
                    }
                    runtime.rule("TRANSITIVITY", logical_depth=new_depth, detail=relation)
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
                        proof_support=self._proof_support(
                            premises, rule_id="TRANSITIVITY", relation_id=relation
                        ),
                    )
                if target.uid not in visited:
                    runtime.subgoal(
                        logical_depth=new_depth,
                        ref=target,
                        detail=f"continue {relation} proof from focused successor",
                    )
                    visited.add(target.uid)
                    queue.append((target, new_trace, new_depth))

        conflict = self._conflict_outcome(
            tuple(conflicted_premises), expanded=expanded, logical_depth=deepest_depth
        )
        if conflict is not None:
            return conflict
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
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        if query.premise_refs:
            return self._cause_from_explicit_premises(
                goal, query, workspace_refs, attention, runtime
            )
        return self._cause_legacy_one_step(goal, workspace_refs, attention, runtime)

    def _cause_from_explicit_premises(
        self,
        goal: CauseEntailmentGoal,
        query: InferenceQuery,
        workspace_refs: tuple[Ref, ...],
        attention: InferenceAttention | None,
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        """Goal-directed multi-step modus ponens over canonical CAUSE rules.

        If A is an explicit premise and A --CAUSE--> B, B becomes a derived
        proposition for this search state. The derived B can license the next MP
        step without being materialized. This repeats only until Goal is reached or
        a deterministic depth/state limit is hit.
        """

        workspace = {ref.uid for ref in workspace_refs}
        max_depth, budget = self._limits(query)
        distance_to_goal = self._reverse_distances("CAUSE", goal.effect, max_depth, runtime)

        premises: list[Ref] = []
        conflicted_premises: list[Ref] = []
        seen_premises: set[str] = set()
        for ref in query.premise_refs:
            if ref.uid in seen_premises:
                continue
            seen_premises.add(ref.uid)
            if self.conflicts.is_conflicted(ref):
                conflicted_premises.append(ref)
                continue
            if self._is_refuted(ref):
                continue
            premises.append(ref)
        premises.sort(
            key=lambda ref: (
                0 if ref.uid in workspace else 1,
                -self.core.store.runtime_state(ref.uid).excitation,
                ref.uid,
            )
        )

        if not premises:
            conflict = self._conflict_outcome(tuple(conflicted_premises))
            if conflict is not None:
                return conflict
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
                workspace = {
                    ref.uid for ref in runtime.focus(premise, logical_depth=0, reason="explicit CAUSE premise")
                }
                runtime.rule("EXPLICIT_PREMISE", logical_depth=0, detail="goal already among explicit CAUSE premises")
                return InferenceOutcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ExistingRefConclusion(goal.effect),
                    (premise,),
                    (premise,),
                    domain_from_premises(self.core, (premise,)),
                    0,
                    logical_depth=0,
                    proof_support=self._proof_support(
                        (premise,), rule_id="EXPLICIT_PREMISE"
                    ),
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

            workspace = {
                ref.uid for ref in runtime.focus(current, logical_depth=depth, reason="CAUSE proof frontier")
            }

            if depth > deepest_depth:
                deepest_depth = depth
                deepest_trace = trace

            links = list(self.core.store.outgoing_links(current.uid, "CAUSE"))
            runtime.memory_query(
                "OUTGOING_RELATION",
                f"CAUSE|source={current.uid}",
                logical_depth=depth,
                focus_ref=current,
                candidate_count=len(links),
                detail="typed adjacency from current established premise",
            )
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
                if self.conflicts.is_conflicted(target):
                    conflicted_premises.append(target)
                    continue
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
                    workspace = {
                        ref.uid
                        for ref in runtime.focus(target, logical_depth=new_depth, reason="CAUSE goal satisfied")
                    }
                    runtime.rule("CAUSE_MP", logical_depth=new_depth, detail=f"{current.uid} -> {target.uid}")
                    return InferenceOutcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        ExistingRefConclusion(goal.effect),
                        new_trace,
                        new_trace,
                        domain_from_premises(self.core, new_trace),
                        expanded,
                        logical_depth=new_depth,
                        proof_support=self._proof_support(
                            new_trace, rule_id="CAUSE_MP", relation_id="CAUSE"
                        ),
                    )

                previous_depth = visited_depth.get(target.uid)
                if previous_depth is None or new_depth < previous_depth:
                    runtime.subgoal(
                        logical_depth=new_depth,
                        ref=target,
                        detail="CAUSE-derived intermediate becomes next proof focus",
                    )
                    visited_depth[target.uid] = new_depth
                    queue.append((target, new_trace, new_depth))

        conflict = self._conflict_outcome(
            tuple(conflicted_premises), expanded=expanded, logical_depth=deepest_depth
        )
        if conflict is not None:
            return conflict
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
        runtime: GoalRuntime,
    ) -> InferenceOutcome:
        """Compatibility path for pre-v0.38 callers without explicit premises.

        This preserves the previous one-step MP contract. Multi-step CAUSE requires
        InferenceQuery(..., premise_refs=(...)) so intermediate canonical nodes are
        not silently treated as independent starting truths.
        """

        workspace = {ref.uid for ref in workspace_refs}
        workspace = {
            ref.uid for ref in runtime.focus(goal.effect, logical_depth=1, reason="reverse CAUSE query target")
        }
        incoming = list(self.core.store.incoming_links(goal.effect.uid, "CAUSE"))
        runtime.memory_query(
            "INCOMING_CAUSE",
            f"effect={goal.effect.uid}",
            logical_depth=1,
            focus_ref=goal.effect,
            candidate_count=len(incoming),
            detail="reverse causal candidate retrieval; not reverse proof",
        )
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
        conflicted_sources = tuple(
            candidate.source for candidate in incoming
            if self.conflicts.is_conflicted(candidate.source)
        )
        link = next(
            (
                candidate for candidate in incoming
                if not self._is_refuted(candidate.source)
                and not self.conflicts.is_conflicted(candidate.source)
            ),
            None,
        )
        if link is None:
            conflict = self._conflict_outcome(conflicted_sources, expanded=len(incoming))
            if conflict is not None:
                return conflict
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
        workspace = {
            ref.uid for ref in runtime.focus(source, logical_depth=0, reason="direct CAUSE premise")
        }
        link_ref = self.core.ref(link.uid)
        runtime.rule("CAUSE_MP", logical_depth=1, detail="one-step compatibility path")
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
            proof_support=self._proof_support(
                premises, rule_id="CAUSE_MP", relation_id="CAUSE"
            ),
        )
