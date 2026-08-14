from __future__ import annotations

from dataclasses import dataclass
import random

from ah.config import PacemakerSettings
from ah.core import AHCore
from ah.model import Domain, Ref, RefKind


@dataclass(frozen=True, slots=True)
class PacemakerSnapshot:
    phase: float = 0.0
    cursor: int = 0
    pulse_count: int = 0


@dataclass(frozen=True, slots=True)
class PacemakerPulse:
    ref: Ref
    amount: float


class ExcitabilityPacemaker:
    """Periodic internal stimulation driven by ν on the engine tick clock.

    The monograph leaves target selection implementation-specific (random or a
    criterion). We make that choice explicit in config. The default round-robin
    policy is deterministic and therefore reproducible in tests/demos.
    """

    def __init__(
        self,
        core: AHCore,
        settings: PacemakerSettings,
        *,
        nu: float,
        tick_interval_seconds: float,
        pulse_amount: float,
    ) -> None:
        self.core = core
        self.settings = settings
        self.nu = float(nu)
        self.tick_interval_seconds = float(tick_interval_seconds)
        self.pulse_amount = float(pulse_amount)
        self.phase = 0.0
        self.cursor = 0
        self.pulse_count = 0

    def snapshot(self) -> PacemakerSnapshot:
        return PacemakerSnapshot(self.phase, self.cursor, self.pulse_count)

    def restore(self, snapshot: PacemakerSnapshot) -> None:
        self.phase = max(0.0, float(snapshot.phase))
        self.cursor = max(0, int(snapshot.cursor))
        self.pulse_count = max(0, int(snapshot.pulse_count))

    def pulses_for_tick(self, workspace: tuple[Ref, ...] = ()) -> tuple[PacemakerPulse, ...]:
        if not self.settings.enabled or self.nu <= 0 or self.pulse_amount <= 0:
            return ()

        self.phase += self.nu * self.tick_interval_seconds
        count = int(self.phase)
        if count <= 0:
            return ()
        self.phase -= count

        pulses: list[PacemakerPulse] = []
        for _ in range(count):
            target = self._choose_target(workspace)
            if target is not None:
                pulses.append(PacemakerPulse(target, self.pulse_amount))
                self.pulse_count += 1
        return tuple(pulses)

    def _eligible(self) -> tuple[Ref, ...]:
        refs: list[Ref] = []
        if self.settings.include_symbols:
            for uid in sorted(self.core.store._state.symbols):
                refs.append(Ref(uid, RefKind.S))
        allowed = {Domain(raw) for raw in self.settings.domains}
        for domain in Domain:
            if domain not in allowed:
                continue
            for element in sorted(self.core.store.elements(domain), key=lambda e: e.uid):
                refs.append(self.core.ref(element.uid))
        return tuple(refs)

    def _choose_target(self, workspace: tuple[Ref, ...]) -> Ref | None:
        policy = self.settings.target_policy
        if policy == "workspace":
            eligible = tuple(ref for ref in workspace if ref.kind is not RefKind.L)
        elif policy == "active":
            eligible = tuple(
                Ref(uid, self.core.store.kind_of(uid))
                for uid, state in self.core.store.runtime_items()
                if state.excitation > 0 and self.core.store.kind_of(uid) is not RefKind.L
            )
        else:
            eligible = self._eligible()

        if not eligible:
            return None

        eligible = tuple(sorted(eligible, key=lambda r: r.uid))
        if policy == "random":
            rng = random.Random(self.settings.random_seed + self.pulse_count)
            return rng.choice(eligible)

        # workspace/active are also round-robin across their current candidate set.
        target = eligible[self.cursor % len(eligible)]
        self.cursor = (self.cursor + 1) % max(1, len(eligible))
        return target
