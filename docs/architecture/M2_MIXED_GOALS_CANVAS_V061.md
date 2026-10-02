# v0.12.61 — typed mixed inference, explicit Goal semantics and Canvas Browser

## 1. Goal is fixed before search

Runtime inference is driven by an explicit target:

```text
QueryCandidate
    -> deterministic QueryGoalBuilder / test query builder
    -> InferenceQuery(
           goal = GoalSpec(G),
           premise_refs = P,
           max_depth = D,
           max_expanded_states = B
       )
    -> InferenceEngine.solve(...)
```

`GoalSpec` and all search states are runtime-only. They are not AH elements and are
never written to H.

For normal dialogue QA, `QueryGoalBuilder` resolves the query predicate/template,
known actants and requested roles, then constructs `RoleFillGoal`,
`MultiRoleFillGoal` or `ExistsGoal`.

M2 constructs exact canonical `RelationGoal`, `CauseEntailmentGoal` and
`AllOfGoal` programmatically so the expected target is independent of the proof.

## 2. Formal satisfaction predicate

Let `K_i` be the set of propositions/bindings derived after the i-th valid rule
application. Search stops on the first `i` for which `Satisfied(G, K_i)` is decided.

Current MVP goal families:

```text
Satisfied(RoleFill(T, known, r), K)
<=> exists canonical non-refuted N:T such that
    N matches every known role and N[r] = v

Satisfied(MultiRoleFill(T, known, R), K)
<=> exists one canonical non-refuted N:T such that
    N matches every known role and every r in R has a binding

Satisfied(Exists(T, known), K)
<=> exists canonical non-refuted N:T matching every known role

Disproved(Exists(T, exact_roles), K)
<=> exact matching N exists and FALSE(N) is canonical

Satisfied(Relation(R, a, b), K)
<=> R(a,b) is direct or derivable by a registered rule for R
    (MVP transitivity only for IS-A and FOLLOW)

Satisfied(CauseEntailment(e), K)
<=> e is an explicit non-refuted premise OR e has been established
    by one or more valid CAUSE/MP steps from explicit premises

Satisfied(AllOf(g1,...,gn), K)
<=> forall j: Satisfied(gj, K)
```

The corresponding runtime stop rule is:

```text
if Proved(G):
    status = PROVED
    stop_reason = GOAL_SATISFIED
elif ExplicitlyDisproved(G):
    status = DISPROVED
    stop_reason = GOAL_SATISFIED
elif expanded_states >= B:
    status = UNKNOWN
    stop_reason = BUDGET_EXHAUSTED
elif required logical depth > D:
    status = UNKNOWN
    stop_reason = DEPTH_EXHAUSTED
elif no valid rule candidate remains:
    status = UNKNOWN
    stop_reason = SEARCH_EXHAUSTED
```

`x`, Workspace membership, reaching a graph endpoint and exhausting a branch are
not Goal predicates.

## 3. Mixed rules are typed composition, not heterogeneous reachability

A path such as:

```text
A --CAUSE--> B --FOLLOW--> C --IS-A--> D
```

is not by itself a proof of any arbitrary relation between A and D. The MVP has no
rule saying that CAUSE composes transitively with FOLLOW or IS-A.

Mixed proofs therefore use `AllOfGoal` and retain the semantics of every child
rule. Example:

```text
ALL-OF {
    CauseEntailmentGoal(B),
    RelationGoal(FOLLOW, B, C),
    RelationGoal(IS-A, C, D)
}
```

Each child is solved only by its registered rule family. Logical depth and expanded
state budgets are global across the complete proof, and the exact UID traces are
merged into one auditable connected proof trace when child boundaries share a ref.

A true cross-rule inference in which a conclusion produced by rule family X is
accepted as a premise by rule family Y requires an explicit typed bridge rule.
Until such a rule exists, graph adjacency cannot create that implication.

## 4. M2 suite

The suite now contains 40 cases:

- homogeneous CAUSE depth 1..6 (two domains/families);
- homogeneous FOLLOW depth 1..6;
- homogeneous IS-A depth 1..6;
- independent cross-chain cases;
- branched cold/warm cases;
- 8 typed mixed cases from depth 2 through depth 6,
  including CAUSE + FOLLOW + IS-A.

Every case freezes a `ProofChainSnapshot` with Goal, status/stop reason, logical
steps, semantic explanation, exact UID trace, attention sequence and individual
acceptance checks.

## 5. GUI

`Логический вывод` is a normal dock widget, not a separate top-level window.

The central graph is a Canvas Browser:

```text
Canvas: [Обычный AH | M2 sandbox]
```

The M2 page is a frozen read-only snapshot of the semantic test graph. Synthetic
cold stress-noise used only to bring the sandbox to 150k UIDs remains part of the
acceptance AH count but is intentionally hidden from rendering so the GUI does not
attempt to draw 150k meaningless disconnected points.

Selecting an M2 proof can highlight its UID path on the M2 sandbox page. Selecting
a LIVE proof switches to the ordinary AH page and highlights the canonical live
UIDs there.
