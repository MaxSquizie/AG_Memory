# Slice 5 — lifecycle, persistence and full turn-cycle

## Goal

Connect the already implemented semantic memory, ignition, Workspace projection and inference into a persistent executable agent cycle without violating the architecture boundaries.

## Added

### Core indexes

`AHStore` now maintains derived indexes for symbol forms, predicates, entities/properties, domain-local N signatures, N actants/reverse actants, relation adjacency and k memberships. `rebuild_indexes()` reconstructs them from canonical records.

Concrete H event instances can be marked `dedup_exempt`; they do not pollute semantic N signature indexes.

### Lifecycle / GC

N-only lifecycle:

```text
NEW → REINFORCED → CONSOLIDATED
```

Transitions require spaced activation/reactivation events. GC conservatively deletes expired unconsolidated N and safe auto-created orphans while preserving structurally/history-referenced nodes.

### Persistence

`JsonPersistence` atomically saves canonical AH and optionally runtime excitation/pending impulses. Indexes are never treated as truth and are rebuilt after load.

### Text sensory

Text observations first update/reuse `S.R_text` and emit sensory activation seeds. No semantic fact is created at this stage.

### LLM perception

`LLMPerceptionService` calls the local LLM boundary and validates strict JSON into the existing `PerceptionResult` contracts. Canonical UID is excluded from the model-facing schema.

### Full orchestrator

`AgentOrchestrator.handle_user_text()` implements:

```text
input
→ sensory
→ perception
→ integration
→ ignition
→ Workspace
→ inference/materialization
→ projection
→ agent response
→ H-only response integration
→ persistence
```

Own output is recorded as experienced H semantics but never sent through the ordinary external C/P learning path.

## Architecture-sensitive corrections

- Existing S can expand its `R_text` with a newly observed normalized/surface form.
- H event instances are not globally semantic-deduplicated.
- A new predicate encountered on the H-only response path creates its T in H rather than leaking a semantic schema into C/P.
- `FALSE`/refutation is not approximated here; it remains a dedicated next-step implementation rather than abusing ordinary h_L depression.
- Derived indexes are rebuildable and not serialized as canonical truth.

## Verification

```text
python -m compileall -q src tests
python -m unittest discover -s tests -q
```

Expected for this slice:

```text
36 tests
OK
```
