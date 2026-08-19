from __future__ import annotations

from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference.contracts import InferenceOutcome
from ah.projection.semantic_projection import SemanticProjector


class TraceView:
    """Human-readable UID proof trace for debug/M2/live demo only."""

    def __init__(self, core: AHCore) -> None:
        self.core = core
        self.semantic = SemanticProjector(core, ContextSettings(include_structural_uids=False))

    def render(self, outcome: InferenceOutcome) -> str:
        lines = [
            f"status={outcome.status.value}",
            f"stop={outcome.stop_reason.value}",
            f"logical_depth={outcome.logical_depth}",
            f"expanded={outcome.expanded_states}",
        ]
        if outcome.goal_spec is not None:
            lines.append(f"goal={outcome.goal_spec.target!r}")
        if outcome.conclusion_domain is not None:
            lines.append(f"domain={outcome.conclusion_domain.value}")
        lines.append("trace:")
        for index, ref in enumerate(outcome.uid_trace, 1):
            try:
                semantic = self.semantic.dependency_text(ref)
            except Exception:
                semantic = ref.uid
            lines.append(f"  {index:02d}. {ref.kind.value}:{ref.uid} | {semantic}")
        if outcome.diagnostics:
            lines.append("diagnostics:")
            lines.extend(f"  - {item}" for item in outcome.diagnostics)
        return "\n".join(lines)
