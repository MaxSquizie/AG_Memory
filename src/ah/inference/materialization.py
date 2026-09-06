from __future__ import annotations

from dataclasses import dataclass

from ah.config import IntegrationSettings
from ah.core import AHCore, SupportRecord
from ah.model import Domain, Ref

from .contracts import (
    DerivedLinkConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    LogicalStatus,
    MultiRoleBindingConclusion,
    RoleBindingConclusion,
)
from .domain import domain_from_premises


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    ref: Ref | None
    domain: Domain | None
    created: bool


class InferenceMaterializer:
    """Canonical commit boundary for final inference conclusions only.

    It intentionally emits no ActivationSeedRequest: materialization is not a new
    external observation and therefore must not act as confirmation of N.w.
    """

    def __init__(self, core: AHCore, integration: IntegrationSettings) -> None:
        self.core = core
        self.integration = integration

    def materialize(self, outcome: InferenceOutcome) -> MaterializationResult:
        if outcome.status is not LogicalStatus.PROVED or outcome.conclusion is None:
            return MaterializationResult(None, None, False)
        # Counterfactual and branch-local conclusions are runtime results only.
        # They must never leak into factual AH merely because a caller invokes the
        # ordinary materializer on a successful sandbox proof.
        if outcome.proof_context is not None and outcome.proof_context.is_counterfactual():
            return MaterializationResult(None, None, False)

        domain = domain_from_premises(self.core, outcome.premise_refs)
        conclusion = outcome.conclusion

        if isinstance(conclusion, ExistingRefConclusion):
            # A formula proof may establish an already-addressable N/g that was
            # previously only a zero-occurrence conclusion placeholder.  Persist
            # dependency supports without manufacturing a second semantic object.
            # This makes the conclusion admissible through its proof while keeping
            # proof metadata outside canonical q-types.
            for support in outcome.proof_support:
                self.core.add_support(
                    conclusion.ref,
                    SupportRecord(
                        premise_refs=support.premise_refs,
                        rule_id=support.rule_id,
                        relation_id=support.relation_id,
                    ),
                )
            return MaterializationResult(conclusion.ref, domain, False)

        if isinstance(conclusion, RoleBindingConclusion):
            # This is retrieval from an existing N; there is nothing new to commit.
            return MaterializationResult(conclusion.value, domain, False)

        if isinstance(conclusion, MultiRoleBindingConclusion):
            # Multi-WH retrieval also refers to one already existing fact. There is
            # no single new semantic object to materialize; return the supporting N.
            return MaterializationResult(conclusion.fact, domain, False)

        if isinstance(conclusion, DerivedLinkConclusion):
            link, created = self.core.ensure_link(
                conclusion.relation_id,
                conclusion.source,
                conclusion.target,
                weight=self.integration.initial_inferred_link_weight,
            )
            link_ref = self.core.ref(link.uid)
            for support in outcome.proof_support:
                self.core.add_support(
                    link_ref,
                    SupportRecord(
                        premise_refs=support.premise_refs,
                        rule_id=support.rule_id,
                        relation_id=support.relation_id,
                    ),
                )
            return MaterializationResult(link_ref, domain, created)

        raise TypeError(f"Unsupported conclusion: {type(conclusion).__name__}")
