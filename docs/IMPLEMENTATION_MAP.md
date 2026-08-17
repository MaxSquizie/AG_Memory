# Implementation map — slice 9

```text
config/default.toml
        ↓
RuntimeServices.build(AppConfig)
        │
        ├─ AHCore / canonical store / rebuildable indexes
        ├─ DSLInterpreter
        ├─ TextSensoryService
        ├─ LLMPerceptionService
        ├─ IntegrationService + SemanticCorrectionService
        ├─ IgnitionEngine
        │    ├─ f / g / h
        │    ├─ ν Pacemaker
        │    ├─ Lifecycle / GC
        │    └─ Workspace
        ├─ IgnitionClock
        ├─ InferenceEngine + Materializer
        ├─ ContextProjector
        ├─ LLMAgent
        ├─ JsonPersistence
        ├─ GraphInspector / TraceView / RuntimeDiagnostics
        └─ AgentOrchestrator
```

## Full user turn

```text
External text
→ TextSensoryService
→ LLMPerceptionService
→ PerceptionResult
→ IntegrationService
    ├─ positive assertions → C/P + H experience
    ├─ negated assertion → N operand + FALSE(N)
    └─ domain-local dedup
→ Activation/refutation requests
→ IgnitionEngine
    ├─ scheduled input + ν pacemaker
    ├─ f(x,z) / output
    ├─ one-edge-per-tick propagation
    ├─ h_L / h_N
    ├─ g decay
    ├─ lifecycle / GC
    └─ Workspace = x > t
→ QueryGoalBuilder
→ InferenceEngine
    ├─ ROLE
    ├─ IS-A
    ├─ FOLLOW
    ├─ CAUSE
    └─ explicit FALSE → DISPROVED where exact
→ optional Materialization, domain=max(C<P<H premises)
→ ContextProjector ACTIVE/DEPENDENCY
→ LLMAgent
→ response perception
→ H-only integration
→ FOLLOW
→ persistence
```

## Continuous runtime

```text
RuntimeServices.start()
→ local LLM process (if enabled)
→ IgnitionClock
→ IgnitionEngine.tick() at tick_interval
→ pacemaker uses ν over the same clock

RuntimeServices.stop()
→ stop clock
→ save
→ stop LLM process
```

## Canonical ownership

Only `AHCore` changes canonical `S/C/P/H/L`. DSL, integration, correction, inference materialization and GC all route canonical changes through the core boundary.

## Diagnostics boundary

```text
GraphInspector / TraceView / RuntimeDiagnostics
→ may expose internals to developer/GUI
→ read-only
→ never becomes AgentContext or H automatically
```


## GUI observer / control plane

```text
RuntimeServices
├─ operation_lock ── coordinates canonical phases with IgnitionClock
├─ GraphInspector ── read-only GraphSnapshot
│      ↓
│  GraphVisualMapper
│      ↓
│  VisPy SceneCanvas (2.5D / 3D)
├─ ConfigDocument → validate → atomic TOML save → apply_config
└─ QMainWindow docks
   ├─ Dialogue
   ├─ Config
   ├─ Node Inspector
   └─ Runtime / Trace
```

`TickResult.propagations` is diagnostics-only and animates actual one-edge-per-tick impulses. It is never written to AH/H or AgentContext.

### GUI focus / manual mutation extension (7.4)

```text
GraphSnapshot + VisualGraph
→ build_focus_geometry(uid)
→ hover/selection overlay only
→ incident L + structural edges + immediate neighbours

NodeManagerWidget
→ ManualNodeManager
→ RuntimeServices.operation_lock
→ AHCore.add_abstract_symbol / AHCore.add_entity
→ optional AHCore.add_link
→ optional IgnitionEngine.seed (explicit diagnostic action)
```

Hover/selection state is never persisted to AH and never affects Workspace or inference.

## GUI manual graph editing (0.7.5)

- `ah.gui.manual_nodes`: domain-aware manual m/S resolution and transactional creation.
- `ah.gui.manual_links`: canonical L creation/reuse between two existing nodes.
- `ah.gui.graph_state`: explicit selectable edge metadata + screen-space hit-test helpers.
- `ah.gui.graph_canvas`: mutually exclusive node/edge selection and read-only hover focus.
- `ah.core.persistence`: narrow legacy repair for invalid duplicate S records created by pre-0.7.5 GUI.
- `ah.core.store`: S wordform collision validation now happens before canonical mutation.

Architecture constraints preserved: name is not m identity; S is global/non-domain; C/P/H may carry equal semantics independently; a shared identity may also be referenced across domains; L remains a canonical directed relation; all hover/selection geometry is diagnostic/UI-only.


## Shared LLM role boundary (slice 9)

```text
                         one local model / one VRAM allocation
                                      │
                         LocalLLMProcessBackend
                           history_messages = 0
                           /                  \
              perception role                  agent role
          prompts/perception/*.txt           prompts/agent.txt
                    │                              │
          LLMPerceptionService                  LLMAgent
                    │                              │
          PerceptionResult                    natural response
                    │                              │
 deterministic integration               H-only response parse
```

No role call receives implicit conversation history. The response role receives memory only through deterministic `AgentContext`.

For this text-agent scope, `loader_type=causal_lm` is deliberate even when the local checkpoint is multimodal. The worker loads `AutoTokenizer + AutoModelForCausalLM` and does not instantiate `AutoProcessor`, so vision preprocessing dependencies are not part of the normal runtime. Explicit `image_text_to_text` remains a future opt-in path.

Perception now uses adaptive scalar probes and builds the richer runtime `PerceptionResult` deterministically:

```text
ACT_TYPE / PREDICATE_SPAN / PREDICATE_SYMBOL / ACTANT probes
        ↓
LLMPerceptionService deterministic builder
        ↓
AssertionCandidate / QueryCandidate / CommandCandidate
        ↓
Deterministic Integration
```

`evidence`, `parser_confidence`, `semantic_hint` and runtime alternatives are still supported by the canonical contracts, but are not mandatory output burden for every parser call. An invalid probe may be retried statelessly with the same question; the previous bad answer is never fed back to the model. Probe failure never writes AH.

## Weight / excitation invariant

```text
x --g--> decay with time

w --h--> changes only on plasticity events

L.w: 1/1 -> strengthen; 1/0 or 0/1 -> weak depression; 0/0 -> no change
N.w: semantic confirmation -> strengthen; explicit refutation -> strong decrease
```

Pacemaker-only activation is filtered out of `h_L` by default so background ν does not manufacture associative evidence.

## Direction visualization

`TickResult.propagations` is aggregated only in GUI state. Each recent directed source→target track gets a red glow plus an animated head/tail moving in causal direction. Animation phase uses wall-clock GUI time, not tick index, so high engine frequency remains legible.

## Adaptive Perception + English predicate symbols (slice 10)

```text
Russian source text
  ├─ Text Sensory -> observed lexical S (source wordforms)
  └─ adaptive_v2 probes
       ACT_TYPE
       PREDICATE_SPAN
       PREDICATE_SYMBOL -> English snake_case
       NEGATION / QUERY_MODE
       NEXT_ACTANT <-> ACTANT_ROLE
            ↓
       PerceptionResult
            ↓
       TemplateResolver
            ↓
       predicate S (English) -> T
```

The split is deliberate and architecture-compatible: source-language `surface/evidence` is not merged into the English semantic predicate S. No `canonical_form` field was added to S; both remain ordinary `<UID,R>` symbols with different recognition sets.

Adaptive probe prompts live in `prompts/perception/*.txt`, are read per request, and can be edited from the LLM dock. Retry never includes the previous bad answer.

## Weak-model discrete perception (slice 11)

В slice 11 default protocol был `adaptive_v2`; slice 12 superseded it with `adaptive_v3`. The LLM is explicitly treated as an AH-unaware semantic recognizer. Historically this path used enumerated numeric choices for several perception decisions; later slices progressively replaced semantically fragile multi-way role decisions with bounded exact-choice probes. In v0.12.54 canonical role routing uses neutral binary `A/B` partitions over the actually remaining candidate-role meanings, while morphology and deterministic syntax still eliminate choices when they provide formal evidence. Predicate lexical identity is deterministic only when structural morphology leaves one materially plausible lexeme; a remaining binary lexical homonymy is resolved by the separate bounded `lexeme_identity` A/B probe. Older adaptive protocols retain their compatibility path.

## Morphology-assisted discrete perception (slice 11.2)

Before `predicate_start`, Russian tokens are analyzed by a deterministic morphology layer (`pymorphy3` when installed). Morphological and syntactic evidence can narrow or eliminate probes, but context-free analyzer probability is not canonical semantic authority. Morphology never selects UID/domain/T/N or mutates AH. The normalized source-language predicate lexeme supplies the lexical `S` used by `T`; when exactly two materially plausible predicate lexemes remain after structural filtering, v0.12.54 resolves only that lexical identity through the bounded `lexeme_identity` A/B probe and then returns to deterministic construction. The older English-symbol path is compatibility-only.

## Slice 12 — adaptive_v3 perception

- `perception/linguistic_candidates.py`: runtime linguistic candidate graph.
- `perception/morphology.py`: preserves alternative Russian morphology parses.
- `perception/adaptive_parser.py`: candidate narrowing + stateless finite LLM probes + nested candidate refs.
- `perception/contracts.py`: structured AND/OR actant composition candidate.
- `integration/service.py`: materializes actant composition through canonical `g.AND/g.OR`.
- Active perception prompts contain no examples/few-shot anchors.


## Slice 12.19 residual perception boundary

- `perception/morphology.py`: carries grammatical animacy and scored morphology.
- `perception/adaptive_parser.py`: mood/number predicate agreement, tightly licensed
  coordinated object ellipsis, self-contained control probes and descriptive-role
  narrowing for copular adverbials.
- Its LLM antecedent-choice experiment is superseded by Slice 12.20.

## Slice 12.20 architecture-aligned T / ambiguity boundary

- `integration/service.py::template_requests`: deterministic read-only detection of
  predicates with no canonical `T`.
- `perception/adaptive_parser.py::propose_template_candidate`: finite Perception-layer
  reusable valency proposal; occurrence filling never defines the schema.
- `agent/orchestrator.py`: routes TemplateRequest back to Perception and attaches the
  runtime proposal before canonical integration.
- `integration/template_resolver.py`: reuses one existing compatible `T`; automatic
  valency evolution/parallel T creation is forbidden in MVP.
- `AssertionCandidate.alternatives`: unresolved local coreference/control readings.
- `integration/service.py`: resolves runtime alternatives canonically and creates
  `k_AMBIGUOUS` only after Entity Resolution if multiple `m` candidates remain.
- The obsolete `prompts/perception/pronoun_coreference.txt` was removed.


## Slice 12.21 end-to-end clarification lifecycle

- `integration/contracts.py`: structured `ClarificationRequest`, options/uses and
  `ClarificationResolutionCommit`.
- `integration/service.py`: projects canonical `k_AMBIGUOUS` into a clarification
  request and deterministically replaces `k -> selected member` after explicit user
  evidence; N collision handling preserves domain-local dedup.
- `agent/interaction_context.py`: persisted pending clarification queue.
- `agent/orchestrator.py`: interactive clarification sequencing; diagnostic runs do
  not arm pending clarification state.
- `agent/llm_agent.py`: dedicated `agent_clarification` role verbalizes options only.
- `perception/adaptive_parser.py`: `clarification_answer` finite probe interprets only
  the NEW user answer and never revisits/guesses the original ambiguous sentence.

## Slice 12.22 structural normalization / lexical narrowing

- `perception/adaptive_parser.py::_strip_structural_relation_actants`: removes
  redundant situation-valued `CAUSE/TIME` actants after canonical `CAUSE/FOLLOW`
  candidates exist; entity-valued circumstances remain ordinary actants.
- `integration/candidate_validator.py`: rejects duplicate inter-situation L+actant
  encoding at the trust boundary.
- `perception/adaptive_parser.py::propose_template_candidate`: weak-model hierarchy
  `template_hidden_role` (one tiny fixed-choice latent-core-role decision).
- `perception/morphology.py::stable_normal_form`: permits strongly dominant lexical
  paradigms such as `Петру -> Пётр` without collapsing equal-score homonymy.
- Coreference uses only materially competitive morphology and a conservative
  immediately-previous-sentence same-role preference after explicit continuation
  markers.
- Spatial lexical adverbs such as `дома` deterministically narrow to LOCATION.
- Unrepresentable `с + instrumental` noun/predicate attachment remains explicit
  ambiguity rather than being mislabeled as TOOL/AUXILLIARY.



## Slice 12.23 bounded TemplateCandidate discovery

- `perception/adaptive_parser.py::propose_template_candidate`: counterbalanced binary
  hidden-role probe plus strict per-template LLM/hidden-role budgets.
- A raw numeric option preference can no longer drive role-ontology traversal.
- Exhaustive positive hidden-role responses terminate as explicit `AdaptiveParseError`;
  no partial AH mutation occurs before validated T creation.
- `tests/test_architecture_alignment_1223.py`: numeric-token-bias and endless-YES guards.


## v0.12.24 — bounded one-shot TemplateCandidate schema

- Replaced recursive hidden-role interrogation with exactly one `perception_template_hidden_role` request per unknown predicate.
- Filled roles from the observed frame are a deterministic lower bound; echoed filled roles are ignored conservatively and cannot widen `T`.
- The LLM may return `NONE` or a finite comma-separated subset of canonical omitted roles.
- No `template_more_core`, `template_role_family`, or `template_role` runtime stages remain.
- Deterministic Integration still validates and registers canonical `T`; valency evolution remains deferred.


## v0.12.26 robust TemplateCandidate protocol

- `perception/adaptive_parser.py::propose_template_candidate`: one small fixed-choice hidden-core-role request (`perception_template_hidden_role`) per unknown predicate sense when deterministic construction still has a plausible latent role.
- `perception/adaptive_parser.py::_template_role_schema`: deterministic first-line protocol parser; canonical role-name validation; trailing non-protocol chatter ignored.
- `prompts/perception/template_hidden_role.txt`: one-label English micro-prompt; no free schema generation.
- `tests/test_architecture_alignment_1223.py`: real-Qwen-style trailing-chatter regression and conservative legacy `NONE.` handling.

## v0.12.27 — SLM-first English micro-probes

- Deterministic code narrows every decision before the model is called.
- Semantic probes use short English fixed-choice outputs (`ASSERTION`, `YES`, `RECIPIENT`, `CAUSE`, `FIRST`, etc.).
- Numeric outputs remain only for literal token/span addressing.
- Dynamic T no longer asks for a full schema: observed roles are kept deterministically and at most one latent core role may be added by `perception_template_hidden_role`.
- `template_hidden_role` is fixed-choice scored; no free generation, recursive follow-up, ontology walk, or explanatory text is possible.
- All service `.txt` prompts and legacy parser system prompts are English. Source user text is kept in its original language.


## v0.12.28 — pairwise SLM decisions with margin gating

- `llm/worker.py::_score_fixed_choice_details`: exact continuation likelihoods + winner margin.
- `perception/adaptive_parser.py::_binary_probe`: only `YES/NO`; low margin -> unresolved parser cue.
- `propose_template_candidate`: deterministic hidden-role candidate, one binary question at a time.
- `_choose_frame_relation`: ordered `CONTENT/PURPOSE/CAUSE/MANNER` hypotheses instead of multi-class abstention.
- `_resolve_control_subjects`: one controller candidate per binary probe.
- `_classify_role`: ordered pairwise family/role tests; stop on first confident match.
- `_derive_situation_relations`: discourse sequencing adverbs compile to `FOLLOW`; `_strip_structural_relation_actants` removes the temporary TIME marker.


## v0.12.29 — contrastive SLM choices and score diagnostics

- `perception/adaptive_parser.py::_fixed_choice_probe`: generic finite-choice scoring boundary with deterministic margin gating; active semantic paths no longer use universal YES/NO.
- `propose_template_candidate`: role-specific contrastive labels for one latent role hypothesis at a time.
- `_resolve_control_subjects`: one direct mutually-exclusive ordinal choice over narrowed controller candidates; low margin preserves runtime alternatives.
- `_choose_frame_relation`: `PARENT_ARGUMENT / SEPARATE_EVENT` classification for one structurally proposed nesting relation.
- `_classify_role`: direct family and exact-role fixed choices over deterministic candidate sets.
- `llm/process_backend.py::LLMRequestDiagnostic`: persists choice outputs, per-choice scores, explicit winner, margin, threshold, and accepted/rejected evidence into acceptance diagnostics.
- `tests/test_slm_contrastive_1229.py`: contrastive hidden-role, direct-controller, low-margin ambiguity, and diagnostic evidence regressions.

## v0.12.30 — deterministic valency narrowing + fail-closed nesting

- `perception/morphology.py::MorphInfo`: preserves dictionary grammemes and lexical `tran/intr` evidence.
- `perception/morphology.py::stable_transitivity`: accepts transitivity only when material verbal readings agree.
- `perception/adaptive_parser.py::propose_template_candidate`: dictionary transitivity resolves/blocks hidden OBJECT before any SLM call; unresolved hidden-role low margin fails explicitly instead of poisoning a non-evolvable canonical T.
- `perception/adaptive_parser.py::_template_hidden_role_prompt`: concrete English slot questions (`TAKES_RECEIVER`, `TAKES_SOURCE`, etc.), no universal YES/NO and no full-schema generation.
- `perception/adaptive_parser.py::_choose_frame_relation`: relation-specific finite choices (`CONTENT_LINK`, `GOAL_LINK`, `CAUSE_LINK`, `MANNER_LINK`); low margin raises explicit ambiguity/error rather than silently dropping candidate_ref structure.
- Bare `что` clauses deterministically test only CONTENT; explicit causal markers retain the structural CAUSE path.
- `tests/test_architecture_alignment_1230.py`: transitivity consensus, zero-SLM intransitive filtering, transitive OBJECT pre-resolution, relation-specific prompts, and fail-closed low-margin nesting.


## v0.12.31 — gated hidden valency without ontology walking

- `perception/adaptive_parser.py::propose_template_candidate`: no role-by-role RECIPIENT/SOURCE traversal. Grammar resolves SUBJECT/OBJECT first; one event-type cue can license at most one hidden directional role.
- `_has_deterministic_omitted_agent`: narrow Russian finite-plural omitted-agent grammar adds a reusable SUBJECT slot without fabricating an entity in the concrete N.
- `template_direct_object`: one English direct-accusative grammar classification used only when stable dictionary `tran/intr` is unavailable.
- `template_event_frame`: one four-way event classification (`TRANSFER_TO_RECEIVER`, `COMMUNICATE_TO_ADDRESSEE`, `ACQUIRE_FROM_SOURCE`, `OTHER_EVENT`) mapped deterministically to at most one RECIPIENT/SOURCE role.
- Explicit RECIPIENT/SOURCE or non-participant frame structure stops further directional-role speculation.
- Low-margin justified hypotheses remain fail-closed; no canonical T is created until deterministic Integration validates a complete runtime TemplateCandidate.
- `tests/test_architecture_alignment_1231.py`: no SOURCE-after-RECIPIENT, OTHER-event conservatism, one-role transfer/source mapping, direct-accusative fallback, fail-closed margin, omitted-agent grammar.


## v0.12.32 — counterbalanced ordinal semantic cues + morphology agreement

- `perception/adaptive_parser.py::_counterbalanced_binary_semantic_probe`: two-pass `FIRST/SECOND` fixed-choice scoring with swapped descriptions; low margin or semantic disagreement is explicit ambiguity.
- `template_event_directionality`: binary existence of a normal directional participant; no semantic output label.
- `template_event_direction`: binary recipient-side vs source-side classification only after directionality is established.
- `propose_template_candidate`: maps the stable ordinal cue to at most one RECIPIENT/SOURCE and then stops; canonical T creation remains deterministic Integration.
- `_filter_predicate_analyses_for_template`: first reuses the predicate lexeme already resolved by Perception, then applies explicit subject-number agreement before `stable_transitivity`.
- `tests/test_architecture_alignment_1232.py`: positional-bias rejection, swap-consistent no-role/recipient mapping, lexeme reuse, and coordinated-subject homograph filtering.

## v0.12.33 — calibrated semantic completions + deterministic PURPOSE object-control

- `llm/worker.py::_score_exact_continuations`: reusable length-normalized exact-continuation scorer.
- `llm/worker.py::_score_calibrated_choice_details`: scores the same semantic continuations under the real verb prompt and a neutral `UNKNOWN_VERB` prompt, then ranks `actual - baseline`; raw and calibrated margins remain parser diagnostics only.
- `llm/process_backend.py::LLMRequestDiagnostic`: persists `calibration_choice_scores`, `calibrated_choice_scores`, `raw_choice_margin`, and `choice_scoring_mode` alongside the existing fixed-choice evidence.
- `perception/adaptive_parser.py::_calibrated_event_semantic_probe`: one bounded three-way lexical cue encoded in the continuation text itself; no ordinal or semantic class output tokens are scored. The deterministic mapping can add at most one hidden `RECIPIENT` or `SOURCE`.
- `prompts/perception/semantic_completion_system.txt`: dedicated system instruction for complete-statement likelihood scoring; ordinary label-return protocol text is not reused.
- `perception/adaptive_parser.py::_resolve_control_subjects`: `PURPOSE` child + exactly one parent `OBJECT` is resolved as local object-control grammar before any controller LLM fallback.
- `tests/test_architecture_alignment_1233.py`: continuation-prior cancellation, neutral calibration transport, fail-closed calibrated margin, no-role/recipient mapping, deterministic PURPOSE object-control, and diagnostic persistence.


## v0.12.34 — additional-valency scoring with bound-role context

- `integration/contracts.py::TemplateRequest`: transports predicate-specific source context and noncanonical textual role bindings alongside `filled_roles`; no canonical UID/ref is exposed to Perception probes.
- `integration/service.py::template_requests`: deterministically extracts role binding text already present in `PerceptionResult`, including safe placeholders for nested/context-resolved values.
- `agent/orchestrator.py::_complete_dynamic_templates`: forwards the runtime source excerpt and textual role bindings back to Perception before canonical Integration.
- `perception/adaptive_parser.py::_calibrated_event_semantic_probe`: keeps content-free calibrated completion scoring but changes the target from event participants to **additional valency slots beyond the roles already shown**.
- `template_event_semantics.txt` / `semantic_completion_system.txt`: explicitly forbid counting an already shown SUBJECT/OBJECT participant as a new receiver/source slot.
- Neutral calibration preserves the same known-role shape while replacing lexical values with `[known subject]`, `[known object]`, etc.
- No margin threshold change; low calibrated margin remains fail-closed under `[DEFER]` T valency evolution.
- `tests/test_architecture_alignment_1234.py`: runtime binding transport, UID-hiding, additional-slot prompt semantics, neutral role-shape calibration, and completion wording regressions.

## v0.12.35 — bounded generative hidden-valency proposal

- `perception/adaptive_parser.py::_generative_hidden_valency_probe`: one ordinary temperature-zero generation for residual hidden `RECIPIENT`/`SOURCE` valency; no fixed-choice/logprob/calibration override is supplied.
- `_TEMPLATE_HIDDEN_VALENCY_LABELS`: strict finite runtime protocol: `NONE`, `RECIPIENT`, `SOURCE`, `RECIPIENT,SOURCE`, `AMBIGUOUS`.
- `perception/adaptive_parser.py::_template_hidden_valency_prompt`: transports only predicate-specific source text, lexical predicate and noncanonical textual role bindings already present in `PerceptionResult`.
- `prompts/perception/template_candidate_system.txt`: strict one-line output contract; no explanatory prose or free schema generation.
- `prompts/perception/template_hidden_valency.txt`: asks only for reusable additional directional slots beyond already-known roles; shown SUBJECT/OBJECT may not be relabelled.
- `AMBIGUOUS` and malformed output fail before TemplateCandidate acceptance; Integration still owns canonical validation, UID allocation, T registration and atomic AH mutation.
- Historical v0.12.35 protocol coverage is superseded by the v0.12.36 binary-protocol regression file below.


## v0.12.36 — sequential binary hidden-valency generation

- `perception/adaptive_parser.py::_generative_hidden_directional_probe`: tests RECIPIENT first with one ordinary binary generation and tests SOURCE only after an exact negative recipient answer.
- Active labels are `HAS_RECIPIENT_SLOT` / `NO_RECIPIENT_SLOT` and `HAS_SOURCE_SLOT` / `NO_SOURCE_SLOT`; there is no combined directional outcome.
- `_template_hidden_valency_prompt`: emits only source sentence, lexical verb, textual known-role bindings, one slot-specific question and two choices.
- `template_hidden_valency.txt`: shared short English instruction for the binary protocol; already-known SUBJECT/OBJECT roles may not be counted again.
- The hidden-valency path sends no choice scorer, calibration, margins, token probabilities or continuation-likelihood request.
- Exact-label validation is fail-closed before `TemplateCandidate` acceptance.
- `tests/test_architecture_alignment_1236.py`: RECIPIENT short-circuit, SOURCE second-call gating, no-slot two-call path, no-scoring override, exact-protocol rejection and no-probe-when-directional-role-already-observed regressions.

## v0.12.37 — hidden-valency order-bias preflight

- `diagnostics/hidden_valency_diagnostic.py`: six fixed RECIPIENT/SOURCE capability cases, each sent with canonical and reversed binary label order.
- Uses `AdaptivePerceptionParser._template_hidden_valency_prompt(..., choices_override=...)` so the diagnostic exercises the production prompt shape without changing production decision flow.
- Separates exact protocol compliance from a diagnostic-only recovery of the known trailing orphan `</think>` wrapper; production remains exact/fail-closed.
- Classifies each pair as `SEMANTIC_OK`, `ORDER_BIAS`, `SEMANTIC_WRONG`, `INCONSISTENT`, or `MALFORMED`; records first-choice frequency and all prompts/raw responses.
- Temporarily pauses/restores Ignition and verifies an empty canonical AH diff; no Orchestrator/Integration/AH write path is invoked.
- `gui/main_window.py`: dedicated `Hidden-valency preflight` button and result dialog with the generated ZIP path.
- `tests/test_hidden_valency_diagnostic_1237.py`: first-choice copying + orphan `</think>` detection and order-invariant semantic-control coverage.

## v0.12.38 — semantic oracle + architecture revision baseline

- `diagnostics/semantic_oracle.py`: strict semantic evaluator for perception, integration, queries/inference, canonical assertions and cumulative explicit-role `T` coverage; statuses are `PASS`, `FAIL`, and `GAP`.
- `data/acceptance_oracle.json`: curated expectations for the existing 40-case corpus, kept separate from the raw input sentences.
- `diagnostics/acceptance_runner.py`: persists semantic verdicts per turn, copies the exact oracle into each bundle, and reports semantic counts independently of runtime exceptions.
- `evaluate_acceptance_bundle(...)`: reconstructs AH turn-by-turn from a saved bundle and re-grades old runs without LLM execution.
- `gui/main_window.py`: validates case/oracle alignment before execution and presents semantic PASS/FAIL/GAP as the primary quality result.
- `docs/ARCHITECTURE_AUDIT_01238.md`: mechanism-by-mechanism audit against Architecture_v3. It identifies immutable first-use T + hidden-role guessing as the principal structural conflict with open-ended correctness.
- Next implementation decision: lift `[DEFER]` for controlled monotonic T valency evolution from validated explicit roles, then remove one-shot hidden SUBJECT/OBJECT/RECIPIENT/SOURCE prediction from production TemplateCandidate construction.
- Production parser semantics are otherwise frozen in this slice so the new oracle establishes a clean baseline before behavior changes.



## v0.12.39 — explicit-evidence T evolution; hidden valency retired from production

- `integration/template_resolver.py`: one unique existing canonical T may grow monotonically from `filled_roles`; same UID, canonical role order, no role removal. Several incompatible legacy T frames fail closed instead of being merged.
- `core/operations.py::expand_template_roles`: canonical T-growth primitive. `edit_element` independently rejects T predicate changes and role removal; store index rebuild keeps old N signatures valid after expansion.
- `perception/llm_parser.py::propose_template_candidate`: packages the already parsed explicit roles directly; no auxiliary LLM call.
- `perception/adaptive_parser.py::propose_template_candidate`: same explicit-role-only policy for direct adaptive callers.
- Removed retired production template guessing for hidden SUBJECT/OBJECT/RECIPIENT/SOURCE and dead template prompt files.
- `diagnostics/hidden_valency_diagnostic.py`: owns the retained hidden-valency capability prompt and order-swap instrumentation; production parser no longer contains the hidden-valency probe path. It never reaches Integration/AH writes.
- Query `requested_role` is passed to TemplateResolver as explicit schema evidence and can expand T without materializing an N.
- Architecture reference moved to working specification v0.5 and no longer lists controlled T valency evolution under `[DEFER]`.
- Remaining semantic work is deliberately separate: control/complement OBJECT semantics, turn-local P provenance, canonical conditional representation, and general parse ambiguity clarification.

## v0.12.40 — nested content semantics; binary generation; local identity provenance

- `perception/adaptive_parser.py::_fixed_choice_probe`: exactly two choices now use strict temperature-zero label generation with no `choice_outputs`, scorer, calibration, or margin veto. Multi-way fixed choices retain the legacy scorer temporarily pending a separate oracle audit.
- `perception/adaptive_parser.py::_choose_frame_relation`: same-clause child situations test `OBJECT` content/complement before `PURPOSE`; PURPOSE is narrowed to an actual goal of performing the parent action.
- `perception/adaptive_parser.py::_deterministic_role_candidates`: animate accusative participants narrow to `{OBJECT, RECIPIENT}` instead of being forced to OBJECT; the LLM makes only that bounded semantic distinction.
- `perception/adaptive_parser.py::_resolve_control_subjects`: removed the historical `PURPOSE + OBJECT => deterministic object-controller` shortcut. Controller resolution is independent of frame relation and may use the bounded participant choice.
- `perception/adaptive_parser.py::_resolve_relative_antecedents`: exact parent evidence is preferred, but a containing actant span with the same normalized semantic head may share the antecedent `entity_ref`, preserving identity and domain provenance.
- `tests/test_semantic_roots_1240.py`: direct regressions for request semantics, want-as-content, relative span identity and P-domain propagation.
- `docs/reference/Архитектура_v3.md`: working specification v0.6 records nested OBJECT-content semantics, binary generation policy and turn-local identity reuse before domain routing.

## v0.12.41 — delayed participant role decision; provenance-locked lexical resolution

- `perception/adaptive_parser.py::_deterministic_role_candidates`: ordinary accusative remains deterministic `OBJECT`; the v0.12.40 global animate-accusative `{OBJECT, RECIPIENT}` probe is removed.
- `perception/adaptive_parser.py::_attach_nested_assertions`: when a nested situation is independently established as semantic `OBJECT` content but one entity-valued OBJECT is already present, only that narrowed conflict may invoke `RECIPIENT / NOT_RECIPIENT` and reclassify the participant.
- `prompts/perception/content_addressee.txt`: exact binary addressee probe used only at the structural conflict boundary.
- `perception/adaptive_parser.py::_resolve_control_subjects`: participant descriptions and exact `FIRST/SECOND` protocol labels are separated; the model is never shown `SECOND: description` as a choice label.
- `integration/entity_resolver.py`: lexical name lookup accepts an optional preferred domain; names/aliases remain retrieval keys rather than cross-domain identity proof.
- `integration/service.py`: strong deixis/candidate_ref/turn-local entity_ref provenance establishes a provisional domain before ordinary lexical lookup; weak/default C does not lock lookup and preserves normal global candidate generation.
- `tests/test_semantic_roots_1241.py`: regressions for ordinary object pronouns, discourse coreference, delayed recipient reclassification, exact controller labels and cross-domain same-name isolation.
- `docs/reference/Архитектура_v3.md`: working specification v0.7 records delayed semantic decisions, bare-label protocols and provenance-safe entity lookup.
- Real v0.12.40 model baseline that motivated this slice: `31 PASS / 6 FAIL / 3 GAP`; v0.12.41 requires a fresh real acceptance run before any semantic success claim.
## v0.12.42 — sticky content relation; fail-closed participant reconciliation

- `perception/adaptive_parser.py::_attach_nested_assertions`: once `OBJECT/CONTENT_LINK` wins for a parent-child pair, inability to free the proposition-valued OBJECT slot no longer triggers a second relation search. The parser raises an explicit unresolved content-participant conflict instead of mutating the child relation into PURPOSE.
- `perception/adaptive_parser.py::free_nested_object_slot`: the remaining binary probe is phrased as the direct parent-event role distinction `RECIPIENT / NOT_RECIPIENT`, after CONTENT is already known.
- `prompts/perception/content_addressee.txt`: records the narrowed receiver/addressee/target-only contract.
- `tests/test_semantic_roots_1242.py`: regression coverage proves CONTENT cannot be overwritten by a GOAL fallback and that the narrowed prompt keeps human-readable semantics separate from protocol labels.
- `docs/reference/Архитектура_v3.md`: working specification v0.8 records semantic-relation monotonicity and fail-closed conflict handling.
- Real v0.12.41 baseline: `34 PASS / 2 FAIL / 4 GAP`; both FAIL cases were the same `попросить + infinitive` orchestration root.



## v0.12.43 — content addressee semantic cue

- `src/ah/perception/adaptive_parser.py`: after `CONTENT_LINK` and an occupied entity-valued OBJECT, asks only `CONTENT_ADDRESSEE / NOT_CONTENT_ADDRESSEE`; positive cue is deterministically mapped to runtime `RECIPIENT`.
- `prompts/perception/content_addressee.txt`: concrete natural-language cue contract; no canonical role label is emitted by the model.
- `tests/test_semantic_roots_1243.py`: locks cue/role separation and exact fail-closed protocol.

## v0.12.44 — scoped conditional propositions + structural clarification

- `core/signatures.py`: `N` signature now includes `meta.semantic_scope`; conditional proposition content cannot deduplicate with an ordinary asserted fact.
- `projection/function_registry.py`: built-in exact-arity `IF` functional construction.
- `integration/service.py`: `AssertionStatus.CONDITIONAL` endpoints are integrated as scoped canonical `N`; multi-member sides use `AND`; top-level conditional is canonical `IF`; only IF is seeded as semantic content, not branch N as standalone facts.
- `inference/engine.py`: ordinary `EXISTS` / `ROLE_FILL` ignores scoped proposition N.
- `integration/contracts.py`: `IntegratedConditional` exposes canonical IF/branch refs in acceptance diagnostics.
- `perception/adaptive_parser.py`: genuine direct-object + `с` instrumental attachment ambiguity emits a bounded structural clarification spec; explicit replay can select predicate attachment or object-NP attachment without an LLM attachment vote.
- `integration/service.py` + `experience_mapper.py`: pending structural choices are H-only dialogue state. Resolved semantics are attached to the original H experience rather than creating a duplicate user experience.
- `agent/orchestrator.py`: structural clarification is normal successful control flow. Diagnostic no-response runs do not arm pending dialogue state.
- `diagnostics/semantic_oracle.py`: validates canonical IF/AND shape, scoped branch predicates, and structural clarification kind/options.
- `data/acceptance_oracle.json`: former GAP cases 30–32 and 39 are now exact expectations.
- `docs/reference/Архитектура_v3.md`: working specification v0.10.



## v0.12.45 — case syncretism + fail-closed selected actants

- `perception/adaptive_parser.py::_material_morph_analyses`: preserves lower-scored case alternatives for the same nominal lexeme/non-case feature bundle, so syntax can resolve Russian case syncretism such as `Петра` genitive/accusative.
- `perception/adaptive_parser.py::_extract_actants`: a span already selected as relevant can no longer disappear when role classification is unresolved; parser fails closed instead of committing a partial frame.
- `tests/test_acceptance_regressions_1218.py`: regression reproduces the real pymorphy score pattern from case 39 and verifies structural clarification is reached without a semantic role probe; another regression locks no-partial-frame behavior under low-margin role ambiguity.
- `docs/reference/Архитектура_v3.md`: working specification v0.11 records both invariants.
- Real v0.12.44 baseline: `39 PASS / 1 FAIL / 0 GAP`; the single FAIL is the exact root addressed here.


## v0.12.46 — oracle link-domain accounting

- `diagnostics/semantic_oracle.py`: `cp_semantic_addition_count` no longer treats every domainless `L` as C/P semantics. Link endpoint domains determine whether the link touches C/P.
- `tests/test_semantic_oracle_1238.py`: H→H FOLLOW is excluded while C/P CAUSE remains counted.
- Production Perception/Integration/AH Core unchanged; Architecture_v3 remains v0.11.
- Exact saved v0.12.45 real bundle offline regrade: `40 PASS / 0 FAIL / 0 GAP`.


## v0.12.47 — broad200 semantic corpus

- `data/acceptance_cases.txt`: 200-case `broad200-v2` default corpus; first 40 frozen regression turns + 160 new stress turns.
- `data/acceptance_oracle.json`: 200 EXACT expectations with optional `family` and `tags`.
- `data/acceptance_cases_regression40.txt` / `data/acceptance_oracle_regression40.json`: preserved original 40-case real-40/40 baseline.
- `diagnostics/semantic_oracle.py`: family/tag metadata and per-family offline report aggregation.
- `diagnostics/acceptance_runner.py`: family/tag persistence and per-family live summary/manifest aggregation.
- Production semantics unchanged; Architecture_v3 stays v0.11.



## v0.12.49 — acceptance evaluator resilience

- `src/ah/diagnostics/semantic_oracle.py`: nullable query outcomes are treated as missing inference results and produce semantic FAIL checks rather than exceptions.
- `src/ah/diagnostics/acceptance_runner.py`: semantic evaluator exceptions are persisted per turn and do not truncate the remaining acceptance corpus.
- No production semantic-path changes.

## v0.12.48 — atomic diagnostics snapshots

- `src/ah/diagnostics/graph_dump.py`: `GraphInspector` accepts the shared runtime lock and holds it for the complete graph snapshot.
- `src/ah/diagnostics/summary.py`: `RuntimeDiagnostics` uses the same barrier for multi-read summaries.
- `src/ah/bootstrap.py`: wires `operation_lock` into both diagnostic readers.
- `src/ah/gui/main_window.py`: pauses graph visualization during long acceptance runs and resumes it after completion.
- No production semantic or architecture change.


## v0.12.50 — scenario-isolated acceptance

- `src/ah/diagnostics/semantic_oracle.py`: `SemanticOracleCase.scenario_id`; offline bundle evaluation resets AH/template-role accumulation on scenario transitions.
- `src/ah/diagnostics/acceptance_runner.py`: captures/restores canonical AH + InteractionContext + Ignition; resets state between scenarios; pauses/restarts Ignition clock; records scenario ids in turn/manifest/summary.
- `data/acceptance_oracle.json`: 149 explicit scenarios across 200 cases; regression40 and deliberate learning/query chains preserve continuity.
- Production Perception/Integration/AH Core unchanged.

## v0.12.51 — broad200-v2 oracle audit

- Production perception/integration semantics unchanged.
- `data/acceptance_oracle.json` corpus id is `broad200-v2`.
- Case 100 now requires the explicit `FOLLOW` signaled by `затем`.
- `cp_semantic_addition_count` excludes canonical T wrappers referenced only by newly added H `event_instance` nodes, while genuine C/P semantic additions and C/P-touching links are still counted.


## v0.12.53 — architecture correction of role narrowing

- `src/ah/perception/adaptive_parser.py`
  - removed broad200-specific lexical/grammar repairs from v0.12.52;
  - preserves finite number/gender agreement only as one-way negative SUBJECT evidence;
  - preserves a governing preposition in WH evidence; that WH path no longer strips the preposition before semantic routing;
  - replaces role-family / role-within-family multi-choice scoring with a generic binary semantic router;
  - maps natural semantic cue labels to `ActantRole` deterministically in Python;
  - respects an existing `allowed_roles` subset monotonically at every binary partition.
- `prompts/perception/role_*.txt` now require one exact label from `CHOICES`; all role-router model calls are binary.
- `tests/test_role_router_1253.py` verifies generic TOOL/TIME routing on synthetic `TARGET_X`, monotonic allowed-role subsets, no broad200 lexical literals in production, formal finite agreement, and preposition evidence preservation.
- `docs/reference/Архитектура_v3.md`: working specification v0.12 formalizes the distinction between valid negative constraints and semantic heuristics.


## v0.12.54 — neutral semantic partitions and contextual lexeme identity

- `src/ah/perception/adaptive_parser.py`
  - binary role routing now uses protocol labels `A/B` only;
  - each branch displays natural-language descriptions of the concrete role candidates actually remaining after deterministic narrowing;
  - invented intermediate labels (`ENTITY_OR_CONTENT_RELATION`, `CIRCUMSTANTIAL_MODIFIER`, etc.) are no longer part of the runtime semantic protocol;
  - two-way nominal lexical homonymy is resolved by a bounded `lexeme_identity` A/B probe before its morphology is consumed by role/identity logic;
  - two-way predicate lexical homonymy uses the same boundary instead of raising solely because context-free morphology leaves two lexemes;
  - lexical choice filters runtime morphology evidence only; canonical roles/UIDs remain deterministic Integration concerns;
  - >2 materially plausible lexical identities fail closed.
- `prompts/perception/lexeme_identity.txt`: exact A/B lexical protocol.
- `tests/test_role_router_1254.py`: neutral-label routing, monotonic candidate visibility, generic nominal/predicate lexical ambiguity, and fail-closed nonbinary ambiguity.
- `docs/reference/Архитектура_v3.md`: working specification v0.13.
- Acceptance cases/oracle unchanged from `broad200-v2`.

Note: v0.12.54 does not add new lexical role tables.  Older deterministic actant heuristics that predate this slice remain separately auditable implementation debt; the new semantic router is designed so they can be weakened later without reintroducing multi-choice role scoring.

## v0.12.55 — relation contracts and lexical monotonicity

- `src/ah/perception/adaptive_parser.py`
  - canonical role descriptions used by the binary A/B router are now event-relative contracts instead of short overlapping glosses;
  - TOOL/MATERIAL, TIME/HOW-TO, SOURCE/LOCATION and other neighboring meanings explicitly state their semantic boundary without adding new protocol labels;
  - an exclusively ADVB span may eliminate nominal participant/TOOL/MATERIAL roles as formal negative POS evidence, while leaving the remaining modifier semantics to the bounded router;
  - nominal `lexeme_identity` prompts include the analyser morphology profile for each remaining lemma;
  - predicate `lexeme_identity` prompts use the same profile boundary, exposing distinctions such as passive participle vs short adjective without hard-coded words;
  - a selected nominal lexical identity is reused by `normalized_hint`; later stable-normal-form code cannot silently replace it;
  - pre-predicate SUBJECT assignment reuses finite agreement and handles AND-coordinated nominative groups as grammatical plural;
  - relative antecedent matching safely falls back to the source mention when no normalized hint exists instead of raising on `None.casefold()`.
- `tests/test_role_contract_1255.py`: generic relation-contract, ADVB negative-evidence, morphology-profile and lexical-monotonicity regressions.
- `docs/reference/Архитектура_v3.md`: working specification v0.14.
- Broad200 corpus/oracle unchanged (`broad200-v2`). Older deterministic lexical/preposition role hints remain separately auditable debt and are not expanded in this slice.

## v0.12.56 — semantic-property role routing

- `src/ah/perception/adaptive_parser.py`
  - replaces the early heterogeneous role-family A/B partition with independent `YES/NO` semantic-property probes;
  - each property owns an exact Python-side `ActantRole` subset; NO removes only that subset, YES selects it and permits only a local binary contrast;
  - keeps pre-narrowed `allowed_roles` monotonic and keeps role classification off the >2 scorer path;
  - removes the now-dead legacy family-router constants/helpers so there is only one production role-routing path;
  - removes the legacy direct `из/от -> SOURCE` shortcut while retaining the full governing PP as semantic evidence;
  - adds a generic NUMERAL+nominal post-extraction boundary: counted participant vs whole event/state measure, with whole measures routed only as DURATION/AMOUNT and no unit-word lexicon.
- `prompts/perception/role_property.txt`: exact `YES/NO` single-property protocol.
- `prompts/perception/role_contrast.txt`: exact `A/B` local relation contrast.
- `prompts/perception/quantified_phrase.txt`: exact `A/B` counted-entity vs event-measure protocol.
- `tests/test_role_properties_1256.py`: synthetic property-routing, monotonicity, origin-preposition, quantified-phrase and fail-closed regressions.
- `docs/reference/Архитектура_v3.md`: working specification v0.15.
- Broad200 corpus/oracle unchanged (`broad200-v2`). Confirmed real baseline before this slice is v0.12.55: 171/200 semantic PASS, runtime 199/200, frozen40 40/40.


## v0.12.57

- `src/ah/perception/adaptive_parser.py`: replaces multi-step family/property role routing with one exact `RuntimeRoleCue` generation over the structurally admissible candidate set; removes the direct `из/от -> SOURCE` shortcut; adds grammatical-person mismatch as negative coreference evidence.
- `prompts/perception/role_cue.txt`: exact English protocol for the one-target role cue.
- `tests/test_role_cue_1257.py`: cue-boundary, no-score, admissible-set and pronoun-person regressions.
- `docs/reference/Архитектура_v3.md`: working specification v0.16.

## v0.12.58 — structural ambiguity boundaries and broad200-v3

- Confirmed real v0.12.57 run: runtime `200/200`, raw semantic `178/200`, frozen40 `40/40`.
- Oracle audit corrected eight evaluator-only noun-normalization overconstraints for source-denoting adverbial/directional fillers. Regrading the exact saved v0.12.57 runtime bundle under `broad200-v3` yields `186/200`; this is not a new product run.
- `src/ah/perception/adaptive_parser.py`
  - preserves NOM/ACC and DAT/ACC structural ambiguity instead of ordered case winners;
  - blocks only the formally unsafe postverbal NOM/ACC SUBJECT reading under a stably transitive predicate while preserving intransitive postverbal subjects;
  - treats OR coordinated postverbal nominals symmetrically with AND in the direct-object region;
  - makes NP-internal genitive absorption conservative when non-genitive material cases survive;
  - uses materially structural readings for relative antecedents and keeps the governing PREP inside relative role evidence;
  - routes preposition-governed relative roles through the ordinary one-shot `RuntimeRoleCue` boundary;
  - resolves binary lexical identity with two symmetric `YES/NO` lexeme-hypothesis probes; exactly one positive hypothesis is required;
  - fuses a numeral into a duration only after the head is already semantically DURATION;
  - recognizes morphology-marked substantivized anaphors as nominal-like and, when needed, uses a bounded local source-label (`C1..Cn/UNCLEAR`) antecedent probe without exposing UIDs;
  - extends fronted conditional consequents only across contiguous additive same-sentence siblings.
- `src/ah/integration/service.py`: computes direct deictic P provenance before dependency ordering and propagates it only through turn-local `candidate_ref` containment.
- `prompts/perception/lexeme_hypothesis.txt`: symmetric exact `YES/NO` lexical-hypothesis protocol.
- `prompts/perception/antecedent_choice.txt`: bounded local source-label/`UNCLEAR` protocol.
- Dead `lexeme_identity` and v0.12.56 property/contrast/quantified prompt files are removed from the current artifact; historical map entries remain as version history only.
- `tests/test_semantic_boundaries_1258.py`: structural ambiguity, relative PP, lexical fail-closed, duration anti-overgeneralization, anaphoric source-label, conditional scope, P-provenance and oracle-v3 regressions.
- `docs/reference/Архитектура_v3.md`: working specification v0.17.
- No real v0.12.58 broad200 product score is claimed before a fresh run.
