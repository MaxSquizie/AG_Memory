from __future__ import annotations

from dataclasses import dataclass

from ah.config import InferenceSettings
from ah.conflict import ConflictEngine
from ah.core import AHCore
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Group, Hypernode, Ref, RefKind

from .attention import InferenceAttention
from .bindings import BindingEnvironment
from .contracts import (
    ExistingRefConclusion,
    FormulaGoal,
    InferenceOutcome,
    InferenceQuery,
    LogicalStatus,
    ProofSupport,
    StopReason,
)
from .domain import domain_from_premises
from .context import BranchContext, CounterfactualContext, ProofContext
from .runtime import GoalRuntime


@dataclass(slots=True)
class _EvalState:
    expanded: int = 0
    budget_exhausted: bool = False


@dataclass(slots=True)
class _BoundProof:
    """One successful quantified-pattern proof branch."""

    bindings: BindingEnvironment
    premise_refs: tuple[Ref, ...]
    uid_trace: tuple[Ref, ...]
    logical_depth: int


class GroundFormulaReasoner:
    """Deterministic proof over canonical N/g expressions.

    The historical class name is kept for API compatibility. Atomic propositions
    remain N and compound expressions remain g; quantified formula patterns reuse
    N with scoped ``BoundVar`` actants and never introduce a second formula store
    or a new AH node kind. Concrete substitutions live only in
    ``BindingEnvironment``.

    Search is goal-directed. Quantified rule discovery starts from the current
    target template and follows rebuildable reverse function indexes; unrelated AH
    nodes are not globally scanned.
    """

    def __init__(
        self,
        core: AHCore,
        settings: InferenceSettings,
        query: InferenceQuery,
        *,
        attention: InferenceAttention | None = None,
        proof_context: ProofContext | None = None,
        runtime: GoalRuntime | None = None,
    ) -> None:
        self.core = core
        self.settings = settings
        self.query = query
        self.attention = attention
        self.runtime = runtime
        self.max_depth = query.max_depth if query.max_depth is not None else settings.max_depth
        self.budget = (
            query.max_expanded_states
            if query.max_expanded_states is not None
            else settings.max_expanded_states
        )
        self.state = _EvalState()
        self.conflicts = ConflictEngine(core)
        self.proof_context = proof_context or ProofContext()
        self._active_context = self.proof_context

    def solve(self, goal: FormulaGoal) -> InferenceOutcome:
        return self._eval(goal.expression, depth=0, stack=())

    def _visible_assumptions(self) -> tuple[Ref, ...]:
        return self._active_context.visible_assumptions()

    def _assumption_not_for(self, ref: Ref) -> Ref | None:
        cursor: ProofContext | None = self._active_context
        while cursor is not None:
            if isinstance(cursor, CounterfactualContext):
                for uid, source_assumption in reversed(cursor.assumed_negative_refs):
                    if uid == ref.uid:
                        return source_assumption
            cursor = cursor.parent
        for assumption in reversed(self._visible_assumptions()):
            if assumption.kind is not RefKind.G or not self.core.store.has_uid(assumption.uid):
                continue
            obj = self.core.store.get_element_any_domain(assumption.uid)
            if not isinstance(obj, FunctionSymbol):
                continue
            try:
                canonical = self.core.function_registry.canonical_id(obj.function_id)
            except KeyError:
                continue
            if canonical == "NOT" and len(obj.operands) == 1 and obj.operands[0] == ref:
                return assumption
        return None

    def _assumption_positive(self, ref: Ref) -> bool:
        cursor: ProofContext | None = self._active_context
        while cursor is not None:
            if isinstance(cursor, CounterfactualContext) and ref.uid in cursor.assumed_positive_uids:
                return True
            cursor = cursor.parent
        return any(item == ref for item in self._visible_assumptions())

    def _suppressed_uid(self, uid: str) -> bool:
        cursor: ProofContext | None = self._active_context
        while cursor is not None:
            if isinstance(cursor, CounterfactualContext) and uid in cursor.suppressed_premise_uids:
                return True
            cursor = cursor.parent
        return False

    def _premise_admissible(self, premise: Ref, visiting: frozenset[str]) -> bool:
        if self._assumption_positive(premise):
            return True
        if self._assumption_not_for(premise) is not None or self._suppressed_uid(premise.uid):
            return False
        if self.conflicts.is_conflicted(premise):
            return False
        if premise.kind is RefKind.N:
            if self._false_parent(premise) is not None:
                return False
            node = self.core.store.get_hypernode(premise.uid)
            if node.meta.get("semantic_scope"):
                return False
            if int(node.meta.get("occurrence_count", 0)) > 0:
                return True
            if premise.uid in visiting:
                return False
            records = self.core.resolve_supports(premise)
            return any(
                all(
                    self._premise_admissible(ref, visiting | {premise.uid})
                    for ref in record.premise_refs
                )
                for record in records
            )
        if premise.kind is RefKind.G:
            obj = self.core.store.get_element_any_domain(premise.uid)
            if isinstance(obj, FunctionSymbol) and self._asserted_function(premise, obj):
                return True
            if premise.uid in visiting:
                return False
            records = self.core.resolve_supports(premise)
            return any(
                all(
                    self._premise_admissible(ref, visiting | {premise.uid})
                    for ref in record.premise_refs
                )
                for record in records
            )
        # Structural L/T/M/S premises are canonical stored objects. Their logical
        # admissibility is controlled by the relation/rule family that emitted the
        # support; counterfactual suppression can still disable them explicitly.
        return self.core.store.has_uid(premise.uid)

    def _support_admissible(self, premise_refs: tuple[Ref, ...]) -> bool:
        return all(self._premise_admissible(ref, frozenset()) for ref in premise_refs)

    def _evaluate_in_context(
        self,
        ref: Ref,
        context: ProofContext,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome:
        previous = self._active_context
        self._active_context = context
        try:
            return self._eval(ref, depth=depth, stack=stack)
        finally:
            self._active_context = previous

    def _focus(self, ref: Ref, depth: int) -> None:
        if self.runtime is not None:
            self.runtime.focus(ref, logical_depth=depth, reason="formula proof step")
        elif self.attention is not None:
            self.attention.focus(ref, logical_depth=depth)

    def _consume(self) -> bool:
        if self.state.expanded >= self.budget:
            self.state.budget_exhausted = True
            return False
        self.state.expanded += 1
        return True

    @staticmethod
    def _support(
        premises: tuple[Ref, ...],
        rule_id: str,
        relation_id: str | None = None,
    ) -> tuple[ProofSupport, ...]:
        return (
            ProofSupport(
                premise_refs=premises,
                rule_id=rule_id,
                relation_id=relation_id,
            ),
        ) if premises else ()

    def _outcome(
        self,
        status: LogicalStatus,
        stop: StopReason,
        ref: Ref | None,
        premises: tuple[Ref, ...],
        trace: tuple[Ref, ...],
        *,
        depth: int,
        diagnostics: tuple[str, ...] = (),
        rule_id: str | None = None,
        bindings: BindingEnvironment | None = None,
    ) -> InferenceOutcome:
        domain = domain_from_premises(self.core, premises) if premises else None
        if rule_id is not None and self.runtime is not None:
            self.runtime.rule(
                rule_id,
                logical_depth=depth,
                detail=f"status={status.value}; premises={len(premises)}",
            )
        return InferenceOutcome(
            status,
            stop,
            ExistingRefConclusion(ref) if ref is not None else None,
            premises,
            trace,
            domain,
            self.state.expanded,
            diagnostics,
            logical_depth=depth,
            proof_support=(self._support(premises, rule_id) if rule_id else ()),
            bindings=(bindings.copy() if bindings is not None else None),
        )

    def _leaf_scopes(self, ref: Ref, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else seen
        if ref.uid in seen or not self.core.store.has_uid(ref.uid):
            return set()
        seen.add(ref.uid)
        if ref.kind is RefKind.N:
            node = self.core.store.get_hypernode(ref.uid)
            scope = str(node.meta.get("semantic_scope") or "").upper()
            return {scope} if scope else set()
        if ref.kind is not RefKind.G:
            return set()
        obj = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(obj, FunctionSymbol):
            return set()
        out: set[str] = set()
        for operand in obj.operands:
            if isinstance(operand, Ref):
                out.update(self._leaf_scopes(operand, seen))
        return out

    def _has_external_occurrence(self, ref: Ref) -> bool:
        """Whether a C/P expression is top-level content of an H user turn.

        External integration writes semantic C/P content and separately records the
        utterance occurrence in H.  Agent self-output is H-only, so a C/P root with
        an H occurrence is a stable way to distinguish an asserted compound g from
        a merely nested helper g without adding Pr/Mt to FunctionSymbol.
        """
        if self.core.store.domain_of(ref.uid) not in {Domain.C, Domain.P}:
            return False

        candidates = [ref]
        for group in self.core.store.groups_containing(ref.uid):
            if self.core.store.domain_of(group.uid) is not Domain.H:
                continue
            if str(group.meta.get("type") or "").upper() != "UTTERANCE_CONTENT":
                continue
            candidates.append(self.core.ref(group.uid))

        for candidate in candidates:
            for node in self.core.store.hypernodes_for_actant(candidate.uid):
                if self.core.store.domain_of(node.uid) is not Domain.H:
                    continue
                if not bool(node.meta.get("event_instance", False)):
                    continue
                if node.actants.get(ActantRole.OBJECT) == candidate:
                    return True
        return False

    def _asserted_function(self, ref: Ref, obj: FunctionSymbol) -> bool:
        if self._suppressed_uid(ref.uid):
            return False
        if self._assumption_positive(ref):
            return True
        if not self._has_external_occurrence(ref):
            return False
        scopes = self._leaf_scopes(ref)
        # Reported/quoted/hypothetical/modal content protects its nested P from
        # ordinary factual use. Conditional/disjunctive roots remain assertable
        # because only their leaves carry those scopes.
        return not bool(scopes & {"EMBEDDED", "QUOTED", "HYPOTHETICAL", "MODAL"})

    def _function_parents(self, ref: Ref, canonical_id: str) -> tuple[tuple[Ref, FunctionSymbol], ...]:
        out: list[tuple[Ref, FunctionSymbol]] = []
        parents = tuple(self.core.store.function_parents(ref.uid))
        if self.runtime is not None:
            self.runtime.memory_query(
                "FUNCTION_PARENTS",
                f"operand={ref.uid}|function={canonical_id}",
                logical_depth=0,
                focus_ref=ref,
                candidate_count=len(parents),
                detail="reverse function index derived from current formula goal/subgoal",
            )
        for obj in parents:
            try:
                actual = self.core.function_registry.canonical_id(obj.function_id)
            except KeyError:
                continue
            if actual != canonical_id:
                continue
            out.append((self.core.ref(obj.uid), obj))
        out.sort(key=lambda item: item[0].uid)
        return tuple(out)

    def _alternative_parents(
        self, ref: Ref
    ) -> tuple[tuple[Ref, FunctionSymbol], ...]:
        """Return asserted-alternative containers discoverable from one operand.

        XOR entails OR-style exhaustiveness, so elimination/proof-by-cases can use
        either operator. Exclusivity-specific reasoning remains in dedicated rules.
        """
        out = [
            item
            for operator in ("OR", "XOR")
            for item in self._function_parents(ref, operator)
        ]
        out.sort(key=lambda item: item[0].uid)
        return tuple(out)

    def _asserted_not_parent(self, ref: Ref) -> Ref | None:
        # Explicit local assumptions override incompatible canonical polarity only
        # inside the active proof scope.
        if self._assumption_positive(ref):
            return None
        assumed_not = self._assumption_not_for(ref)
        if assumed_not is not None:
            return assumed_not
        for parent_ref, obj in self._function_parents(ref, "NOT"):
            if self._suppressed_uid(parent_ref.uid):
                continue
            if len(obj.operands) == 1 and obj.operands[0] == ref and self._asserted_function(parent_ref, obj):
                return parent_ref
        return None

    def _false_parent(self, ref: Ref) -> Ref | None:
        # A positive counterfactual/branch assumption can locally restore P even
        # when canonical history contains FALSE(P). The FALSE node is not deleted.
        if self._assumption_positive(ref):
            return None
        for parent_ref, obj in self._function_parents(ref, "FALSE"):
            if self._suppressed_uid(parent_ref.uid):
                continue
            if len(obj.operands) == 1 and obj.operands[0] == ref:
                return parent_ref
        return None

    def _atom_asserted(self, ref: Ref) -> bool:
        if ref.kind is not RefKind.N:
            return False
        if self._assumption_not_for(ref) is not None:
            return False
        if self._assumption_positive(ref):
            return True
        if self._suppressed_uid(ref.uid):
            return False
        node = self.core.store.get_hypernode(ref.uid)
        if node.meta.get("semantic_scope"):
            return False
        if int(node.meta.get("occurrence_count", 0)) > 0:
            return True
        # Derived facts remain admissible only while at least one independent
        # support survives the current overlay. Counterfactual suppression does
        # not mutate the persisted support ledger.
        return any(
            self._support_admissible(record.premise_refs)
            for record in self.core.resolve_supports(ref)
        )

    def _ordinary_equivalent_atom(self, ref: Ref) -> Ref | None:
        """Resolve a scoped proposition pattern to one ordinary canonical N.

        Conditional/quoted/embedded N are addressable proposition content, not
        factual premises.  For rule validation they may nevertheless *match* an
        independently asserted ordinary proposition with the same T+actants.  The
        match is deterministic and succeeds only when exactly one ordinary N has
        that canonical structure.
        """
        if ref.kind is not RefKind.N:
            return None
        node = self.core.store.get_hypernode(ref.uid)
        if not node.meta.get("semantic_scope"):
            return None
        matches = [
            item
            for item in self.core.store.find_hypernodes_by_template(node.template.uid)
            if item.uid != node.uid
            and not item.meta.get("semantic_scope")
            and dict(item.actants) == dict(node.actants)
        ]
        if len(matches) != 1:
            return None
        return self.core.ref(matches[0].uid)


    @staticmethod
    def _has_bound_actants(node: Hypernode) -> bool:
        return any(isinstance(value, BoundVar) for value in node.actants.values())

    @staticmethod
    def _merge_refs(*chunks: tuple[Ref, ...]) -> tuple[Ref, ...]:
        out: list[Ref] = []
        seen: set[tuple[str, str]] = set()
        for chunk in chunks:
            for ref in chunk:
                key = (ref.kind.value, ref.uid)
                if key in seen:
                    continue
                seen.add(key)
                out.append(ref)
        return tuple(out)

    def _bind_declared(self, env: BindingEnvironment, variable: BoundVar, value: Ref) -> bool:
        """Bind the nearest declaration of ``variable`` in a nested scope chain."""
        cursor: BindingEnvironment | None = env
        while cursor is not None:
            if cursor.is_declared_here(variable):
                existing = cursor.resolve(variable)
                if existing is not None:
                    return existing == value
                try:
                    cursor.bind(variable, value)
                except ValueError:
                    return False
                return True
            cursor = cursor.parent
        try:
            env.bind(variable, value)
        except ValueError:
            return False
        return True

    def _match_pattern_node(
        self,
        pattern: Hypernode,
        ground: Hypernode,
        env: BindingEnvironment,
    ) -> BindingEnvironment | None:
        if pattern.template != ground.template:
            return None
        candidate = env.copy()
        for role, expected in pattern.actants.items():
            actual = ground.actants.get(role)
            if not isinstance(actual, Ref):
                return None
            if isinstance(expected, Ref):
                if expected != actual:
                    return None
                continue
            if isinstance(expected, BoundVar):
                resolved = candidate.resolve(expected)
                if resolved is not None:
                    if resolved != actual:
                        return None
                    continue
                if not self._bind_declared(candidate, expected, actual):
                    return None
                continue
            return None
        return candidate

    def _pattern_atom_proofs(
        self,
        pattern_ref: Ref,
        env: BindingEnvironment,
        *,
        depth: int,
    ) -> tuple[_BoundProof, ...]:
        """Find admissible ordinary N witnesses for one variable-bearing N pattern.

        Candidate generation is restricted by the canonical T index; it never scans
        unrelated AH nodes. Conflicted/refuted facts are not accepted as positive
        premises.
        """
        pattern = self.core.store.get_hypernode(pattern_ref.uid)
        out: list[_BoundProof] = []
        for ground in self.core.store.find_hypernodes_by_template(pattern.template.uid):
            if ground.uid == pattern.uid or ground.meta.get("semantic_scope"):
                continue
            if not self._consume():
                break
            ground_ref = self.core.ref(ground.uid)
            matched = self._match_pattern_node(pattern, ground, env)
            if matched is None:
                continue
            if self._false_parent(ground_ref) is not None:
                continue
            if self.conflicts.is_conflicted(ground_ref):
                continue
            positive = self._atom_asserted(ground_ref)
            negated = self._asserted_not_parent(ground_ref)
            if not positive or negated is not None:
                continue
            self._focus(ground_ref, depth)
            self._focus(pattern_ref, depth)
            out.append(
                _BoundProof(
                    matched,
                    (ground_ref,),
                    (ground_ref, pattern_ref),
                    depth,
                )
            )
        return tuple(out)

    def _pattern_atom_negative_proofs(
        self,
        pattern_ref: Ref,
        env: BindingEnvironment,
        *,
        depth: int,
    ) -> tuple[_BoundProof, ...]:
        """Match only explicit NOT/FALSE evidence for a bound atom pattern."""
        pattern = self.core.store.get_hypernode(pattern_ref.uid)
        out: list[_BoundProof] = []
        for ground in self.core.store.find_hypernodes_by_template(pattern.template.uid):
            if ground.uid == pattern.uid or ground.meta.get("semantic_scope"):
                continue
            if not self._consume():
                break
            ground_ref = self.core.ref(ground.uid)
            matched = self._match_pattern_node(pattern, ground, env)
            if matched is None:
                continue
            if self.conflicts.is_conflicted(ground_ref):
                continue
            false_ref = self._false_parent(ground_ref)
            not_ref = self._asserted_not_parent(ground_ref)
            negative = false_ref or not_ref
            # A simultaneous positive assertion and NOT(P) is unresolved conflict,
            # not a clean negative witness.
            if negative is None:
                continue
            if self._atom_asserted(ground_ref) and not_ref is not None:
                continue
            self._focus(negative, depth)
            self._focus(pattern_ref, depth)
            out.append(
                _BoundProof(
                    matched,
                    (negative,),
                    (negative, ground_ref, pattern_ref),
                    depth,
                )
            )
        return tuple(out)

    def _prove_bound(
        self,
        ref: Ref,
        env: BindingEnvironment,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> tuple[_BoundProof, ...]:
        """Backtracking proof over a canonical N/g formula with scoped variables."""
        if depth > self.max_depth or ref.uid in stack or not self.core.store.has_uid(ref.uid):
            return ()
        if self.core.store.kind_of(ref.uid) is not ref.kind:
            return ()
        next_stack = (*stack, ref.uid)

        if ref.kind is RefKind.N:
            node = self.core.store.get_hypernode(ref.uid)
            if self._has_bound_actants(node):
                return self._pattern_atom_proofs(ref, env, depth=depth)
            outcome = self._eval(ref, depth=depth, stack=stack)
            if outcome.status is not LogicalStatus.PROVED:
                return ()
            return (
                _BoundProof(
                    env.copy(),
                    outcome.premise_refs,
                    outcome.uid_trace,
                    outcome.logical_depth,
                ),
            )

        if ref.kind is not RefKind.G:
            return ()
        obj = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(obj, FunctionSymbol):
            return ()
        try:
            canonical = self.core.function_registry.canonical_id(obj.function_id)
        except KeyError:
            return ()

        if canonical == "AND":
            children = tuple(item for item in obj.operands if isinstance(item, Ref))
            if len(children) != len(obj.operands):
                return ()
            branches = (_BoundProof(env.copy(), (), (), depth),)
            for child in children:
                next_branches: list[_BoundProof] = []
                for branch in branches:
                    for proved in self._prove_bound(
                        child,
                        branch.bindings,
                        depth=depth + 1,
                        stack=next_stack,
                    ):
                        next_branches.append(
                            _BoundProof(
                                proved.bindings,
                                self._merge_refs(branch.premise_refs, proved.premise_refs),
                                (*branch.uid_trace, *proved.uid_trace),
                                max(branch.logical_depth, proved.logical_depth),
                            )
                        )
                branches = tuple(next_branches)
                if not branches:
                    return ()
            return tuple(
                _BoundProof(
                    branch.bindings,
                    branch.premise_refs,
                    (*branch.uid_trace, ref),
                    max(branch.logical_depth, depth),
                )
                for branch in branches
            )

        if canonical == "OR":
            out: list[_BoundProof] = []
            for child in obj.operands:
                if not isinstance(child, Ref):
                    return ()
                out.extend(
                    self._prove_bound(child, env.copy(), depth=depth + 1, stack=next_stack)
                )
            return tuple(
                _BoundProof(
                    branch.bindings,
                    branch.premise_refs,
                    (*branch.uid_trace, ref),
                    branch.logical_depth,
                )
                for branch in out
            )

        if canonical == "XOR":
            # Variable-bearing XOR needs explicit negative evidence for every
            # non-selected branch before one witness can establish "exactly one".
            # Until that complete bound proof exists, only an explicitly asserted
            # XOR is admissible here; treating XOR as OR would be unsound.
            if self._asserted_function(ref, obj):
                return (_BoundProof(env.copy(), (ref,), (ref,), depth),)
            return ()

        if canonical == "NOT":
            if len(obj.operands) != 1 or not isinstance(obj.operands[0], Ref):
                return ()
            operand = obj.operands[0]
            if operand.kind is RefKind.N:
                node = self.core.store.get_hypernode(operand.uid)
                if self._has_bound_actants(node):
                    negatives = self._pattern_atom_negative_proofs(operand, env, depth=depth + 1)
                    return tuple(
                        _BoundProof(
                            branch.bindings,
                            branch.premise_refs,
                            (*branch.uid_trace, ref),
                            branch.logical_depth,
                        )
                        for branch in negatives
                    )
            child = self._eval(operand, depth=depth + 1, stack=next_stack)
            if child.status is LogicalStatus.DISPROVED:
                return (
                    _BoundProof(
                        env.copy(),
                        child.premise_refs,
                        (*child.uid_trace, ref),
                        child.logical_depth,
                    ),
                )
            return ()

        if canonical == "EXISTS":
            if len(obj.operands) != 2:
                return ()
            variable, body = obj.operands
            if not isinstance(variable, BoundVar) or not isinstance(body, Ref):
                return ()
            scoped = env.child(variable)
            witnesses = self._prove_bound(body, scoped, depth=depth + 1, stack=next_stack)
            # The witness binding belongs to the quantifier scope and therefore
            # must not leak into the parent environment. Premises/trace do survive.
            return tuple(
                _BoundProof(
                    env.copy(),
                    branch.premise_refs,
                    (*branch.uid_trace, ref),
                    branch.logical_depth,
                )
                for branch in witnesses
            )

        if canonical == "FORALL":
            # Open-world FORALL is never established by enumerating known objects.
            # Only an explicitly asserted/proof-supported universal formula is a
            # valid universal premise at this layer.
            if self._asserted_function(ref, obj):
                return (_BoundProof(env.copy(), (ref,), (ref,), depth),)
            return ()

        if canonical == "IMPLIES":
            if self._asserted_function(ref, obj):
                return (_BoundProof(env.copy(), (ref,), (ref,), depth),)
            return ()

        return ()

    def _quantifier_parent_chains(
        self,
        body_ref: Ref,
    ) -> tuple[tuple[tuple[Ref, FunctionSymbol, BoundVar], ...], ...]:
        """Return nested FORALL chains whose innermost body is ``body_ref``.

        Each chain is ordered outer -> inner. Lookup follows only the rebuildable
        reverse function-operand index from the current rule body. Nesting is not
        capped by an arbitrary architecture constant: the query's ordinary proof
        depth budget is the only limit, and cycles are rejected explicitly.
        """
        chains: list[tuple[tuple[Ref, FunctionSymbol, BoundVar], ...]] = []

        def ascend(
            current: Ref,
            inner_to_outer: tuple[tuple[Ref, FunctionSymbol, BoundVar], ...],
            path: frozenset[str],
        ) -> None:
            found = False
            for parent in self.core.store.function_parents(current.uid):
                try:
                    canonical = self.core.function_registry.canonical_id(parent.function_id)
                except KeyError:
                    continue
                if canonical != "FORALL" or len(parent.operands) != 2:
                    continue
                variable, body = parent.operands
                if not isinstance(variable, BoundVar) or body != current:
                    continue
                parent_ref = self.core.ref(parent.uid)
                if parent_ref.uid in path:
                    continue
                # Runtime/query depth is a resource bound, not a semantic limit on
                # how many nested quantifiers the canonical representation allows.
                if len(inner_to_outer) >= self.max_depth:
                    continue
                found = True
                entry = (parent_ref, parent, variable)
                ascend(
                    parent_ref,
                    (*inner_to_outer, entry),
                    path | {parent_ref.uid},
                )
            if inner_to_outer and not found:
                chains.append(tuple(reversed(inner_to_outer)))

        ascend(body_ref, (), frozenset({body_ref.uid}))
        return tuple(chains)

    def _try_quantified_implication(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        if target.kind is not RefKind.N or depth >= self.max_depth:
            return None
        ground_target = self.core.store.get_hypernode(target.uid)

        # T-index gives only proposition patterns capable of unifying with the
        # current goal. No full-AH rule scan is performed.
        quantified_patterns = tuple(
            self.core.store.find_hypernodes_by_template(ground_target.template.uid)
        )
        if self.runtime is not None:
            self.runtime.memory_query(
                "RULE_HEAD_TEMPLATE",
                f"T={ground_target.template.uid}|target={target.uid}",
                logical_depth=depth,
                focus_ref=target,
                candidate_count=len(quantified_patterns),
                detail="backward quantified rule-head lookup",
            )
        for pattern in quantified_patterns:
            if pattern.uid == ground_target.uid or not self._has_bound_actants(pattern):
                continue
            pattern_ref = self.core.ref(pattern.uid)
            for implication in self.core.store.function_parents(pattern.uid):
                try:
                    canonical = self.core.function_registry.canonical_id(implication.function_id)
                except KeyError:
                    continue
                if canonical != "IMPLIES" or len(implication.operands) != 2:
                    continue
                antecedent, consequent = implication.operands
                if consequent != pattern_ref or not isinstance(antecedent, Ref):
                    continue
                implication_ref = self.core.ref(implication.uid)
                for chain in self._quantifier_parent_chains(implication_ref):
                    if not chain:
                        continue
                    outer_ref, outer_obj, _ = chain[0]
                    if not self._asserted_function(outer_ref, outer_obj):
                        continue

                    env = BindingEnvironment()
                    for _qref, _qobj, variable in chain:
                        env = env.child(variable)
                    matched = self._match_pattern_node(pattern, ground_target, env)
                    if matched is None:
                        continue

                    self._focus(outer_ref, depth)
                    antecedent_proofs = self._prove_bound(
                        antecedent,
                        matched,
                        depth=depth + 1,
                        stack=(*stack, implication_ref.uid),
                    )
                    if not antecedent_proofs:
                        continue
                    proof = antecedent_proofs[0]
                    self._focus(implication_ref, depth + 1)
                    self._focus(target, depth + 1)
                    quantifier_refs = tuple(item[0] for item in chain)
                    premises = self._merge_refs(
                        proof.premise_refs,
                        quantifier_refs,
                        (implication_ref,),
                    )
                    trace = (*proof.uid_trace, *quantifier_refs, implication_ref, target)
                    return self._outcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        target,
                        premises,
                        trace,
                        depth=max(proof.logical_depth + 1, depth + 1),
                        diagnostics=("FORALL-instantiated IMPLIES modus ponens",),
                        rule_id="FORALL_IMPLIES_MP",
                        bindings=proof.bindings,
                    )
        return None

    def _try_and_elimination(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        for parent_ref, obj in self._function_parents(target, "AND"):
            if target not in obj.operands or not self._asserted_function(parent_ref, obj):
                continue
            self._focus(parent_ref, depth)
            self._focus(target, depth + 1)
            premises = (parent_ref,)
            return self._outcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                target,
                premises,
                (parent_ref, target),
                depth=depth + 1,
                diagnostics=("AND elimination from asserted compound",),
                rule_id="AND_ELIM",
            )
        return None

    def _try_disjunctive_elimination(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        """Derive one disjunct when an asserted OR leaves it as the only live branch.

        This is target-directed OR elimination: for an asserted OR(A, B, ...),
        target B is proved only when every *other* branch is explicitly disproved.
        UNKNOWN branches block the rule, and conflicted branches remain UNKNOWN via
        the ordinary evaluator, so open-world absence can never eliminate a branch.
        """
        if depth >= self.max_depth:
            return None

        checked: set[str] = set()
        for or_ref, or_obj in self._alternative_parents(target):
            if or_ref.uid in checked:
                continue
            checked.add(or_ref.uid)
            if not self._asserted_function(or_ref, or_obj):
                continue
            if self.conflicts.is_conflicted(or_ref):
                continue
            branches = tuple(item for item in or_obj.operands if isinstance(item, Ref))
            if len(branches) != len(or_obj.operands) or target not in branches or len(branches) < 2:
                continue

            other_outcomes: list[InferenceOutcome] = []
            blocked = False
            for branch in branches:
                if branch == target:
                    continue
                outcome = self._eval(branch, depth=depth + 1, stack=(*stack, or_ref.uid))
                if outcome.status is not LogicalStatus.DISPROVED:
                    blocked = True
                    break
                other_outcomes.append(outcome)
            if blocked or len(other_outcomes) != len(branches) - 1:
                continue

            self._focus(or_ref, depth)
            premises: list[Ref] = [or_ref]
            seen = {or_ref.uid}
            trace: list[Ref] = [or_ref]
            max_depth = depth
            for outcome in other_outcomes:
                for premise in outcome.premise_refs:
                    if premise.uid not in seen:
                        seen.add(premise.uid)
                        premises.append(premise)
                trace.extend(outcome.uid_trace)
                max_depth = max(max_depth, outcome.logical_depth)
            trace.append(target)
            self._focus(target, max_depth + 1)
            return self._outcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                target,
                tuple(premises),
                tuple(trace),
                depth=max_depth + 1,
                diagnostics=(
                    "asserted "
                    f"{self.core.function_registry.canonical_id(or_obj.function_id)} "
                    f"leaves {target.uid} as the only non-refuted branch",
                ),
                rule_id=(
                    f"{self.core.function_registry.canonical_id(or_obj.function_id)}_ELIM"
                ),
            )
        return None

    def _try_xor_exclusion(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        """Refute one XOR branch when a different exclusive branch is proved.

        This is the information that inclusive OR deliberately does not provide.
        A branch is never rejected from absence alone: another branch must have a
        positive proof under the ordinary open-world evaluator.
        """
        if depth >= self.max_depth:
            return None

        for xor_ref, xor_obj in self._function_parents(target, "XOR"):
            if not self._asserted_function(xor_ref, xor_obj):
                continue
            if self.conflicts.is_conflicted(xor_ref):
                continue
            branches = tuple(
                item for item in xor_obj.operands if isinstance(item, Ref)
            )
            if (
                len(branches) != len(xor_obj.operands)
                or target not in branches
                or len(branches) < 2
            ):
                continue

            for branch in branches:
                if branch == target:
                    continue
                outcome = self._eval(
                    branch,
                    depth=depth + 1,
                    stack=(*stack, xor_ref.uid),
                )
                if outcome.status is not LogicalStatus.PROVED:
                    continue
                self._focus(xor_ref, depth)
                self._focus(target, max(depth + 1, outcome.logical_depth))
                premises = self._merge_refs((xor_ref,), outcome.premise_refs)
                return self._outcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_REFUTED,
                    target,
                    premises,
                    (xor_ref, *outcome.uid_trace, target),
                    depth=max(depth + 1, outcome.logical_depth),
                    diagnostics=(
                        f"XOR exclusion: proved {branch.uid}, therefore {target.uid} is false",
                    ),
                    rule_id="XOR_EXCLUSION",
                )
        return None

    def _try_proof_by_cases(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        """Disjunctive elimination with runtime-only branch assumptions.

        Goal-directed discovery starts from IMPLIES rules whose consequent is the
        current target, then follows the reverse function index from an antecedent
        to an asserted OR.  No arbitrary scan over unrelated formulas is used.
        """
        if depth >= self.max_depth:
            return None

        rules_by_antecedent: dict[Ref, tuple[Ref, FunctionSymbol]] = {}
        for rule_ref, rule in self._function_parents(target, "IMPLIES"):
            if len(rule.operands) != 2 or rule.operands[1] != target:
                continue
            antecedent = rule.operands[0]
            if not isinstance(antecedent, Ref) or not self._asserted_function(rule_ref, rule):
                continue
            rules_by_antecedent.setdefault(antecedent, (rule_ref, rule))

        if len(rules_by_antecedent) < 2:
            return None

        checked_or: set[str] = set()
        for antecedent in tuple(rules_by_antecedent):
            for or_ref, or_obj in self._alternative_parents(antecedent):
                if or_ref.uid in checked_or:
                    continue
                checked_or.add(or_ref.uid)
                if not self._asserted_function(or_ref, or_obj):
                    continue
                if self.conflicts.is_conflicted(or_ref):
                    continue
                branches = tuple(item for item in or_obj.operands if isinstance(item, Ref))
                if len(branches) != len(or_obj.operands) or len(branches) < 2:
                    continue
                if any(branch not in rules_by_antecedent for branch in branches):
                    continue

                branch_outcomes: list[InferenceOutcome] = []
                for branch in branches:
                    if self.runtime is not None:
                        self.runtime.subgoal(
                            logical_depth=depth + 1,
                            ref=branch,
                            detail=f"proof-by-cases branch under {or_ref.uid}",
                        )
                    branch_context = BranchContext(
                        parent=self._active_context,
                        bindings=self._active_context.bindings.child(),
                        assumptions=(branch,),
                        branch_assumption=branch,
                    )
                    branch_stack = tuple(uid for uid in stack if uid != target.uid)
                    outcome = self._evaluate_in_context(
                        target,
                        branch_context,
                        depth=depth + 1,
                        stack=(*branch_stack, or_ref.uid),
                    )
                    if outcome.status is not LogicalStatus.PROVED:
                        branch_outcomes = []
                        break
                    branch_outcomes.append(outcome)
                if len(branch_outcomes) != len(branches):
                    continue

                self._focus(or_ref, depth)
                premises: list[Ref] = [or_ref]
                premise_seen = {or_ref.uid}
                trace: list[Ref] = [or_ref]
                max_branch_depth = depth
                for branch, outcome in zip(branches, branch_outcomes):
                    rule_ref, _rule = rules_by_antecedent[branch]
                    if rule_ref.uid not in premise_seen:
                        premise_seen.add(rule_ref.uid)
                        premises.append(rule_ref)
                    for premise in outcome.premise_refs:
                        # Branch assumptions are scoped hypotheses licensed by OR,
                        # not independent factual supports of the final conclusion.
                        if premise == branch:
                            continue
                        if premise.uid not in premise_seen:
                            premise_seen.add(premise.uid)
                            premises.append(premise)
                    trace.extend((branch, rule_ref))
                    trace.extend(outcome.uid_trace)
                    max_branch_depth = max(max_branch_depth, outcome.logical_depth)
                trace.append(target)
                self._focus(target, max_branch_depth + 1)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    target,
                    tuple(premises),
                    tuple(trace),
                    depth=max_branch_depth + 1,
                    diagnostics=(
                        "proof by cases over asserted "
                        f"{self.core.function_registry.canonical_id(or_obj.function_id)} "
                        f"with {len(branches)} branches",
                    ),
                    rule_id=(
                        f"{self.core.function_registry.canonical_id(or_obj.function_id)}_CASES"
                    ),
                )
        return None

    def _try_implication(
        self,
        target: Ref,
        *,
        depth: int,
        stack: tuple[str, ...],
    ) -> InferenceOutcome | None:
        if depth >= self.max_depth:
            return None
        for rule_ref, obj in self._function_parents(target, "IMPLIES"):
            if len(obj.operands) != 2 or obj.operands[1] != target:
                continue
            if not self._asserted_function(rule_ref, obj):
                continue
            antecedent = obj.operands[0]
            if not isinstance(antecedent, Ref):
                continue
            self._focus(rule_ref, depth)
            if self.runtime is not None:
                self.runtime.subgoal(
                    logical_depth=depth + 1,
                    ref=antecedent,
                    detail=f"backward decomposition from IMPLIES rule {rule_ref.uid}",
                )
            ant = self._eval(antecedent, depth=depth + 1, stack=stack)
            if ant.status is not LogicalStatus.PROVED:
                continue
            self._focus(target, depth + 1)
            premises = tuple(dict.fromkeys((*ant.premise_refs, rule_ref)))
            trace = tuple((*ant.uid_trace, rule_ref, target))
            return self._outcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                target,
                premises,
                trace,
                depth=max(depth + 1, ant.logical_depth + 1),
                diagnostics=("Ground IMPLIES modus ponens",),
                rule_id="IMPLIES_MP",
            )
        return None

    def _eval_atom(self, ref: Ref, *, depth: int, stack: tuple[str, ...]) -> InferenceOutcome:
        ordinary = self._ordinary_equivalent_atom(ref)
        if ordinary is not None:
            grounded = self._eval(ordinary, depth=depth, stack=stack)
            if grounded.status is LogicalStatus.PROVED:
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    grounded.premise_refs,
                    tuple((*grounded.uid_trace, ref)),
                    depth=grounded.logical_depth,
                    diagnostics=("Scoped proposition matched one ordinary asserted N",),
                    rule_id="SCOPED_ATOM_MATCH",
                )
            if grounded.status is LogicalStatus.DISPROVED:
                return self._outcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_REFUTED,
                    grounded.conclusion.ref if isinstance(grounded.conclusion, ExistingRefConclusion) else None,
                    grounded.premise_refs,
                    tuple((*grounded.uid_trace, ref)),
                    depth=grounded.logical_depth,
                    diagnostics=("Scoped proposition matched one refuted ordinary N",),
                    rule_id="SCOPED_ATOM_MATCH",
                )

        false_ref = self._false_parent(ref)
        if false_ref is not None:
            self._focus(false_ref, depth)
            self._focus(ref, depth)
            premises = (false_ref, ref)
            return self._outcome(
                LogicalStatus.DISPROVED,
                StopReason.GOAL_REFUTED,
                false_ref,
                premises,
                premises,
                depth=depth,
                diagnostics=("Explicit FALSE(N) refutation",),
                rule_id="EXPLICIT_REFUTATION",
            )

        positive = self._atom_asserted(ref)
        not_ref = self._asserted_not_parent(ref)
        if positive and not_ref is not None:
            self._focus(ref, depth)
            self._focus(not_ref, depth)
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.CONFLICTED,
                None,
                (ref, not_ref),
                (ref, not_ref),
                depth=depth,
                diagnostics=("Both P and NOT(P) are asserted",),
            )
        if positive:
            self._focus(ref, depth)
            return self._outcome(
                LogicalStatus.PROVED,
                StopReason.GOAL_SATISFIED,
                ref,
                (ref,),
                (ref,),
                depth=depth,
                rule_id="FACT_ASSERTED",
            )
        if not_ref is not None:
            self._focus(not_ref, depth)
            self._focus(ref, depth)
            return self._outcome(
                LogicalStatus.DISPROVED,
                StopReason.GOAL_REFUTED,
                not_ref,
                (not_ref,),
                (not_ref, ref),
                depth=depth,
                diagnostics=("Asserted NOT(P)",),
                rule_id="NOT_ASSERTED",
            )

        eliminated = self._try_and_elimination(ref, depth=depth, stack=stack)
        if eliminated is not None:
            return eliminated
        disjunct = self._try_disjunctive_elimination(ref, depth=depth, stack=stack)
        if disjunct is not None:
            return disjunct
        xor_excluded = self._try_xor_exclusion(ref, depth=depth, stack=stack)
        if xor_excluded is not None:
            return xor_excluded
        implied = self._try_implication(ref, depth=depth, stack=stack)
        if implied is not None:
            return implied
        quantified = self._try_quantified_implication(ref, depth=depth, stack=stack)
        if quantified is not None:
            return quantified
        by_cases = self._try_proof_by_cases(ref, depth=depth, stack=stack)
        if by_cases is not None:
            return by_cases

        return self._outcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            depth=depth,
        )

    def _eval_function(self, ref: Ref, obj: FunctionSymbol, *, depth: int, stack: tuple[str, ...]) -> InferenceOutcome:
        canonical = self.core.function_registry.canonical_id(obj.function_id)

        if any(isinstance(operand, Ref) and operand.uid == ref.uid for operand in obj.operands):
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (ref,),
                depth=depth,
                diagnostics=("Self-referential meta/formula expression is excluded from ordinary proof",),
            )

        if canonical == "FALSE":
            if len(obj.operands) == 1 and isinstance(obj.operands[0], Ref):
                target = obj.operands[0]
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref, target),
                    (ref, target),
                    depth=depth,
                    rule_id="EXPLICIT_REFUTATION",
                )

        if canonical in {"CONTRADICTS", "CORRECTS"}:
            # These are operational meta-propositions created only by explicit
            # deterministic services. Their presence proves the meta statement,
            # never the truth of their embedded operands.
            if len(obj.operands) == 2 and all(isinstance(item, Ref) for item in obj.operands):
                if self._suppressed_uid(ref.uid):
                    return self._outcome(
                        LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), depth=depth
                    )
                self._focus(ref, depth)
                operands = tuple(item for item in obj.operands if isinstance(item, Ref))
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref, *operands),
                    depth=depth,
                    rule_id=f"{canonical}_EXPLICIT",
                )

        if canonical == "NOT":
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id="NOT_ASSERTED",
                )
            operand = obj.operands[0] if len(obj.operands) == 1 else None
            if isinstance(operand, Ref):
                child = self._eval(operand, depth=depth, stack=stack)
                if child.status is LogicalStatus.DISPROVED:
                    premises = child.premise_refs
                    return self._outcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        ref,
                        premises,
                        tuple((*child.uid_trace, ref)),
                        depth=child.logical_depth,
                        rule_id="NOT_INTRO",
                    )
                if child.status is LogicalStatus.PROVED:
                    return self._outcome(
                        LogicalStatus.DISPROVED,
                        StopReason.GOAL_REFUTED,
                        operand,
                        child.premise_refs,
                        tuple((*child.uid_trace, ref)),
                        depth=child.logical_depth,
                        rule_id="NOT_CONTRADICTION",
                    )
            return self._outcome(LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), depth=depth)

        if canonical == "XOR":
            # Natural-language n-ary XOR means exactly one true branch, not parity
            # XOR. Open-world UNKNOWN therefore blocks introduction unless every
            # other branch has explicit negative support.
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id="XOR_ASSERTED",
                )

            children = [
                operand for operand in obj.operands if isinstance(operand, Ref)
            ]
            if len(children) != len(obj.operands):
                return self._outcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.SEARCH_EXHAUSTED,
                    None,
                    (),
                    (),
                    depth=depth,
                    diagnostics=("XOR contains unresolved non-Ref operands",),
                )
            outcomes = [
                self._eval(child, depth=depth, stack=stack)
                for child in children
            ]
            proved = [
                item for item in outcomes if item.status is LogicalStatus.PROVED
            ]
            disproved = [
                item for item in outcomes if item.status is LogicalStatus.DISPROVED
            ]

            if len(proved) >= 2:
                witnesses = proved[:2]
                premises = tuple(
                    dict.fromkeys(
                        premise
                        for item in witnesses
                        for premise in item.premise_refs
                    )
                )
                trace = tuple(
                    step for item in witnesses for step in item.uid_trace
                ) + (ref,)
                return self._outcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_REFUTED,
                    ref,
                    premises,
                    trace,
                    depth=max(
                        (item.logical_depth for item in witnesses), default=depth
                    ),
                    diagnostics=("XOR refuted by multiple proved branches",),
                    rule_id="XOR_MULTI_TRUE",
                )

            if len(proved) == 1 and len(disproved) == len(children) - 1:
                premises = tuple(
                    dict.fromkeys(
                        premise
                        for item in outcomes
                        for premise in item.premise_refs
                    )
                )
                trace = tuple(
                    step for item in outcomes for step in item.uid_trace
                ) + (ref,)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    premises,
                    trace,
                    depth=max(
                        (item.logical_depth for item in outcomes), default=depth
                    ),
                    rule_id="XOR_INTRO",
                )

            if outcomes and len(disproved) == len(children):
                premises = tuple(
                    dict.fromkeys(
                        premise
                        for item in outcomes
                        for premise in item.premise_refs
                    )
                )
                trace = tuple(
                    step for item in outcomes for step in item.uid_trace
                ) + (ref,)
                return self._outcome(
                    LogicalStatus.DISPROVED,
                    StopReason.GOAL_REFUTED,
                    ref,
                    premises,
                    trace,
                    depth=max(
                        (item.logical_depth for item in outcomes), default=depth
                    ),
                    diagnostics=("XOR refuted because every branch is false",),
                    rule_id="XOR_ALL_FALSE",
                )

            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
            )

        if canonical in {"AND", "OR"}:
            # A top-level compound explicitly asserted by the user is sufficient
            # evidence for the compound itself, while its scoped children retain
            # their own admissibility rules.
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id=f"{canonical}_ASSERTED",
                )

            children = [operand for operand in obj.operands if isinstance(operand, Ref)]
            if len(children) != len(obj.operands):
                return self._outcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.SEARCH_EXHAUSTED,
                    None,
                    (),
                    (),
                    depth=depth,
                    diagnostics=(f"{canonical} contains unresolved non-Ref operands",),
                )
            outcomes = [self._eval(child, depth=depth, stack=stack) for child in children]
            if canonical == "AND":
                disproved = next((item for item in outcomes if item.status is LogicalStatus.DISPROVED), None)
                if disproved is not None:
                    return self._outcome(
                        LogicalStatus.DISPROVED,
                        StopReason.GOAL_REFUTED,
                        disproved.conclusion.ref if isinstance(disproved.conclusion, ExistingRefConclusion) else None,
                        disproved.premise_refs,
                        tuple((*disproved.uid_trace, ref)),
                        depth=max((item.logical_depth for item in outcomes), default=depth),
                        rule_id="AND_REFUTED",
                    )
                if all(item.status is LogicalStatus.PROVED for item in outcomes):
                    premises = tuple(dict.fromkeys(r for item in outcomes for r in item.premise_refs))
                    trace = tuple(r for item in outcomes for r in item.uid_trace) + (ref,)
                    return self._outcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        ref,
                        premises,
                        trace,
                        depth=max((item.logical_depth for item in outcomes), default=depth),
                        rule_id="AND_INTRO",
                    )
            else:
                proved = next((item for item in outcomes if item.status is LogicalStatus.PROVED), None)
                if proved is not None:
                    return self._outcome(
                        LogicalStatus.PROVED,
                        StopReason.GOAL_SATISFIED,
                        ref,
                        proved.premise_refs,
                        tuple((*proved.uid_trace, ref)),
                        depth=proved.logical_depth,
                        rule_id="OR_INTRO",
                    )
                if outcomes and all(item.status is LogicalStatus.DISPROVED for item in outcomes):
                    premises = tuple(dict.fromkeys(r for item in outcomes for r in item.premise_refs))
                    trace = tuple(r for item in outcomes for r in item.uid_trace) + (ref,)
                    return self._outcome(
                        LogicalStatus.DISPROVED,
                        StopReason.GOAL_REFUTED,
                        ref,
                        premises,
                        trace,
                        depth=max((item.logical_depth for item in outcomes), default=depth),
                        rule_id="OR_REFUTED",
                    )
            return self._outcome(LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), depth=depth)

        if canonical == "IMPLIES":
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id="IMPLIES_ASSERTED",
                )
            return self._outcome(LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), depth=depth)

        if canonical == "FORALL":
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id="FORALL_ASSERTED",
                )
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=(
                    "Open-world FORALL requires an explicit universal rule or formal universal proof",
                ),
            )

        if canonical == "EXISTS":
            if self._asserted_function(ref, obj):
                self._focus(ref, depth)
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    (ref,),
                    (ref,),
                    depth=depth,
                    rule_id="EXISTS_ASSERTED",
                )
            if len(obj.operands) != 2:
                return self._outcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.SEARCH_EXHAUSTED,
                    None,
                    (),
                    (),
                    depth=depth,
                    diagnostics=("EXISTS has no executable body",),
                )
            variable, body = obj.operands
            if not isinstance(variable, BoundVar) or not isinstance(body, Ref):
                return self._outcome(
                    LogicalStatus.UNKNOWN,
                    StopReason.SEARCH_EXHAUSTED,
                    None,
                    (),
                    (),
                    depth=depth,
                    diagnostics=("EXISTS operands are not (BoundVar, body_ref)",),
                )
            root_env = BindingEnvironment()
            scoped = root_env.child(variable)
            witnesses = self._prove_bound(body, scoped, depth=depth + 1, stack=stack)
            if witnesses:
                witness = witnesses[0]
                self._focus(ref, depth)
                premises = witness.premise_refs
                return self._outcome(
                    LogicalStatus.PROVED,
                    StopReason.GOAL_SATISFIED,
                    ref,
                    premises,
                    (*witness.uid_trace, ref),
                    depth=witness.logical_depth,
                    diagnostics=("EXISTS witness found",),
                    rule_id="EXISTS_WITNESS",
                    bindings=witness.bindings,
                )
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.BUDGET_EXHAUSTED if self.state.budget_exhausted else StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=("No EXISTS witness found; open-world result is UNKNOWN",),
            )

        return self._outcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            depth=depth,
            diagnostics=(f"No ground formula rule for {canonical}",),
        )

    def _eval(self, ref: Ref, *, depth: int, stack: tuple[str, ...]) -> InferenceOutcome:
        if not self._consume():
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.BUDGET_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=("Formula proof budget exhausted",),
            )
        if depth > self.max_depth:
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.DEPTH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
            )
        if ref.uid in stack:
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=("Cyclic formula/rule dependency",),
            )
        if not self.core.store.has_uid(ref.uid):
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=(f"Missing formula UID: {ref.uid}",),
            )

        actual = self.core.store.kind_of(ref.uid)
        if actual is not ref.kind:
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.SEARCH_EXHAUSTED,
                None,
                (),
                (),
                depth=depth,
                diagnostics=(f"Formula ref kind mismatch for {ref.uid}",),
            )

        # A canonical k_CONFLICT is an addressable record of unresolved opposed
        # propositions, not a truth selector.  Any member of a still-live conflict
        # is inadmissible as an unconditional premise.  Explicit FALSE/correction
        # can make the historical group resolved; ConflictEngine computes that from
        # current support instead of deleting whichever side happened to be older.
        conflict_sets = self.conflicts.unresolved_for(ref)
        local_override = (
            self._assumption_positive(ref)
            or self._assumption_not_for(ref) is not None
            or self._suppressed_uid(ref.uid)
        )
        if conflict_sets and not local_override:
            record = conflict_sets[0]
            self._focus(record.group_ref, depth)
            for member in record.members:
                self._focus(member, depth)
            premises = tuple(record.members)
            return self._outcome(
                LogicalStatus.UNKNOWN,
                StopReason.CONFLICTED,
                None,
                premises,
                tuple((*premises, record.group_ref)),
                depth=depth,
                diagnostics=(
                    "Both P and NOT(P) are asserted; unresolved canonical conflict "
                    f"{record.group_ref.uid}: "
                    + ", ".join(member.uid for member in record.members),
                ),
            )

        next_stack = (*stack, ref.uid)
        if ref.kind is RefKind.N:
            return self._eval_atom(ref, depth=depth, stack=next_stack)
        if ref.kind is RefKind.G:
            obj = self.core.store.get_element_any_domain(ref.uid)
            if not isinstance(obj, FunctionSymbol):
                return self._outcome(LogicalStatus.UNKNOWN, StopReason.SEARCH_EXHAUSTED, None, (), (), depth=depth)
            return self._eval_function(ref, obj, depth=depth, stack=next_stack)
        return self._outcome(
            LogicalStatus.UNKNOWN,
            StopReason.SEARCH_EXHAUSTED,
            None,
            (),
            (),
            depth=depth,
            diagnostics=("FormulaGoal accepts only N/G",),
        )
