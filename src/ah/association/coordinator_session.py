from __future__ import annotations

from .contracts import AssociationBudget, AssociationDomainPolicy, AssociationOutcome
from .coordinator_specific import AssociationCoordinator as _StructuredAssociationCoordinator
from .history import remember_signature


class AssociationCoordinator(_StructuredAssociationCoordinator):
    """Structured association search with runtime result-history support."""

    def solve(
        self,
        request,
        *,
        budget: AssociationBudget | None = None,
        domain_policy: AssociationDomainPolicy = AssociationDomainPolicy.ALL,
        excluded_signatures=(),
    ) -> AssociationOutcome:
        inherited = tuple(getattr(request, "excluded_signatures", ()) or ())
        explicit = tuple(excluded_signatures or ())
        combined = tuple(dict.fromkeys((*inherited, *explicit)))
        outcome = super().solve(
            request,
            budget=budget,
            domain_policy=domain_policy,
            excluded_signatures=combined,
        )
        if outcome.found:
            remember_signature(
                self.core,
                outcome.goal.left,
                outcome.goal.right,
                outcome.result_signature,
            )
        return outcome
