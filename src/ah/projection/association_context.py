from __future__ import annotations

from ah.association.contracts import AssociationOutcome, AssociationStatus
from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import InferenceOutcome
from ah.model import Hypernode, Ref

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
    Model-facing context contains only the scoped semantic result/status and the
    minimal canonical facts that ground a selected structured frame. Search paths and
    the warm Workspace remain available to diagnostics/UI but are deliberately
    excluded from response generation so the language model cannot perform a second,
    unscoped association pass over provenance details.
    """

    def __init__(self, core: AHCore, settings: ContextSettings) -> None:
        super().__init__(core, settings)

    def _ref_text(self, ref: Ref) -> str:
        if not self.core.store.has_uid(ref.uid):
            return f"unavailable {ref.kind.value}"
        return self.model_semantic.inference_text_for_ref(ref)

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

    def _fact(self, ref: Ref) -> Hypernode | None:
        try:
            value = self.core.store.get_hypernode(ref.uid)
        except Exception:
            return None
        return value if isinstance(value, Hypernode) else None

    def _operand_text(self, value) -> str:
        if isinstance(value, Ref):
            return self._ref_text(value)
        if value is None:
            return "<нет значения>"
        return str(value)

    def _frame_grounding_text(self, outcome: AssociationOutcome) -> str:
        """Render the minimal facts that give a runtime frame its actual meaning.

        A frame such as ``есть(SUBJECT=_, OBJECT=ножки)`` is intentionally compact,
        but the lexical predicate alone can be ambiguous for a response LLM.  The
        two supporting N facts disambiguate the predicate and show exactly how the
        compared endpoints instantiate every variable role.  They are evidence for
        the already-selected association, not an extra search surface.
        """
        pattern = outcome.frame_pattern
        if pattern is None:
            return ""
        left_fact = self._fact(pattern.left_fact)
        right_fact = self._fact(pattern.right_fact)
        if left_fact is None or right_fact is None:
            return ""

        left_endpoint = self._ref_text(outcome.goal.left)
        right_endpoint = self._ref_text(outcome.goal.right)
        lines: list[str] = []

        if pattern.left_fact == pattern.right_fact:
            lines.append(
                f"Общий опорный канонический факт: {self._ref_text(pattern.left_fact)}."
            )
        else:
            lines.append(
                f"Левый опорный канонический факт: {self._ref_text(pattern.left_fact)}."
            )
            lines.append(
                f"Правый опорный канонический факт: {self._ref_text(pattern.right_fact)}."
            )

        for role in pattern.variable_roles:
            left_value = self._operand_text(left_fact.actants.get(role))
            right_value = self._operand_text(right_fact.actants.get(role))
            lines.append(
                f"Переменная роль {role.value}: левый сравниваемый объект="
                f"{left_endpoint}; правый сравниваемый объект={right_endpoint}; "
                f"значение роли в левом факте={left_value}; "
                f"значение роли в правом факте={right_value}."
            )

        for binding in pattern.bindings:
            left_value = self._operand_text(left_fact.actants.get(binding.role))
            right_value = self._operand_text(right_fact.actants.get(binding.role))
            common_value = self._ref_text(binding.value)
            if binding.generalized:
                lines.append(
                    f"Общая фиксированная роль {binding.role.value}: слева={left_value}; "
                    f"справа={right_value}; каноническое обобщение={common_value} "
                    "через IS-A."
                )
            else:
                lines.append(
                    f"Общая фиксированная роль {binding.role.value}: слева={left_value}; "
                    f"справа={right_value}; фиксированное значение={common_value}."
                )

        return " ".join(lines)

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
            pattern = self._frame_pattern_text(outcome)
            semantics = (
                ""
                if outcome.semantics is None
                else f" Тип сходимости: {outcome.semantics.value}."
            )
            if pattern is not None:
                grounding_facts = self._frame_grounding_text(outcome)
                result = (
                    f"{scope} Ассоциативный поиск: FOUND. Авторитетное основание "
                    "общей черты — эта общая семантическая схема вместе с её "
                    f"опорными фактами: {pattern}."
                )
                if grounding_facts:
                    result += " " + grounding_facts
                grounding = (
                    " Символ '_' в схеме означает семантический слот, который "
                    "занимают два сравниваемых объекта; это не отдельное свойство и "
                    "не неизвестный факт. Интерпретируй predicate только вместе с "
                    "ролями и опорными фактами, а не по одному слову-предикату. "
                    "Сформулируй человеческим языком именно отношение, общее для "
                    "обоих объектов. Роли, которые различаются в опорных фактах и "
                    "не входят в fixed bindings, не объявляй общими."
                )
            else:
                common = self._ref_text(outcome.common_ref)
                result = (
                    f"{scope} Ассоциативный поиск: FOUND. Авторитетный результат — "
                    f"ТОЛЬКО эта общая репрезентация: {common}."
                )
                grounding = (
                    " Сообщай только непосредственно найденную общую репрезентацию "
                    "в пределах ограничений цели."
                )
            text = (
                result
                + semantics
                + " Это ассоциативная сходимость памяти, НЕ логическое доказательство "
                "и НЕ новый утверждённый факт. Не расширяй найденную общность мировыми "
                "знаниями или другими активными воспоминаниями."
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
        # second, unscoped search surface. Workspace stays in AgentContext metadata
        # for diagnostics/UI, but is hidden from response generation on this turn.
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

    @staticmethod
    def _has_unresolved_association(
        unresolved_goal_diagnostics: tuple[tuple[str, ...], ...],
    ) -> bool:
        return any(
            any(str(item).startswith("semantic:association") for item in diagnostics)
            for diagnostics in unresolved_goal_diagnostics
        )

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
        association_unresolved = self._has_unresolved_association(
            unresolved_goal_diagnostics
        )
        if not association_results and not association_unresolved:
            return base

        association_blocks = tuple(
            self._association_block(outcome) for outcome in association_results
        )
        # Even when compilation failed before a coordinator outcome could exist,
        # association semantics remain fail-closed: expose the explicit UNRESOLVED
        # diagnostic but not the warm Workspace as an alternate unscoped answer
        # source for the response model.
        rendered = self._render_with_association_sections(
            current_input,
            (),
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
