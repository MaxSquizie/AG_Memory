# Slice 11.2 — morphology-assisted adaptive perception

Perception now narrows Russian syntax deterministically before asking the shared LLM.

- `pymorphy3` is a project dependency.
- Russian POS/lemma analysis is used only as preprocessing; it has no AH knowledge.
- A single high-confidence finite predicate head is selected without an LLM probe.
- Morphologically atomic predicates use a one-token predicate span without `predicate_end` probing.
- Common Russian predicate lemmas map deterministically to English semantic `S` labels (`бывать -> be`, etc.); unknown lemmas still use the tiny translation probe.
- A single nominative pre-predicate noun/pronoun is resolved as `SUBJECT` deterministically.
- For copular `be`, an unambiguous coordinated adjective phrase is resolved as `STATE` deterministically.
- Russian zero-copula forms such as `Яблоко красное` can become implicit `be(SUBJECT, STATE)`.
- After a parsed clause, a second `act_type` probe is skipped when morphology finds no remaining predicate head.
- Ambiguous cases still fall back to the discrete numeric LLM probe tree.

No canonical AH rule changed: morphology is runtime Perception preprocessing only.
