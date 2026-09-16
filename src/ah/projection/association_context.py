from __future__ import annotations

from ah.association.contracts import AssociationOutcome, AssociationStatus
from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import InferenceOutcome
from ah.model import Ref

from .set_valued_context import SetValuedContextProjector
from .contracts import (
    AgentContext,
    ProjectionBlock,
    ProjectionBudgetExceeded,
    ProjectionMode,
    SourceScope,
)


class AssociationContextProjector(SetValuedContextProjector):
    """Project associative convergence separately from logical inference.

    AssociationOutcome is runtime search provenance, not a proof and not a new fact.
    When an association goal has an outcome, the response prompt is intentionally
    *scoped*: unrelated active Workspace facts are not rendered beside the result.
    Otherwise the response LLM can ignore the search stop condition and independently
    reconstruct old commonalities from whatever happens to be warm in memory.
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

    def _frame_pattern_text(self, outcome: AssociationOutcome) -> str | None:
        pattern = outcome.frame_pattern
        if pattern is None:
            return None
        rows: list[tuple[str, str]] = []
        for role in pattern.variable_roles:
            rows.append((role.value, "_"))
        for binding in pattern.bindings:
            value = self._ref_text(binding.value)
            if binding.generalized:
                value = f"{value} [IS-A generalization]"
            rows.append((binding.role.value, value))
        rows.sort(key=lambda item: item[0])
        predicate = self._ref_text(pattern.predicate)
        return f"{predicate}({', '.join(f'{role}={value}' for role, value in rows)})"

    def _scope_text(self, outcome: AssociationOutcome) -> str:
        constraints = tuple(getattr(outcome.goal, "constraints", ()) or ())
        if not constraints:
            return "Ограничения цели: нет."
        rendered = ", ".join(
            f"{item.role.value}={self._ref_text(item.value)}"
            for item in constraints
        )
        return f"Ограничения цели: {rendered}."

    def _association_block(self, outcome: AssociationOutcome) -> ProjectionBlock:
        scope = self._scope_text(outcome)
        if outcome.status is AssociationStatus.FOUND and outcome.common_ref is not None:
            common = self._ref_text(outcome.common_ref)
            left = self._path_text(outcome.left_path)
            right = self._path_text(outcome.right_path)
            pattern = self._frame_pattern_text(outcome)
            semantics = (
                ""
                if outcome.semantics is None
                else f" Тип сходимости: {outcome.semantics.value}."
            )
            if pattern is not None:
                result = (
                    f"{scope} Ассоциативный поиск: FOUND. Авторитетный ответ для общей "
                    "черты — ТОЛЬКО эта общая семантическая схема: "
                    f"{pattern}. Структурная точка сходимости активации: {common}. "
                    f"Левая ветвь provenance: {left}. Правая ветвь provenance: {right}."
                )
                grounding = (
                    " Поддерживающие ветви являются только provenance поиска: НЕ выводи "
                    "из их полного текста дополнительные общие свойства. Ответ должен "
                    "описывать ровно predicate, variable roles и fixed bindings указанной "
                    "схемы и соблюдать ограничения цели."
                )
            else:
                result = (
                    f"{scope} Ассоциативный поиск: FOUND. Общая активированная "
                    f"репрезентация: {common}. Левая ветвь: {left}. Правая ветвь: {right}."
                )
                grounding = (
                    " Не превращай детали одной поддерживающей ветви в свойства второго "
                    "объекта; сообщай только непосредственно найденную общую репрезентацию "
                    "в пределах ограничений цели."
                )
            text = (
                result
                + semantics
                + " Это ассоциативная сходимость памяти, НЕ логическое доказательство "
                "и НЕ новый утверждённый факт. Не расширяй найденную общность мировыми "
                "знаниями за пределы указанной схемы."
                + grounding
            )
            return ProjectionBlock(
                outcome.common_ref,
                ProjectionMode.ASSOCIATION,
                text,
            )

        text = (
            f"{scope} Ассоциативный поиск: {outcome.status.value}. "
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
        # Association results are already a bounded, goal-scoped read from memory.
        # Rendering the entire warm Workspace next to them gives the response model a
        # second, unscoped search surface and was the direct cause of replies that
        # re-listed previously emitted legs/workshop facts. Keep Workspace metadata in
        # AgentContext for diagnostics/UI, but do not expose it to response generation
        # on a turn with an association outcome.
        if workspace_blocks and not association_blocks:
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
