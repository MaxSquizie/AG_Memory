from __future__ import annotations

from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import (
    DerivedLinkConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    LogicalStatus,
    RoleBindingConclusion,
)
from ah.model import Ref

from .contracts import AgentContext, ProjectionBlock, ProjectionMode
from .semantic_projection import SemanticProjector


class ContextProjector:
    """Read-only Workspace/Inference -> AgentContext.

    There is deliberately no ranking/top-k stage here. Every Workspace root is
    serialized once. Infrastructure token-budget handling belongs outside the
    cognitive selection mechanism and must never silently drop active roots.
    """

    def __init__(self, core: AHCore, settings: ContextSettings) -> None:
        self.core = core
        self.settings = settings
        self.semantic = SemanticProjector(core, settings)

    def project(
        self,
        current_input: str,
        workspace_refs: tuple[Ref, ...],
        inference_results: tuple[InferenceOutcome, ...] = (),
    ) -> AgentContext:
        # Deduplicate roots without changing their cognitive selection.
        seen: set[str] = set()
        roots: list[Ref] = []
        for ref in workspace_refs:
            if ref.uid not in seen:
                seen.add(ref.uid)
                roots.append(ref)

        workspace_blocks = tuple(self.semantic.active_block(ref) for ref in roots)
        inference_blocks = tuple(
            block
            for outcome in inference_results
            if (block := self._inference_block(outcome)) is not None
        )
        rendered = self._render_context(current_input, workspace_blocks, inference_blocks)
        return AgentContext(current_input, workspace_blocks, inference_blocks, rendered)

    def _inference_block(self, outcome: InferenceOutcome) -> ProjectionBlock | None:
        if outcome.status is not LogicalStatus.PROVED or outcome.conclusion is None:
            return None
        c = outcome.conclusion
        if isinstance(c, ExistingRefConclusion):
            text = self.semantic.inference_text_for_ref(c.ref)
            root = c.ref
        elif isinstance(c, RoleBindingConclusion):
            value = self.semantic.inference_text_for_ref(c.value)
            fact = self.semantic.inference_text_for_ref(c.fact)
            text = f"{c.role.value}={value}; supported_by={fact}"
            root = c.value
        elif isinstance(c, DerivedLinkConclusion):
            source = self.semantic.inference_text_for_ref(c.source)
            target = self.semantic.inference_text_for_ref(c.target)
            text = f"{source} --{c.relation_id}--> {target}"
            root = None
        else:
            raise TypeError(type(c).__name__)
        return ProjectionBlock(root, ProjectionMode.INFERENCE, text)

    @staticmethod
    def _render_context(
        current_input: str,
        workspace_blocks: tuple[ProjectionBlock, ...],
        inference_blocks: tuple[ProjectionBlock, ...],
    ) -> str:
        sections = ["# CURRENT INPUT", current_input]
        if workspace_blocks:
            sections.extend(["", "# ACTIVE MEMORY"])
            sections.extend(f"- {block.semantic}" for block in workspace_blocks)
        if inference_blocks:
            sections.extend(["", "# INFERENCE RESULTS"])
            sections.extend(f"- {block.semantic}" for block in inference_blocks)
        return "\n".join(sections).strip()
