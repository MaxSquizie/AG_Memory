# Slice v0.12.50 — scenario-isolated broad acceptance

## Evidence from the completed broad200 run

The first complete v0.12.49 broad200 run produced 107 semantic PASS / 93 FAIL with
189 runtime OK / 11 ERROR. The frozen first 40 remained 40/40. Inspection of the
final AH showed that the single-session harness itself was creating later ambiguity:
independent examples repeatedly introduced same-name entities (`книга`, `Мария`,
`Анна`, etc.), followed by many `AMBIGUOUS_REFERENCE` groups. Those later failures
therefore mixed parser weaknesses with test-history contamination.

## Diagnostic contract

- Oracle case `scenario` is the state-continuity key.
- A scenario transition restores canonical AH, InteractionContext and Ignition to the
  acceptance baseline.
- `required_template_roles` is reset at the same boundary.
- The frozen regression40 remains one scenario.
- Only explicit T-evolution/query chains among the new 160 cases share a scenario.
- The Ignition wall-clock is paused while acceptance runs, eliminating timing variance.
- The user's complete live state is restored in `finally`, even if diagnostics fail.
- The existing LLM backend/process remains loaded and is reused.
- Offline `evaluate_acceptance_bundle()` performs the same per-scenario snapshot reset.

No production semantic mechanism changes in this slice. Architecture_v3 remains v0.11.
