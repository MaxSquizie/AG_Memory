from __future__ import annotations

from ah.perception import AssertionCandidate, PerceptionResult

from .errors import CandidateValidationError


class CandidateValidator:
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

        for candidate in result.assertions:
            for actant in candidate.actants:
                if actant.candidate_ref is not None and actant.candidate_ref not in by_id:
                    raise CandidateValidationError(
                        f"Unknown candidate_ref {actant.candidate_ref!r} "
                        f"in {candidate.local_id}"
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
