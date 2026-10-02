# Slice 12.16 — deterministic lexical frames and strict finite probes

Acceptance diagnostics exposed several systemic perception failures: open-ended
predicate naming, LLM speech-act classification for obvious clauses, stale
`TemplateCandidate` schemas after frame normalization, and rare morphology readings
being treated as full structural evidence.

Changes:

- `adaptive_v3` no longer asks the LLM to invent an English predicate symbol.
  Predicate identity is derived deterministically from the morphology normal form;
  established compatibility aliases such as `читать -> read` are retained, while an
  unknown lexeme uses its normalized source-language form directly as ordinary `S`
  content.
- Obvious `QUERY`, `ASSERTION`, and `COMMAND` clause force is decided
  algorithmically from punctuation, explicit nominative subjects and unambiguous
  imperative morphology. Only structurally unresolved cases may reach the LLM.
- Every finite LLM probe passes its exact allowed numeric continuations to the local
  worker. The worker scores only those continuations and returns the highest-scoring
  allowed value verbatim; arbitrary generated explanations cannot enter the probe
  protocol.
- Morphological analyses remain available in full for semantic ambiguity, but only
  readings materially competitive with the best analysis may create predicate heads
  or other structural syntax. Rare dictionary readings such as `чай -> чаять` or
  `и -> NOUN` therefore cannot fabricate predicates/subjects.
- `TemplateCandidate` is finalized after nested-frame attachment, omitted/shared
  subject inheritance and coreference normalization. Its role schema therefore
  covers the final frame rather than the earlier surface draft.
- Comma-separated serial predicates with an omitted subject are handled as a
  structural paratactic inheritance case, without a generic "previous subject"
  heuristic. An explicit subject in the next frame blocks inheritance.
- If deterministic integration rejects a completed `PerceptionResult`, the failed
  semantic transaction remains rolled back but the external communication itself is
  still recorded exactly once as a raw H experience, matching the architecture's
  requirement that every user turn is experienced.

No semantic fallback, repair parser, retry reinterpretation, or phrase-specific
hardcode was added.
