from __future__ import annotations

from dataclasses import replace
from collections import deque

from ah.model import ActantRole, Domain, FunctionSymbol, Group, Hypernode, Ref, RefKind, Template

from .contracts import (
    AssociationBudget,
    AssociationDomainPolicy,
    AssociationFrameBinding,
    AssociationFramePattern,
    AssociationOutcome,
    AssociationSemantics,
)
from .coordinator import (
    AssociationCoordinator as _BaseAssociationCoordinator,
    AssociationSearchState,
    _LEFT,
    _RIGHT,
)


class AssociationCoordinator(_BaseAssociationCoordinator):
    """Association search that reports the nearest shared semantic frame.

    Raw activation convergence at a predicate/template symbol is useful search
    provenance but is usually too generic to answer ``what do A and B have in
    common?``.  This layer waits for the two fronts to expose supporting N facts and
    intersects those frames.  The queried endpoint role becomes a hole while roles
    shared by both facts remain constrained.  Thus

        HAVE(crow, paws) + HAVE(table, legs) + paws IS-A legs

    is reported as ``HAVE(SUBJECT=_, OBJECT=legs)`` rather than merely ``HAVE``.

    The pattern is runtime-only.  It never creates T/N/g/k or a new world fact.
    """

    _ISA_DEPTH = 6

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._excluded_signatures: frozenset[str] = frozenset()

    def solve(
        self,
        request,
        *,
        budget: AssociationBudget | None = None,
        domain_policy: AssociationDomainPolicy = AssociationDomainPolicy.ALL,
        excluded_signatures: tuple[str, ...] | frozenset[str] = (),
    ) -> AssociationOutcome:
        previous = self._excluded_signatures
        self._excluded_signatures = frozenset(str(item) for item in excluded_signatures if item)
        try:
            return super().solve(
                request,
                budget=budget,
                domain_policy=domain_policy,
            )
        finally:
            self._excluded_signatures = previous

    def _element(self, ref: Ref):
        if ref.kind in {RefKind.S, RefKind.L}:
            return None
        try:
            return self.core.store.get_element_any_domain(ref.uid)
        except Exception:
            return None

    def _operand_contains(self, operand, target: Ref, seen: set[str] | None = None) -> bool:
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
            return any(self._operand_contains(member, target, seen) for member in obj.members)
        if isinstance(obj, FunctionSymbol):
            return any(
                self._operand_contains(member, target, seen)
                for member in obj.operands
                if isinstance(member, Ref)
            )
        return False

    @staticmethod
    def _relation_key(value: str) -> str:
        return value.upper().replace("_", "-")

    def _is_a_ancestors(self, origin: Ref) -> dict[str, tuple[Ref, int]]:
        """Bounded nearest ancestors reached only through canonical positive IS-A L."""
        found: dict[str, tuple[Ref, int]] = {origin.uid: (origin, 0)}
        queue = deque([(origin, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= self._ISA_DEPTH:
                continue
            try:
                links = tuple(self.core.store.outgoing_links(current.uid))
            except Exception:
                links = ()
            for link in links:
                if link.weight <= 0 or self._relation_key(link.relation_id) != "IS-A":
                    continue
                target = link.target
                next_depth = depth + 1
                old = found.get(target.uid)
                if old is not None and old[1] <= next_depth:
                    continue
                found[target.uid] = (target, next_depth)
                queue.append((target, next_depth))
        return found

    def _common_role_value(self, left, right) -> tuple[Ref, bool] | None:
        if not isinstance(left, Ref) or not isinstance(right, Ref):
            return None
        if left == right:
            return left, False
        left_ancestors = self._is_a_ancestors(left)
        right_ancestors = self._is_a_ancestors(right)
        common = set(left_ancestors) & set(right_ancestors)
        if not common:
            return None
        uid = min(
            common,
            key=lambda item: (
                left_ancestors[item][1] + right_ancestors[item][1],
                max(left_ancestors[item][1], right_ancestors[item][1]),
                item,
            ),
        )
        value = left_ancestors[uid][0]
        # If the only common value is one of the two observations this is still a
        # real generalization (e.g. paws IS-A legs, legs == legs).
        return value, True

    def _active_facts(self, state: AssociationSearchState, front: str):
        out: list[tuple[Ref, Hypernode]] = []
        for uid in state.parents[front]:
            try:
                ref = self.core.ref(uid)
            except Exception:
                continue
            if ref.kind is not RefKind.N:
                continue
            obj = self._element(ref)
            if isinstance(obj, Hypernode) and obj.weight > 0:
                out.append((ref, obj))
        return out

    def _compatible_frame_schema(
        self,
        left: Hypernode,
        right: Hypernode,
    ) -> tuple[Ref, Ref, tuple[ActantRole, ...]] | None:
        """Return a common predicate schema for two supporting facts.

        Template UID equality is stronger than semantic predicate equality. In
        production the same predicate may legitimately have several T shapes because
        one occurrence exposes an optional role (TIME, LOCATION, CAUSE, ...), while
        another does not. Requiring the exact same T made two otherwise compatible
        facts invisible to association. Keep lexical predicate identity strict, but
        intersect their role schemas instead of requiring identical template UIDs.
        """
        left_template = self._element(left.template)
        right_template = self._element(right.template)
        if not isinstance(left_template, Template) or not isinstance(right_template, Template):
            return None
        if left_template.predicate != right_template.predicate:
            return None

        common_roles = tuple(
            sorted(
                set(left_template.roles) & set(right_template.roles),
                key=lambda role: role.value,
            )
        )
        if not common_roles:
            return None

        # AssociationFramePattern keeps one structural anchor for provenance. When
        # both facts use distinct compatible templates, choose a stable canonical
        # anchor; semantic rendering uses the shared predicate and common roles.
        template_anchor = min(
            (left.template, right.template),
            key=lambda ref: (ref.kind.value, ref.uid),
        )
        return template_anchor, left_template.predicate, common_roles

    def _pattern_for_pair(
        self,
        state: AssociationSearchState,
        left_ref: Ref,
        left: Hypernode,
        right_ref: Ref,
        right: Hypernode,
    ) -> AssociationFramePattern | None:
        schema = self._compatible_frame_schema(left, right)
        if schema is None:
            return None
        template_anchor, predicate_ref, common_roles = schema

        variable_roles: list[ActantRole] = []
        for role in common_roles:
            left_operand = left.actants.get(role)
            right_operand = right.actants.get(role)
            if left_operand is None or right_operand is None:
                continue
            if (
                self._operand_contains(left_operand, state.goal.left)
                and self._operand_contains(right_operand, state.goal.right)
            ):
                variable_roles.append(role)

        # A shared predicate is an association between the queried endpoints only
        # when both endpoints occupy the same semantic slot in the supporting frames.
        # This also covers one H fact whose role is a group containing both members.
        if not variable_roles:
            return None

        bindings: list[AssociationFrameBinding] = []
        for role in common_roles:
            if role in variable_roles:
                continue
            left_operand = left.actants.get(role)
            right_operand = right.actants.get(role)
            if left_operand is None or right_operand is None:
                continue
            common = self._common_role_value(left_operand, right_operand)
            if common is None:
                continue
            value, generalized = common
            bindings.append(AssociationFrameBinding(role, value, generalized))

        variable_tuple = tuple(sorted(variable_roles, key=lambda role: role.value))
        binding_tuple = tuple(sorted(bindings, key=lambda item: item.role.value))
        if left.template == right.template:
            frame_identity = left.template.uid
        else:
            template_pair = ",".join(sorted((left.template.uid, right.template.uid)))
            frame_identity = f"PRED:{predicate_ref.uid}|TEMPLATES:{template_pair}"
        signature = "FRAME:{}|VAR:{}|BIND:{}".format(
            frame_identity,
            ",".join(role.value for role in variable_tuple),
            ",".join(f"{item.role.value}={item.value.uid}" for item in binding_tuple),
        )
        semantics = (
            AssociationSemantics.EPISODIC
            if (
                self.core.store.domain_of(left_ref.uid) is Domain.H
                or self.core.store.domain_of(right_ref.uid) is Domain.H
            )
            else AssociationSemantics.SEMANTIC
        )
        return AssociationFramePattern(
            template=template_anchor,
            predicate=predicate_ref,
            variable_roles=variable_tuple,
            bindings=binding_tuple,
            left_fact=left_ref,
            right_fact=right_ref,
            signature=signature,
            semantics=semantics,
        )

    def _pattern_excluded(self, pattern: AssociationFramePattern) -> bool:
        if pattern.signature in self._excluded_signatures:
            return True
        # A raw convergence on the sole retained binding and the corresponding
        # one-binding frame express the same answer at two representation levels.
        # Example: REF:legs and HAVE(SUBJECT=_, OBJECT=legs).  History used to see
        # different strings and emit the same natural-language commonality twice.
        # Do not generalize this rule to richer frames: SEE(_, yard, user) remains
        # a distinct association even if one of its individual bindings was seen.
        if len(pattern.bindings) == 1:
            return f"REF:{pattern.bindings[0].value.uid}" in self._excluded_signatures
        return False

    def _frame_patterns(self, state: AssociationSearchState) -> tuple[AssociationFramePattern, ...]:
        patterns: dict[str, AssociationFramePattern] = {}
        left_facts = self._active_facts(state, _LEFT)
        right_facts = self._active_facts(state, _RIGHT)
        for left_ref, left in left_facts:
            for right_ref, right in right_facts:
                pattern = self._pattern_for_pair(state, left_ref, left, right_ref, right)
                if pattern is None or self._pattern_excluded(pattern):
                    continue
                current = patterns.get(pattern.signature)
                if current is None:
                    patterns[pattern.signature] = pattern
                    continue
                current_depth = (
                    state.depths[_LEFT].get(current.left_fact.uid, 10**6)
                    + state.depths[_RIGHT].get(current.right_fact.uid, 10**6)
                )
                new_depth = (
                    state.depths[_LEFT].get(pattern.left_fact.uid, 10**6)
                    + state.depths[_RIGHT].get(pattern.right_fact.uid, 10**6)
                )
                if new_depth < current_depth:
                    patterns[pattern.signature] = pattern
        return tuple(patterns.values())

    def _best_frame_pattern(self, state: AssociationSearchState) -> AssociationFramePattern | None:
        patterns = self._frame_patterns(state)
        if not patterns:
            return None

        def key(pattern: AssociationFramePattern):
            depth = (
                state.depths[_LEFT].get(pattern.left_fact.uid, 10**6)
                + state.depths[_RIGHT].get(pattern.right_fact.uid, 10**6)
            )
            exact = sum(1 for item in pattern.bindings if not item.generalized)
            generalized = sum(1 for item in pattern.bindings if item.generalized)
            # Distance remains primary (the nearest association wins); at equal
            # distance prefer the frame carrying more shared semantic constraints.
            return (
                depth,
                -len(pattern.bindings),
                -exact,
                generalized,
                pattern.signature,
            )

        return min(patterns, key=key)

    def _raw_common_allowed(self, state: AssociationSearchState, uid: str) -> bool:
        if f"REF:{uid}" in self._excluded_signatures:
            return False
        ref = self.core.ref(uid)
        # S/T are structural hubs. They may explain propagation, but stopping there
        # discards argument structure (the bug that produced bare ``есть``).
        if ref.kind in {RefKind.S, RefKind.T}:
            return False
        if ref.kind is RefKind.N:
            obj = self._element(ref)
            if not isinstance(obj, Hypernode):
                return False
            # A concrete fact is a legitimate direct association only when that one
            # fact itself contains both queried endpoints. Otherwise one front may
            # merely have reached the other endpoint's fact through a shared actant.
            has_left = any(
                self._operand_contains(value, state.goal.left)
                for value in obj.actants.values()
            )
            has_right = any(
                self._operand_contains(value, state.goal.right)
                for value in obj.actants.values()
            )
            return has_left and has_right
        return True

    def _select_common(self, state: AssociationSearchState) -> Ref | None:
        common = state.intersection()
        if not common:
            return None

        pattern = self._best_frame_pattern(state)
        if pattern is not None:
            # Use an actually converged canonical structural ref only as ancestry
            # anchor. The answer/projection uses the richer runtime frame pattern.
            if pattern.template.uid in common:
                return pattern.template
            if pattern.predicate.uid in common:
                return pattern.predicate
            return None

        eligible = [uid for uid in common if self._raw_common_allowed(state, uid)]
        if not eligible:
            return None

        def key(uid: str):
            left_tick = state.discovered_tick[_LEFT].get(uid, -1)
            right_tick = state.discovered_tick[_RIGHT].get(uid, -1)
            left_depth = state.depths[_LEFT][uid]
            right_depth = state.depths[_RIGHT][uid]
            return (
                max(left_tick, right_tick),
                left_depth + right_depth,
                max(left_depth, right_depth),
                uid,
            )

        return self.core.ref(min(eligible, key=key))

    def _outcome(self, state, status, common, start_tick, policy, *, ticks_executed=0):
        outcome = super()._outcome(
            state,
            status,
            common,
            start_tick,
            policy,
            ticks_executed=ticks_executed,
        )
        pattern = self._best_frame_pattern(state) if outcome.found else None
        if pattern is not None:
            return replace(
                outcome,
                semantics=pattern.semantics,
                frame_pattern=pattern,
                result_signature=pattern.signature,
            )
        if outcome.common_ref is not None:
            return replace(outcome, result_signature=f"REF:{outcome.common_ref.uid}")
        return outcome