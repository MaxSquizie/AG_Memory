from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace
from threading import RLock

from ah.config import IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore
from ah.integration.contracts import ActivationSeedRequest, RefutationRequest, SeedReason
from ah.model import Domain, Hypernode, Link, Ref, RefKind, RuntimeState

from .gc import GCResult, GarbageCollector
from .lifecycle import LifecycleManager, LifecycleTickResult
from .pacemaker import ExcitabilityPacemaker, PacemakerSnapshot
from .policies import ActivationPolicy, DecayPolicy
from .workspace import WorkspaceView


@dataclass(frozen=True, slots=True)
class IgnitionSnapshot:
    tick_index: int
    incoming: dict[str, float]
    seed_reasons: dict[str, tuple[str, ...]]
    pending_refutations: tuple[str, ...] = ()
    pacemaker: PacemakerSnapshot = PacemakerSnapshot()


@dataclass(frozen=True, slots=True)
class PropagationEvent:
    source: Ref
    target: Ref
    via_uid: str
    via_kind: str
    relation: str
    amount: float


@dataclass(frozen=True, slots=True)
class TickResult:
    tick: int
    activation_events: tuple[Ref, ...]
    workspace: tuple[Ref, ...]
    incoming_consumed: dict[str, float]
    outgoing_scheduled: dict[str, float]
    lifecycle: LifecycleTickResult | None = None
    gc: GCResult | None = None
    propagations: tuple[PropagationEvent, ...] = ()


class IgnitionEngine:
    """Synchronous excitation/decay/plasticity/lifecycle engine.

    Canonical ordering follows Архитектура_v3:
      collect z → f/output → propagate → h → g → lifecycle/GC → Workspace → commit view.

    A fresh excitation/reactivation tick does not apply g immediately. L has no x;
    it only transmits source output through its weight.
    """

    def __init__(
        self,
        core: AHCore,
        ignition: IgnitionSettings,
        workspace: WorkspaceSettings,
        lifecycle: LifecycleSettings | None = None,
    ) -> None:
        self.core = core
        self.settings = ignition
        self.workspace_settings = workspace
        self.lifecycle_settings = lifecycle or LifecycleSettings()
        self.activation = ActivationPolicy(ignition.activation, ignition.x_max)
        self.decay = DecayPolicy(ignition.decay)
        self.lifecycle = LifecycleManager(core, self.lifecycle_settings)
        self.pacemaker = ExcitabilityPacemaker(
            core,
            ignition.pacemaker,
            nu=ignition.nu,
            tick_interval_seconds=ignition.tick_interval_seconds,
            pulse_amount=ignition.seeds.pacemaker,
        )
        self.gc = GarbageCollector(
            core,
            enabled=self.lifecycle_settings.gc_enabled,
            orphan_cleanup=self.lifecycle_settings.orphan_cleanup,
        )
        self.tick_index = 0
        self._incoming: dict[str, float] = defaultdict(float)
        self._seed_reasons: dict[str, list[SeedReason]] = defaultdict(list)
        self._pending_refutations: set[str] = set()
        self._lock = RLock()

    def reconfigure(
        self,
        ignition: IgnitionSettings,
        workspace: WorkspaceSettings,
        lifecycle: LifecycleSettings,
    ) -> None:
        """Apply hot-safe runtime parameters without touching canonical/runtime memory state.

        Tick semantics stay identical; only policy objects/configurable coefficients are
        replaced between ticks. Pacemaker phase/cursor are preserved.
        """
        with self._lock:
            pacemaker_snapshot = self.pacemaker.snapshot()
            self.settings = ignition
            self.workspace_settings = workspace
            self.lifecycle_settings = lifecycle
            self.activation = ActivationPolicy(ignition.activation, ignition.x_max)
            self.decay = DecayPolicy(ignition.decay)
            self.lifecycle = LifecycleManager(self.core, lifecycle)
            self.pacemaker = ExcitabilityPacemaker(
                self.core,
                ignition.pacemaker,
                nu=ignition.nu,
                tick_interval_seconds=ignition.tick_interval_seconds,
                pulse_amount=ignition.seeds.pacemaker,
            )
            self.pacemaker.restore(pacemaker_snapshot)
            self.gc = GarbageCollector(
                self.core,
                enabled=lifecycle.gc_enabled,
                orphan_cleanup=lifecycle.orphan_cleanup,
            )

    def _seed_amount(self, reason: SeedReason) -> float:
        seeds = self.settings.seeds
        if reason is SeedReason.NEW_FACT:
            return seeds.new_fact
        if reason is SeedReason.REACTIVATED_FACT:
            return seeds.reactivated_fact
        if reason is SeedReason.EXPERIENCE:
            return seeds.experience
        if reason is SeedReason.SENSORY_SYMBOL:
            return seeds.sensory_symbol
        if reason is SeedReason.CORRECTION:
            return seeds.correction
        if reason is SeedReason.PACEMAKER:
            return seeds.pacemaker
        raise ValueError(f"Unhandled seed reason: {reason}")

    def seed(self, ref: Ref, amount: float, *, reason: SeedReason | None = None) -> None:
        with self._lock:
            if not self.core.store.has_uid(ref.uid):
                raise KeyError(ref.uid)
            if ref.kind is RefKind.L:
                raise ValueError("L has no excitation state and cannot be seeded")
            if amount < 0:
                raise ValueError("Seed amount must be >= 0")
            self._incoming[ref.uid] += amount
            if reason is not None:
                self._seed_reasons[ref.uid].append(reason)

    def apply_seed_requests(self, requests: tuple[ActivationSeedRequest, ...]) -> None:
        for request in requests:
            self.seed(request.ref, self._seed_amount(request.reason), reason=request.reason)

    def apply_refutation_requests(self, requests: tuple[RefutationRequest, ...]) -> None:
        with self._lock:
            for request in requests:
                if not self.core.store.has_uid(request.target.uid):
                    raise KeyError(request.target.uid)
                if request.target.kind is not RefKind.N:
                    raise ValueError("Refutation target must be N")
                self._pending_refutations.add(request.target.uid)

    def begin_prompt_epoch(self) -> None:
        """Start a fresh decay epoch from current x without changing excitation."""
        with self._lock:
            new_states = {uid: deepcopy(state) for uid, state in self.core.store.runtime_items()}
            for state in new_states.values():
                if state.excitation > 0:
                    state.decay_age = 0
                    state.decay_origin_excitation = state.excitation
            self.core.store._replace_runtime_states(new_states)

    def workspace_refs(self) -> tuple[Ref, ...]:
        with self._lock:
            return WorkspaceView(self.core, self.workspace_settings.threshold).refs()

    def export_snapshot(self, *, include_pending: bool = True) -> IgnitionSnapshot:
        with self._lock:
            incoming = dict(self._incoming) if include_pending else {}
            reasons = (
                {uid: tuple(reason.value for reason in values) for uid, values in self._seed_reasons.items()}
                if include_pending
                else {}
            )
            return IgnitionSnapshot(
                self.tick_index,
                incoming,
                reasons,
                tuple(sorted(self._pending_refutations)) if include_pending else (),
                self.pacemaker.snapshot(),
            )

    def restore_snapshot(self, snapshot: IgnitionSnapshot) -> None:
        with self._lock:
            self.tick_index = max(0, int(snapshot.tick_index))
            self._incoming = defaultdict(
                float,
                {
                    uid: float(amount)
                    for uid, amount in snapshot.incoming.items()
                    if self.core.store.has_uid(uid) and self.core.store.kind_of(uid) is not RefKind.L
                },
            )
            restored: dict[str, list[SeedReason]] = defaultdict(list)
            for uid, raw_values in snapshot.seed_reasons.items():
                if not self.core.store.has_uid(uid):
                    continue
                for raw in raw_values:
                    try:
                        restored[uid].append(SeedReason(raw))
                    except ValueError:
                        continue
            self._seed_reasons = restored
            self._pending_refutations = {
                uid for uid in snapshot.pending_refutations
                if self.core.store.has_uid(uid) and self.core.store.kind_of(uid) is RefKind.N
            }
            self.pacemaker.restore(snapshot.pacemaker)

    def tick(self) -> TickResult:
        with self._lock:
            return self._tick_locked()

    def _tick_locked(self) -> TickResult:
        tick = self.tick_index
        snapshot = {uid: deepcopy(state) for uid, state in self.core.store.runtime_items()}
        incoming = dict(self._incoming)
        seed_reasons_mut = {uid: list(values) for uid, values in self._seed_reasons.items()}

        # Pacemaker is an internal stimulus scheduled on the same tick clock. It is
        # explicitly marked so h_N does not mistake it for external confirmation.
        workspace_before = WorkspaceView(self.core, self.workspace_settings.threshold).refs()
        for pulse in self.pacemaker.pulses_for_tick(workspace_before):
            incoming[pulse.ref.uid] = incoming.get(pulse.ref.uid, 0.0) + pulse.amount
            seed_reasons_mut.setdefault(pulse.ref.uid, []).append(SeedReason.PACEMAKER)

        seed_reasons = {uid: tuple(values) for uid, values in seed_reasons_mut.items()}
        refutations = set(self._pending_refutations)
        self._incoming = defaultdict(float)
        self._seed_reasons = defaultdict(list)
        self._pending_refutations = set()

        next_states = {uid: deepcopy(state) for uid, state in snapshot.items()}
        outputs: dict[str, float] = {}
        activation_uids: set[str] = set()
        eps = self.settings.activation.epsilon

        # PHASE 1/2 — collect z and compute f(x,z), output, activation event.
        for uid, before in snapshot.items():
            z = float(incoming.get(uid, 0.0))
            is_active_or_stimulated = before.excitation > eps or z > eps
            after = next_states[uid]
            after.activation_event = False
            after.output = 0.0

            if not is_active_or_stimulated:
                continue

            x_raw = self.activation.raw(before.excitation, z)
            x_after_f = self.activation.clamp(x_raw)
            output = x_after_f
            # Architecture_v3 compares reactivation strength before clamp so x_max
            # saturation cannot hide a strong incoming stimulus.
            input_gain = max(0.0, x_raw - before.excitation)
            activation_event = z > eps and input_gain > eps
            first_excitation = before.first_excitation_tick is None and activation_event

            after.output = output
            after.last_output_tick = tick
            outputs[uid] = output

            if activation_event:
                after.activation_event = True
                after.last_activation_tick = tick
                activation_uids.add(uid)

            # PHASE 5 — fresh/reset activation has no g on that same tick.
            if first_excitation:
                after.excitation = x_after_f
                after.first_excitation_tick = tick
                after.decay_age = 0
                after.decay_origin_excitation = x_after_f
                continue

            expected_loss = self.decay.expected_loss(before.excitation, before.decay_age)
            reset_threshold = expected_loss * self.settings.decay.reactivation_reset_ratio
            reset_epoch = activation_event and input_gain > reset_threshold

            if reset_epoch:
                after.excitation = x_after_f
                after.decay_age = 0
                after.decay_origin_excitation = x_after_f
            else:
                factor = self.decay.step_factor(before.decay_age)
                after.excitation = max(0.0, min(self.settings.x_max, x_after_f * factor))
                after.decay_age = before.decay_age + 1
                if after.decay_origin_excitation <= 0:
                    after.decay_origin_excitation = before.excitation

        # PHASE 3 — this tick's f output propagates only into next tick's buffer.
        scheduled: dict[str, float] = defaultdict(float)
        propagations: list[PropagationEvent] = []
        for link in self.core.store.links():
            source_output = outputs.get(link.source.uid, 0.0)
            if source_output > eps and link.weight > 0:
                amount = source_output * link.weight
                scheduled[link.target.uid] += amount
                propagations.append(
                    PropagationEvent(
                        source=link.source,
                        target=link.target,
                        via_uid=link.uid,
                        via_kind="L",
                        relation=link.relation_id,
                        amount=amount,
                    )
                )

        for domain in Domain:
            for element in self.core.store.elements(domain):
                if not isinstance(element, Hypernode):
                    continue
                source_output = outputs.get(element.uid, 0.0)
                if source_output <= eps or element.weight <= 0:
                    continue
                impulse = source_output * element.weight
                for role, ref in element.actants.items():
                    scheduled[ref.uid] += impulse
                    propagations.append(
                        PropagationEvent(
                            source=self.core.ref(element.uid),
                            target=ref,
                            via_uid=element.uid,
                            via_kind="N",
                            relation=role.value,
                            amount=impulse,
                        )
                    )

        # PHASE 4 — h uses association-relevant activation events from this tick
        # and old weights. Pure pacemaker stimulation is excitability noise, not
        # associative experience; otherwise a background ν pulse would slowly
        # depress arbitrary incident links even while the agent experiences nothing.
        link_updates: list[Link] = []
        plasticity = self.settings.plasticity
        plasticity_activation_uids = set(activation_uids)
        if plasticity.ignore_pacemaker_only_events:
            for uid in tuple(plasticity_activation_uids):
                reasons = seed_reasons.get(uid, ())
                if reasons and all(reason is SeedReason.PACEMAKER for reason in reasons):
                    plasticity_activation_uids.discard(uid)

        if plasticity.enabled:
            for link in self.core.store.links():
                a = link.source.uid in plasticity_activation_uids
                b = link.target.uid in plasticity_activation_uids
                new_weight = link.weight
                if a and b:
                    new_weight = min(1.0, link.weight + plasticity.link_hebb_increment)
                elif a ^ b:
                    new_weight = max(
                        plasticity.link_weight_floor,
                        link.weight - plasticity.link_async_decrement,
                    )
                if new_weight != link.weight:
                    link_updates.append(replace(link, weight=new_weight))

        hypernode_updates: list[tuple[Domain, Hypernode]] = []
        if plasticity.enabled:
            pending_by_uid: dict[str, tuple[Domain, Hypernode]] = {}
            for uid, reasons in seed_reasons.items():
                if uid not in activation_uids or not self.core.store.has_uid(uid):
                    continue
                if self.core.store.kind_of(uid) is not RefKind.N:
                    continue
                if SeedReason.REACTIVATED_FACT not in reasons:
                    continue
                domain = self.core.store.domain_of(uid)
                if domain is None:
                    continue
                node = self.core.store.get_hypernode(uid)
                new_weight = min(1.0, node.weight + plasticity.hypernode_confirmation_increment)
                if new_weight != node.weight:
                    pending_by_uid[uid] = (domain, replace(node, weight=new_weight))

            # Explicit FALSE(N) is a semantic refutation event. It has priority over
            # same-tick confirmation: confirmation for the refuted N is ignored on
            # this tick, then the strong h_N correction is applied to the old weight.
            # N_old is preserved and w is still association strength, not truth.
            for uid in refutations:
                if not self.core.store.has_uid(uid) or self.core.store.kind_of(uid) is not RefKind.N:
                    continue
                domain = self.core.store.domain_of(uid)
                if domain is None:
                    continue
                node = self.core.store.get_hypernode(uid)
                new_weight = max(0.0, node.weight - plasticity.hypernode_refutation_decrement)
                if new_weight != node.weight:
                    pending_by_uid[uid] = (domain, replace(node, weight=new_weight))
                else:
                    pending_by_uid.pop(uid, None)
            hypernode_updates.extend(pending_by_uid.values())

        # Begin simultaneous commit: runtime and weights become the current state.
        self.core.store._replace_runtime_states(next_states)
        for link in link_updates:
            self.core.store._replace_link(link)
        for domain, node in hypernode_updates:
            # Preserve lifecycle/meta changes only happen after this point.
            self.core.store._replace_hypernode(domain, node)

        # PHASE 6 — lifecycle + GC decisions on committed activation events.
        lifecycle_result = self.lifecycle.tick(
            tick=tick,
            activation_uids=activation_uids,
            seed_reasons=seed_reasons,
        )
        gc_result = self.gc.collect(lifecycle_result.expired_candidates)

        # Swap next incoming buffer, dropping impulses whose target was GC'd.
        for uid, amount in scheduled.items():
            if self.core.store.has_uid(uid) and self.core.store.kind_of(uid) is not RefKind.L:
                self._incoming[uid] += amount

        # PHASE 7 — Workspace is exactly committed x > t after GC.
        workspace = WorkspaceView(self.core, self.workspace_settings.threshold).refs()
        activation_refs = tuple(
            sorted(
                (self.core.ref(uid) for uid in activation_uids if self.core.store.has_uid(uid)),
                key=lambda r: r.uid,
            )
        )
        result = TickResult(
            tick=tick,
            activation_events=activation_refs,
            workspace=workspace,
            incoming_consumed=incoming,
            outgoing_scheduled={uid: amount for uid, amount in scheduled.items() if self.core.store.has_uid(uid)},
            lifecycle=lifecycle_result,
            gc=gc_result,
            propagations=tuple(propagations),
        )
        self.tick_index += 1
        return result
