# Slice v0.12.46 — semantic-oracle H chronology fix

## Scope

Diagnostics-only correction. Production Perception, Integration, AH Core, and architecture semantics are unchanged from v0.12.45 / Architecture_v3 working specification v0.11.

## Real-run finding

The real v0.12.45 acceptance run reached runtime `40/40` and semantic `39 PASS / 1 FAIL / 0 GAP`. Case 39 correctly produced an H-only structural clarification with zero assertions/world writes, but the oracle counted the ordinary domainless `FOLLOW` link between consecutive H experiences as a C/P semantic addition.

That metric was wrong: a link object has no own domain, so its semantic domain must be determined from its endpoints. `FOLLOW(H -> H)` is experience chronology, not a C/P world-semantic write.

## Change

`diagnostics/semantic_oracle.py` now counts a domainless `L` in `cp_semantic_addition_count` only when at least one endpoint resolves to canonical domain C or P. Domain-C/P elements themselves are still counted directly.

Regression coverage verifies both directions:

- H -> H FOLLOW does not fail a safe structural clarification;
- a C/P semantic link such as CAUSE(C -> C) is still counted.

## Offline regrade

The exact saved real v0.12.45 bundle regrades as:

```text
PASS 40/40
FAIL 0
GAP  0
```

No parser/model rerun is required for this correction because the stored turn already contains the correct structural-clarification result; only the evaluator misclassified its H chronology link.
