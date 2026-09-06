from __future__ import annotations

from dataclasses import replace
import re

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
    ProjectionBudgetExceeded, SourceScope, WorkspaceContextDiagnostic,
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
        unresolved_goal_diagnostics: tuple[tuple[str, ...], ...] = (),
        *,
        source_scope: SourceScope | None = None,
        budget_tokens: int | None = None,
    ) -> AgentContext:
        # Exact cognitive roots are retained for the operator diagnostic snapshot.
        seen: set[str] = set()
        roots: list[Ref] = []
        for ref in workspace_refs:
            if ref.uid not in seen:
                seen.add(ref.uid)
                roots.append(ref)

        allowed_uids = (
            None
            if source_scope is None
            else {ref.uid for ref in source_scope.semantic_roots}
        )
        workspace_blocks = self._model_memory_blocks(
            current_input, tuple(roots), allowed_uids=allowed_uids
        )
        if source_scope is not None:
            visible_roots = tuple(
                ref for ref in roots
                if ref.uid in allowed_uids and self.core.store.has_uid(ref.uid)
            )
            workspace_blocks += self._source_relation_blocks(visible_roots, source_scope)

        inference_blocks = tuple(
            block
            for outcome in inference_results
            if (block := self._inference_block(outcome)) is not None
        ) + tuple(
            self._unresolved_goal_block(diagnostics)
            for diagnostics in unresolved_goal_diagnostics
        )
        rendered = self._render_context(current_input, workspace_blocks, inference_blocks)
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
            workspace_blocks,
            inference_blocks,
            rendered,
            source_workspace_refs=tuple(roots),
            source_scope_ref=(None if source_scope is None else source_scope.source_ref),
            estimated_tokens=estimated_tokens,
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
        *,
        allowed_uids: set[str] | None = None,
    ) -> tuple[ProjectionBlock, ...]:
        """Compress ACTIVE graph roots into LLM-oriented semantic memory.

        S and T remain fully active in Ignition but are implementation scaffolding for
        the Agent.  N/G/K carry proposition-level meaning.  M is emitted only when it
        is not already represented by an active proposition.  Repeated semantic text
        is collapsed deterministically without ranking or top-k selection.
        """
        if allowed_uids is not None:
            roots = tuple(ref for ref in roots if ref.uid in allowed_uids)
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
            covered_m.update(ref.uid for ref in node.actants.values() if isinstance(ref, Ref) and ref.kind is RefKind.M)

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
                # DOCUMENT raw text is provenance, not model-facing retrieval memory.
                # Legacy persisted document events may still contain a text property;
                # fail closed here rather than leaking it into AgentContext.
                if str(obj.meta.get("batch_kind") or "").upper() == "DOCUMENT":
                    return None
                text_prop = obj.properties.get("text")
                if text_prop is None or not isinstance(text_prop.value, str):
                    return None
                text = text_prop.value.strip()
                speaker = self._event_speaker(obj)
                if speaker == "USER" and self._same_text(text, current_input):
                    return None  # CURRENT INPUT already contains it verbatim.
                if text in source_texts_used:
                    return None
                kinds = self._event_speech_act_kinds(obj)
                if speaker == "USER":
                    if kinds and "ASSERTION" not in kinds:
                        if kinds == ("QUERY",):
                            prefix = "Контекст диалога — ранее пользователь задал вопрос (НЕ ФАКТ)"
                        elif kinds == ("COMMAND",):
                            prefix = "Контекст диалога — ранее пользователь сформулировал запрос/команду (НЕ ФАКТ)"
                        else:
                            joined = "/".join(kinds)
                            prefix = f"Контекст диалога — неутверждающий ход пользователя [{joined}] (НЕ ФАКТ)"
                    else:
                        prefix = "Ранее пользователь сказал"
                else:
                    prefix = "Ранее агент ответил"
                return ProjectionBlock(ref, ProjectionMode.ACTIVE, f'{prefix}: «{text}»')

            # Scoped proposition content may be needed internally as a target or an
            # operand, but mentioning it under QUERY/COMMAND/quotation does not make
            # it model-visible factual evidence. Deterministic inference results are
            # projected separately below.
            scope = str(obj.meta.get("semantic_scope") or "").upper()
            if scope in {"EMBEDDED", "QUOTED", "CONDITIONAL"}:
                return None

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
                if isinstance(operand, Ref) and operand.kind is RefKind.N and self.core.store.has_uid(operand.uid):
                    node = self.core.store.get_hypernode(operand.uid)
                    source = self._source_user_utterance(operand)
                    base = (
                        f'утверждение «{source}»'
                        if source is not None
                        else self._humanize_hypernode(node)
                    )
                    if function == "NOT":
                        return ProjectionBlock(ref, ProjectionMode.ACTIVE, f"Отрицание: {base}")
                    return ProjectionBlock(
                        ref,
                        ProjectionMode.ACTIVE,
                        f"Опровержение конкретного утверждения: {base}",
                    )
            return ProjectionBlock(
                ref, ProjectionMode.ACTIVE, self.model_semantic.active_block(ref).semantic
            )

        if isinstance(obj, Group):
            group_type = str(obj.meta.get("TYPE") or obj.meta.get("type") or "").upper()
            if group_type == "CONFLICT":
                members: list[str] = []
                for member in obj.members:
                    if not self.core.store.has_uid(member.uid):
                        continue
                    member_obj = (
                        self.core.store.get_link(member.uid)
                        if member.kind is RefKind.L
                        else self.core.store.get_element_any_domain(member.uid)
                    )
                    if isinstance(member_obj, Hypernode):
                        source = self._source_user_utterance(member)
                        text = source if source is not None else self._humanize_hypernode(member_obj)
                    else:
                        text = self.model_semantic.inference_text_for_ref(member)
                    if text not in members:
                        members.append(text)
                if not members:
                    return None
                return ProjectionBlock(
                    ref,
                    ProjectionMode.ACTIVE,
                    "Неразрешённый конфликт: " + " ↔ ".join(members),
                )

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
        """Return exact USER wording that introduced one canonical content root.

        Lookup is reverse-indexed from the semantic root through optional
        UTTERANCE_CONTENT groups into H event actants.  Projection must not scan
        the whole H domain merely to recover provenance wording.
        """
        candidates: list[tuple[int, str]] = []
        container_uids: list[str] = [content_ref.uid]
        seen_containers: set[str] = set()
        cursor = 0
        while cursor < len(container_uids):
            uid = container_uids[cursor]
            cursor += 1
            if uid in seen_containers:
                continue
            seen_containers.add(uid)
            for group in self.core.store.groups_containing(uid):
                if group.uid not in seen_containers:
                    container_uids.append(group.uid)

        seen_events: set[str] = set()
        for uid in container_uids:
            for element in self.core.store.hypernodes_for_actant(uid):
                if element.uid in seen_events:
                    continue
                seen_events.add(element.uid)
                if self.core.store.domain_of(element.uid) is not Domain.H:
                    continue
                if not bool(element.meta.get("event_instance", False)):
                    continue
                if self._event_speaker(element) != "USER":
                    continue
                if str(element.meta.get("batch_kind") or "").upper() == "DOCUMENT":
                    continue
                kinds = self._event_speech_act_kinds(element)
                # New-format H events explicitly preserve pragmatic type. Only a turn
                # containing a top-level ASSERTION can be provenance for a canonical
                # world fact. Legacy events without the metadata retain old behaviour.
                if kinds and "ASSERTION" not in kinds:
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
        stack = [ref]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current.uid == target_uid:
                return True
            if current.uid in seen:
                continue
            seen.add(current.uid)
            if current.kind is not RefKind.K or not self.core.store.has_uid(current.uid):
                continue
            group = self.core.store.get_element_any_domain(current.uid)
            if isinstance(group, Group):
                stack.extend(group.members)
        return False

    @staticmethod
    def _event_speech_act_kinds(event: Hypernode) -> tuple[str, ...]:
        raw = event.meta.get("speech_act_kinds")
        if raw is None:
            return ()
        if isinstance(raw, str):
            values = (raw,)
        elif isinstance(raw, (list, tuple, set, frozenset)):
            values = tuple(str(item) for item in raw)
        else:
            return ()
        return tuple(dict.fromkeys(item.strip().upper() for item in values if item.strip()))

    def _event_speaker(self, event: Hypernode) -> str:
        subject_ref = event.actants.get(ActantRole.SUBJECT)
        if isinstance(subject_ref, Ref) and subject_ref.kind is RefKind.M and self.core.store.has_uid(subject_ref.uid):
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
            role: (
                self.model_semantic.dependency_text(ref)
                if isinstance(ref, Ref)
                else f"${ref.local_id}:{ref.sort.value}"
            )
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


    def _source_relation_blocks(
        self,
        visible_roots: tuple[Ref, ...],
        source_scope: SourceScope,
    ) -> tuple[ProjectionBlock, ...]:
        """Preserve direct structural ordering inside one bounded source scope.

        L has no x and therefore cannot appear in Workspace by itself.  For source
        projection we inspect only outgoing adjacency of already-visible source
        semantic roots and include a structural relation only when both endpoints
        belong to the same source scope.  This keeps CAUSE/FOLLOW/IS-A continuity
        without a global link scan.
        """
        visible = {ref.uid for ref in visible_roots}
        allowed = {ref.uid for ref in source_scope.semantic_roots}
        blocks: list[ProjectionBlock] = []
        seen: set[str] = set()
        for ref in visible_roots:
            for link in self.core.store.outgoing_links(ref.uid):
                relation = link.relation_id.upper()
                if relation not in {"CAUSE", "FOLLOW", "IS-A"}:
                    continue
                if link.uid in seen:
                    continue
                if link.source.uid not in allowed or link.target.uid not in allowed:
                    continue
                if link.source.uid not in visible or link.target.uid not in visible:
                    continue
                seen.add(link.uid)
                blocks.append(
                    ProjectionBlock(
                        self.core.ref(link.uid),
                        ProjectionMode.DEPENDENCY,
                        self.model_semantic.inference_text_for_ref(self.core.ref(link.uid)),
                    )
                )
        return tuple(blocks)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Deterministic tokenizer-independent context budget estimate.

        The external model tokenizer is deployment-specific.  We count word and
        punctuation units deterministically so the projector can fail closed before
        a backend silently truncates.  The value is diagnostic/budgeting metadata,
        never semantic AH state.
        """
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


    @staticmethod
    def _unresolved_goal_block(diagnostics: tuple[str, ...]) -> ProjectionBlock:
        detail = ", ".join(diagnostics) if diagnostics else "no compiler diagnostic"
        return ProjectionBlock(
            None,
            ProjectionMode.INFERENCE,
            "Логический вывод: UNRESOLVED. Формальная GoalSpec для текущей "
            "эпистемической цели не построена; ACTIVE MEMORY не является "
            f"доказательством этой цели. Диагностика: {detail}.",
        )

    def _inference_block(self, outcome: InferenceOutcome) -> ProjectionBlock | None:
        # Logical status is semantic result, not debug telemetry.  UNKNOWN and
        # DISPROVED must reach the response model; otherwise the model can invent a
        # proof after the deterministic reasoner explicitly failed or refuted it.
        if outcome.status is LogicalStatus.UNKNOWN:
            return ProjectionBlock(
                None,
                ProjectionMode.INFERENCE,
                "Логический вывод: UNKNOWN. Цель не доказана и не опровергнута.",
            )
        if outcome.status is LogicalStatus.DISPROVED:
            evidence = None
            if isinstance(outcome.conclusion, ExistingRefConclusion):
                evidence = self.model_semantic.inference_text_for_ref(outcome.conclusion.ref)
            text = "Логический вывод: DISPROVED. Цель явно опровергнута памятью."
            if evidence:
                text += f" Основание: {evidence}"
            return ProjectionBlock(None, ProjectionMode.INFERENCE, text)
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
