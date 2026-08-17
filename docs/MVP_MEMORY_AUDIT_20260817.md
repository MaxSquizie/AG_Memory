# MVP memory runtime audit — 2026-08-17

## Already implemented

The project already contains the core Senior runtime: synchronous Ignition ticks, f/g, h_L/h_N, pacemaker ν, Workspace, N lifecycle + GC, persistence, H dialogue events/FOLLOW, symbolic role/IS-A/FOLLOW/CAUSE inference, deterministic context projection and UID traces.

## Blockers fixed in this audit

### 1. Pacemaker could consolidate memory

Pacemaker-only activation is background excitability, not experience. Lifecycle now ignores direct pacemaker-only activation. In addition, pacemaker-only provenance is carried through causal propagation and residual excitation, so downstream nodes cannot accidentally become learning/consolidation events one tick later. A mixed semantic/sensory input removes the pacemaker-only classification.

### 2. An H turn could expire while the local LLM was thinking

With 20 engine ticks/s and the default NEW TTL, an unlinked first H event could expire after about ten seconds. Since the IgnitionClock intentionally continues during LLM calls, this could delete the current experience and leave `last_experience_ref` dangling. H hypernodes marked `event_instance=true` are now protected from ordinary TTL GC.

### 3. LLM worker silently truncated overflowing AgentContext

The worker previously left-truncated tokenized input to fit the model context. It now fails explicitly. `context.max_tokens` is passed to the agent backend as an exact tokenized input limit, additionally bounded by the real model context minus generation reserve. No ACTIVE roots are silently discarded.

## Important deferred item: reverse hyperedge incidence

A diagnostic confirmed that current `N → actants` propagation does not automatically wake another N that shares an actant. A naive `actant → N` implementation was tested and reverted: under the current additive activation function it creates a recurrent positive-feedback loop and rapidly saturates the local subgraph at x=1.

For the two-day MVP this is intentionally deferred. Exact factual recall continues through the deterministic reasoner, while Ignition spreading remains the stable architecture-defined `L` direction plus `N → actants`. Proper reverse incidence requires refractory/inhibition/normalization or another explicit recurrent-stability policy.

## Fast verification

Use unit tests and the deterministic memory smoke harness. Do not rerun broad200 for memory-runtime work.

### 4. Non-zero decay tail made Workspace permanently self-driven

With the previous default `alpha=0.08`, a single seeded N converged to a non-zero excitation tail and continued emitting impulses forever. Its actants accumulated those impulses and saturated at `x=1`, so Workspace never returned to quiescence. The MVP operational default is now `alpha=0`. Canonical AH, associative weights and lifecycle retain long-term memory; excitation is transient focus. Non-zero alpha is deferred until recurrent stabilization/inhibition exists.
