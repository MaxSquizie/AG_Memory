# v0.12.25 — live canvas during acceptance

This slice restores the VisPy graph canvas during file-driven acceptance runs.

## Runtime behavior

Acceptance no longer calls `GraphCanvasWidget.set_live_updates_enabled(False)`.
The canvas refresh timer remains active and continues rebuilding/rendering the
current `GraphInspector` snapshot while the batch mutates AH.

The separate 300 ms runtime/status poll is still paused during the batch because
it performs another full `GraphInspector.snapshot()` and would duplicate work
already performed by the live canvas. LLM status polling remains independent.

When the acceptance worker finishes, the canvas is refreshed once immediately and
normal runtime/status polling resumes.

This is visualization-only; perception, integration, ignition, persistence and
acceptance semantics are unchanged from v0.12.24.
