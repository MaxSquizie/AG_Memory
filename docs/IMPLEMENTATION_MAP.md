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

В slice 11 default protocol был `adaptive_v2`; slice 12 supersedes it with `adaptive_v3`. The LLM is explicitly treated as an AH-unaware semantic recognizer. Python enumerates legal numeric choices for speech-act class, token boundaries and role decisions; the model returns one number. Role names are not required model knowledge: plain-language option descriptions map to `ActantRole` after validation. Obvious negation/no-negation, empty candidate sets, single remaining ends/roles and high-confidence wh-word roles are deterministic fast paths. In current `adaptive_v3`, even predicate lexical identity is deterministic: morphology supplies the stable source-language lexeme used for the `S` referenced by `T`. Older adaptive protocols retain their compatibility path.

## Morphology-assisted discrete perception (slice 11.2)

Before `predicate_start`, Russian tokens are analyzed by a deterministic morphology layer (`pymorphy3` when installed). High-confidence POS/lemma results narrow or eliminate LLM probes; uncertain syntax still uses the existing adaptive numeric choices. Morphology never selects UID/domain/T/N or mutates AH. For current `adaptive_v3`, the normalized source-language predicate lexeme supplies the stable lexical `S` used by `T`; morphology still never selects UID/domain/T/N or mutates AH. The older English-symbol path is compatibility-only.

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
  coordinated object ellipsis, self-contained control probes, descriptive-role
  narrowing for copular adverbials, and bounded discourse-continuation coreference.
- `prompts/perception/pronoun_coreference.txt`: finite continuation-only antecedent
  choice with explicit abstention.
- Genuine unmarked pronoun ambiguity still fails before canonical integration.
