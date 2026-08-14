from __future__ import annotations

from math import exp

from ah.config import ActivationSettings, DecaySettings


class ActivationPolicy:
    def __init__(self, settings: ActivationSettings, x_max: float) -> None:
        self.settings = settings
        self.x_max = x_max

    def raw(self, x: float, z: float) -> float:
        if self.settings.kind != "additive_clamp":
            raise ValueError(f"Unsupported activation kind: {self.settings.kind}")
        return x + self.settings.gain * z

    def clamp(self, value: float) -> float:
        return min(self.x_max, max(0.0, value))

    def apply(self, x: float, z: float) -> float:
        return self.clamp(self.raw(x, z))


class DecayPolicy:
    def __init__(self, settings: DecaySettings) -> None:
        self.settings = settings
        if settings.kind != "sigmoid_epoch":
            raise ValueError(f"Unsupported decay kind: {settings.kind}")
        self._d0 = self._raw(0)

    def _raw(self, age: int | float) -> float:
        s = self.settings
        return 1.0 / (1.0 + exp(s.steepness * (float(age) - s.midpoint_ticks)))

    def multiplier(self, age: int) -> float:
        """D(age): D(0)=1, monotone, tends to alpha."""
        s = self.settings
        return s.alpha + (1.0 - s.alpha) * (self._raw(age) / self._d0)

    def step_factor(self, age: int) -> float:
        """Ratio D(age+1)/D(age), used to decay the current post-f state."""
        current = self.multiplier(age)
        nxt = self.multiplier(age + 1)
        if current <= 0:
            return 0.0
        return max(0.0, min(1.0, nxt / current))

    def expected_loss(self, x: float, age: int) -> float:
        return max(0.0, x - x * self.step_factor(age))
