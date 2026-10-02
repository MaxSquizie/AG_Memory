# Slice 12.20 — architecture-aligned Perception / T / ambiguity boundary

This slice follows `Архитектура_v3` v0.4 literally at the trust boundary instead of
optimizing only for the fixed acceptance cases.

## Dynamic T creation

Raw sentence parsing no longer synthesizes `TemplateCandidate` from the roles filled
in one concrete occurrence. Concrete `N` filling therefore cannot accidentally
become the reusable predicate valency schema.

The runtime path is now:

```text
PerceptionResult
  ↓
Integration.template_requests()   # deterministic, read-only preflight
  ↓ unknown predicate only
Perception.propose_template_candidate()
  ↓
validated runtime TemplateCandidate
  ↓
TemplateResolver
  ↓
canonical T registration
  ↓
resume normal integration
```

`TemplateCandidate` is proposed one canonical role at a time through fixed finite
choices. The LLM never sees AH UIDs and never writes/registers `T` itself.

Once a canonical `T` exists, sparse occurrences may fill any subset of its roles.
A later occurrence requiring a role outside that schema fails explicitly because
`T` valency evolution is `[DEFER]`; integration does not create a parallel
narrower/wider `T` as an implicit workaround.

Query/Command candidates participate in Predicate/T Resolution as well. They may
register a validated representational `T`, but do not create an asserted `N` fact.

## Runtime alternatives and canonical ambiguity

Perception no longer asks the LLM to choose a canonical antecedent for a pronoun.
Deterministic morphology/syntax may assign a unique turn-local `entity_ref`; when
several structurally compatible readings remain, Perception emits complete
`AssertionCandidate.alternatives`.

Control-subject abstention follows the same rule. An LLM answer of `0` no longer
silently drops the child SUBJECT. The structurally valid controller readings remain
runtime alternatives.

Integration validates alternatives, resolves each local reading through the normal
canonical `EntityResolver`, collapses aliases that resolve to the same `m`, and only
then materializes `k_AMBIGUOUS` when several canonical referents remain. The resulting
`N` points to that `k` and `clarification_required=True`.

This preserves the architecture distinction:

```text
runtime alternatives != canonical k
```

## Removed behavior

- occurrence roles no longer auto-create `TemplateCandidate`;
- no automatic second `T` for a wider/narrower occurrence;
- no LLM `pronoun_coreference` canonical entity chooser;
- ambiguous control no longer produces an incomplete child fact.

Ignition/activation policy is unchanged in this slice.
