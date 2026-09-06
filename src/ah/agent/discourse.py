from __future__ import annotations

from dataclasses import dataclass
from ah.integration import IntegrationError, IntegrationService
from ah.integration.contracts import IntegratedRelation, IntegrationCommit
from ah.model import ActantRole, Domain, FunctionSymbol, Group, Ref, RefKind
from ah.perception import DiscourseRelationDecision
from ah.projection import ContextProjector


@dataclass(frozen=True, slots=True)
class _HistorySlice:
    narrative_text: str
    event_refs: tuple[Ref, ...]


@dataclass(frozen=True, slots=True)
class DiscourseReview:
    narrative_text: str
    prior_refs: tuple[Ref, ...]
    current_refs: tuple[Ref, ...]
    prior_semantics: tuple[str, ...]
    current_semantics: tuple[str, ...]
    excluded_pairs: tuple[tuple[int, int], ...] = ()
    resolved_current: tuple[int, ...] = ()


class DiscourseRelationRefiner:
    """Bounded cross-turn relation induction over cognitively accessible history.

    This is not a global AH search.  Starting from the current H experience, the
    refiner walks backward only while prior H turn-events are themselves present in
    Workspace.  Semantic candidate events must likewise be active Workspace N roots
    and ordinary asserted C/P content.  The H FOLLOW chain supplies narrative order;
    the context token budget supplies the only serialization bound.

    Perception sees raw narrative text plus UID-free semantic event strings.  It may
    propose one primary incoming discourse edge for each current event.  Integration
    validates canonical endpoints and performs the actual L write.  No model-selected
    UID ever crosses this boundary.
    """

    def __init__(
        self,
        integration: IntegrationService,
        perception: object,
        projector: ContextProjector,
    ) -> None:
        self.integration = integration
        self.perception = perception
        self.projector = projector

    def _ordinary_world_event(self, ref: Ref) -> bool:
        core = self.integration.core
        if ref.kind is not RefKind.N or not core.store.has_uid(ref.uid):
            return False
        if core.store.domain_of(ref.uid) not in {Domain.C, Domain.P}:
            return False
        node = core.store.get_hypernode(ref.uid)
        return (
            not bool(node.meta.get("event_instance", False))
            and node.meta.get("semantic_scope") is None
        )

    def _content_events(self, ref: Ref, active_uids: set[str]) -> tuple[Ref, ...]:
        """Return active ordinary N contained by one H utterance content object."""
        core = self.integration.core
        out: list[Ref] = []
        seen: set[str] = set()

        def visit(item: Ref) -> None:
            if item.uid in seen or not core.store.has_uid(item.uid):
                return
            seen.add(item.uid)
            if item.kind is RefKind.N:
                if item.uid in active_uids and self._ordinary_world_event(item):
                    out.append(item)
                return
            if item.kind is RefKind.K:
                group = core.store.get_element_any_domain(item.uid)
                if isinstance(group, Group):
                    for member in group.members:
                        visit(member)
                return
            if item.kind is RefKind.G:
                function = core.store.get_element_any_domain(item.uid)
                if isinstance(function, FunctionSymbol):
                    for operand in function.operands:
                        if isinstance(operand, Ref):
                            visit(operand)

        visit(ref)
        return tuple(out)

    def _history_slice(
        self,
        current_experience_ref: Ref,
        workspace_refs: tuple[Ref, ...],
        current_text: str,
    ) -> _HistorySlice:
        core = self.integration.core
        active_uids = {ref.uid for ref in workspace_refs}
        # This is an infrastructure serialization budget, not a cognitive top-k.
        # Candidate access is already determined by Workspace; the budget only
        # limits how much of that active H chain is serialized to the semantic probe.
        char_budget = max(4000, int(self.projector.settings.max_tokens) * 3)
        used_chars = len(current_text)
        prior_turns: list[tuple[str, tuple[Ref, ...]]] = []
        seen_events: set[str] = set()

        cursor = current_experience_ref
        while True:
            incoming = core.store.incoming_links(cursor.uid, "FOLLOW")
            if len(incoming) != 1:
                break
            previous = incoming[0].source
            if previous.uid not in active_uids:
                break
            if previous.kind is not RefKind.N or core.store.domain_of(previous.uid) is not Domain.H:
                break
            event = core.store.get_hypernode(previous.uid)
            if not bool(event.meta.get("event_instance", False)):
                break
            text_prop = event.properties.get("text")
            prior_text = str(text_prop.value) if text_prop is not None else ""
            object_ref = event.actants.get(ActantRole.OBJECT)
            refs = self._content_events(object_ref, active_uids) if object_ref is not None else ()
            refs = tuple(ref for ref in refs if ref.uid not in seen_events)
            serialized = sum(
                len(self.projector.model_semantic.dependency_text(ref)) + 8 for ref in refs
            )
            cost = len(prior_text) + serialized + 16
            if prior_turns and used_chars + cost > char_budget:
                break
            used_chars += cost
            for ref in refs:
                seen_events.add(ref.uid)
            prior_turns.append((prior_text, refs))
            cursor = previous

        prior_turns.reverse()
        narrative_parts = [text for text, _refs in prior_turns if text.strip()]
        narrative_parts.append(current_text)
        event_refs = tuple(
            ref for _text, refs in prior_turns for ref in refs
        )
        return _HistorySlice("\n".join(narrative_parts), event_refs)

    def _participant_uids(self, ref: Ref) -> set[str]:
        """Collect semantic M participants through bounded N/K/G actant structure."""
        core = self.integration.core
        found: set[str] = set()
        seen: set[str] = set()

        def visit(item: Ref, depth: int) -> None:
            if depth > 3 or item.uid in seen or not core.store.has_uid(item.uid):
                return
            seen.add(item.uid)
            if item.kind is RefKind.M:
                found.add(item.uid)
                return
            if item.kind is RefKind.N:
                node = core.store.get_hypernode(item.uid)
                for child in node.actants.values():
                    if isinstance(child, Ref):
                        visit(child, depth + 1)
                return
            if item.kind is RefKind.K:
                group = core.store.get_element_any_domain(item.uid)
                if isinstance(group, Group):
                    for child in group.members:
                        visit(child, depth + 1)
                return
            if item.kind is RefKind.G:
                function = core.store.get_element_any_domain(item.uid)
                if isinstance(function, FunctionSymbol):
                    for child in function.operands:
                        if isinstance(child, Ref):
                            visit(child, depth + 1)

        visit(ref, 0)
        return found

    def prepare(
        self,
        integration: IntegrationCommit,
        workspace_refs: tuple[Ref, ...],
        current_text: str,
    ) -> DiscourseReview | None:
        classifier = getattr(self.perception, "classify_discourse_relation", None)
        if not callable(classifier):
            return None

        current_refs = tuple(
            item.ref
            for item in integration.assertions
            if item.semantic_scope is None
            and item.domain in {Domain.C, Domain.P}
            and self._ordinary_world_event(item.ref)
        )
        if not current_refs:
            return None

        history = self._history_slice(
            integration.experience_ref,
            workspace_refs,
            current_text,
        )
        prior_refs = history.event_refs
        if not prior_refs:
            return None

        # Conservative scene-continuity gate.  It decides only whether a semantic
        # review is warranted, never which prior event caused/followed which current
        # event.  Cross-entity causes remain possible because only the current event
        # needs to share a participant with *some* active event in the narrative
        # window; the model may select a different prior event as the actual source.
        prior_participants: set[str] = set()
        for ref in prior_refs:
            prior_participants.update(self._participant_uids(ref))
        current_refs = tuple(
            ref for ref in current_refs
            if self._participant_uids(ref) & prior_participants
        )
        if not current_refs:
            return None

        prior_semantics = tuple(
            self.projector.model_semantic.dependency_text(ref) for ref in prior_refs
        )
        current_semantics = tuple(
            self.projector.model_semantic.dependency_text(ref) for ref in current_refs
        )

        prior_index = {ref.uid: index for index, ref in enumerate(prior_refs)}
        excluded: set[tuple[int, int]] = set()
        resolved_current: set[int] = set()

        # Existing cross-turn truth already supplies the primary incoming discourse
        # edge for a current event. Do not ask the model to duplicate it.
        for c_index, current in enumerate(current_refs):
            for relation_id in ("CAUSE", "FOLLOW"):
                for link in self.integration.core.store.incoming_links(current.uid, relation_id):
                    p_index = prior_index.get(link.source.uid)
                    if p_index is not None:
                        resolved_current.add(c_index)
                        break
                if c_index in resolved_current:
                    break

        for c_index in resolved_current:
            excluded.update((p_index, c_index) for p_index in range(len(prior_refs)))

        return DiscourseReview(
            narrative_text=history.narrative_text,
            prior_refs=prior_refs,
            current_refs=current_refs,
            prior_semantics=prior_semantics,
            current_semantics=current_semantics,
            excluded_pairs=tuple(sorted(excluded)),
            resolved_current=tuple(sorted(resolved_current)),
        )

    def decide(
        self,
        review: DiscourseReview | None,
    ) -> tuple[DiscourseRelationDecision, ...]:
        """Run UID-free semantic probes against one immutable candidate snapshot."""
        if review is None:
            return ()
        classifier = getattr(self.perception, "classify_discourse_relation", None)
        if not callable(classifier):
            return ()

        excluded = set(review.excluded_pairs)
        resolved_current = set(review.resolved_current)
        decisions: list[DiscourseRelationDecision] = []
        # One primary incoming discourse edge per newly asserted event in this pass.
        # The bound is the finite set of current semantic events, not an arbitrary
        # parser/event-count cap. It prevents one uncertain narrative turn from
        # multiplying speculative causal shortcuts while still allowing every
        # current event to acquire its own cross-turn dependency.
        while len(resolved_current) < len(review.current_refs):
            decision = classifier(
                review.narrative_text,
                review.prior_semantics,
                review.current_semantics,
                excluded_pairs=tuple(sorted(excluded)),
            )
            if decision is None:
                break
            if (
                decision.prior_index < 0
                or decision.prior_index >= len(review.prior_refs)
                or decision.current_index < 0
                or decision.current_index >= len(review.current_refs)
                or decision.current_index in resolved_current
                or (decision.prior_index, decision.current_index) in excluded
            ):
                break
            decisions.append(decision)
            resolved_current.add(decision.current_index)
            excluded.update(
                (p_index, decision.current_index)
                for p_index in range(len(review.prior_refs))
            )
        return tuple(decisions)

    def integrate(
        self,
        review: DiscourseReview | None,
        decisions: tuple[DiscourseRelationDecision, ...],
    ) -> tuple[IntegratedRelation, ...]:
        """Map local decision indexes back to canonical refs and write validated L."""
        if review is None or not decisions:
            return ()
        integrated: list[IntegratedRelation] = []
        for decision in decisions:
            if (
                not 0 <= decision.prior_index < len(review.prior_refs)
                or not 0 <= decision.current_index < len(review.current_refs)
            ):
                continue
            source = review.prior_refs[decision.prior_index]
            target = review.current_refs[decision.current_index]
            try:
                relation = self.integration.integrate_discourse_relation(
                    decision.canonical_relation_id,
                    source,
                    target,
                )
            except IntegrationError:
                # Optional semantic enrichment fails closed. Canonical validation is
                # authoritative; a rejected relation must not destroy the primary
                # user-turn integration that already succeeded.
                continue
            integrated.append(relation)
        return tuple(integrated)
