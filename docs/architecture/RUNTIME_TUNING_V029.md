# Runtime tuning v0.29

The Runtime / Trace panel exposes three hot Ignition decay controls:

- floating floor (`ignition.decay.alpha`);
- upper roll-off speed (`ignition.decay.midpoint_ticks`, displayed as speed);
- strong-reactivation threshold (`ignition.decay.reactivation_min_input`).

Dragging any slider applies immediately without resetting AH, x, w, decay origin, or decay age. Releasing/idle mirrors the settled values into the config editor; explicit Save persists them.

The same panel exposes a manual selected-node excitation button. It queues `ignition.seeds.reactivated_fact` into the selected excitable node. When the continuous Ignition clock is stopped, one ordinary tick is executed immediately for visual testing. Links (`L`) cannot be excited.

The Runtime toolbar also has `Полный canvas` (`F11`). It temporarily hides all dock panels so the VisPy graph occupies the full client area; toggling it again restores the previous dock visibility. This is visualization-only.
