from __future__ import annotations

from ah.model import FunctionSymbol, Hypernode, Ref, RefKind

from .contracts import AssociationBudget, AssociationDomainPolicy, AssociationOutcome
from .coordinator import _LEFT, _RIGHT
from .coordinator_specific import AssociationCoordinator as _StructuredAssociationCoordinator
from .history import remember_signature


class AssociationCoordinator(_StructuredAssociationCoordinator):
    """Structured association search with scoped runtime result history.

    Explicit association restrictions (LOCATION/TIME/etc.) are stop conditions, not
    prose hints.  A structured frame is admissible only when *both* supporting facts
    satisfy every restriction.  Under a scoped goal, an unscoped raw concept is not
    an answer because it cannot establish that the requested condition held.
    """

    @staticmethod
    def _goal_constraints(state) -> tuple:
        goal = getattr(state, "goal", None)
        return tuple(getattr(goal, "constraints", ()) or ())

    def _fact_satisfies_constraints(self, fact: Hypernode, constraints) -> bool:
        for constraint in constraints:
            actual = fact.actants.get(constraint.role)
            if not isinstance(actual, Ref):
                return False
            if actual == constraint.value:
                continue
            # Conditions use the same canonical taxonomy direction as ordinary
            # role matching: an observed subtype may satisfy a requested ancestor.
            ancestors = self._is_a_ancestors(actual)
            if constraint.value.uid not in ancestors:
                return False
        return True

    def _pattern_for_pair(self, state, left_ref, left, right_ref, right):
        constraints = self._goal_constraints(state)
        if constraints and (
            not self._fact_satisfies_constraints(left, constraints)
            or not self._fact_satisfies_constraints(right, constraints)
        ):
            return None
        return super()._pattern_for_pair(state, left_ref, left, right_ref, right)

    def _path_uses_fact(self, state, front: str, ref: Ref) -> bool:
        """Whether reaching ``ref`` on this front depended on a concrete N fact.

        A raw representation reached *through* an assertion/episode is useful
        propagation evidence but is a lossy terminal answer: stopping at one actant,
        formula or other child throws away the predicate frame that explains why the
        endpoints are related. Direct/taxonomic convergence remains eligible because
        it does not cross an N fact and therefore does not hide that richer frame.
        """
        if state is None:
            return False
        try:
            path = state.path(front, ref, self.core)
        except Exception:
            return False
        if path is None:
            return False

        # Most N-mediated paths expose the supporting fact directly in refs.
        if any(item.kind is RefKind.N for item in path.refs[1:-1]):
            return True

        # Memory-query/propagation hops can also keep the structural carrier in
        # provenance rather than as an explicit path vertex.
        for hop in path.hops:
            via_uid = hop.via_uid
            if not via_uid:
                continue
            try:
                if self.core.ref(via_uid).kind is RefKind.N:
                    return True
            except Exception:
                continue
        return False

    def _raw_common_allowed(self, state, uid: str) -> bool:
        ref = self.core.ref(uid)
        # K produced by actant coordination is a structural carrier, not a useful
        # answer to "what do these two things have in common?".
        if ref.kind is RefKind.K:
            return False

        # A functional container whose operands recursively contain both queried
        # endpoints is likewise only packaging of the pair, not a property shared by
        # the pair. This is deliberately structural rather than an AND/OR blacklist:
        # any g that merely encloses both origins remains usable for propagation but
        # cannot terminate the association as ``(left) FUNCTION (right)``.
        if ref.kind is RefKind.G and state is not None:
            obj = self._element(ref)
            if (
                isinstance(obj, FunctionSymbol)
                and self._operand_contains(ref, state.goal.left)
                and self._operand_contains(ref, state.goal.right)
            ):
                return False

        # Do not terminate on a raw child that a front reached through a concrete
        # fact. Example: two SEE facts share SUBJECT=user. Returning raw M(user)
        # discards SEE(OBJECT=_, SUBJECT=user, LOCATION=...) and can stop the search
        # one tick before the structured frame becomes available. The same invariant
        # applies to any non-N child representation; a concrete N that itself
        # contains both endpoints remains eligible in the structured base layer.
        if ref.kind is not RefKind.N and (
            self._path_uses_fact(state, _LEFT, ref)
            or self._path_uses_fact(state, _RIGHT, ref)
        ):
            return False

        constraints = self._goal_constraints(state) if state is not None else ()
        if constraints:
            # A raw concept/template cannot prove LOCATION=yard (or any other
            # explicit scope). Only a concrete fact carrying that role may be a raw
            # terminal result. Structured two-fact frames are handled above.
            if ref.kind is not RefKind.N:
                return False
            obj = self._element(ref)
            if not isinstance(obj, Hypernode):
                return False
            if not self._fact_satisfies_constraints(obj, constraints):
                return False
        return super()._raw_common_allowed(state, uid)

    def _remember_outcome(self, outcome: AssociationOutcome) -> None:
        left = outcome.goal.left
        right = outcome.goal.right
        constraints = tuple(getattr(outcome.goal, "constraints", ()) or ())

        def remember(signature: str | None) -> None:
            remember_signature(
                self.core,
                left,
                right,
                signature,
                constraints,
            )

        remember(outcome.result_signature)
        pattern = outcome.frame_pattern
        if pattern is None:
            return
        remember(f"REF:{pattern.template.uid}")
        remember(f"REF:{pattern.predicate.uid}")

        # A frame and its canonical supporting facts are one answer, not several
        # answers at different representation levels.
        for fact_ref in (pattern.left_fact, pattern.right_fact):
            remember(f"REF:{fact_ref.uid}")

        left_fact = self.core.store.get_hypernode(pattern.left_fact.uid)
        right_fact = self.core.store.get_hypernode(pattern.right_fact.uid)
        for binding in pattern.bindings:
            remember(f"REF:{binding.value.uid}")
            if not binding.generalized:
                continue
            for fact in (left_fact, right_fact):
                operand = fact.actants.get(binding.role)
                if isinstance(operand, Ref):
                    remember(f"REF:{operand.uid}")

    def solve(
        self,
        request,
        *,
        budget: AssociationBudget | None = None,
        domain_policy: AssociationDomainPolicy = AssociationDomainPolicy.ALL,
        excluded_signatures=(),
    ) -> AssociationOutcome:
        inherited = tuple(getattr(request, "excluded_signatures", ()) or ())
        explicit = tuple(excluded_signatures or ())
        combined = tuple(dict.fromkeys((*inherited, *explicit)))
        outcome = super().solve(
            request,
            budget=budget,
            domain_policy=domain_policy,
            excluded_signatures=combined,
        )
        if outcome.found:
            self._remember_outcome(outcome)
        return outcome
