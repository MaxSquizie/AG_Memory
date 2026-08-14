from __future__ import annotations

from dataclasses import dataclass

from ah.config import IntegrationSettings
from ah.core import AHCore
from ah.model import Domain, Ref

from .contracts import (
    DerivedLinkConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    LogicalStatus,
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

        domain = domain_from_premises(self.core, outcome.premise_refs)
        conclusion = outcome.conclusion

        if isinstance(conclusion, ExistingRefConclusion):
            return MaterializationResult(conclusion.ref, domain, False)

        if isinstance(conclusion, RoleBindingConclusion):
            # This is retrieval from an existing N; there is nothing new to commit.
            return MaterializationResult(conclusion.value, domain, False)

        if isinstance(conclusion, DerivedLinkConclusion):
            link, created = self.core.ensure_link(
                conclusion.relation_id,
                conclusion.source,
                conclusion.target,
                weight=self.integration.initial_inferred_link_weight,
            )
            return MaterializationResult(self.core.ref(link.uid), domain, created)

        raise TypeError(f"Unsupported conclusion: {type(conclusion).__name__}")
