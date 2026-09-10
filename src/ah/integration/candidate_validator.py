from __future__ import annotations

from dataclasses import replace

from ah.perception import CommandCandidate, QueryCandidate

from .candidate_validator_base import CandidateValidator as _BaseCandidateValidator
from .errors import CandidateValidationError


class CandidateValidator(_BaseCandidateValidator):
    """Validate runtime ASSOCIATION goal markers without treating them as AH L.

    The base validator intentionally whitelists canonical intra-act world relations
    (currently IS-A). ASSOCIATION is different: it is a query/command goal marker and
    must never be materialized as a relation asserted by the user. Strip only that
    marker for base world-relation validation, then enforce its separate contract.
    """

    def validate(self, result) -> None:
        association = tuple(
            item
            for item in result.act_relations
            if item.canonical_relation_id == "ASSOCIATION"
        )
        ordinary = tuple(
            item
            for item in result.act_relations
            if item.canonical_relation_id != "ASSOCIATION"
        )
        super().validate(replace(result, act_relations=ordinary))
        if not association:
            return

        acts: dict[str, QueryCandidate | CommandCandidate] = {}
        acts.update(
            {
                item.local_id: item
                for item in result.queries
                if item.local_id is not None
            }
        )
        acts.update(
            {
                item.local_id: item
                for item in result.commands
                if item.local_id is not None
            }
        )
        seen: set[str] = set()
        for relation in association:
            act = acts.get(relation.act_ref)
            if act is None:
                raise CandidateValidationError(
                    "ASSOCIATION may target only an explicit QUERY/COMMAND act: "
                    f"{relation.act_ref!r}"
                )
            if relation.act_ref in seen:
                raise CandidateValidationError(
                    f"Duplicate ASSOCIATION goal marker in {relation.act_ref!r}"
                )
            seen.add(relation.act_ref)
            if act.quoted:
                raise CandidateValidationError(
                    f"Quoted act {relation.act_ref!r} cannot execute ASSOCIATION"
                )
            if isinstance(act, QueryCandidate) and act.quantified is not None:
                raise CandidateValidationError(
                    "Quantified+association goal composition requires an explicit "
                    "combined contract and is not supported"
                )
            if isinstance(act, CommandCandidate) and act.negated:
                raise CandidateValidationError(
                    f"Negated command {relation.act_ref!r} cannot execute ASSOCIATION"
                )
            roles = {item.role for item in act.actants}
            if (
                relation.source_role not in roles
                or relation.target_role not in roles
            ):
                raise CandidateValidationError(
                    f"ASSOCIATION endpoints are not present in {relation.act_ref!r}"
                )
