from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

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
    """N-only consolidation/lifetime policy.

    Machine lifecycle fields live in N.Mt/meta. Initial creation is not counted as
    a qualifying reactivation; later activation/reactivation events may advance the
    state if the configured spacing has elapsed.
    """

    META_STAGE = "lifecycle_state"
    META_CREATED = "created_tick"
    META_EXPIRES = "expires_tick"
    META_LAST_QUALIFY = "last_qualifying_tick"
    META_QUALIFY_COUNT = "qualifying_reactivations"

    def __init__(self, core: AHCore, settings: LifecycleSettings) -> None:
        self.core = core
        self.settings = settings

    def tick(
        self,
        *,
        tick: int,
        activation_uids: set[str],
        seed_reasons: dict[str, tuple[SeedReason, ...]],
    ) -> LifecycleTickResult:
        updates: list[LifecycleUpdate] = []
        expired: list[str] = []

        for domain in Domain:
            for element in tuple(self.core.store.elements(domain)):
                if not isinstance(element, Hypernode):
                    continue
                meta = dict(element.meta)
                before_stage = self._stage(meta)
                reasons = seed_reasons.get(element.uid, ())
                just_created = SeedReason.NEW_FACT in reasons and before_stage is None

                if before_stage is None:
                    # Lifecycle begins when a fact first participates in cognitive
                    # runtime. Static fixtures can opt out by setting no lifecycle Mt.
                    if not (just_created or element.uid in activation_uids):
                        continue
                    meta[self.META_STAGE] = LifecycleStage.NEW.value
                    meta[self.META_CREATED] = tick
                    meta[self.META_EXPIRES] = tick + self.settings.initial_lifetime_ticks
                    meta[self.META_LAST_QUALIFY] = tick
                    meta[self.META_QUALIFY_COUNT] = 0
                    after_stage = LifecycleStage.NEW
                else:
                    after_stage = before_stage
                    if element.uid in activation_uids and not just_created:
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
                    self.core.store._replace_hypernode(domain, replace(element, meta=meta))
                    updates.append(LifecycleUpdate(element.uid, before_stage, after_stage))

                current_stage = self._stage(meta)
                expires = meta.get(self.META_EXPIRES)
                if (
                    current_stage in {LifecycleStage.NEW, LifecycleStage.REINFORCED}
                    and expires is not None
                    and tick >= int(expires)
                ):
                    expired.append(element.uid)

        return LifecycleTickResult(tuple(updates), tuple(sorted(set(expired))))

    @classmethod
    def _stage(cls, meta: dict) -> LifecycleStage | None:
        raw = meta.get(cls.META_STAGE)
        if raw is None:
            return None
        try:
            return LifecycleStage(str(raw))
        except ValueError:
            return None
