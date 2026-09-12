from __future__ import annotations

from dataclasses import replace

from ah.perception import (
    AssociationActRelationCandidate,
    CommandCandidate,
    PropositionExprCandidate,
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

    @staticmethod
    def _base_validation_view(result, ordinary_relations):
        """Expose candidate-ref content as proposition content to logical validation.

        Adaptive perception may initially represent a matrix/content dependency as
        ``candidate_ref`` and only later lift that same local edge into a proposition
        formula.  For a frame consumed as ``operator_source_refs`` those two runtime
        encodings are semantically equivalent: the matrix structurally governs an
        already parsed proposition.  The base validator historically recognized only
        ``actant.proposition`` and therefore rejected valid impersonal modal shells
        such as REQUIRED/PERMITTED when their content was still carried by
        ``candidate_ref``.

        This is a validation-only view.  The original PerceptionResult is returned to
        Integration unchanged, so no canonical mutation, role binding or UID choice is
        delegated to this adapter.
        """

        operator_sources = {
            ref
            for root in result.proposition_roots
            for ref in root.operator_source_refs
        }
        if not operator_sources:
            return replace(result, act_relations=ordinary_relations)

        assertions = []
        for assertion in result.assertions:
            if assertion.local_id not in operator_sources:
                assertions.append(assertion)
                continue
            actants = tuple(
                replace(
                    actant,
                    candidate_ref=None,
                    proposition=PropositionExprCandidate.ref_expr(actant.candidate_ref),
                )
                if actant.candidate_ref is not None
                and actant.proposition is None
                and actant.composition is None
                else actant
                for actant in assertion.actants
            )
            assertions.append(
                assertion if actants == assertion.actants else replace(assertion, actants=actants)
            )
        return replace(
            result,
            assertions=tuple(assertions),
            act_relations=ordinary_relations,
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
        super().validate(self._base_validation_view(result, ordinary))
        if not association:
            return

        ordinary_by_act: dict[str, int] = {}
        for relation in ordinary:
            ordinary_by_act[relation.act_ref] = ordinary_by_act.get(relation.act_ref, 0) + 1

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
            if ordinary_by_act.get(relation.act_ref, 0):
                raise CandidateValidationError(
                    "ASSOCIATION cannot share one act with a canonical world-relation "
                    f"goal in {relation.act_ref!r}; the intended operation must be "
                    "resolved before GoalCompiler"
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