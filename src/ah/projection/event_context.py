from __future__ import annotations

from dataclasses import replace

from ah.inference.contracts import (
    CompositeConclusion,
    ExistingRefConclusion,
    LogicalStatus,
)
from ah.inference.event_query import EventMatchGoal
from ah.inference.identity_query import EntityIdentityGoal
from ah.inference.quantified_exists import DerivedAtomConclusion
from ah.integration.identity_graph import identity_name_refs_for_owner, identity_name_text
from ah.model import ActantRole, Domain, Hypernode, Ref, RefKind, SemanticEntity

from .agent_context import ContextProjector as _BaseContextProjector
from .contracts import ProjectionBlock, ProjectionMode


class EventAwareContextProjector(_BaseContextProjector):
    """Project complete proof results without losing canonical entity identity.

    A turn with an explicit formal proof obligation is response-grounded by the
    reasoner result, not by arbitrary simultaneously active memory. Workspace is
    still retained in ``source_workspace_refs`` for diagnostics/Proof Explorer, but
    its prose is withheld from the Main LLM whenever inference or an unresolved
    GoalSpec result is present.

    Identity questions may be supported by explicit IDENTITY_NAME edges and/or
    unary conceptual descriptors such as ``студент(Алексей)``. Quantified inference
    may also return a proved ground atom before it is materialized; both are rendered
    directly from typed proof objects rather than guessed by the response model.
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
            context = replace(context, source_workspace_refs=tuple(workspace_refs))
        return context

    @staticmethod
    def _property_values(entity: SemanticEntity, key: str) -> tuple[str, ...]:
        prop = entity.properties.get(key)
        if prop is None:
            return ()
        raw = prop.value
        items = raw if isinstance(raw, (tuple, list, set, frozenset)) else (raw,)
        out: list[str] = []
        seen: set[str] = set()
        for item in items:
            value = str(item).strip()
            folded = value.casefold()
            if value and folded not in seen:
                seen.add(folded)
                out.append(value)
        return tuple(out)

    def _entity_identity_parts(self, ref: Ref) -> tuple[str, tuple[str, ...]] | None:
        if ref.kind is not RefKind.M:
            return None
        try:
            entity = self.core.store.get_element_any_domain(ref.uid)
        except KeyError:
            return None
        if not isinstance(entity, SemanticEntity):
            return None
        names = self._property_values(entity, "name")
        aliases = list(self._property_values(entity, "aliases"))
        for name_ref in identity_name_refs_for_owner(self.core, ref):
            try:
                name_entity = self.core.store.get_element_any_domain(name_ref.uid)
            except KeyError:
                continue
            if not isinstance(name_entity, SemanticEntity):
                continue
            value = identity_name_text(name_entity)
            if value and value.casefold() not in {item.casefold() for item in aliases}:
                aliases.append(value)
        primary = names[0] if names else ref.uid
        unique_aliases = tuple(
            value
            for value in aliases
            if value.casefold() != primary.casefold()
        )
        return primary, unique_aliases

    def _entity_identity_text(self, ref: Ref) -> str:
        parts = self._entity_identity_parts(ref)
        if parts is None:
            return self.model_semantic.inference_text_for_ref(ref)
        primary, aliases = parts
        if not aliases:
            return primary
        return f"{primary} (тот же объект; имена/идентификаторы: {', '.join(aliases)})"

    def _proof_ref_text(self, ref: Ref) -> str:
        if ref.kind is RefKind.M:
            return self._entity_identity_text(ref)
        if ref.kind is not RefKind.N:
            return self.model_semantic.inference_text_for_ref(ref)
        try:
            node = self.core.store.get_hypernode(ref.uid)
            template = self.core.store.get_template(node.template.uid)
        except (KeyError, TypeError):
            return self.model_semantic.inference_text_for_ref(ref)
        if not isinstance(node, Hypernode):
            return self.model_semantic.inference_text_for_ref(ref)

        predicate = self.model_semantic.inference_text_for_ref(template.predicate)
        chunks: list[str] = []
        for role in template.roles:
            value = node.actants.get(role)
            if not isinstance(value, Ref):
                return self.model_semantic.inference_text_for_ref(ref)
            rendered = (
                self._entity_identity_text(value)
                if value.kind is RefKind.M
                else self.model_semantic.inference_text_for_ref(value)
            )
            chunks.append(f"{role.value}={rendered}")
        return f"{predicate}({', '.join(chunks)})"

    def _identity_descriptors(
        self,
        target: Ref,
        premise_refs: tuple[Ref, ...],
    ) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for ref in premise_refs:
            if ref.kind is not RefKind.N or not self.core.store.has_uid(ref.uid):
                continue
            if self.core.store.domain_of(ref.uid) is not Domain.C:
                continue
            try:
                node = self.core.store.get_hypernode(ref.uid)
                template = self.core.store.get_template(node.template.uid)
            except (KeyError, TypeError):
                continue
            if tuple(template.roles) != (ActantRole.SUBJECT,):
                continue
            if node.actants.get(ActantRole.SUBJECT) != target:
                continue
            predicate = self.model_semantic.inference_text_for_ref(template.predicate).strip()
            folded = predicate.casefold()
            if predicate and folded not in seen:
                seen.add(folded)
                out.append(predicate)
        return tuple(out)

    def _identity_block(
        self,
        ref: Ref,
        premise_refs: tuple[Ref, ...] = (),
    ) -> ProjectionBlock:
        parts = self._entity_identity_parts(ref)
        descriptors = self._identity_descriptors(ref, premise_refs)
        if parts is None:
            return ProjectionBlock(
                ref,
                ProjectionMode.INFERENCE,
                "Идентичность сущности подтверждена, но её человекочитаемая метка недоступна.",
            )
        primary, aliases = parts
        chunks: list[str] = []
        if descriptors:
            chunks.append(
                f"Описание сущности: «{primary}» — {', '.join(descriptors)}."
            )
        if aliases:
            chunks.append(
                f"«{primary}» и «{', '.join(aliases)}» связаны как обозначения одного объекта."
            )
        if not chunks:
            chunks.append(f"Идентичность сущности: известное обозначение — «{primary}».")
        return ProjectionBlock(ref, ProjectionMode.INFERENCE, " ".join(chunks))

    def _derived_atom_block(self, conclusion: DerivedAtomConclusion) -> ProjectionBlock:
        try:
            template = self.core.store.get_template(conclusion.template_ref.uid)
        except KeyError:
            return ProjectionBlock(
                None,
                ProjectionMode.INFERENCE,
                "Логический вывод доказал целевое атомарное утверждение.",
            )
        predicate = self.model_semantic.inference_text_for_ref(template.predicate)
        roles = conclusion.role_map()
        chunks: list[str] = []
        for role in template.roles:
            value = roles.get(role)
            if value is None:
                continue
            rendered = (
                self._entity_identity_text(value)
                if value.kind is RefKind.M
                else self.model_semantic.inference_text_for_ref(value)
            )
            chunks.append(f"{role.value}={rendered}")
        text = f"Доказано логическим выводом: {predicate}({', '.join(chunks)})."
        return ProjectionBlock(None, ProjectionMode.INFERENCE, text)

    def _inference_block(self, outcome):
        conclusion = outcome.conclusion
        target = None if outcome.goal_spec is None else outcome.goal_spec.target

        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(conclusion, DerivedAtomConclusion)
        ):
            return self._derived_atom_block(conclusion)

        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(target, EntityIdentityGoal)
            and isinstance(conclusion, ExistingRefConclusion)
            and conclusion.ref.kind is RefKind.M
        ):
            return self._identity_block(conclusion.ref, outcome.premise_refs)

        if (
            outcome.status is LogicalStatus.PROVED
            and isinstance(target, EventMatchGoal)
            and isinstance(conclusion, ExistingRefConclusion)
        ):
            return ProjectionBlock(
                conclusion.ref,
                ProjectionMode.INFERENCE,
                "Найденное событие по формальным ограничениям: "
                + self._proof_ref_text(conclusion.ref),
            )

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
                self._proof_ref_text(item.ref)
                for item in conclusion.conclusions
            )
            text = "Найденные события по формальным ограничениям: " + "; ".join(facts)
            return ProjectionBlock(None, ProjectionMode.INFERENCE, text)
        return super()._inference_block(outcome)
