from __future__ import annotations

from math import exp, log

MIN_MIDPOINT_TICKS = 2.0
MAX_MIDPOINT_TICKS = 600.0


def midpoint_from_speed(value: int) -> float:
    """Map operator speed slider [1..100] to sigmoid midpoint ticks.

    Higher slider value means faster roll-off, hence fewer midpoint ticks.
    Log interpolation preserves useful resolution across short and long decay
    epochs. Wall-clock labels are derived separately from the configured tick interval.
    """
    t = (max(1, min(100, int(value))) - 1) / 99.0
    lo = log(MIN_MIDPOINT_TICKS)
    hi = log(MAX_MIDPOINT_TICKS)
    return exp(hi + t * (lo - hi))


def speed_from_midpoint(midpoint_ticks: float) -> int:
    m = max(MIN_MIDPOINT_TICKS, min(MAX_MIDPOINT_TICKS, float(midpoint_ticks)))
    lo = log(MIN_MIDPOINT_TICKS)
    hi = log(MAX_MIDPOINT_TICKS)
    if hi == lo:
        return 50
    t = (hi - log(m)) / (hi - lo)
    return max(1, min(100, round(1 + 99 * t)))
