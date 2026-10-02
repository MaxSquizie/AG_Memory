# Slice 6 — DSL, semantic correction, pacemaker and diagnostics

## Goal

Close the remaining Senior infrastructure before the first GUI shell: canonical DSL operations, explicit `FALSE(N)` correction, a real `ν` pacemaker on the engine clock, continuous tick driving and read-only diagnostics.

## Added

### Full canonical operation facade + DSL

`AHCore` now exposes the operation family required by the architecture/monograph:

```text
add/edit abstract symbol
add/edit element
add/edit Pr
add/edit Mt
add/edit L weight through the canonical core
get/find abstract symbols
get/find S references
get/find m references
get/find m
get/find k
get T
get/find N
findRoles
get/find L
```

`DSLInterpreter` maps textual commands to those operations and supports deterministic pipelines, e.g.:

```text
findRoles role=LOCATION value=@M_1 domain=H
| findLists domain=H
| where meta.TYPE=Episode
```

The pipeline is only composition of canonical reads plus explicit read-only filters; it never writes indexes or store internals directly.

### Explicit negation / semantic supersession

Perception now has a runtime-only `negated` flag. A negated assertion is represented as:

```text
positive proposition N
→ FALSE(N)
```

Rules implemented:

```text
N_old is preserved
FALSE(N_old) is created/reused in the same C/P/H domain
negative input does not increment positive occurrence_count
FALSE(N_old) receives the semantic activation seed
N_old.w is decreased only through an Ignition h_N refutation request
```

For exact `EXISTS` goals, explicit `FALSE(N)` yields `DISPROVED`; partial open-world goals remain `UNKNOWN`.

### `ν` pacemaker

The pacemaker runs on the same tick clock:

```text
phase += ν * tick_interval
phase >= 1
→ emit configured internal pulse(s)
```

Target selection is explicit config, never hard-coded:

```text
round_robin
random
workspace
active
```

Pacemaker stimulation is tagged separately and cannot be mistaken for external confirmation by `h_N`.

### Continuous ignition clock

`IgnitionClock` is a wall-clock driver around the deterministic `IgnitionEngine.tick()`.

```text
engine running → ticks advance
engine stopped → memory time stops
```

If a tick takes longer than the configured interval, the clock does not invent catch-up cognitive ticks.

### Diagnostics

Read-only diagnostics intended for the GUI/live demo:

```text
GraphInspector.snapshot()
GraphInspector.to_json()
GraphInspector.to_dot()
RuntimeDiagnostics.summary()
TraceView.render(outcome)
```

Diagnostics exposes `x/w/tick/lifecycle/UID trace` without feeding those internals into the LLM context.

### CLI

Minimal diagnostic CLI:

```text
python -m ah.cli --config config/default.toml summary
python -m ah.cli --config config/default.toml dsl "findSymbols domain=P name=Пользователь"
python -m ah.cli --config config/default.toml dump-json
python -m ah.cli --config config/default.toml dump-dot
python -m ah.cli --config config/default.toml tick 5
python -m ah.cli --config config/default.toml refute N_1 --tick
```

## Architecture-sensitive correction

While reconciling Ignition against `Архитектура_v3`, reactivation was corrected to use the **pre-clamp** `x_raw` when comparing input strength with expected decay:

```text
x_raw = f(x_t, z)
Δ_input = x_raw - x_t
x_act = clamp(x_raw)

x_decay_expected = g(x_t)
Δ_decay = x_t - x_decay_expected
```

This prevents `x_max` saturation from hiding a strong reactivation.

## Validation

```text
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v

50 tests
OK
```

Additional invariants covered in this slice:

```text
explicit refutation overrides same-tick N confirmation
pacemaker phase/cursor/pulse count survive persistence
pending h_N refutation survives persistence
```

