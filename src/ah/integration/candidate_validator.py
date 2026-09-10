from __future__ import annotations

from dataclasses import replace

from ah.perception import (
    AssociationActRelationCandidate,
    CommandCandidate,
    QueryCandidate,
)

from .candidate_validator_base import CandidateValidator as _BaseCandidateValidator
from .errors import CandidateValidationError


class CandidateValidator(_BaseCandidateValidator):
    """Validate runtime ASSOCIATION goals separately from canonical AH relations."""

    @staticmethod
    def _validate_selector(act, *, role, member_index, label: str) -> None:
        matches = tuple(item for item in act.actants if item.role is role)
        if len(matches) != 1:
            raise CandidateValidationError(
                f"ASSOCIATION {label} role {role.value} is not uniquely present in {act.local_id!r}"
            )
        actant = matches[0]
        if member_index is None:
            if actant.composition is not None:
                raise CandidateValidationError(
                    f"ASSOCIATION {label} must select a member of composed role {role.value}"
                )
            return
        if actant.composition is None:
            raise CandidateValidationError(
                f"ASSOCIATION {label} member selector targets non-composed role {role.value}"
            )
        if member_index >= len(actant.composition.members):
            raise CandidateValidationError(
                f"ASSOCIATION {label} member index {member_index} is out of range"
            )

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
        # The base validator owns world-relation semantics (currently IS-A). A
        # runtime association goal is intentionally removed from that whitelist.
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
            # Do not accept a generic ActRelationCandidate merely because somebody
            # supplied the string ASSOCIATION. Member addressing and its invariants
            # are part of the dedicated typed contract.
            if not isinstance(relation, AssociationActRelationCandidate):
                raise CandidateValidationError(
                    "ASSOCIATION requires AssociationActRelationCandidate"
                )
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

            self._validate_selector(
                act,
                role=relation.source_role,
                member_index=relation.source_member_index,
                label="source",
            )
            self._validate_selector(
                act,
                role=relation.target_role,
                member_index=relation.target_member_index,
                label="target",
            )
