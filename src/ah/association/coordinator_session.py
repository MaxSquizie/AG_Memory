from __future__ import annotations

from .contracts import AssociationBudget, AssociationDomainPolicy, AssociationOutcome
from .coordinator_specific import AssociationCoordinator as _StructuredAssociationCoordinator
from .history import remember_signature


class AssociationCoordinator(_StructuredAssociationCoordinator):
    """Structured association search with runtime result-history support.

    A returned partial frame owns not only its exact frame signature but also the
    structural/template and fixed-value hubs that constitute that answer.  Otherwise
    ``А ещё?`` could merely decompose ``SEE(OBJECT=_, LOCATION=yard)`` into the raw
    predicate ``SEE`` or raw concept ``yard`` and incorrectly present it as a new
    association.
    """

    def _remember_outcome(self, outcome: AssociationOutcome) -> None:
        left = outcome.goal.left
        right = outcome.goal.right
        remember_signature(self.core, left, right, outcome.result_signature)
        pattern = outcome.frame_pattern
        if pattern is None:
            return
        remember_signature(self.core, left, right, f"REF:{pattern.template.uid}")
        remember_signature(self.core, left, right, f"REF:{pattern.predicate.uid}")
        for binding in pattern.bindings:
            remember_signature(self.core, left, right, f"REF:{binding.value.uid}")

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
            self._remember_outcome(outcome)
        return outcome
