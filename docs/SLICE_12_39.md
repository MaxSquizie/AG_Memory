# Slice 12.39 — controlled T evolution from explicit evidence

## Goal

Remove the structural need to guess a complete predicate valency schema from the first occurrence. Canonical memory must be able to learn a newly observed role later without rewriting old facts or trusting speculative hidden-role probes.

## Canonical rule

```text
Roles(T_old) ⊆ Roles(T_new)
UID(T_old) = UID(T_new)
```

Only validated explicit semantic evidence may add a role:

- a filled assertion role;
- a filled query role;
- `requested_role` in a query;
- a filled command role.

Absence in one occurrence is not negative valency evidence. Hidden-role guesses are not canonical evidence.

## Implementation

`TemplateResolver` now reuses a compatible T, or asks `AHCore.expand_template_roles()` to expand the sole existing T in place when the current explicit roles require it. `AHCore.edit_element()` itself forbids T predicate changes and role removal, so monotonicity is enforced at the canonical write boundary rather than only by Integration convention. The edit happens inside the existing Integration transaction. If downstream integration fails, the T edit rolls back with the rest of the turn.

Existing N remain unchanged and valid because concrete N may fill a subset of T roles. Store indexes are rebuilt by the existing `edit_element` operation, so domain-local N dedup signatures remain consistent after expansion.

When several incompatible legacy T exist for one predicate S and none already covers the new role set, Integration refuses to guess which one to mutate. That case belongs to lexical-sense resolution.

## Perception simplification

Production TemplateCandidate creation is now an explicit-role packaging step. It performs no hidden SUBJECT, OBJECT, RECIPIENT or SOURCE discovery and no auxiliary LLM call. The old morphology/SLM template-guessing helpers and unused prompt files were removed.

`template_hidden_valency` remains only for the standalone preflight diagnostic introduced in v0.12.37. Its prompt construction now lives in the diagnostics module rather than the production parser. Diagnostic output cannot mutate AH.

## Architecture update

The embedded Architecture_v3 working reference is bumped from specification v0.4 to v0.5. Controlled monotonic T evolution is now normative MVP behavior and is removed from `[DEFER]`.

## Deliberately not solved in this slice

- control/content complement role correction;
- personalized-domain provenance propagation;
- canonical conditional propositions;
- general syntactic ambiguity clarification;
- lexical polysemy / canonical sense identity.

Those remain independently measurable semantic-oracle targets.
