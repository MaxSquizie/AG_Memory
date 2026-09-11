from __future__ import annotations

from ah.core import AHCore
from ah.ignition import IgnitionEngine
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import ActantRole, Domain, Group, Ref, RefKind

from .contracts import (
    SourceProjectionCursor,
    SourceScope,
    SourceScopeActivation,
    SourceScopeSlice,
    SourceScopedContextResult,
)


class SourceScopeNotFound(KeyError):
    pass


_COHERENCE_RELATIONS = frozenset({"CAUSE", "FOLLOW", "BEFORE", "AFTER", "OVERLAP"})


class SourceScopeResolver:
    """Resolve a technical source handle to its canonical semantic roots.

    Resolution is deliberately index-bounded: ``source_ref -> H occurrences`` is
    a rebuildable AHStore index.  The resolver follows only the OBJECT references
    of those occurrences and flattens the dedicated UTTERANCE_CONTENT grouping.
    It never scans C/P/H and never reads raw source text.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def resolve(self, source_ref: str) -> SourceScope:
        key = source_ref.strip()
        if not key:
            raise ValueError("source_ref must be non-empty")
        events = self.core.store.find_experiences_by_source_ref(key)
        if not events:
            raise SourceScopeNotFound(key)

        experience_refs: list[Ref] = []
        roots: list[Ref] = []
        seen_roots: set[str] = set()
        for event in events:
            if self.core.store.domain_of(event.uid) is not Domain.H:
                continue
            experience_refs.append(self.core.ref(event.uid))
            content = event.actants.get(ActantRole.OBJECT)
            if not isinstance(content, Ref):
                continue
            for ref in self._content_roots(content):
                if ref.uid in seen_roots or not self.core.store.has_uid(ref.uid):
                    continue
                seen_roots.add(ref.uid)
                roots.append(ref)

        roots.sort(key=lambda ref: self.core.store.creation_sequence(ref.uid))
        experience_refs.sort(key=lambda ref: self.core.store.creation_sequence(ref.uid))
        return SourceScope(key, tuple(experience_refs), tuple(roots))

    def slice(
        self,
        cursor: SourceProjectionCursor,
        *,
        max_primary_roots: int,
    ) -> SourceScopeSlice:
        """Return an index-bounded semantic slice without reading raw source text.

        Cursor advancement counts only primary roots.  One-hop causal/temporal
        neighbors from the same source are carried as overlap so relations that
        cross a slice boundary remain representable without duplicating progress.
        """
        if max_primary_roots < 1:
            raise ValueError("max_primary_roots must be >= 1")
        full = self.resolve(cursor.source_ref)
        start = cursor.next_index
        if start > len(full.semantic_roots):
            raise ValueError("source projection cursor is past end of source")
        end = min(len(full.semantic_roots), start + max_primary_roots)
        primary = full.semantic_roots[start:end]
        primary_uids = {ref.uid for ref in primary}
        source_by_uid = {ref.uid: ref for ref in full.semantic_roots}
        source_index = {ref.uid: index for index, ref in enumerate(full.semantic_roots)}
        overlap: dict[str, Ref] = {}
        for ref in primary:
            for link in (*self.core.store.outgoing_links(ref.uid), *self.core.store.incoming_links(ref.uid)):
                if link.relation_id.upper() not in _COHERENCE_RELATIONS:
                    continue
                other = link.target if link.source.uid == ref.uid else link.source
                if other.uid in primary_uids or other.uid not in source_by_uid:
                    continue
                # Cursor slices may carry already-seen semantic context forward,
                # but must not expose future roots before their primary turn.
                if source_index[other.uid] >= start:
                    continue
                overlap[other.uid] = source_by_uid[other.uid]
        ordered_overlap = tuple(
            sorted(overlap.values(), key=lambda ref: self.core.store.creation_sequence(ref.uid))
        )
        roots = tuple(
            sorted(
                (*primary, *ordered_overlap),
                key=lambda ref: self.core.store.creation_sequence(ref.uid),
            )
        )
        sliced_scope = SourceScope(full.source_ref, full.experience_refs, roots)
        next_cursor = SourceProjectionCursor(full.source_ref, end)
        return SourceScopeSlice(
            scope=sliced_scope,
            cursor=cursor,
            next_cursor=next_cursor,
            primary_refs=primary,
            overlap_refs=ordered_overlap,
            done=end >= len(full.semantic_roots),
        )

    def _content_roots(self, ref: Ref) -> tuple[Ref, ...]:
        if ref.kind is not RefKind.K or not self.core.store.has_uid(ref.uid):
            return (ref,)
        obj = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(obj, Group):
            return (ref,)
        group_type = str(obj.meta.get("type") or obj.meta.get("TYPE") or "").upper()
        if group_type != "UTTERANCE_CONTENT":
            return (ref,)
        out: list[Ref] = []
        for member in obj.members:
            out.extend(self._content_roots(member))
        return tuple(out)


class SourceScopeActivator:
    """Activate one source's semantic roots through the ordinary Ignition engine."""

    def __init__(
        self,
        core: AHCore,
        ignition: IgnitionEngine,
        resolver: SourceScopeResolver | None = None,
    ) -> None:
        self.core = core
        self.ignition = ignition
        self.resolver = resolver or SourceScopeResolver(core)

    def activate_scope(
        self, scope: SourceScope, *, settle_ticks: int = 1
    ) -> SourceScopeActivation:
        if settle_ticks < 1:
            raise ValueError("settle_ticks must be >= 1")
        seedable = tuple(ref for ref in scope.semantic_roots if ref.kind is not RefKind.L)
        self.ignition.apply_seed_requests(
            tuple(ActivationSeedRequest(ref, SeedReason.QUERY_RECALL) for ref in seedable)
        )
        for _ in range(settle_ticks):
            self.ignition.tick(include_pacemaker=False)
        return SourceScopeActivation(
            source_scope=scope,
            seeded_refs=seedable,
            tick_count=settle_ticks,
            workspace_after=self.ignition.workspace_refs(),
        )

    def activate(self, source_ref: str, *, settle_ticks: int = 1) -> SourceScopeActivation:
        return self.activate_scope(
            self.resolver.resolve(source_ref), settle_ticks=settle_ticks
        )


class SourceScopedContextService:
    """Compose source activation and deterministic AgentContext projection.

    This is a runtime convenience boundary, not a document ontology.  It is useful
    for requests such as article/source summarization: resolve the provenance
    handle, seed only its semantic roots, let ordinary Ignition form Workspace,
    then project only active semantics still inside that source scope.
    """

    def __init__(self, activator: SourceScopeActivator, projector) -> None:
        self.activator = activator
        self.projector = projector

    def build(
        self,
        current_input: str,
        source_ref: str,
        *,
        settle_ticks: int = 1,
        inference_results=(),
        unresolved_goal_diagnostics=(),
        budget_tokens: int | None = None,
    ) -> SourceScopedContextResult:
        activation = self.activator.activate(source_ref, settle_ticks=settle_ticks)
        context = self.projector.project(
            current_input,
            activation.workspace_after,
            tuple(inference_results),
            tuple(unresolved_goal_diagnostics),
            source_scope=activation.source_scope,
            budget_tokens=budget_tokens,
        )
        return SourceScopedContextResult(activation, context)

    def build_source_slice(
        self,
        current_input: str,
        cursor: SourceProjectionCursor,
        *,
        max_primary_roots: int,
        settle_ticks: int = 1,
        inference_results=(),
        unresolved_goal_diagnostics=(),
        budget_tokens: int | None = None,
    ) -> tuple[SourceScopeSlice, SourceScopedContextResult]:
        """Project one bounded AH-only slice and return the next deterministic cursor."""
        sliced = self.activator.resolver.slice(
            cursor, max_primary_roots=max_primary_roots
        )
        activation = self.activator.activate_scope(
            sliced.scope, settle_ticks=settle_ticks
        )
        context = self.projector.project_compact_source(
            current_input,
            sliced.scope,
            tuple(inference_results),
            tuple(unresolved_goal_diagnostics),
            budget_tokens=budget_tokens,
        )
        return sliced, SourceScopedContextResult(activation, context)

    def build_complete_source(
        self,
        current_input: str,
        source_ref: str,
        *,
        settle_ticks: int = 1,
        inference_results=(),
        unresolved_goal_diagnostics=(),
        budget_tokens: int | None = None,
    ) -> SourceScopedContextResult:
        """Build document context from every root in the bounded source index."""
        activation = self.activator.activate(source_ref, settle_ticks=settle_ticks)
        context = self.projector.project_compact_source(
            current_input,
            activation.source_scope,
            tuple(inference_results),
            tuple(unresolved_goal_diagnostics),
            budget_tokens=budget_tokens,
        )
        return SourceScopedContextResult(activation, context)
