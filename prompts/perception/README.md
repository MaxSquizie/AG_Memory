# Adaptive perception probes v3

Active protocol: `adaptive_v3`.

Rules:
- no AH terminology in model-facing prompts;
- simple English instructions and English protocol labels;
- no demonstrations or expected-output examples;
- deterministic structure narrows the problem before any semantic probe;
- role classification uses only binary natural-semantic cue decisions; grammar may remove impossible roles, but case/preposition/lexeme associations are not themselves canonical role assignments;
- one small semantic decision per probe;
- every bounded semantic choice uses ordinary temperature-zero generation and accepts only one exact allowed protocol label; no likelihood scorer, margin threshold, calibration veto, or hidden tournament is a semantic voter; multi-option paths include an explicit UNCLEAR label when ambiguity must be preserved;
- protocol labels are separated from human-readable participant/relation descriptions;
- previous invalid output is never shown on retry;
- Python owns tokenization, morphology, clause candidates, spans, role mapping, protocol validation and `PerceptionResult` construction;
- production `TemplateCandidate` construction uses only explicit semantic roles observed/requested in the runtime frame; hidden SUBJECT/OBJECT/RECIPIENT/SOURCE valency guessing is not part of the production T path;
- nested situations distinguish semantic content (`OBJECT -> candidate_ref(child)`) from actual parent-action goal (`PURPOSE`);
- once a parent-child semantic relation such as `CONTENT_LINK` is accepted inside a parse hypothesis, downstream participant-role reconciliation may not overwrite it with another relation; unresolved role conflict is fail-closed;
- ordinary accusative OBJECT extraction stays deterministic. A participant is reconsidered as `RECIPIENT` only after an independently proven proposition-valued OBJECT creates a real single-slot conflict;
- controller identity of a nested predicate is a separate bounded decision after frame nesting; with several plausible controllers the model returns one local label or `UNCLEAR`, and `UNCLEAR` preserves runtime alternatives; there is no generic `PURPOSE + OBJECT => controller` shortcut;
- predicate coordination is resolved as a frame-group property; an already-classified actant may be shared only after structural narrowing, with at most one exact `SHARED/LOCAL` decision and no role reclassification;
- runtime entity identity is established before final domain routing; lexical name/alias retrieval is evidence, not cross-domain identity proof;
- explicit PP attachment ambiguity remains fail-closed when the competing readings cannot yet be represented/clarified canonically.

`template_hidden_valency.txt` is retained only for the standalone hidden-valency capability diagnostic and does not authorize production canonical writes.

- binary lexical ambiguity is resolved by mirrored comparative A/B probes: both candidate orders must select the same lemma; independent YES/NO hypotheses are not used.
- lexical predicate sense is resolved separately from role schema: Perception sees only local Cn labels plus UID-free observed-use profiles and returns Cn / NEW / UNCLEAR; deterministic orchestration alone maps Cn to canonical T.

- `relative_clause_mode.txt` — exact `RELATIVE/SUBORDINATE` decision for relative-adverb surface ambiguity after structural narrowing.
- `clause_subject_control.txt` — exact `SAME_SUBJECT/INDEPENDENT` decision for omitted finite subordinate subjects.
