# Slice 12.2

Perception candidate-graph correction:

- function words/operators (`PRCL`, `CONJ`, `INTJ`) cannot become standalone actant heads;
- predicate negation particle is therefore consumed only as negation and cannot reappear as `OBJECT`/other actant;
- content-bearing negative pronouns/adverbs remain eligible (`никто`, `нигде`, etc.);
- bare prepositions are not standalone actants; prepositional phrases remain supported;
- when several remaining phrases have different unambiguous morphology-derived roles, parser consumes them deterministically instead of asking the LLM which one to process first.
