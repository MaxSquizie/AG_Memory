from __future__ import annotations

from ah.association.contracts import AssociationOutcome, AssociationStatus
from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import InferenceOutcome
from ah.model import Ref

from .agent_context import ContextProjector
from .contracts import (
    AgentContext,
    ProjectionBlock,
    ProjectionBudgetExceeded,
    ProjectionMode,
    SourceScope,
)


class AssociationContextProjector(ContextProjector):
    """Project associative convergence separately from logical inference.

    AssociationOutcome is runtime search provenance, not a proof and not a new fact.
    The response model therefore receives it in its own ASSOCIATION RESULTS section
    and AgentContext keeps it outside ``inference_blocks`` as well.
    """

    def __init__(self, core: AHCore, settings: ContextSettings) -> None:
        super().__init__(core, settings)

    def _ref_text(self, ref: Ref) -> str:
        if not self.core.store.has_uid(ref.uid):
            return f"unavailable {ref.kind.value}"
        return self.model_semantic.inference_text_for_ref(ref)

    def _path_text(self, path) -> str:
        if path is None or not path.refs:
            return "no path"
        parts: list[str] = [self._ref_text(path.refs[0])]
        for hop, target in zip(path.hops, path.refs[1:]):
            parts.append(f"--{hop.relation}--> {self._ref_text(target)}")
        return " ".join(parts)

    def _association_block(self, outcome: AssociationOutcome) -> ProjectionBlock:
        if outcome.status is AssociationStatus.FOUND and outcome.common_ref is not None:
            common = self._ref_text(outcome.common_ref)
            left = self._path_text(outcome.left_path)
            right = self._path_text(outcome.right_path)
            semantics = (
                ""
                if outcome.semantics is None
                else f" Тип сходимости: {outcome.semantics.value}."
            )
            text = (
                "Ассоциативный поиск: FOUND. Общая активированная репрезентация: "
                f"{common}. Левая ветвь: {left}. Правая ветвь: {right}."
                f"{semantics} Это ассоциативная сходимость памяти, НЕ логическое "
                "доказательство и НЕ новый утверждённый факт."
            )
            return ProjectionBlock(
                outcome.common_ref,
                ProjectionMode.ASSOCIATION,
                text,
            )

        text = (
            f"Ассоциативный поиск: {outcome.status.value}. "
            "В пределах заданного runtime-бюджета подтверждённая точка сходимости "
            "не найдена. Это результат поиска активации, НЕ логическое опровержение."
        )
        return ProjectionBlock(None, ProjectionMode.ASSOCIATION, text)

    @staticmethod
    def _render_with_association_sections(
        current_input: str,
        workspace_blocks: tuple[ProjectionBlock, ...],
        inference_blocks: tuple[ProjectionBlock, ...],
        association_blocks: tuple[ProjectionBlock, ...],
    ) -> str:
        sections = ["# CURRENT INPUT", current_input]
        if workspace_blocks:
            sections.extend(["", "# ACTIVE MEMORY"])
            sections.extend(f"- {block.semantic}" for block in workspace_blocks)
        if inference_blocks:
            sections.extend(["", "# INFERENCE RESULTS"])
            sections.extend(f"- {block.semantic}" for block in inference_blocks)
        if association_blocks:
            sections.extend(["", "# ASSOCIATION RESULTS"])
            sections.extend(f"- {block.semantic}" for block in association_blocks)
        return "\n".join(sections).strip()

    def project_with_associations(
        self,
        current_input: str,
        workspace_refs: tuple[Ref, ...],
        inference_results: tuple[InferenceOutcome, ...] = (),
        unresolved_goal_diagnostics: tuple[tuple[str, ...], ...] = (),
        association_results: tuple[AssociationOutcome, ...] = (),
        *,
        source_scope: SourceScope | None = None,
        budget_tokens: int | None = None,
    ) -> AgentContext:
        base = super().project(
            current_input,
            workspace_refs,
            inference_results,
            unresolved_goal_diagnostics,
            source_scope=source_scope,
            budget_tokens=budget_tokens,
        )
        if not association_results:
            return base

        association_blocks = tuple(
            self._association_block(outcome) for outcome in association_results
        )
        rendered = self._render_with_association_sections(
            current_input,
            base.workspace_blocks,
            base.inference_blocks,
            association_blocks,
        )
        estimated_tokens = self._estimate_tokens(rendered)
        limit = self.settings.max_tokens if budget_tokens is None else min(
            self.settings.max_tokens, int(budget_tokens)
        )
        if limit <= 0:
            raise ValueError("budget_tokens must be > 0")
        if estimated_tokens > limit:
            raise ProjectionBudgetExceeded(estimated_tokens, limit)

        return AgentContext(
            current_input,
            base.workspace_blocks,
            base.inference_blocks,
            rendered,
            source_workspace_refs=base.source_workspace_refs,
            source_scope_ref=base.source_scope_ref,
            estimated_tokens=estimated_tokens,
            association_blocks=association_blocks,
        )
