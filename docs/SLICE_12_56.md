# Slice v0.12.56 — semantic-property role routing

## Why this slice exists

The real v0.12.55 broad200-v2 run reached **171/200 semantic PASS**, **199/200 runtime OK**, and preserved the frozen regression40 at **40/40**. Relation contracts fixed a substantial part of the earlier TOOL/MATERIAL and morphology failures, but the remaining adjunct/query traces exposed a more general defect: role routing could still discard the correct role during an early A/B decision between large heterogeneous role groups.

A SOURCE PP can look like a generic circumstance; a TIME adverb is also an adverbial modifier. Asking the model which broad group applies makes the model solve an unnecessary ontology-partition problem before the actual local relation is compared. That violates the project rule that deterministic code should narrow the task and the model should perform only a tiny bounded semantic decision.

## Production change: one semantic property at a time

`AdaptivePerceptionParser._classify_role()` now uses independent binary semantic-property probes. Each probe asks only whether one natural relation property applies to the current target, with exact `YES/NO` output. Python owns the canonical role subset for that property.

The current properties are:

- temporal information → `{TIME, DURATION}`;
- non-temporal measure → `{AMOUNT}`;
- cause or goal → `{CAUSE, PURPOSE}`;
- means/material/manner → `{TOOL, MATERIAL, HOW-TO}`;
- place or transfer endpoint → `{LOCATION, SOURCE, RECIPIENT}`;
- predicated state → `{STATE}`.

`NO` removes only that exact subset. `YES` selects that subset and, when more than one role remains, a local A/B `role_contrast` resolves only the neighboring meanings. A previously established `allowed_roles` subset is never widened.

The model therefore no longer chooses between large hidden bags such as “participant” versus “circumstance”. Runtime role calls remain binary exact-generation probes; malformed output fails closed.

The obsolete family-router constants, prompt builders, and description/circumstance resolver methods are removed from production source rather than left as a dormant alternate path.

## Origin prepositions are evidence, not SOURCE

The legacy direct shortcut `из/от → SOURCE` was removed. It was demonstrably unsound: the same surface preposition can participate in source/origin, material and other semantic relations. The governing preposition remains in the evidence span supplied to the bounded semantic probe, but Python does not assign SOURCE from that surface token alone.

Other older deterministic PP/time hints remain separately auditable debt in this evolutionary slice; v0.12.56 does not pretend to remove all legacy heuristics at once.

## Generic quantified-phrase boundary

A second broad200 failure exposed a structural ambiguity shared across languages: `NUMERAL + nominal` can be a counted entity or a whole event/state measure. A duration-unit lexicon would be corpus-shaped, so v0.12.56 does not introduce one.

After ordinary actant extraction, a single adjacent `AMOUNT` numeral plus nominal actant triggers one binary `quantified_phrase` probe:

- A: the numeral counts/measures a separate participant entity;
- B: the combined phrase measures the event/state itself and the nominal is a measure/unit expression.

A keeps the existing actants. B fuses the source span and routes it only within `{DURATION, AMOUNT}`. Several correlated quantified phrases in the same frame are left unresolved rather than guessed independently.

## Diagnostics and regressions

`tests/test_role_properties_1256.py` uses synthetic targets rather than broad200 sentence literals. It verifies:

- one-property YES/NO prompts do not contain a heterogeneous negative branch;
- unrelated property rejections do not remove SOURCE;
- MATERIAL is reached only through the means/material/manner property plus local contrasts;
- a pre-narrowed `{TOOL, MATERIAL}` set never expands;
- the old `из/от → SOURCE` source shortcut is absent;
- counted-entity and event-measure NUMERAL+nominal readings use one generic mechanism without a unit lexicon;
- malformed property and quantified outputs fail closed.

The acceptance corpus/oracle remain `broad200-v2`. No v0.12.56 broad200 score is claimed until a fresh real-model run is performed.
