# Slice 12.13 — memory-bounded acceptance diagnostics

Acceptance diagnostics keep the cognitive runtime unchanged while suppressing expensive GUI-only work during a batch run.

## GUI

While `Прогнать acceptance-файл` is running:

- the 30 Hz graph refresh timer is stopped;
- the 300 ms status/inspector polling timer is stopped;
- propagation animation collection is disabled and pending visual flow tracks are cleared;
- Ignition, AH mutation, LLM calls and the orchestrator continue normally.

After the worker finishes, graph live updates resume and exactly one immediate graph rebuild is performed before normal status polling is restarted.

## Acceptance runner

Per-turn runtime summaries no longer call `GraphInspector.snapshot()`. That method projects every node and is reserved for the final graph dump / interactive GUI. Runtime summaries now read only Workspace refs and ignition pending state, projecting semantics only for active Workspace roots.

JSON output is streamed to disk instead of first constructing a complete JSON string. Per-turn records that are already JSON-compatible are written without recursively cloning the whole record a second time. Full `before` / `after` canonical AH snapshots used for the diff are explicitly released before the next turn.

The diagnostic file format and semantic content are unchanged. No fallback, retry, parser repair or cognitive behavior was added.
