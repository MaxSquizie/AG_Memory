from __future__ import annotations

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

        for candidate in result.assertions:
            for actant in candidate.actants:
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
