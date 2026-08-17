from __future__ import annotations

from dataclasses import replace

from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import (
    DerivedLinkConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    LogicalStatus,
    MultiRoleBindingConclusion,
    RoleBindingConclusion,
)
from ah.model import (
    ActantRole,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Ref,
    RefKind,
    SemanticEntity,
    Template,
)

from .contracts import (
    AgentContext, AgentContextDiagnostic, ProjectionBlock, ProjectionMode,
    WorkspaceContextDiagnostic,
)
from .semantic_projection import SemanticProjector


class ContextProjector:
    """Read-only Workspace/Inference -> AgentContext.

    Workspace is a cognitive set, not a serialization format.  Model-visible memory
    therefore preserves the semantic content of ACTIVE roots while removing graph
    implementation detail (UIDs, standalone S/T scaffolding and duplicate dependency
    nodes).  The exact source Workspace remains available through the diagnostic
    channel and never leaks into the Agent prompt.
    """

    _ROLE_LABELS = {
        ActantRole.SUBJECT: "субъект",
        ActantRole.OBJECT: "объект",
        ActantRole.AUXILLIARY: "уточнение",
        ActantRole.RECIPIENT: "получатель",
        ActantRole.SOURCE: "источник",
        ActantRole.ABSENTEE: "отсутствующий участник",
        ActantRole.LOCATION: "место",
        ActantRole.STATE: "состояние",
        ActantRole.TIME: "время",
        ActantRole.DURATION: "длительность",
        ActantRole.CAUSE: "причина",
        ActantRole.PURPOSE: "цель",
        ActantRole.TOOL: "инструмент",
        ActantRole.MATERIAL: "материал",
        ActantRole.AMOUNT: "количество",
        ActantRole.HOW_TO: "способ",
    }

    def __init__(self, core: AHCore, settings: ContextSettings) -> None:
        self.core = core
        self.settings = settings
        # Debug/operator projection may expose structural UIDs. Agent-facing semantic
        # projection never does: model input must be meaning, not an AH graph dump.
        self.semantic = SemanticProjector(core, settings)
        self.model_semantic = SemanticProjector(
            core, replace(settings, include_structural_uids=False)
        )

    def project(
        self,
        current_input: str,
        workspace_refs: tuple[Ref, ...],
        inference_results: tuple[InferenceOutcome, ...] = (),
    ) -> AgentContext:
        # Exact cognitive roots are retained for the operator diagnostic snapshot.
        seen: set[str] = set()
        roots: list[Ref] = []
        for ref in workspace_refs:
            if ref.uid not in seen:
                seen.add(ref.uid)
                roots.append(ref)

        workspace_blocks = self._model_memory_blocks(current_input, tuple(roots))
        inference_blocks = tuple(
            block
            for outcome in inference_results
            if (block := self._inference_block(outcome)) is not None
        )
        rendered = self._render_context(current_input, workspace_blocks, inference_blocks)
        return AgentContext(
            current_input,
            workspace_blocks,
            inference_blocks,
            rendered,
            source_workspace_refs=tuple(roots),
        )

    def diagnose(
        self,
        context: AgentContext,
        *,
        tick_index: int,
        workspace_threshold: float,
        settle_ticks: int = 0,
    ) -> AgentContextDiagnostic:
        """Capture the exact source Workspace independently from model compression."""
        rows: list[WorkspaceContextDiagnostic] = []
        for position, ref in enumerate(context.source_workspace_refs, start=1):
            if not self.core.store.has_uid(ref.uid):
                continue
            state = self.core.store.runtime_state(ref.uid)
            domain = self.core.store.domain_of(ref.uid)
            lifecycle_state: str | None = None
            if ref.kind is RefKind.N:
                try:
                    node = self.core.store.get_hypernode(ref.uid)
                    raw = node.meta.get("lifecycle_state")
                    lifecycle_state = None if raw is None else str(getattr(raw, "value", raw))
                except (KeyError, TypeError):
                    lifecycle_state = None
            rows.append(
                WorkspaceContextDiagnostic(
                    position=position,
                    root=ref,
                    semantic=self.semantic.active_block(ref).semantic,
                    kind=ref.kind.value,
                    domain=(None if domain is None else domain.value),
                    excitation=float(state.excitation),
                    output=float(state.output),
                    decay_age=int(state.decay_age),
                    lifecycle_state=lifecycle_state,
                )
            )
        return AgentContextDiagnostic(
            tick_index=max(0, int(tick_index)),
            workspace_threshold=float(workspace_threshold),
            workspace=tuple(rows),
            settle_ticks=max(0, int(settle_ticks)),
        )

    def _model_memory_blocks(
        self,
        current_input: str,
        roots: tuple[Ref, ...],
    ) -> tuple[ProjectionBlock, ...]:
        """Compress ACTIVE graph roots into LLM-oriented semantic memory.

        S and T remain fully active in Ignition but are implementation scaffolding for
        the Agent.  N/G/K carry proposition-level meaning.  M is emitted only when it
        is not already represented by an active proposition.  Repeated semantic text
        is collapsed deterministically without ranking or top-k selection.
        """
        active_n = {
            ref.uid for ref in roots
            if ref.kind is RefKind.N and self.core.store.has_uid(ref.uid)
        }
        covered_m: set[str] = set()
        for uid in active_n:
            try:
                node = self.core.store.get_hypernode(uid)
            except (KeyError, TypeError):
                continue
            covered_m.update(ref.uid for ref in node.actants.values() if ref.kind is RefKind.M)

        blocks: list[ProjectionBlock] = []
        seen_semantic: set[str] = set()
        source_texts_used: set[str] = set()

        # Proposition-level roots first so their dependencies can be suppressed.
        ordered = sorted(
            roots,
            key=lambda ref: (
                0 if ref.kind in {RefKind.N, RefKind.G, RefKind.K} else 1,
                self.core.store.creation_sequence(ref.uid)
                if self.core.store.has_uid(ref.uid) else 0,
            ),
        )
        for ref in ordered:
            if not self.core.store.has_uid(ref.uid):
                continue
            block = self._model_block_for_ref(
                ref,
                current_input=current_input,
                covered_m=covered_m,
                source_texts_used=source_texts_used,
            )
            if block is None:
                continue
            normalized = " ".join(block.semantic.split()).casefold()
            if not normalized or normalized in seen_semantic:
                continue
            seen_semantic.add(normalized)
            blocks.append(block)
        return tuple(blocks)

    def _model_block_for_ref(
        self,
        ref: Ref,
        *,
        current_input: str,
        covered_m: set[str],
        source_texts_used: set[str],
    ) -> ProjectionBlock | None:
        # Lexical/schema nodes drive retrieval but are not themselves memory prose.
        if ref.kind in {RefKind.S, RefKind.T, RefKind.L}:
            return None

        obj = self.core.store.get_element_any_domain(ref.uid)

        if isinstance(obj, SemanticEntity):
            identity = str(obj.meta.get("identity_role", "")).upper()
            if identity in {"USER", "SELF"} or ref.uid in covered_m:
                return None
            name = obj.properties.get("name")
            semantic = str(name.value) if name is not None else ref.uid
            return ProjectionBlock(ref, ProjectionMode.ACTIVE, f"Связанная сущность: {semantic}.")

        if isinstance(obj, Hypernode):
            if bool(obj.meta.get("event_instance", False)):
                text_prop = obj.properties.get("text")
                if text_prop is None or not isinstance(text_prop.value, str):
                    return None
                text = text_prop.value.strip()
                speaker = self._event_speaker(obj)
                if speaker == "USER" and self._same_text(text, current_input):
                    return None  # CURRENT INPUT already contains it verbatim.
                if text in source_texts_used:
                    return None
                prefix = "Ранее пользователь сказал" if speaker == "USER" else "Ранее агент ответил"
                return ProjectionBlock(ref, ProjectionMode.ACTIVE, f'{prefix}: «{text}»')

            source = self._source_user_utterance(ref)
            if source is not None:
                if self._same_text(source, current_input):
                    return None  # current semantic content is already in CURRENT INPUT
                source_texts_used.add(source)
                return ProjectionBlock(
                    ref,
                    ProjectionMode.ACTIVE,
                    f'Пользователь ранее сказал: «{source}»',
                )
            return ProjectionBlock(ref, ProjectionMode.ACTIVE, self._humanize_hypernode(obj))

        if isinstance(obj, FunctionSymbol):
            function = obj.function_id.upper()
            if function in {"FALSE", "NOT"} and len(obj.operands) == 1:
                operand = obj.operands[0]
                if operand.kind is RefKind.N and self.core.store.has_uid(operand.uid):
                    node = self.core.store.get_hypernode(operand.uid)
                    source = self._source_user_utterance(operand)
                    base = (
                        f'утверждение «{source}»'
                        if source is not None
                        else self._humanize_hypernode(node)
                    )
                    return ProjectionBlock(ref, ProjectionMode.ACTIVE, f"Отрицание/опровержение: {base}")
            return ProjectionBlock(
                ref, ProjectionMode.ACTIVE, self.model_semantic.active_block(ref).semantic
            )

        if isinstance(obj, Group):
            members: list[str] = []
            for member in obj.members:
                if not self.core.store.has_uid(member.uid):
                    continue
                member_obj = self.core.store.get_element_any_domain(member.uid)
                if isinstance(member_obj, Hypernode):
                    source = self._source_user_utterance(member)
                    if source is not None and self._same_text(source, current_input):
                        continue
                    text = source if source is not None else self._humanize_hypernode(member_obj)
                    if text not in members:
                        members.append(text)
            if not members:
                return None
            return ProjectionBlock(
                ref,
                ProjectionMode.ACTIVE,
                "Связанный фрагмент памяти: " + "; ".join(members),
            )

        return ProjectionBlock(ref, ProjectionMode.ACTIVE, self.model_semantic.active_block(ref).semantic)

    def _source_user_utterance(self, content_ref: Ref) -> str | None:
        """Return exact USER wording that introduced one canonical content root."""
        candidates: list[tuple[int, str]] = []
        for element in self.core.store.elements(Domain.H):
            if not isinstance(element, Hypernode) or not bool(element.meta.get("event_instance", False)):
                continue
            if self._event_speaker(element) != "USER":
                continue
            object_ref = element.actants.get(ActantRole.OBJECT)
            if object_ref is None or not self._ref_contains(object_ref, content_ref.uid):
                continue
            text_prop = element.properties.get("text")
            if text_prop is None or not isinstance(text_prop.value, str) or not text_prop.value.strip():
                continue
            try:
                seq = self.core.store.creation_sequence(element.uid)
            except KeyError:
                seq = 0
            candidates.append((seq, text_prop.value.strip()))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _ref_contains(self, ref: Ref, target_uid: str) -> bool:
        if ref.uid == target_uid:
            return True
        if ref.kind is not RefKind.K or not self.core.store.has_uid(ref.uid):
            return False
        group = self.core.store.get_element_any_domain(ref.uid)
        return isinstance(group, Group) and any(member.uid == target_uid for member in group.members)

    def _event_speaker(self, event: Hypernode) -> str:
        subject_ref = event.actants.get(ActantRole.SUBJECT)
        if subject_ref is not None and subject_ref.kind is RefKind.M and self.core.store.has_uid(subject_ref.uid):
            subject = self.core.store.get_element_any_domain(subject_ref.uid)
            if isinstance(subject, SemanticEntity):
                identity = str(subject.meta.get("identity_role", "")).upper()
                if identity in {"USER", "SELF"}:
                    return identity
        return "UNKNOWN"

    @staticmethod
    def _same_text(left: str, right: str) -> bool:
        return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()

    def _humanize_hypernode(self, node: Hypernode) -> str:
        template = self.core.store.get_template(node.template.uid)
        predicate = self.model_semantic.dependency_text(template.predicate)
        values = {
            role: self.model_semantic.dependency_text(ref)
            for role, ref in node.actants.items()
        }
        subject = values.get(ActantRole.SUBJECT)
        obj = values.get(ActantRole.OBJECT)
        aux = values.get(ActantRole.AUXILLIARY)

        # Common ownership/existence frame: preserve distinct descriptor and value.
        if predicate.casefold() in {"есть", "иметь"} and subject and obj:
            if aux:
                return f"{subject}: есть {obj} — {aux}."
            return f"{subject}: есть {obj}."

        if subject and obj:
            base = f"{subject}: {predicate} → {obj}"
        elif subject:
            base = f"{subject}: {predicate}"
        else:
            base = predicate

        extras: list[str] = []
        for role in template.roles:
            if role in {ActantRole.SUBJECT, ActantRole.OBJECT} or role not in values:
                continue
            extras.append(f"{self._ROLE_LABELS.get(role, role.value.casefold())}: {values[role]}")
        if extras:
            base += " (" + "; ".join(extras) + ")"
        return base + "."

    def _inference_block(self, outcome: InferenceOutcome) -> ProjectionBlock | None:
        if outcome.status is not LogicalStatus.PROVED or outcome.conclusion is None:
            return None
        c = outcome.conclusion
        if isinstance(c, ExistingRefConclusion):
            text = self.model_semantic.inference_text_for_ref(c.ref)
            root = c.ref
        elif isinstance(c, RoleBindingConclusion):
            value = self.model_semantic.inference_text_for_ref(c.value)
            fact = self.model_semantic.inference_text_for_ref(c.fact)
            text = f"Ответ: {value}. Основание в памяти: {fact}"
            root = c.value
        elif isinstance(c, MultiRoleBindingConclusion):
            rendered = [
                f"{self._ROLE_LABELS.get(role, role.value.casefold())}: {self.model_semantic.inference_text_for_ref(value)}"
                for role, value in c.bindings
            ]
            fact = self.model_semantic.inference_text_for_ref(c.fact)
            text = "; ".join(rendered) + f". Основание в памяти: {fact}"
            root = c.fact
        elif isinstance(c, DerivedLinkConclusion):
            source = self.model_semantic.inference_text_for_ref(c.source)
            target = self.model_semantic.inference_text_for_ref(c.target)
            text = f"{source} — {c.relation_id} → {target}"
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
