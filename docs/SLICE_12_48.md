# Slice v0.12.48 — atomic diagnostics snapshots

## Problem

During a long broad200 run the GUI graph could refresh concurrently with an Ignition/GC mutation. `WorkspaceView.refs()` could first observe a runtime UID and then, after GC rebuilt canonical indexes, call `core.ref(uid)` for a UID that no longer existed. The visible failure was `KeyError` from `store.kind_of(uid)`.

This was a read-consistency race, not canonical AH corruption. The same pattern was possible in later stages of `GraphInspector.snapshot()` because the snapshot is a sequence of dependent reads.

## Change

`GraphInspector` and `RuntimeDiagnostics` now optionally receive the shared `RuntimeServices.operation_lock`. Runtime wiring always supplies it. The complete snapshot/summary is read inside that barrier, matching the lock already used by the background Ignition clock and orchestrator canonical mutations.

The broad acceptance GUI also pauses only the graph render loop while the worker runs. Ignition, LLM perception, Integration and acceptance diagnostics continue normally; visualization resumes with a fresh snapshot at completion.

## Semantics

No Perception, Integration, Inference, AH Core or oracle semantics changed. `Архитектура_v3` remains working specification v0.11.
