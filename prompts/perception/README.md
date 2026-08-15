# Adaptive perception probes v3

Active protocol: `adaptive_v3`.

Rules:
- no AH terminology;
- no examples, demonstrations or expected-output samples;
- one small decision per probe;
- finite choices whenever runtime can enumerate candidates;
- previous invalid output is never shown on retry;
- Python owns tokenization, morphology, clause candidates, spans, role mapping,
  validation and `PerceptionResult` construction;
- active `adaptive_v3` does not use open-ended predicate naming; predicate lexical identity comes from deterministic source-language morphology.
