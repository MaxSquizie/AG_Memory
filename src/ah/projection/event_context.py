from __future__ import annotations

from dataclasses import replace

from ah.inference.contracts import (
    CompositeConclusion,
    ExistingRefConclusion,
    LogicalStatus,
)

from .agent_context import ContextProjector as _BaseContextProjector
from .contracts import ProjectionBlock, ProjectionMode


class EventAwareContextProjector(_BaseContextProjector):
    """Project complete open-event result sets without exposing AH structure.

    A turn with an explicit formal proof obligation is response-grounded by the
    reasoner result, not by arbitrary simultaneously active memory.  Workspace is
    still retained in ``source_workspace_refs`` for diagnostics/Proof Explorer, but
    its prose is withheld from the Main LLM whenever inference or an unresolved
    GoalSpec result is present.  This prevents the response model from appending an
    active-but-unproved fact to a constrained answer (for example adding an event
    without the requested TIME merely because that event is active).
    """

    def project(
        self,
        current_input,
        workspace_refs,
        inference_results=(),
        unresolved_goal_diagnostics=(),
        *,
        source_scope=None,
        budget_tokens=None,
    ):
        proof_obligation = bool(inference_results or unresolved_goal_diagnostics)
        model_workspace = () if proof_obligation else workspace_refs
        context = super().project(
            current_input,
            model_workspace,
            inference_results,
            unresolved_goal_diagnostics,
            source_scope=source_scope,
            budget_tokens=budget_tokens,
        )
        if proof_obligation and tuple(workspace_refs) != context.source_workspace_refs:
            # Diagnostics must describe the real cognitive Workspace even though
            # model-facing ACTIVE MEMORY is intentionally proof-gated for this turn.
            context = replace(context, source_workspace_refs=tuple(workspace_refs))
        return context

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
