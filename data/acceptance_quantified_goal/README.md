# Quantified GoalCompiler acceptance v1

This is the dedicated acceptance/oracle for point 4.

**Input boundary:** an already formalized `QuantifiedQuerySpec`.  Natural-language
quantifier recognition belongs to the upstream quantifier-formalization task and is
intentionally not duplicated here.  This keeps work in `temp` independent from the
agent currently changing that upstream layer in `main`.

The suite checks 12 exact downstream cases:

- FORALL against an explicitly asserted universal;
- open-world FORALL with only known instances;
- unrestricted and restricted EXISTS;
- shared-witness versus split-witness restriction semantics;
- NOT(EXISTS) and absence-is-UNKNOWN;
- NOT(FORALL) versus FORALL(body NOT);
- nested FORALL -> EXISTS;
- quantified role plus a fixed ordinary actant.

Required architecture:

```
QuantifiedQuerySpec
  -> Integration: scoped pattern N + canonical g, occurrence_count=0
  -> IntegrationCommit.quantified_queries
  -> SemanticGoalCompiler
  -> FormulaGoal(g_root)
  -> GroundFormulaReasoner
```

The query H occurrence must not make the queried formula asserted.  If a structurally
identical quantified formula was asserted earlier, canonical dedup lets the query
reuse that root; otherwise open-world rules apply normally.
