from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import heapq

from ah.config import LifecycleSettings
from ah.core import AHCore
from ah.integration.contracts import SeedReason
from ah.model import Domain, Hypernode, RefKind


class LifecycleStage(str, Enum):
    NEW = "NEW"
    REINFORCED = "REINFORCED"
    CONSOLIDATED = "CONSOLIDATED"


@dataclass(frozen=True, slots=True)
class LifecycleUpdate:
    uid: str
    before: LifecycleStage | None
    after: LifecycleStage


@dataclass(frozen=True, slots=True)
class LifecycleTickResult:
    updates: tuple[LifecycleUpdate, ...]
    expired_candidates: tuple[str, ...]


class LifecycleManager:
    """N-only consolidation/lifetime policy with sparse per-tick work.

    A lifecycle transition can happen only to an N that has a semantic activation
    event on the current tick. TTL expiry is the only time-driven transition that
    must happen without activation, so expirations are indexed in a min-heap.
    Cold unrelated AH elements are never rescanned on every Ignition tick.

    The heap/index are derived runtime structures. They are rebuilt once from the
    canonical AH when the manager is created, so persistence/restart semantics stay
    identical to the previous full-store implementation.
    """

    META_STAGE = "lifecycle_state"
    META_CREATED = "created_tick"
    META_EXPIRES = "expires_tick"
    META_LAST_QUALIFY = "last_qualifying_tick"
    META_QUALIFY_COUNT = "qualifying_reactivations"

    def __init__(self, core: AHCore, settings: LifecycleSettings) -> None:
        self.core = core
        self.settings = settings
        self._expiry_by_uid: dict[str, int] = {}
        self._expiry_heap: list[tuple[int, str]] = []
        self._overdue: set[str] = set()
        self._rebuild_expiry_index()

    def _rebuild_expiry_index(self) -> None:
        """Rebuild derived TTL index once from persisted canonical N metadata."""
        self._expiry_by_uid.clear()
        self._expiry_heap.clear()
        self._overdue.clear()
        for domain in Domain:
            for element in self.core.store.elements(domain):
                if not isinstance(element, Hypernode):
                    continue
                meta = dict(element.meta)
                stage = self._stage(meta)
                expires = meta.get(self.META_EXPIRES)
                if stage in {LifecycleStage.NEW, LifecycleStage.REINFORCED} and expires is not None:
                    self._schedule_expiry(element.uid, int(expires))

    def _schedule_expiry(self, uid: str, expires_tick: int) -> None:
        expires_tick = int(expires_tick)
        self._expiry_by_uid[uid] = expires_tick
        heapq.heappush(self._expiry_heap, (expires_tick, uid))
        self._overdue.discard(uid)

    def _untrack_expiry(self, uid: str) -> None:
        self._expiry_by_uid.pop(uid, None)
        self._overdue.discard(uid)
        # Stale heap entries are discarded lazily when they reach the heap head.

    def _collect_due(self, tick: int) -> None:
        while self._expiry_heap and self._expiry_heap[0][0] <= tick:
            expires, uid = heapq.heappop(self._expiry_heap)
            if self._expiry_by_uid.get(uid) != expires:
                continue
            if not self.core.store.has_uid(uid):
                self._untrack_expiry(uid)
                continue
            try:
                node = self.core.store.get_hypernode(uid)
            except (KeyError, TypeError):
                self._untrack_expiry(uid)
                continue
            meta = dict(node.meta)
            stage = self._stage(meta)
            current_expires = meta.get(self.META_EXPIRES)
            if (
                stage not in {LifecycleStage.NEW, LifecycleStage.REINFORCED}
                or current_expires is None
            ):
                self._untrack_expiry(uid)
                continue
            current_expires = int(current_expires)
            if current_expires != expires:
                self._schedule_expiry(uid, current_expires)
                continue
            self._overdue.add(uid)

    def tick(
        self,
        *,
        tick: int,
        activation_uids: set[str],
        seed_reasons: dict[str, tuple[SeedReason, ...]],
    ) -> LifecycleTickResult:
        updates: list[LifecycleUpdate] = []

        # Only current semantic participants can create/advance lifecycle state.
        candidates = set(activation_uids)
        candidates.update(seed_reasons)
        for uid in sorted(candidates):
            if not self.core.store.has_uid(uid):
                self._untrack_expiry(uid)
                continue
            try:
                element = self.core.store.get_hypernode(uid)
            except (KeyError, TypeError):
                continue

            domain = self.core.store.domain_of(uid)
            if domain is None:
                continue
            meta = dict(element.meta)
            before_stage = self._stage(meta)
            reasons = seed_reasons.get(uid, ())
            just_created = SeedReason.NEW_FACT in reasons and before_stage is None
            pacemaker_only = bool(reasons) and all(
                reason is SeedReason.PACEMAKER for reason in reasons
            )
            qualifying_activation = uid in activation_uids and not pacemaker_only

            if before_stage is None:
                # The consolidation lifecycle belongs to *newly perceived facts*.
                # Merely recalling/focusing an established proposition for proof or
                # association must not retroactively classify it as NEW and start a
                # forgetting deadline.  General initial-lifetime/structural GC is a
                # separate mechanism and already covers canonical insertions after
                # Ignition starts.
                #
                # In particular QUERY_RECALL is attention, not a new observation.
                # A fact enters this state machine only through the explicit
                # NEW_FACT seed emitted by integration.
                if not just_created:
                    continue
                meta[self.META_STAGE] = LifecycleStage.NEW.value
                meta[self.META_CREATED] = tick
                meta[self.META_EXPIRES] = tick + self.settings.initial_lifetime_ticks
                meta[self.META_LAST_QUALIFY] = tick
                meta[self.META_QUALIFY_COUNT] = 0
                after_stage = LifecycleStage.NEW
            else:
                after_stage = before_stage
                if qualifying_activation and not just_created:
                    last = int(meta.get(self.META_LAST_QUALIFY, meta.get(self.META_CREATED, tick)))
                    required = (
                        self.settings.min_spacing_1_ticks
                        if before_stage is LifecycleStage.NEW
                        else self.settings.min_spacing_2_ticks
                    )
                    if before_stage is not LifecycleStage.CONSOLIDATED and tick - last >= required:
                        if before_stage is LifecycleStage.NEW:
                            after_stage = LifecycleStage.REINFORCED
                            meta[self.META_STAGE] = after_stage.value
                            meta[self.META_EXPIRES] = tick + self.settings.reinforced_lifetime_ticks
                        elif before_stage is LifecycleStage.REINFORCED:
                            after_stage = LifecycleStage.CONSOLIDATED
                            meta[self.META_STAGE] = after_stage.value
                            meta.pop(self.META_EXPIRES, None)
                        meta[self.META_LAST_QUALIFY] = tick
                        meta[self.META_QUALIFY_COUNT] = int(meta.get(self.META_QUALIFY_COUNT, 0)) + 1

            if meta != dict(element.meta):
                element = replace(element, meta=meta)
                self.core.store._replace_hypernode(domain, element)
                updates.append(LifecycleUpdate(uid, before_stage, after_stage))

            current_stage = self._stage(meta)
            expires = meta.get(self.META_EXPIRES)
            if current_stage in {LifecycleStage.NEW, LifecycleStage.REINFORCED} and expires is not None:
                expires_i = int(expires)
                if self._expiry_by_uid.get(uid) != expires_i:
                    self._schedule_expiry(uid, expires_i)
            else:
                self._untrack_expiry(uid)

        # Time-only work is O(number of newly-due/overdue N), never O(|AH|).
        self._collect_due(tick)
        expired: list[str] = []
        for uid in tuple(self._overdue):
            if not self.core.store.has_uid(uid):
                self._untrack_expiry(uid)
                continue
            expires = self._expiry_by_uid.get(uid)
            if expires is None or tick < expires:
                self._overdue.discard(uid)
                continue
            expired.append(uid)

        return LifecycleTickResult(tuple(updates), tuple(sorted(expired)))

    @classmethod
    def _stage(cls, meta: dict) -> LifecycleStage | None:
        raw = meta.get(cls.META_STAGE)
        if raw is None:
            return None
        try:
            return LifecycleStage(str(raw))
        except ValueError:
            return None
