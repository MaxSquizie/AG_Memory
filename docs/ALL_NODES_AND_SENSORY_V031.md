# v0.31 — all-nodes diagnostics and strong S input

## All nodes viewer

GUI now has a separate `Все узлы` dock. It shows every excitable canonical node (`S/M/G/K/T/N`) with ACTIVE human-readable semantics and diagnostics:

- stable diagnostic creation sequence;
- semantic text;
- kind / domain;
- `x` / `output`;
- first excitation tick / decay age;
- N lifecycle;
- Workspace membership;
- UID.

Default order is newest-added first. Every table header is sortable. Selecting a row selects the same node on canvas/inspector.

`creation_sequence` is non-semantic store metadata. It is persisted separately from canonical AH and cannot affect inference, identity, Workspace or activation. Old schema-1 memories without this metadata get a best-effort order from `N.meta.created_tick` / runtime `first_excitation_tick`; after the first v0.31 save the order is exact and stable.

## Strong lexical stimulation

External lexical input is now deliberately stronger than fact/H seeds.

Default seed magnitudes:

```text
surface S candidate = 0.85
resolved canonical S = 0.95
new fact N = 0.65
reactivated N = 0.55
H experience = 0.50
pacemaker = 0.08
```

There are two stages:

1. Text Sensory immediately stimulates every already-known surface/morphology S candidate with `SENSORY_SYMBOL`.
2. After Perception + Integration have resolved canonical predicate identity, every actually used canonical S in the external user turn gets `RESOLVED_SYMBOL` once.

Stage 2 fixes the case where an S is created during the current turn: it did not exist when Text Sensory ran, so previously it could finish the turn with `x=0` despite its wordform being present in the prompt.

Agent H-only self-utterances never emit `RESOLVED_SYMBOL`.

The Runtime/Trace tuning block exposes the resolved-S magnitude as the hot slider `Сильный импульс S`; moving it changes only future seed magnitude and does not reset AH/x/w.
