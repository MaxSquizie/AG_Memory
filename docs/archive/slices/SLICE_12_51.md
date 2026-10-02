# Slice v0.12.51 — broad200 oracle audit correction

v0.12.51 is diagnostics/oracle-only. Production Perception, Integration, AH Core,
prompts, and Architecture_v3 v0.11 are unchanged.

The first scenario-isolated broad200 run exposed two measurement defects:

1. Case 100 contains the explicit discourse marker `затем`. Production correctly
   emitted `FOLLOW(A1,A2)`, while the oracle incorrectly expected no relation.
   `broad200-v2` now expects the explicit FOLLOW relation.
2. `cp_semantic_addition_count` counted the canonical template used only to wrap a
   newly created H experience as C/P sentence semantics. Scenario isolation makes
   that infrastructure template appear on the first H-only structural
   clarification of each independent scenario. The evaluator now excludes a T
   structurally referenced as the template of an added H `event_instance` N. It
   continues to count genuine C/P T/N/M/G additions and domainless L whose
   endpoints touch C/P.

These corrections do not relax parser semantics. They remove false failures caused
by the evaluator itself.
