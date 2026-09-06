from __future__ import annotations

from dataclasses import dataclass, field
import heapq

from ah.core import AHCore
from ah.model import Domain, Hypernode, RefKind


@dataclass(frozen=True, slots=True)
class GCResult:
    requested: tuple[str, ...]
    protected: tuple[str, ...]
    deleted: tuple[str, ...]
    orphan_deleted: tuple[str, ...]
    reasons: dict[str, str] = field(default_factory=dict)


class GarbageCollector:
    """Normative physical GC with an initial-lifetime guard.

    Two mechanisms coexist deliberately:

    * N lifecycle may nominate a proposition whose NEW/REINFORCED support expired;
    * every newly inserted S/C/P/H element receives the general initial-lifetime
      protection required by the monograph/hackathon.  Once that protection ends,
      detached effective components (no path to a non-isolated S) and genuinely
      lost zero-weight leaves may be removed.

    The birth registry and the heap below are technical runtime/persistence
    metadata, not canonical AH semantics.  Effective-topology traversal uses only
    canonical references and rebuildable indexes.  Inactivity/x is never a deletion
    criterion.
    """

    def __init__(
        self,
        core: AHCore,
        *,
        enabled: bool = True,
        orphan_cleanup: bool = True,
        initial_lifetime_ticks: int = 40,
    ) -> None:
        self.core = core
        self.enabled = enabled
        self.orphan_cleanup = orphan_cleanup
        self.initial_lifetime_ticks = max(1, int(initial_lifetime_ticks))
        self._birth_heap: list[tuple[int, str]] = []
        self._scheduled_birth: dict[str, int] = {}
        self._creation_cursor = 0
        self._rebuild_birth_index()

    def _rebuild_birth_index(self) -> None:
        self._birth_heap.clear()
        self._scheduled_birth.clear()
        for uid, birth in self.core.store.lifetime_birth_items():
            if (
                not self.core.store.has_uid(uid)
                or self.core.store.kind_of(uid) is RefKind.L
                or not self.core.store.is_lifetime_managed(uid)
            ):
                continue
            self._schedule(uid, int(birth))
        self._creation_cursor = len(self.core.store.lifetime_creation_log())

    def _schedule(self, uid: str, birth: int) -> None:
        if not self.core.store.has_uid(uid) or self.core.store.kind_of(uid) is RefKind.L:
            return
        birth = max(0, int(birth))
        self._scheduled_birth[uid] = birth
        heapq.heappush(
            self._birth_heap,
            (birth + self.initial_lifetime_ticks, uid),
        )

    def _sync_new_births(self) -> None:
        log = self.core.store.lifetime_creation_log()
        if self._creation_cursor > len(log):
            # Store replacement/rollback can shorten the technical log.
            self._rebuild_birth_index()
            return
        for uid in log[self._creation_cursor :]:
            if (
                self.core.store.has_uid(uid)
                and self.core.store.kind_of(uid) is not RefKind.L
                and self.core.store.is_lifetime_managed(uid)
            ):
                self._schedule(uid, self.core.store.lifetime_birth_tick(uid))
        self._creation_cursor = len(log)

    def _general_due(self, tick: int) -> set[str]:
        self._sync_new_births()
        due: set[str] = set()
        while self._birth_heap and self._birth_heap[0][0] <= tick:
            expiry, uid = heapq.heappop(self._birth_heap)
            birth = self._scheduled_birth.get(uid)
            if birth is None:
                continue
            if expiry != birth + self.initial_lifetime_ticks:
                continue
            self._scheduled_birth.pop(uid, None)
            if self.core.store.has_uid(uid):
                due.add(uid)
        return due

    def collect(
        self,
        expired_candidates: tuple[str, ...],
        *,
        tick: int | None = None,
    ) -> GCResult:
        requested = set(expired_candidates)
        general_due: set[str] = set()
        if tick is not None:
            general_due = self._general_due(max(0, int(tick)))
            requested.update(general_due)
        requested_tuple = tuple(sorted(requested))
        if not self.enabled or not requested:
            return GCResult(requested_tuple, (), (), (), {})

        protected: set[str] = set()
        deletable: set[str] = set()
        orphan_deleted: set[str] = set()
        reasons: dict[str, str] = {}

        # N lifecycle expiry is an eligibility signal, not an unconditional delete.
        # The v4 architecture keeps the local NEW→REINFORCED→CONSOLIDATED state
        # machine separate from physical forgetting.  Therefore an overdue NEW/N
        # must still pass the same structural/liveness checks as any other GC
        # candidate.  This is especially important for long-lived proof facts:
        # expiry of a technical/consolidation timer does not make an S-anchored
        # proposition garbage.
        lifecycle_due = {
            uid
            for uid in expired_candidates
            if self.core.store.has_uid(uid)
        }

        # Explicitly protected H experience events keep their historical semantics.
        # Other lifecycle candidates are handled together with general structural
        # candidates below, so there is one physical-deletion contract.
        for uid in tuple(sorted(lifecycle_due)):
            if self._is_intrinsically_protected_lifecycle_candidate(uid):
                protected.add(uid)
                lifecycle_due.discard(uid)

        if self.orphan_cleanup:
            processed: set[str] = set()
            structural_due = set(general_due)
            structural_due.update(lifecycle_due)
            for uid in sorted(structural_due):
                if uid in processed or uid in deletable or not self.core.store.has_uid(uid):
                    continue
                component = self._effective_component(uid)
                processed.update(component)
                if not component:
                    continue

                # Established snapshot nodes that predate the current Ignition
                # runtime are not retroactively treated as fresh GC candidates. If
                # a new managed node joins such a component, general GC must not
                # delete the older memory along with it.
                if (
                    uid in general_due
                    and uid not in lifecycle_due
                    and any(not self.core.store.is_lifetime_managed(member) for member in component)
                ):
                    protected.update(component)
                    continue

                # A currently excited detached component is still participating in
                # cognition and therefore is not "lost" yet.  This preserves the
                # existing activation-floor semantics; structural GC is retried only
                # after another initial-lifetime window.  Committee-injected orphan
                # nodes are cold, so this guard does not weaken M3.
                active_component = any(
                    self.core.store.kind_of(member) is not RefKind.L
                    and self.core.store.runtime_state(member).excitation > 0.0
                    for member in component
                    if self.core.store.has_uid(member)
                )
                if active_component:
                    for member in component:
                        if self.core.store.has_uid(member):
                            self._schedule(member, int(tick or 0))
                            protected.add(member)
                    continue

                # A component is anchored only by an S that is actually connected
                # to at least one effective neighbor.  This keeps a newly-added lone
                # S alive during initial lifetime but lets GC remove it afterwards.
                anchored = any(
                    self.core.store.kind_of(member) is RefKind.S
                    and bool(self.core.store.gc_neighbors(member))
                    for member in component
                )
                if not anchored:
                    young = [
                        member
                        for member in component
                        if self._age(member, tick or 0) < self.initial_lifetime_ticks
                    ]
                    if young:
                        # Recheck the whole component when the youngest protection
                        # expires. Older nodes are not repeatedly scanned each tick.
                        retry_birth = min(
                            self.core.store.lifetime_birth_tick(member)
                            for member in young
                        )
                        for member in component:
                            if self.core.store.has_uid(member):
                                self._schedule(member, retry_birth)
                                protected.add(member)
                        continue
                    deletable.update(component)
                    orphan_deleted.update(component)
                    for member in component:
                        reasons.setdefault(member, "DETACHED_FROM_S")
                    continue

                # The component is S-anchored. A mature leaf with no positive L/N
                # support and no structural ownership is nevertheless a lost node.
                if self._zero_weight_leaf(uid):
                    deletable.add(uid)
                    orphan_deleted.add(uid)
                    reasons.setdefault(uid, "ZERO_WEIGHT_LOST")
                else:
                    protected.add(uid)

        # If orphan cleanup is disabled, lifecycle expiry still cannot bypass the
        # physical-GC contract.  It remains protected rather than being deleted by
        # timer alone.
        elif lifecycle_due:
            protected.update(lifecycle_due)

        # Referential closure: a direct structural referrer that is not being
        # removed must keep its target. Detached components above are removed as a
        # whole, so this primarily protects lifecycle-expired N/meta targets.
        changed = True
        while changed:
            changed = False
            for uid in tuple(deletable):
                external_referrers = {
                    ref.uid
                    for ref in self.core.store.structural_referrers(uid)
                    if ref.uid not in deletable and self.core.store.has_uid(ref.uid)
                }
                if external_referrers:
                    deletable.remove(uid)
                    orphan_deleted.discard(uid)
                    protected.add(uid)
                    reasons.pop(uid, None)
                    changed = True

        # Remember surviving topology adjacent to deleted nodes. A later deletion
        # can turn an old, already-mature anchored node into a new orphan; those
        # neighbors must be reconsidered even though their original TTL event was
        # consumed long ago.
        topology_neighbors: set[str] = set()
        for uid in deletable:
            if not self.core.store.has_uid(uid):
                continue
            topology_neighbors.update(self.core.store.gc_neighbors(uid, positive_weight_only=False))
            topology_neighbors.update(ref.uid for ref in self.core.store.structural_referrers(uid))
            topology_neighbors.update(ref.uid for ref in self.core.store.structural_children(uid))
        topology_neighbors.difference_update(deletable)

        self._invalidate_support_metadata(deletable)
        removed = self.core.store._delete_uids(deletable)
        removed_nodes = {
            uid for uid in removed if uid in deletable
        }
        # Incident L are deleted by the store and reported too, with an explicit
        # technical reason. L is not itself an excitable/lifetime candidate.
        for uid in removed - removed_nodes:
            reasons.setdefault(uid, "INCIDENT_TO_DELETED_ENDPOINT")

        self._scheduled_birth = {
            uid: birth
            for uid, birth in self._scheduled_birth.items()
            if self.core.store.has_uid(uid)
        }
        if tick is not None:
            retry_birth = max(0, int(tick) + 1 - self.initial_lifetime_ticks)
            for uid in topology_neighbors:
                if self.core.store.has_uid(uid) and self.core.store.kind_of(uid) is not RefKind.L:
                    self._schedule(uid, retry_birth)

        return GCResult(
            requested_tuple,
            tuple(sorted(protected - set(removed))),
            tuple(sorted(removed)),
            tuple(sorted(orphan_deleted & set(removed))),
            reasons,
        )

    def _age(self, uid: str, tick: int) -> int:
        return max(0, int(tick) - self.core.store.lifetime_birth_tick(uid))

    def _effective_component(self, start_uid: str) -> set[str]:
        if not self.core.store.has_uid(start_uid):
            return set()
        seen: set[str] = set()
        stack = [start_uid]
        while stack:
            uid = stack.pop()
            if uid in seen or not self.core.store.has_uid(uid):
                continue
            if self.core.store.kind_of(uid) is RefKind.L:
                continue
            seen.add(uid)
            for neighbor in self.core.store.gc_neighbors(uid, positive_weight_only=True):
                if neighbor not in seen:
                    stack.append(neighbor)
        return seen

    def _zero_weight_leaf(self, uid: str) -> bool:
        if not self.core.store.has_uid(uid):
            return False
        if self.core.store.has_positive_weighted_support(uid):
            return False
        if self.core.store.structural_referrers(uid):
            return False
        # N owns a template/actants but its own hyperedge weight can be zero; it is
        # safe to delete when no other structure refers to the N itself.
        if self.core.store.kind_of(uid) is RefKind.N:
            try:
                return self.core.store.get_hypernode(uid).weight <= 0
            except (KeyError, TypeError):
                return False
        return not self.core.store.structural_children(uid)

    def _is_intrinsically_protected_lifecycle_candidate(self, uid: str) -> bool:
        # Dialogue turns are experienced history. In ordinary operation they are
        # also S-anchored through their event template, but preserve the explicit
        # guard because a current turn may still be under construction.
        if self.core.store.domain_of(uid) is Domain.H:
            try:
                node = self.core.store.get_hypernode(uid)
            except (KeyError, TypeError):
                node = None
            if node is not None and bool(node.meta.get("event_instance", False)):
                return True

        for link in (
            *self.core.store.outgoing_links(uid, "FOLLOW"),
            *self.core.store.incoming_links(uid, "FOLLOW"),
        ):
            source_domain = self.core.store.domain_of(link.source.uid)
            target_domain = self.core.store.domain_of(link.target.uid)
            if Domain.H in {source_domain, target_domain}:
                return True
        return False

    def _invalidate_support_metadata(self, uids: set[str]) -> None:
        # Support metadata is not canonical topology, but it must not retain
        # dangling dependencies. Independent supports on surviving conclusions are
        # preserved by SupportLedger.invalidate_by_premise.
        for uid in uids:
            self.core.supports.invalidate_by_premise(uid)
            self.core.supports.remove_conclusion(uid)
