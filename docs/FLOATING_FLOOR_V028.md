# Floating excitation floor + live tuning — v0.28

Implemented after the formalization freeze.

## Runtime semantics

- `x` is retained cognitive activation.
- `output = max(0, x_act - x_before)` is only newly acquired excitation.
- A decay epoch has `x_floor = alpha * decay_origin_excitation`.
- `g` decays only excitation above that floor.
- Weak input affects current `x` but does not rebase the floor.
- A strong non-pacemaker input rebases only when it exceeds both expected decay loss and `reactivation_min_input`.
- `begin_prompt_epoch()` rebases all currently excited nodes from their current `x`.
- Pacemaker-only activity never rebases the retained floor.
- Hot-increasing `alpha` never creates excitation by itself.

## MVP defaults

- `alpha = 0.60`
- `workspace.threshold = 0.35`
- typical new-fact seed `0.65` therefore settles at `0.39` between prompts and remains ACTIVE.
- at the next prompt, an unreactivated `0.39` node receives a new floor `0.234`, so stale context can leave Workspace while retaining a readiness trace.

## GUI

Runtime/Trace contains two live sliders:

- **Плавающий низ** → `ignition.decay.alpha` (0–90%).
- **Скорость спада верха** → logarithmic control of `ignition.decay.midpoint_ticks`; right = faster.

Slider movement applies immediately to the live `DecayPolicy` without resetting AH/runtime state. When the slider settles, the values are mirrored into the generic Config editor; use **Сохранить / применить** to persist them to TOML.

## Verification

- `pytest`: 346 passed + 4 subtests.
- `compileall`: clean.
- long-run smoke with pacemaker enabled: epoch origins remain stable, retained floor is not re-emitted each tick; only actual pacemaker pulses create new propagation.
