# Adaptive perception probes v3

Active protocol: `adaptive_v3`.

Rules:
- no AH terminology in model-facing prompts;
- simple English instructions and English protocol labels;
- no demonstrations or expected-output examples;
- deterministic structure narrows the problem before any semantic probe;
- one small semantic decision per probe;
- when the runtime has exactly two alternatives, use ordinary temperature-zero generation and accept only one exact allowed label; no scorer/margin/calibration veto is used;
- protocol labels are separated from human-readable participant/relation descriptions;
- previous invalid output is never shown on retry;
- Python owns tokenization, morphology, clause candidates, spans, role mapping, protocol validation and `PerceptionResult` construction;
- production `TemplateCandidate` construction uses only explicit semantic roles observed/requested in the runtime frame; hidden SUBJECT/OBJECT/RECIPIENT/SOURCE valency guessing is not part of the production T path;
- nested situations distinguish semantic content (`OBJECT -> candidate_ref(child)`) from actual parent-action goal (`PURPOSE`);
- once a parent-child semantic relation such as `CONTENT_LINK` is accepted inside a parse hypothesis, downstream participant-role reconciliation may not overwrite it with another relation; unresolved role conflict is fail-closed;
- ordinary accusative OBJECT extraction stays deterministic. A participant is reconsidered as `RECIPIENT` only after an independently proven proposition-valued OBJECT creates a real single-slot conflict;
- controller identity of a nested predicate is a separate bounded decision after frame nesting; there is no generic `PURPOSE + OBJECT => controller` shortcut;
- runtime entity identity is established before final domain routing; lexical name/alias retrieval is evidence, not cross-domain identity proof;
- explicit PP attachment ambiguity remains fail-closed when the competing readings cannot yet be represented/clarified canonically.

`template_hidden_valency.txt` is retained only for the standalone hidden-valency capability diagnostic and does not authorize production canonical writes.
