# Adaptive perception probes v3

Active protocol: `adaptive_v3`.

Rules:
- no AH terminology in model-facing prompts;
- simple English instructions and English protocol labels;
- no demonstrations or expected-output examples;
- deterministic structure narrows the problem before any semantic probe;
- role classification uses one deterministically narrowed natural-semantic choice; grammar may remove impossible roles, but case/preposition/lexeme associations are not themselves canonical role assignments;
- one small semantic decision per probe;
- stage files define semantic distinctions only, remain short, and never restate
  the response format or option menu owned by the shared wire protocol;
- every bounded semantic choice uses the shared numeric-first wire protocol and ordinary temperature-zero non-thinking generation; an exact current label or complete matching menu row remains a format-compatible response, but prose, headings, stale options and mismatched rows are rejected;
- retries repeat the same semantic evidence and options with a format-only correction; invalid model output is never fed back into the prompt;
- choice sets are finite, unique and capped before generation; no likelihood scorer, margin threshold, calibration veto, hidden tournament or semantic fallback is a second voter;
- multi-option paths include an explicit `UNCLEAR`/`UNKNOWN`/`AMBIGUOUS` choice when uncertainty must be preserved rather than coerced to a negative semantic answer;
- protocol labels are separated from human-readable participant/relation descriptions;
- Python owns tokenization, morphology, clause candidates, spans, role mapping, protocol validation and `PerceptionResult` construction;
- production `TemplateCandidate` construction uses only explicit semantic roles observed/requested in the runtime frame; hidden SUBJECT/OBJECT/RECIPIENT/SOURCE valency guessing is not part of the production T path;
- nested situations distinguish semantic content (`OBJECT -> candidate_ref(child)`) from actual parent-action goal (`PURPOSE`);
- once a parent-child semantic relation such as `CONTENT_LINK` is accepted inside a parse hypothesis, downstream participant-role reconciliation may not overwrite it with another relation; unresolved role conflict is fail-closed;
- ordinary accusative OBJECT extraction stays deterministic. A participant is reconsidered as `RECIPIENT` only after an independently proven proposition-valued OBJECT creates a real single-slot conflict;
- controller identity of a nested predicate is a separate bounded decision after frame nesting; with several plausible controllers the model selects one local option or `UNCLEAR`, and `UNCLEAR` preserves runtime alternatives; there is no generic `PURPOSE + OBJECT => controller` shortcut;
- predicate coordination is resolved as a frame-group property; an already-classified actant may be shared only after structural narrowing, with at most one exact `SHARED/LOCAL` decision and no role reclassification;
- runtime entity identity is established before final domain routing; lexical name/alias retrieval is evidence, not cross-domain identity proof;
- explicit PP attachment ambiguity remains fail-closed when the competing readings cannot yet be represented/clarified canonically.

`template_hidden_valency.txt` is retained only for the standalone hidden-valency capability diagnostic and does not authorize production canonical writes.

- binary lexical ambiguity is resolved by mirrored comparative A/B probes: both candidate orders must select the same lemma; independent YES/NO hypotheses are not used.
- lexical predicate sense is resolved separately from role schema: Perception sees only local Cn labels plus UID-free observed-use profiles and returns Cn / NEW / UNCLEAR; deterministic orchestration alone maps Cn to canonical T.

- `relative_clause_mode.txt` — bounded `RELATIVE/SUBORDINATE/UNCLEAR` decision for relative-adverb surface ambiguity after structural narrowing.
- `clause_subject_control.txt` — bounded `SAME_SUBJECT/INDEPENDENT/UNCLEAR` decision for omitted finite subordinate subjects.
- `association_query.txt` — bounded non-thinking association-intent probe. Deterministic parsing first enumerates source-grounded endpoint candidates as local `E1..En` labels, including members of one actant composition. The shared wire menu contains `ORDINARY`, `UNKNOWN`, and the enumerated endpoint pairs and is rejected before generation if pair expansion exceeds its cap. The probe never sees canonical AH UIDs and never constructs `AssociationGoal`; canonical endpoint resolution remains deterministic and read-only in GoalCompiler.
- `quantifier.txt` — bounded source-semantic classification after grammatical candidate extraction. It chooses only a typed quantifier label (or abstains); Python owns restriction/scope construction and canonical Integration.
- `temporal_mode.txt` — bounded occurrence-level `STATE/EVENT/PROCESS/AMBIGUOUS` decision used only when temporal fillers make the distinction observable and morphology/frame metadata did not settle it. It never classifies canonical `T`.
- `identity_query.txt` — distinguishes only the proof-relevant name-versus-
  description target independently of Russian surface form;
  `identity_target.txt` then selects among source-grounded entity candidates. The
  selected kind is preserved through GoalSpec, so a name request requires an
  explicit identity-name edge while a description may use identity or asserted
  descriptive facts.
