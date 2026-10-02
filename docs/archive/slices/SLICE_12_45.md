# Slice v0.12.45 — syncretic morphology preservation and no partial frames

Real v0.12.44 acceptance: **39 semantic PASS / 1 FAIL / 0 GAP**. Cases 30–32 canonical CONDITION passed. The only FAIL was case 39 (`Иван увидел Петра с биноклем.`).

Root cause was earlier than structural clarification: pymorphy scored `Петра` primarily as genitive (`0.857`) and its accusative reading (`0.095`) fell below the 30% structural-materiality floor. Perception therefore invoked the legacy multi-way role scorer, which returned an unresolved low-margin participant role; the parser then silently stopped actant extraction and canonically integrated the partial frame `увидеть(SUBJECT=Иван)`.

This slice fixes two general invariants:

1. Lower-scored case alternatives are retained when they are the same nominal lexeme and agree on non-case structural features with a material reading. This preserves real Russian case syncretism without re-admitting unrelated low-probability homonyms.
2. Once an actant span has been selected as semantically relevant, unresolved role classification is fail-closed. The parser may not omit that span and commit a partial frame.

With the recorded `Петра` morphology, the accusative reading now remains structurally available, so `Петра` is deterministic OBJECT and the following `с биноклем` reaches the existing H-only structural clarification path without an LLM role probe.

No scorer policy was otherwise broadened or replaced in this slice. Multi-way scorer remains a separately auditable legacy implementation detail, but its ambiguity can no longer silently shrink a selected semantic frame.
