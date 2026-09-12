from __future__ import annotations

from dataclasses import replace

from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssociationActRelationCandidate,
    CommandCandidate,
    PropositionExprCandidate,
    QueryCandidate,
    TemplateCandidate,
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
        """Expose logical operator provenance through one validation-only view.

        Adaptive perception can encode an operator source in two equivalent source
        shapes before canonical Integration:

        * a matrix/content edge carried by ``candidate_ref``;
        * a detached preamble whose relation to the already-built proposition is
          represented only by ``PropositionRootCandidate.operator_source_refs``.

        The base validator historically recognized only ``actant.proposition`` as
        evidence that an operator frame governs proposition content.  That rejected
        valid impersonal modal shells and made a detached logical preamble survive as
        an ordinary world fact merely because its internal parser frame did not also
        duplicate the proposition edge.

        Build a *copy used only for validation* in which every authorized operator
        source exposes the exact root expression as proposition content.  Integration
        still receives the original PerceptionResult, so this adapter cannot change
        a role binding, choose a UID, or create canonical semantics.  The explicit
        ``operator_source_refs`` topology remains the authorization boundary.
        """

        source_expr: dict[str, PropositionExprCandidate] = {}
        for root in result.proposition_roots:
            for ref in root.operator_source_refs:
                source_expr.setdefault(ref, root.expression)
        operator_sources = set(source_expr)
        if not operator_sources:
            return replace(result, act_relations=ordinary_relations)

        assertions = []
        for assertion in result.assertions:
            expression = source_expr.get(assertion.local_id)
            if expression is None:
                assertions.append(assertion)
                continue

            actants = list(assertion.actants)
            changed = False

            # First preserve the strongest pre-existing structural edge. A local
            # candidate_ref already names one proposition leaf and only needs to be
            # expressed through the typed proposition channel for base validation.
            for index, actant in enumerate(actants):
                if (
                    actant.candidate_ref is not None
                    and actant.proposition is None
                    and actant.composition is None
                ):
                    actants[index] = replace(
                        actant,
                        candidate_ref=None,
                        proposition=PropositionExprCandidate.ref_expr(
                            actant.candidate_ref
                        ),
                    )
                    changed = True

            # Detached preambles have no matrix/content actant by construction: the
            # bounded logical formalizer recorded the exact governed formula on the
            # root itself.  Project that existing expression into one source role in
            # the validation copy so the old validator can check its leaf refs.
            if not any(item.proposition is not None for item in actants):
                if actants:
                    first = actants[0]
                    actants[0] = replace(
                        first,
                        candidate_ref=None,
                        entity_ref=None,
                        composition=None,
                        proposition=expression,
                        quantifier=None,
                    )
                    predicate = assertion.predicate
                else:
                    role = ActantRole.OBJECT
                    actants.append(ActantCandidate(role, proposition=expression))
                    predicate = assertion.predicate
                    proposed = predicate.template_candidate
                    if proposed is not None and role not in proposed.roles:
                        predicate = replace(
                            predicate,
                            template_candidate=TemplateCandidate(
                                tuple((*proposed.roles, role))
                            ),
                        )
                assertion = replace(
                    assertion,
                    predicate=predicate,
                    actants=tuple(actants),
                )
                changed = False
            elif changed:
                assertion = replace(assertion, actants=tuple(actants))

            assertions.append(assertion)

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