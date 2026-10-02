# v0.12.68 — literal identity and attention-grounded relation endpoints

## Fixed

- Bare numeric literals are canonical values, not ordinary name-ambiguous entities. Persisted duplicates such as two `m("5")` nodes are collapsed deterministically into one canonical `NUMBER(5)` entity.
- Literal collapse rewrites existing N/G/K/L incidences before deleting duplicate m nodes, preserving canonical memory instead of selecting one duplicate and losing attached facts.
- Ambiguous-reference K groups that become singletons during literal collapse are themselves collapsed, so stale one-option clarifications cannot survive.
- Direct QUERY/COMMAND processing performs literal-collision maintenance without asserting a new world fact or creating an unseen literal merely because it was mentioned in a question.
- Ordinary same-name entities remain distinct. Query identity grounding may choose a same-name referent only when exactly one candidate is already present in the active Workspace. If zero or multiple candidates are active, resolution stays ambiguous. Proof reachability is never used to choose identity.
- Relation endpoint diagnostics now distinguish missing, ambiguous and uncanonicalized-literal endpoints instead of returning only `semantic:relation_endpoint_unresolved`.

## Architectural boundary

Numeric-token recognition is deterministic source structure, not an LLM semantic marker. The rule applies only to bare decimal literals. Rich named objects such as an entity named `5` with additional identity properties are not reinterpreted as numeric values.

Workspace-based same-name grounding is priority/attention, not truth. It is allowed only as a unique referent selection among already canonical candidates and never examines whether a candidate would make the requested proof succeed.

## Validation

- `448 passed, 22 subtests passed`
- M2 operator acceptance: `40/40`, AH `153502` UID, cold `149998` UID added
