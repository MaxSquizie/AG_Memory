# Quantified GoalCompiler downstream contract

Branch: `temp`.

This document defines the boundary for task 4 without duplicating the upstream
natural-language quantifier formalizer.

## Input owned by upstream formalization

A quantified polar `QueryCandidate` sets `query.quantified` to
`QuantifiedQuerySpec`.

Each `QuantifiedQueryBinding` provides:

- `entity_ref`: parser-local handle used on the bound query actant(s);
- `variable_id`: local BoundVar id;
- `operator`: `FORALL` or `EXISTS`;
- optional `restriction_lemma`;
- `negated`: negation of this complete quantifier scope.

`QuantifiedQuerySpec.body_negated` is separate predicate/body negation.

Bindings are ordered **outermost to innermost**.

Examples:

```
Все сотрудники пришли?
FORALL x: employee(x) -> arrive(x)

query.quantified.bindings = [
  FORALL(handle=x, restriction=employee)
]
```

```
Кто-то пришёл?
EXISTS x: arrive(x)
```

```
Никто не пришёл?
NOT(EXISTS x: arrive(x))
```

```
Не все сотрудники пришли?
NOT(FORALL x: employee(x) -> arrive(x))
```

Upstream code must decide these semantics. GoalCompiler must not inspect the
Russian surface forms above.

## Integration ownership

Integration materializes only a **query-scoped canonical pattern**:

```
N_body.meta.semantic_scope = QUANTIFIED
occurrence_count = 0
g_quantifier(...)
```

The queried root is stored in `IntegrationCommit.quantified_queries`. It is not
added to the query turn's H semantic OBJECT and receives no NEW_FACT seed.

If an identical quantified formula was already asserted earlier, ordinary
canonical dedup may reuse the same g root. That prior H occurrence, not the
question, is what makes the formula asserted.

Fixed non-quantified actants are resolved normally. Failure to resolve one must not
create a new entity just to formulate the question; the quantified goal then fails
closed as `semantic:quantified_query_not_materialized`.

## GoalCompiler ownership

`SemanticGoalCompiler` performs no quantifier parsing and no canonical writes.

```
IntegratedQuantifiedQuery.ref
    -> FormulaGoal(ref)
```

It must never compile a quantified polar query as ordinary `ExistsGoal`.

## Reasoner semantics

Existing `GroundFormulaReasoner` owns `FORALL/EXISTS/NOT` semantics.

Required open-world behavior:

- `EXISTS P`: one valid witness can prove it;
- no witness: UNKNOWN, not false;
- `FORALL P`: known instances do not prove universal closure;
- `NOT(EXISTS P)`: absence of witnesses is still UNKNOWN;
- `NOT(FORALL P)` and `FORALL NOT(P)` remain distinct formulae.

## Merge note

The agent working on upstream quantifier formalization in `main` only needs to
populate this runtime contract. No surface-word recognition should be copied into
`SemanticGoalCompiler`.
