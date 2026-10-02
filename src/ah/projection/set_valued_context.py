from __future__ import annotations

from ah.inference.contracts import (
    CompositeConclusion,
    LogicalStatus,
    MultiRoleBindingConclusion,
    RoleBindingConclusion,
)

from .contracts import ProjectionBlock, ProjectionMode
from .event_context import EventAwareContextProjector


class SetValuedContextProjector(EventAwareContextProjector):
    """Render every deterministic WH binding from one set-valued query result."""

    def _inference_block(self, outcome):
        conclusion = outcome.conclusion
        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, CompositeConclusion)
            and conclusion.conclusions
            and all(
                isinstance(item, RoleBindingConclusion)
                for item in conclusion.conclusions
            )
        ):
            values: list[str] = []
            facts: list[str] = []
            for item in conclusion.conclusions:
                value = self._proof_ref_text(item.value)
                fact = self._proof_ref_text(item.fact)
                if value not in values:
                    values.append(value)
                if fact not in facts:
                    facts.append(fact)
            text = "Ответы по формальным ограничениям: " + "; ".join(values) + "."
            if facts:
                text += " Основания в памяти: " + "; ".join(facts)
            return ProjectionBlock(None, ProjectionMode.INFERENCE, text)

        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, CompositeConclusion)
            and conclusion.conclusions
            and all(
                isinstance(item, MultiRoleBindingConclusion)
                for item in conclusion.conclusions
            )
        ):
            rows: list[str] = []
            for item in conclusion.conclusions:
                bindings = "; ".join(
                    f"{self._ROLE_LABELS.get(role, role.value.casefold())}: {self._proof_ref_text(value)}"
                    for role, value in item.bindings
                )
                fact = self._proof_ref_text(item.fact)
                rows.append(f"{bindings} (основание: {fact})")
            return ProjectionBlock(
                None,
                ProjectionMode.INFERENCE,
                "Ответы по формальным ограничениям: " + " | ".join(rows),
            )

        return super()._inference_block(outcome)
