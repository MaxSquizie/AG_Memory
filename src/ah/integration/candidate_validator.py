from __future__ import annotations

from ah.model import ActantRole
from ah.perception import AssertionCandidate, AssertionStatus, PerceptionResult

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
                    if alternative.negated != candidate.negated or alternative.status is not candidate.status:
                        raise CandidateValidationError(
                            f"Alternative assertion status mismatch in {candidate.local_id}"
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

        for candidate in result.assertions:
            variants = (candidate, *candidate.alternatives)
            for variant in variants:
                for actant in variant.actants:
                    if actant.candidate_ref is not None and actant.candidate_ref not in by_id:
                        raise CandidateValidationError(
                            f"Unknown candidate_ref {actant.candidate_ref!r} "
                            f"in {candidate.local_id}"
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
            roles = [a.role for a in query.actants]
            if query.requested_role is not None:
                roles.append(query.requested_role)
            self._validate_template_roles(query.predicate, roles, label=f"query#{index}")

        for index, command in enumerate(result.commands, start=1):
            self._validate_template_roles(
                command.predicate,
                [a.role for a in command.actants],
                label=f"command#{index}",
            )

        self._assert_acyclic(by_id)

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
            state[local_id] = BLACK

        for local_id in by_id:
            visit(local_id)
