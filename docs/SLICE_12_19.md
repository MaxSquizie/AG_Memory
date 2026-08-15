# Slice 12.19 — agreement, ellipsis and self-contained residual probes

The third unchanged 40-case acceptance run kept formal completion at 36/40 but
reduced the remaining semantic defects to a small set. This slice fixes those
classes without widening the LLM boundary or adding sentence-specific tables.

## Predicate morphology agreement

`pymorphy3` can assign equal probability to distinct verb lexemes. Parser order is
not a valid semantic tie-break. For one-token predicate heads, `adaptive_v3` now
ranks material analyses by:

1. speech-act/mood compatibility (`ASSERTION ↔ INDC`, `COMMAND ↔ IMPR`);
2. explicit subject-number agreement;
3. analyser score.

A coordinated nominative subject is structurally plural. If distinct lexemes remain
exactly tied after these grammatical constraints, perception fails explicitly.

## Coordinated object ellipsis

A resolved pronominal OBJECT may be inherited into the immediately following
coordinated finite predicate only when all of these hold:

- both predicates are finite and in one clause;
- they share the already established SUBJECT;
- the left predicate has exactly one simple OBJECT;
- that OBJECT is an explicit third-person pronoun with an established `entity_ref`;
- a coordinator lies between that pronoun and the right predicate;
- the right predicate has no explicit OBJECT.

This licenses `открыла её и прочитала [её]` but deliberately does not implement a
generic "copy the previous object" fallback.

## Self-contained control probes

When nested non-finite control remains ambiguous after deterministic frame
construction, the finite probe now receives the complete source text, parent
predicate, known parent roles, child predicate, known child roles, and entity-ref
anchored participant labels. The model still returns only one allowed option number
and may abstain with `0`.

## Narrow role disambiguation

Copular/remain-like predicates followed by a structurally material adverbial reading
are restricted to descriptive roles (`STATE/LOCATION/TIME/DURATION`) before the LLM
sees the choice. A noun/adverb homograph can therefore no longer be routed through
the generic participant family solely because one dictionary parse is nominal.

## Discourse pronoun continuation

Unmarked multi-antecedent pronouns remain explicit ambiguity. A cross-sentence
finite coreference probe is permitted only when the current clause begins with an
explicit continuation marker such as `потом/затем/далее/тогда`. The probe contains
the full discourse, current predicate, pronoun role, and each structurally compatible
antecedent with its prior role/predicate; option `0` is mandatory.

`MorphInfo` also exposes grammatical animacy for future deterministic narrowing, but
this slice does not use animacy to force an antecedent choice.

Ignition/activation policy and full predicate-template valency discovery remain
separate slices.
