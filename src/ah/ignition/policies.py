from __future__ import annotations

from math import exp, log
from typing import Callable

from ah.config import ActivationSettings, DecaySettings, PlasticitySettings


ActivationRawFn = Callable[[float, float, ActivationSettings, float], float]
DecayMultiplierFn = Callable[[int | float, DecaySettings], float]


def _activation_additive_clamp(x: float, z: float, settings: ActivationSettings, x_max: float) -> float:
    del x_max
    return x + settings.gain * z


def _activation_saturating_additive(x: float, z: float, settings: ActivationSettings, x_max: float) -> float:
    """Add input with less gain near saturation, then the common clamp is applied.

    f(x,z) = x + gain*z*(1 - x/x_max)

    This is useful for experiments with recurrent excitation because incoming
    impulses have progressively less effect near x_max without moving decay into f.
    """
    if x_max <= 0:
        return x
    headroom = max(0.0, 1.0 - (x / x_max))
    return x + settings.gain * z * headroom


ACTIVATION_FUNCTIONS: dict[str, ActivationRawFn] = {
    "additive_clamp": _activation_additive_clamp,
    "saturating_additive": _activation_saturating_additive,
}


def _sigmoid_base(age: int | float, settings: DecaySettings) -> float:
    return 1.0 / (1.0 + exp(settings.steepness * (float(age) - settings.midpoint_ticks)))


def _decay_sigmoid_epoch(age: int | float, settings: DecaySettings) -> float:
    d0 = _sigmoid_base(0.0, settings)
    return settings.alpha + (1.0 - settings.alpha) * (_sigmoid_base(age, settings) / d0)


def _decay_exponential_epoch(age: int | float, settings: DecaySettings) -> float:
    """Epoch decay with D(0)=1 and configured half-life.

    D(age) = alpha + (1-alpha) * 2^(-age/half_life_ticks)
    """
    return settings.alpha + (1.0 - settings.alpha) * exp(
        -log(2.0) * float(age) / settings.half_life_ticks
    )


def _transient_sigmoid_epoch(age: int | float, settings: DecaySettings) -> float:
    return _sigmoid_base(age, settings) / _sigmoid_base(0.0, settings)


def _transient_exponential_epoch(age: int | float, settings: DecaySettings) -> float:
    return exp(-log(2.0) * float(age) / settings.half_life_ticks)


DECAY_FUNCTIONS: dict[str, DecayMultiplierFn] = {
    "sigmoid_epoch": _decay_sigmoid_epoch,
    "exponential_epoch": _decay_exponential_epoch,
}

DECAY_TRANSIENT_FUNCTIONS: dict[str, DecayMultiplierFn] = {
    "sigmoid_epoch": _transient_sigmoid_epoch,
    "exponential_epoch": _transient_exponential_epoch,
}


class ActivationPolicy:
    def __init__(self, settings: ActivationSettings, x_max: float) -> None:
        self.settings = settings
        self.x_max = x_max
        try:
            self._raw_fn = ACTIVATION_FUNCTIONS[settings.kind]
        except KeyError as exc:
            supported = ", ".join(sorted(ACTIVATION_FUNCTIONS))
            raise ValueError(f"Unsupported activation kind: {settings.kind}; supported: {supported}") from exc

    def raw(self, x: float, z: float) -> float:
        return self._raw_fn(x, z, self.settings, self.x_max)

    def clamp(self, value: float) -> float:
        return min(self.x_max, max(0.0, value))

    def apply(self, x: float, z: float) -> float:
        return self.clamp(self.raw(x, z))


class DecayPolicy:
    def __init__(self, settings: DecaySettings) -> None:
        self.settings = settings
        try:
            self._multiplier_fn = DECAY_FUNCTIONS[settings.kind]
            self._transient_fn = DECAY_TRANSIENT_FUNCTIONS[settings.kind]
        except KeyError as exc:
            supported = ", ".join(sorted(DECAY_FUNCTIONS))
            raise ValueError(f"Unsupported decay kind: {settings.kind}; supported: {supported}") from exc

    def multiplier(self, age: int) -> float:
        """D(age): D(0)=1, monotone for built-in policies, tends to alpha."""
        return max(0.0, min(1.0, self._multiplier_fn(age, self.settings)))

    def transient_multiplier(self, age: int) -> float:
        """Decay multiplier for excitation *above* the epoch-local floor.

        Built-in D(age) includes the asymptotic floor ``alpha``. For runtime
        decay we keep that floor as retained activation and decay only the
        transient excess above it. This prevents weak input from silently
        raising the floor while still letting that input affect x.
        """
        # Compute the transient curve directly rather than subtracting alpha from
        # D(age). At a long tail D and alpha can be indistinguishable in float
        # precision even though the transient still has a meaningful step ratio.
        return max(0.0, min(1.0, self._transient_fn(age, self.settings)))

    def transient_step_factor(self, age: int) -> float:
        """Ratio R(age+1)/R(age) for the transient component above floor."""
        current = self.transient_multiplier(age)
        nxt = self.transient_multiplier(age + 1)
        if current <= 0:
            return 0.0
        return max(0.0, min(1.0, nxt / current))

    def floor(self, origin: float, *, current: float | None = None) -> float:
        """Epoch-local retained activation floor ``alpha * origin``.

        Hot-increasing alpha must never create excitation from configuration
        alone, so an optional current value caps the effective floor. New prompt
        epochs and strong reactivations naturally establish a fresh origin.
        """
        value = max(0.0, origin) * self.settings.alpha
        if current is not None:
            value = min(value, max(0.0, current))
        return value

    def apply(self, x: float, origin: float, age: int) -> float:
        """Decay current excitation toward the fixed epoch-local floor.

        Weak inputs add to ``x`` but do not change ``origin``. Their excess is
        therefore transient and continues decaying toward the same floor.
        """
        floor = self.floor(origin, current=x)
        excess = max(0.0, x - floor)
        return floor + excess * self.transient_step_factor(age)

    def expected_loss(self, x: float, origin: float, age: int) -> float:
        return max(0.0, x - self.apply(x, origin, age))

    # Compatibility helper for diagnostics/tests that inspect the old total-D
    # ratio directly. Runtime decay uses transient_step_factor/apply instead.
    def step_factor(self, age: int) -> float:
        current = self.multiplier(age)
        nxt = self.multiplier(age + 1)
        if current <= 0:
            return 0.0
        return max(0.0, min(1.0, nxt / current))


class PlasticityPolicy:
    """Config-selected h_L/h_N weight update policies.

    Plasticity decides pending weights only. The engine still owns event timing,
    pacemaker provenance filtering, semantic confirmation/refutation detection and
    simultaneous commit.
    """

    LINK_KINDS = {"additive_hebb"}
    HYPERNODE_KINDS = {"additive_confirmation_refutation"}

    def __init__(self, settings: PlasticitySettings) -> None:
        self.settings = settings
        if settings.link_kind not in self.LINK_KINDS:
            raise ValueError(
                f"Unsupported h_L kind: {settings.link_kind}; supported: {', '.join(sorted(self.LINK_KINDS))}"
            )
        if settings.hypernode_kind not in self.HYPERNODE_KINDS:
            raise ValueError(
                "Unsupported h_N kind: "
                f"{settings.hypernode_kind}; supported: {', '.join(sorted(self.HYPERNODE_KINDS))}"
            )

    def link_weight(self, weight: float, *, source_event: bool, target_event: bool) -> float:
        if not self.settings.enabled:
            return weight
        if source_event and target_event:
            return min(1.0, weight + self.settings.link_hebb_increment)
        if source_event ^ target_event:
            return max(self.settings.link_weight_floor, weight - self.settings.link_async_decrement)
        return weight

    def confirm_hypernode(self, weight: float) -> float:
        if not self.settings.enabled:
            return weight
        return min(1.0, weight + self.settings.hypernode_confirmation_increment)

    def refute_hypernode(self, weight: float) -> float:
        if not self.settings.enabled:
            return weight
        return max(0.0, weight - self.settings.hypernode_refutation_decrement)
