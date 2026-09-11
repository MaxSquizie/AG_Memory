from __future__ import annotations

from ah.model import ActantRole
from ah.perception import (
    ActDependencyKind,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PropositionExprCandidate,
    PropositionOperator,
)

from .errors import CandidateValidationError


class CandidateValidator:
    @staticmethod
    def _validate_template_roles(predicate, roles, *, label: str) -> None:
        proposed = predicate.template_candidate
        if proposed is None:
            return
        if not set(roles).issubset(set(proposed.roles)):
            raise CandidateValidationError(
                f"TemplateCandidate does not cover frame roles in {label}"
            )

    def validate(self, result: PerceptionResult) -> None:
        by_id: dict[str, AssertionCandidate] = {}
        for candidate in result.assertions:
            if not candidate.local_id.strip():
                raise CandidateValidationError("AssertionCandidate.local_id must be non-empty")
            if candidate.local_id in by_id:
                raise CandidateValidationError(f"Duplicate local_id: {candidate.local_id}")
            by_id[candidate.local_id] = candidate

            roles = [a.role for a in candidate.actants]
            if len(roles) != len(set(roles)):
                raise CandidateValidationError(
                    f"Duplicate actant role in {candidate.local_id}"
                )
            candidate.predicate.lookup_form
            self._validate_template_roles(
                candidate.predicate, roles, label=candidate.local_id
            )

            if candidate.alternatives:
                alternative_role_sets: list[set] = []
                for alt_index, alternative in enumerate(candidate.alternatives, start=1):
                    if alternative.alternatives:
                        raise CandidateValidationError(
                            f"Nested runtime alternatives are not supported in {candidate.local_id}"
                        )
                    if alternative.local_id != candidate.local_id:
                        raise CandidateValidationError(
                            f"Alternative local_id mismatch in {candidate.local_id}"
                        )
                    if alternative.predicate.lookup_form.casefold() != candidate.predicate.lookup_form.casefold():
                        raise CandidateValidationError(
                            f"Alternative predicate mismatch in {candidate.local_id}"
                        )
                    if (
                        alternative.negated != candidate.negated
                        or alternative.status is not candidate.status
                        or alternative.quoted != candidate.quoted
                    ):
                        raise CandidateValidationError(
                            f"Alternative assertion status/scope mismatch in {candidate.local_id}"
                        )
                    alt_roles = [a.role for a in alternative.actants]
                    if len(alt_roles) != len(set(alt_roles)):
                        raise CandidateValidationError(
                            f"Duplicate actant role in {candidate.local_id} alternative#{alt_index}"
                        )
                    self._validate_template_roles(
                        alternative.predicate, alt_roles,
                        label=f"{candidate.local_id}.alternative#{alt_index}",
                    )
                    alternative_role_sets.append(set(alt_roles))
                if any(role_set != alternative_role_sets[0] for role_set in alternative_role_sets[1:]):
                    raise CandidateValidationError(
                        f"Runtime alternatives in {candidate.local_id} must share one role schema"
                    )

        act_refs: set[str] = set(by_id)
        for index, query in enumerate(result.queries, start=1):
            if query.local_id is None:
                if query.quantified is not None:
                    raise CandidateValidationError(
                        f"quantified query#{index} requires local_id"
                    )
                continue
            if not query.local_id.strip():
                raise CandidateValidationError(f"query#{index}.local_id must be non-empty")
            if query.local_id in act_refs:
                raise CandidateValidationError(f"Duplicate act local_id: {query.local_id}")
            act_refs.add(query.local_id)

            if query.quantified is not None:
                if query.quoted:
                    raise CandidateValidationError(
                        f"Quantified query {query.local_id} cannot be quoted"
                    )
                if query.query_mode.value != "EXISTS":
                    raise CandidateValidationError(
                        f"Quantified query {query.local_id} currently requires polar EXISTS mode"
                    )
                handles = {
                    actant.entity_ref
                    for actant in query.actants
                    if actant.entity_ref is not None
                }
                for binding in query.quantified.bindings:
                    if binding.entity_ref not in handles:
                        raise CandidateValidationError(
                            f"Quantified query binding {binding.entity_ref!r} "
                            f"is not used by {query.local_id}"
                        )
                bound_handles = {
                    binding.entity_ref for binding in query.quantified.bindings
                }
                for actant in query.actants:
                    if actant.entity_ref not in bound_handles:
                        continue
                    if (
                        actant.candidate_ref is not None
                        or actant.composition is not None
                        or actant.proposition is not None
                    ):
                        raise CandidateValidationError(
                            f"Quantified query actant {actant.role.value} in "
                            f"{query.local_id} must be a direct bound role"
                        )
        for index, command in enumerate(result.commands, start=1):
            if command.local_id is None:
                continue
            if not command.local_id.strip():
                raise CandidateValidationError(f"command#{index}.local_id must be non-empty")
            if command.local_id in act_refs:
                raise CandidateValidationError(f"Duplicate act local_id: {command.local_id}")
            act_refs.add(command.local_id)

        for dependency in result.act_dependencies:
            if dependency.parent_ref not in act_refs or dependency.child_ref not in act_refs:
                raise CandidateValidationError(
                    f"Unknown act dependency endpoint: "
                    f"{dependency.parent_ref!r} -> {dependency.child_ref!r}"
                )

        for candidate in result.assertions:
            variants = (candidate, *candidate.alternatives)
            for variant in variants:
                for actant in variant.actants:
                    if actant.candidate_ref is not None and actant.candidate_ref not in by_id:
                        raise CandidateValidationError(
                            f"Unknown candidate_ref {actant.candidate_ref!r} "
                            f"in {candidate.local_id}"
                        )
                    if actant.proposition is not None:
                        for ref in actant.proposition.leaf_refs():
                            if ref not in by_id:
                                raise CandidateValidationError(
                                    f"Unknown proposition ref {ref!r} in {candidate.local_id}"
                                )


        conditional_refs: set[str] = set()
        for conditional in result.conditionals:
            refs = (*conditional.antecedent_refs, *conditional.consequent_refs)
            for ref in refs:
                if ref not in by_id:
                    raise CandidateValidationError(
                        f"Unknown conditional endpoint: {ref!r}"
                    )
                conditional_refs.add(ref)

        for candidate in result.assertions:
            if candidate.local_id in conditional_refs and candidate.status is not AssertionStatus.CONDITIONAL:
                raise CandidateValidationError(
                    f"Conditional endpoint {candidate.local_id} must have CONDITIONAL status"
                )
            if candidate.status is AssertionStatus.CONDITIONAL and candidate.local_id not in conditional_refs:
                raise CandidateValidationError(
                    f"Conditional assertion {candidate.local_id} is not referenced by a ConditionalCandidate"
                )

        # Top-level logical roots are source assertions of formulae, not extra
        # facts layered on top of independently asserted leaf N nodes.  Validate the
        # complete local topology before Integration decides which leaves must be
        # canonicalized as scoped operands with occurrence_count=0.
        formula_root_ids: set[str] = set()
        seen_formula_members: set[str] = set()
        conditional_endpoint_sets = {
            frozenset((*item.antecedent_refs, *item.consequent_refs))
            for item in result.conditionals
        }
        for index, root in enumerate(result.proposition_roots, start=1):
            if root.local_id in formula_root_ids or root.local_id in act_refs:
                raise CandidateValidationError(
                    f"Duplicate logical root local_id: {root.local_id!r}"
                )
            formula_root_ids.add(root.local_id)
            leaf_refs = tuple(root.expression.leaf_refs())
            if not leaf_refs:
                raise CandidateValidationError(
                    f"Logical root {root.local_id!r} has no proposition leaves"
                )
            for ref in (*leaf_refs, *root.operator_source_refs):
                if ref not in by_id:
                    raise CandidateValidationError(
                        f"Unknown logical formula ref {ref!r} in {root.local_id!r}"
                    )
                if ref in seen_formula_members:
                    raise CandidateValidationError(
                        f"Assertion {ref!r} participates in more than one top-level logical root"
                    )
                seen_formula_members.add(ref)

            conditional_backed = (
                root.expression.operator is PropositionOperator.IMPLIES
                and frozenset(leaf_refs) in conditional_endpoint_sets
                and not root.operator_source_refs
            )
            if conditional_backed:
                if any(by_id[ref].status is not AssertionStatus.CONDITIONAL for ref in leaf_refs):
                    raise CandidateValidationError(
                        f"Conditional-backed logical root {root.local_id!r} must use CONDITIONAL leaves"
                    )
                continue

            for ref in leaf_refs:
                leaf = by_id[ref]
                if leaf.quoted:
                    raise CandidateValidationError(
                        f"Top-level logical formula leaf {ref!r} cannot be quoted"
                    )
                if root.operator_source_refs:
                    if leaf.status not in {AssertionStatus.ASSERTED, AssertionStatus.EMBEDDED}:
                        raise CandidateValidationError(
                            f"Logical wrapper leaf {ref!r} has incompatible scope {leaf.status.value}"
                        )
                elif leaf.status is not AssertionStatus.ASSERTED:
                    raise CandidateValidationError(
                        f"Top-level logical formula leaf {ref!r} must be ASSERTED"
                    )

            for ref in root.operator_source_refs:
                source = by_id[ref]
                if source.status is not AssertionStatus.ASSERTED or source.quoted:
                    raise CandidateValidationError(
                        f"Logical operator source {ref!r} must be an ordinary asserted matrix frame"
                    )
                def contains_modal(expr: PropositionExprCandidate) -> bool:
                    if expr.operator in {
                        PropositionOperator.POSSIBLE,
                        PropositionOperator.REQUIRED,
                        PropositionOperator.PERMITTED,
                    }:
                        return True
                    return any(contains_modal(member) for member in expr.members)

                modal_formula = contains_modal(root.expression)
                has_proposition_content = any(
                    actant.proposition is not None
                    for actant in source.actants
                )
                if not modal_formula and not has_proposition_content:
                    raise CandidateValidationError(
                        f"Logical operator source {ref!r} must structurally govern proposition content"
                    )
                if modal_formula and not has_proposition_content and source.actants:
                    # A zero-actant predicative shell may be consumed as a modal
                    # operator source. Ordinary argument-bearing matrix predicates
                    # remain semantic N propositions instead of being erased here.
                    raise CandidateValidationError(
                        f"Modal operator source {ref!r} must be an argument-free source shell"
                    )

        act_by_ref: dict[str, object] = dict(by_id)
        act_by_ref.update({item.local_id: item for item in result.queries if item.local_id is not None})
        act_by_ref.update({item.local_id: item for item in result.commands if item.local_id is not None})
        seen_act_relations: set[tuple[str, str, ActantRole, ActantRole]] = set()
        for relation in result.act_relations:
            if relation.canonical_relation_id not in {"IS-A"}:
                raise CandidateValidationError(
                    f"Unsupported intra-act relation: {relation.relation_id!r}"
                )
            act = act_by_ref.get(relation.act_ref)
            if act is None:
                raise CandidateValidationError(
                    f"Unknown intra-act relation act_ref: {relation.act_ref!r}"
                )
            roles = {item.role for item in act.actants}
            if relation.source_role not in roles or relation.target_role not in roles:
                raise CandidateValidationError(
                    f"Intra-act relation endpoints are not present in {relation.act_ref!r}"
                )
            key = (
                relation.canonical_relation_id, relation.act_ref,
                relation.source_role, relation.target_role,
            )
            if key in seen_act_relations:
                raise CandidateValidationError(
                    f"Duplicate intra-act relation in {relation.act_ref!r}"
                )
            seen_act_relations.add(key)

        # Runtime relation hints are deliberately weaker than canonical situation
        # relations.  Validate referential integrity here, but do not whitelist them
        # as AH relation IDs and do not materialize them in Integration.  This keeps
        # narrative/temporal hypotheses inside the perception boundary.
        seen_relation_hints: set[tuple[str, str, str]] = set()
        for hint in result.relation_hints:
            if hint.source_ref not in by_id or hint.target_ref not in by_id:
                raise CandidateValidationError(
                    f"Unknown situation relation hint endpoint: "
                    f"{hint.source_ref!r} -> {hint.target_ref!r}"
                )
            if hint.source_ref == hint.target_ref:
                raise CandidateValidationError(
                    f"Situation relation hint cannot be reflexive: {hint.source_ref!r}"
                )
            key = (hint.kind.value, hint.source_ref, hint.target_ref)
            if key in seen_relation_hints:
                raise CandidateValidationError(
                    f"Duplicate situation relation hint: {key!r}"
                )
            seen_relation_hints.add(key)

        for relation in result.relations:
            if relation.canonical_relation_id not in {"FOLLOW", "CAUSE"}:
                raise CandidateValidationError(
                    f"Unsupported situation relation: {relation.relation_id!r}"
                )
            if relation.source_ref not in by_id or relation.target_ref not in by_id:
                raise CandidateValidationError(
                    f"Unknown situation relation endpoint: "
                    f"{relation.source_ref!r} -> {relation.target_ref!r}"
                )
            target = by_id[relation.target_ref]
            if relation.canonical_relation_id == "CAUSE" and any(
                actant.role == ActantRole.CAUSE and actant.candidate_ref == relation.source_ref
                for actant in target.actants
            ):
                raise CandidateValidationError(
                    "Inter-situation CAUSE must be represented once as L, not duplicated as N.CAUSE"
                )
            if relation.canonical_relation_id == "FOLLOW":
                pair = {relation.source_ref, relation.target_ref}
                for assertion in (by_id[relation.source_ref], by_id[relation.target_ref]):
                    if any(
                        actant.role == ActantRole.TIME
                        and actant.candidate_ref in pair - {assertion.local_id}
                        for actant in assertion.actants
                    ):
                        raise CandidateValidationError(
                            "Directional inter-situation time must be represented once as FOLLOW, not duplicated as N.TIME"
                        )

        for index, query in enumerate(result.queries, start=1):
            known_roles = [a.role for a in query.actants]
            overlap = set(known_roles) & set(query.requested_roles)
            if overlap:
                raise CandidateValidationError(
                    f"query#{index} fills and requests the same role(s): "
                    + ", ".join(sorted(role.value for role in overlap))
                )
            roles = [*known_roles, *query.requested_roles]
            self._validate_template_roles(query.predicate, roles, label=f"query#{index}")

        for index, command in enumerate(result.commands, start=1):
            self._validate_template_roles(
                command.predicate,
                [a.role for a in command.actants],
                label=f"command#{index}",
            )

        self._assert_acyclic(by_id)
        self._assert_act_dependencies_acyclic(result)
        self._assert_quotation_scope_consistent(result)

    @staticmethod
    def _assert_quotation_scope_consistent(result: PerceptionResult) -> None:
        adjacency: dict[str, list[str]] = {}
        quoted_refs: set[str] = set()
        for dependency in result.act_dependencies:
            adjacency.setdefault(dependency.parent_ref, []).append(dependency.child_ref)
            if dependency.kind is ActDependencyKind.QUOTED:
                quoted_refs.add(dependency.child_ref)
        queue = list(quoted_refs)
        while queue:
            parent = queue.pop()
            for child in adjacency.get(parent, ()):
                if child not in quoted_refs:
                    quoted_refs.add(child)
                    queue.append(child)

        scoped: dict[str, bool] = {}
        scoped.update({item.local_id: item.quoted for item in result.assertions})
        scoped.update({item.local_id: item.quoted for item in result.queries if item.local_id is not None})
        scoped.update({item.local_id: item.quoted for item in result.commands if item.local_id is not None})
        for ref in quoted_refs:
            if not scoped.get(ref, False):
                raise CandidateValidationError(
                    f"Quoted dependency subtree endpoint {ref!r} is not marked quoted"
                )
    @staticmethod
    def _assert_act_dependencies_acyclic(result: PerceptionResult) -> None:
        adjacency: dict[str, list[str]] = {}
        nodes: set[str] = set()
        for dependency in result.act_dependencies:
            adjacency.setdefault(dependency.parent_ref, []).append(dependency.child_ref)
            nodes.add(dependency.parent_ref)
            nodes.add(dependency.child_ref)
        WHITE, GRAY, BLACK = 0, 1, 2
        state = {node: WHITE for node in nodes}

        def visit(node: str) -> None:
            if state[node] == GRAY:
                raise CandidateValidationError(f"Cyclic act dependency at {node}")
            if state[node] == BLACK:
                return
            state[node] = GRAY
            for child in adjacency.get(node, ()):
                visit(child)
            state[node] = BLACK

        for node in tuple(nodes):
            if state[node] == WHITE:
                visit(node)

    def dependency_order(self, result: PerceptionResult) -> tuple[AssertionCandidate, ...]:
        by_id = {c.local_id: c for c in result.assertions}
        visited: set[str] = set()
        order: list[AssertionCandidate] = []

        def visit(local_id: str) -> None:
            if local_id in visited:
                return
            candidate = by_id[local_id]
            for actant in candidate.actants:
                if actant.candidate_ref is not None:
                    visit(actant.candidate_ref)
                if actant.proposition is not None:
                    for ref in actant.proposition.leaf_refs():
                        visit(ref)
            visited.add(local_id)
            order.append(candidate)

        for candidate in result.assertions:
            visit(candidate.local_id)
        return tuple(order)

    def _assert_acyclic(self, by_id: dict[str, AssertionCandidate]) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        state = {local_id: WHITE for local_id in by_id}

        def visit(local_id: str) -> None:
            if state[local_id] == GRAY:
                raise CandidateValidationError(
                    f"Cyclic candidate_ref dependency at {local_id}"
                )
            if state[local_id] == BLACK:
                return
            state[local_id] = GRAY
            for actant in by_id[local_id].actants:
                if actant.candidate_ref is not None:
                    visit(actant.candidate_ref)
                if actant.proposition is not None:
                    for ref in actant.proposition.leaf_refs():
                        visit(ref)
            state[local_id] = BLACK

        for local_id in by_id:
            visit(local_id)
