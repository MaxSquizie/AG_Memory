from __future__ import annotations

from ah.inference.contracts import (
    CompositeConclusion,
    ExistingRefConclusion,
    LogicalStatus,
)

from .agent_context import ContextProjector as _BaseContextProjector
from .contracts import ProjectionBlock, ProjectionMode


class EventAwareContextProjector(_BaseContextProjector):
    """Project complete open-event result sets without exposing AH structure."""

    def _inference_block(self, outcome):
        conclusion = outcome.conclusion
        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, CompositeConclusion)
            and conclusion.conclusions
            and all(
                isinstance(item, ExistingRefConclusion)
                for item in conclusion.conclusions
            )
        ):
            facts = tuple(
                self.model_semantic.inference_text_for_ref(item.ref)
                for item in conclusion.conclusions
            )
            text = "Найденные события по формальным ограничениям: " + "; ".join(facts)
            return ProjectionBlock(None, ProjectionMode.INFERENCE, text)
        return super()._inference_block(outcome)
