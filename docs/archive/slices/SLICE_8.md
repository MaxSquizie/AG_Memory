# Slice 8 — Weight audit + excitation flow + shared LLM roles

## Architecture checks

Checked against `docs/reference/Архитектура_v3.md`:

- §14.1: residual `x > 0` is not a Hebbian activation event;
- §14.2: `L.w` strengthens on same-tick endpoint events, weakly depresses when exactly one endpoint has an event, and does nothing on `0/0` inactivity;
- §14.3: `N.w` changes through semantic confirmation/refutation, not through time decay;
- §17–18: AgentContext contains explicit current input + Workspace projection + semantic inference results, not engine/debug state;
- §22: the same external turn still runs Perception before deterministic Integration and Agent only after Context Projection.

## Weight audit result

There was no direct per-tick `w *= decay` implementation. `x` and `w` are separate in the engine. However, the enabled ν pacemaker could create isolated activation events; those were being consumed by `h_L` and could weakly depress incident links while no external experience occurred. In practice this looked like passive weight loss.

The default now treats a **pacemaker-only** event as excitability noise for `h_L` and excludes it from associative plasticity. If the same node also receives a non-pacemaker input on that tick, the event remains plasticity-relevant.

Regression coverage:

- no activity for 30 ticks → `L.w` unchanged;
- `N.x` decays over ticks → `N.w` unchanged;
- one relevant endpoint event → weak `L.w` depression;
- two same-tick relevant endpoint events → `L.w` strengthening;
- pacemaker-only event → no `L.w` change.

## Visualization

Excitation is no longer encoded mainly as brighter domain color:

- quiet node → muted domain color;
- `x > 0` → red heat scale;
- adjacent canonical/structural edge → red according to endpoint excitation;
- actual propagation → persistent red directed flow overlay.

For high tick rates, individual tick particles are not restarted. Real propagation events update a recent directed track. GUI time moves a bright head plus darker tail from source to target, while new ticks only refresh track strength/lifetime.

## One LLM, two roles

Only one child process loads the local model. Both roles share that backend:

- Perception role: `prompts/perception.txt`, deterministic JSON-oriented generation settings;
- Agent role: `prompts/agent.txt`, natural-language generation settings.

`llm.history_messages = 0` is enforced. There is no hidden conversation buffer between calls, so parser output cannot leak into the agent through chat history and agent output cannot leak into the next parser call. Cognitive memory is supplied explicitly by AH `AgentContext`.

The GUI LLM panel provides model/process status, start/stop/restart, loading stage/log, context-window metadata after load, and live editing/saving of both role prompts.
