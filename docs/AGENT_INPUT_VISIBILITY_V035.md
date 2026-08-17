# Agent input visibility v0.35

The GUI now separates three different things that were previously easy to confuse.

## Agent CONTEXT

Exact `AgentContext.rendered` used as the logical user message for the Agent role:

- `# CURRENT INPUT`
- `# ACTIVE MEMORY`
- `# INFERENCE RESULTS`

While a slow local Agent request is still running, the backend exposes the in-flight logical request so this tab can already show the model-visible context before generation finishes.

## Memory INPUT

The first half is model-visible and contains exactly the semantic lines placed in `ACTIVE MEMORY` and `INFERENCE RESULTS`.

The second half is explicitly debug-only and is never appended to the LLM prompt. It explains each serialized Workspace root with:

- serialization position;
- root UID;
- kind/domain;
- projection-time `x`;
- Workspace threshold `t`;
- output;
- decay age;
- lifecycle state;
- exact semantic text sent for that root.

The diagnostic snapshot is captured at the same projection point at which AgentContext is assembled, so later Ignition ticks do not rewrite the explanation of a historical Agent call.

## Agent FINAL prompt

Unchanged purpose: exact worker-rendered chat-template input when available, including system message, AgentContext user message and model generation marker.

## Architecture boundary

`x`, `t`, tick index, decay/lifecycle and debug UID trace remain hidden from ordinary AgentContext. They are operator diagnostics only and do not influence the Agent LLM.
