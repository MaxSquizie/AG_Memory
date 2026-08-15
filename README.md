# AH Agent MVP — v0.12.19

Накопительный исполняемый проект АГ-памяти для текстового LLM-агента.

`docs/reference/Архитектура_v3.md` — архитектурный источник для реализации. Код строится так, чтобы каноническая память, runtime-динамика, inference и LLM boundary оставались отдельными слоями.

## Текущий end-to-end pipeline

```text
External Text
→ Text Sensory / S recognition
→ LLM Perception
→ deterministic Integration
→ C / P semantic content + H experience
→ domain-local dedup
→ atomic AH commit
→ ActivationSeedRequest
→ synchronous Ignition ticks
→ Workspace = refs with x > t
→ Symbolic Inference
→ optional materialization with C < P < H
→ deterministic ACTIVE / DEPENDENCY projection
→ AgentContext
→ LLM Agent
→ Response
→ H-only response integration
→ FOLLOW / episodic history
→ persistence
```

## Реализовано

### 1. AH Core

- `S`, `m`, `g`, `k`, `T`, `N`, `L`;
- `C/P/H`, typed refs, globally unique UID;
- referential integrity и canonical write boundary;
- domain-local `N` dedup;
- `Mt.occurrence_count` без прямого `w += constant`;
- dedup-exempt event instances для конкретных H-событий;
- atomic copy-on-write transactions;
- derived indexes, полностью перестраиваемые из canonical AH.

Derived indexes включают:

```text
UID/type/domain
R_text → S
predicate S → T
entity name/alias → m
Pr name/value
N canonical signature per C/P/H
N → actants
actant → N
L outgoing/incoming
IS-A / FOLLOW / CAUSE adjacency
k membership
```

### 2. Text Sensory

Текст до LLM perception проходит отдельный сенсорный слой:

```text
text
→ token observations
→ reuse/create/extend S.R_text
→ sensory ActivationSeedRequest
```

Сенсорная активация не создаёт семантических `m/N` и не является утверждением о мире.

### 3. LLM Perception — adaptive multi-call

Default parser больше не просит модель сериализовать JSON/AST/line protocol. Одна и та же локальная LLM выполняет последовательность маленьких stateless probes:

```text
TEXT
→ ACT_TYPE             deterministic when structurally obvious, finite probe otherwise
→ PREDICATE_SPAN       deterministic linguistic candidates / finite choice
→ PREDICATE S          source-language lexical normal form + observed R_text forms
→ NEGATION / QUERY_MODE when needed
→ NEXT_ACTANT          token span
→ ACTANT_ROLE          enum
→ ...
→ deterministic PerceptionResult builder
```

Каждый probe имеет отдельный короткий файл в `prompts/perception/`, отвечает одним scalar value и валидируется Python runtime до следующего шага. Retry повторяет исходный probe с чистого листа и **не получает предыдущий ошибочный ответ**.

Поддерживаются `AssertionCandidate`, `QueryCandidate`, `CommandCandidate`, source evidence spans, explicit negation и query `EXISTS/FILL_ROLE`. LLM не выдаёт canonical UID и не пишет AH напрямую. Semantic perception имеет только два исхода: валидный `PerceptionResult` или явный `PerceptionParseError`; partial/empty semantic fallback запрещён. При ошибке исходный внешний turn всё равно фиксируется как сырой пережитый H-event, но C/P semantics не фабрикуются.

Языковая политика: `S` представляет одну устойчивую лексическую единицу/парадигму. Морфология используется как детерминированный индексный ключ: нормальная форма и реально наблюдаемые surface-формы расширяют один `R_text`. `adaptive_v3` не просит LLM придумывать английское имя предиката; `T` ссылается на тот же source-language lexical `S`.

### 4. Deterministic Integration

```text
PerceptionResult
→ validation
→ T resolution/create
→ actant/entity/deixis resolution
→ ambiguity handling
→ C/P/H routing
→ canonical construction
→ domain-local dedup
→ atomic commit
→ seeds/reactivations
```

Дополнительно:

- неизвестный предикат может создать validated `T`;
- словоформы расширяют `R_text` существующего lexical `S`, включая predicate use;
- turn-local `entity_ref` принудительно сводит все кореферентные упоминания к одному canonical `m`;
- morphology-normalized nominal hint используется только для deterministic entity lookup (`Мария/Марии/Марию`), а не как identity key;
- interrogative placeholders (`кто/что/кому/...`) формируют `QueryCandidate.requested_role` и не материализуются как `m`;
- OR одного актанта поднимается в `g_OR` над полными proposition `N`, а не над raw-значениями;
- passive, compound temporal/conditional connectors, relative matrix binding и contrastive `не X, а Y` имеют детерминированную структурную обработку;
- неразрешённая pronoun/attachment ambiguity завершается явной ошибкой/неопределённостью вместо silent commit;
- `k_AMBIGUOUS` используется только после deterministic ambiguity;
- внешний user turn фиксируется в `H` и отдельно извлекает C/P semantics;
- собственный ответ интегрируется через отдельный **H-only** путь;
- H-only path не создаёт новый C/P `T` как побочный эффект;
- последовательные события диалога связываются `FOLLOW`.

### 5. Ignition Engine

- synchronous snapshot/commit tick;
- incoming buffers;
- `f(x,z)` вычисляет и новое возбуждение, и outgoing impulse;
- исходящий импульс не уменьшает `x`;
- информация проходит максимум одно новое ребро за tick;
- свежая активация/реактивация не получает `g` в том же tick;
- дальнейшее затухание через configurable decay epoch;
- activation event отделён от residual `x > 0`;
- `h_L+` для same-tick endpoint activation;
- weak associative `h_L-` только когда ровно один endpoint имеет relevant activation event;
- полная inactivity (`0/0`) никогда не меняет `L.w`;
- pacemaker-only pulse по умолчанию исключён из `h_L`, чтобы фоновое `ν` не имитировало опыт и не создавало псевдо-пассивную depression;
- `h_N` меняется только через semantic confirmation/refutation; обычное decay `x` не меняет `N.w`;
- `Workspace` строго определяется `x > t`;
- `L` не имеет собственного `x` и не является Workspace node.

### 6. Lifecycle + GC

Lifecycle существует только для `N`:

```text
NEW
→ spaced reactivation
REINFORCED
→ spaced reactivation
CONSOLIDATED
```

GC:

- удаляет expired `NEW/REINFORCED N`;
- не удаляет `CONSOLIDATED` по обычному TTL;
- учитывает structural referrers;
- защищает исторически используемые факты через H/FOLLOW refs;
- удаляет только явно auto-created structural orphans;
- удаление выполняется через canonical store, после чего индексы перестраиваются.

### 7. Workspace → AgentContext

```text
Workspace roots
→ ACTIVE projection
references of ACTIVE elements
→ DEPENDENCY projection
semantic inference results
→ AgentContext
```

Инварианты:

- Projector не решает, что релевантно;
- после `x > t` нет второго cognitive top-k/reranker;
- ACTIVE owner получает полную собственную семантику;
- DEPENDENCY получает только минимально достаточную семантику;
- `Pr` dependency не раскрываются;
- `Mt`, `x`, `w`, tick/decay и proof trace в prompt не выводятся;
- overflow не может молча удалить активные roots.

### 8. Symbolic Inference

Реализованы:

- role fill / exists по `T/N`;
- `IS-A` transitivity;
- `FOLLOW` transitivity;
- `CAUSE` MP-like inference;
- depth/budget/visited policy;
- exact UID trace вне H;
- read-only search;
- materialization только финального proved result.

Домен материализованного вывода:

```text
C < P < H
Domain(conclusion) = max(Domain(premises))
```

### 9. DSL / canonical operation API

`DSLInterpreter` covers the canonical operation family and compositional read pipelines. High-level syntax is translated to `AHCore`; it never bypasses the canonical write boundary.

Example:

```text
findRoles role=LOCATION value=@M_1 domain=H | findLists domain=H | where meta.TYPE=Episode
```

### 10. Explicit FALSE / semantic correction

Explicit negation is represented as `FALSE(N_old)`. The old proposition is preserved, its positive occurrence counter is not incremented by a negative assertion, and the strong weight correction is applied by `h_N` inside Ignition rather than by direct mutation. Exact `EXISTS` queries can return `DISPROVED` from explicit `FALSE(N)`.

### 11. ν pacemaker + continuous clock

`ExcitabilityPacemaker` schedules internal pulses using `ν` over the same engine tick clock. Target policy and pulse amount are config. `IgnitionClock` provides optional continuous wall-clock driving while cognitive time remains tick-count based.

### 12. Diagnostics

Read-only `GraphInspector`, `RuntimeDiagnostics` and `TraceView` provide GUI/live-demo state without leaking engine internals into the LLM context. A small `ah.cli` exposes DSL, graph dump, manual ticks and refutation for diagnostics.

### 13. Persistence

`JsonPersistence` сохраняет каноническую память:

```text
S / C / P / H / L
UID
Pr / Mt
w
```

По конфигу также сохраняется runtime:

- `x` и decay state;
- lifecycle metadata;
- current ignition tick;
- pending impulses.

Не сохраняются как semantic memory:

- `PerceptionResult`;
- `InferenceState`;
- UID proof trace;
- `AgentContext`;
- derived indexes.

Save атомарный: temp file → `os.replace`. После load индексы перестраиваются из canonical records.

### 14. Full Turn Orchestrator

`AgentOrchestrator.handle_user_text()` связывает реализованные подсистемы:

```text
begin prompt epoch
→ sensory S recognition + seeds
→ LLM perception
→ external deterministic integration
→ ignition ticks
→ Workspace
→ query building / inference
→ optional materialization
→ AgentContext projection
→ LLM response
→ response perception
→ H-only integration
→ response seeds / ticks
→ autosave
```

Это первая реализация полного когнитивного turn-cycle. Команды пока распознаются, но отдельный Action Executor ещё не реализован.

### 15. Local LLM process boundary

На основе полезных инфраструктурных решений из переданного `infer_ext.zip`:

```text
LocalLLMProcessBackend
→ UTF-8 JSONL subprocess
→ ah.llm.worker
→ local Hugging Face model
```

Worker поддерживает:

- local-only model loading;
- text-only `loader_type=causal_lm` by default, including composite Qwen checkpoints;
- optional explicit multimodal loader for future vision input;
- отдельный tokenizer path;
- LoRA adapter;
- 4-bit loading;
- device map / dtype;
- context budget;
- generation parameters.

AH Core не зависит от `torch/transformers/CUDA`.

Perception wire-format is intentionally compact: the LLM emits only `{a,q,c}` with predicate/roles/text, then deterministic code expands it into the full `PerceptionResult`. This keeps canonical UID/domain/entity decisions outside the model while reducing parser prompt/output complexity.

### 16. GPU GUI / cognitive graph

Первый desktop shell теперь строится на `PySide6 + VisPy`, а не Tkinter. Центральный canvas отображает AH как 2.5D/3D GPU-сцену:

```text
quiet hue        → C/P/H/S domain
red heat         → excitation x
node size        → excitation x
white flash      → activation/reactivation
cyan outline     → Workspace
yellow outline   → pending input
quiet L opacity  → L.w
red adjacent edge→ endpoint excitation
red comet trail  → real source → target propagation, animated on GUI time
```

Canvas использует read-only `GraphInspector`; layout никогда не влияет на память или reasoning. Diagnostics экспортирует также structural edges `T→S`, `N→T`, `N→actant`, `g→operand`, `k→member`, поэтому виден сам гиперграф, а не только `L`.

GUI содержит dock-панели диалога, полного config editor, node inspector и inference trace. Все TOML-параметры можно менять из GUI; `paths.llm_model_dir` имеет отдельный folder picker. Поля помечаются `LIVE / NEXT_TURN / RESTART_LLM / RESTART_RUNTIME`.

В slice 7.4 добавлены:

- default LLM path `C:/AI/qwen_3.6_27B_uncesored`;
- hover focus (жёлтый) и persistent selection focus (cyan);
- подсветка всех непосредственных incoming/outgoing `L` и structural edges выбранного/hovered узла;
- подсветка соседних узлов без изменения AH/Workspace;
- простой ручной node manager для `S` и `m`;
- опциональное создание `L` к текущему выделенному узлу (`IS-A/FOLLOW/CAUSE` или произвольный ID);
- опциональный diagnostic seed после ручного создания.

Ручной manager намеренно не создаёт `T/N/g/k` через упрощённую форму: эти структуры имеют семантические контракты и пока остаются за perception/DSL, чтобы GUI не превратился во второй неконтролируемый write API.

Запуск:

```powershell
pip install -e ".[gui,llm]"
ah-gui --config config/default.toml
```

или `run_gui.bat`.

## Центральный config

Главный файл:

```text
config/default.toml
```

Путь к локальной модели задаётся только здесь:

```toml
[paths]
llm_model_dir = "C:/Models/Qwen"
```

Также конфиг содержит:

```text
paths
LLM loader/generation
integration initial weights
f / g / h / t / ν
semantic/sensory seed strengths
lifecycle / GC
inference depth/budget
Workspace threshold
AgentContext budget
persistence/runtime snapshot policy
agent/user identity
orchestrator tick counts
```

## Структура проекта

```text
config/
  default.toml

prompts/
  agent.txt
  system.txt
  perception/
    probe_system.txt
    act_type.txt
    predicate_start.txt
    predicate_end.txt
    predicate_symbol.txt          # legacy adaptive protocols only
    predicate_symbol_verify.txt   # legacy adaptive protocols only
    negation.txt
    actant_start.txt
    actant_end.txt
    role_family.txt
    role_participant.txt
    role_circumstance.txt
    role_description.txt
    frame_relation.txt
    control_subject.txt
    relative_role.txt
    query_mode.txt
    requested_role.txt

docs/
  reference/Архитектура_v3.md
  IMPLEMENTATION_MAP.md
  INFER_EXT_REUSE.md
  SLICE_2.md
  SLICE_3.md
  SLICE_4.md
  SLICE_5.md

src/ah/
  bootstrap.py
  config.py

  model/
  core/
  perception/
  integration/
  ignition/
  inference/
  projection/
  llm/
  agent/

tests/
```

## Тесты

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Slice 7.5: **65 tests**. `compileall` и полный `unittest` suite проходят.

## Следующий срез

Основной Senior runtime уже связан. Следующий срез — первый GUI-shell поверх готовых сервисов, без логики памяти внутри UI:

```text
chat / turn execution
start-stop LLM + IgnitionClock
config editor + LLM path picker
Workspace view
graph / runtime diagnostics
inference trace panel
DSL console
manual tick / save / refute
```

После GUI — evaluation/demo harness M1–M5 и RAG baseline, не меняющие AH Core.

## Slice 6 architecture reconciliation

Ignition reactivation compares input strength using `x_raw` before `x_max` clamp, while expected decay is computed from pre-input `x_t`, matching `docs/reference/Архитектура_v3.md`.

## GUI compatibility patches

- 0.7.1: VisPy `TextVisual` label layer uses a hidden non-empty placeholder position.
- 0.7.2: VisPy marker `scaling` is assigned as a `MarkersVisual` property instead of an unsupported `set_data()` keyword. Marker sizes remain fixed in screen pixels.


## Slice 7.5 — domain-aware manual editing and selectable edges

- Manual `m` creation is domain-aware. Default policy reuses one exact-name candidate only inside the selected C/P/H domain. The operator can explicitly reuse a single matching UID across C/P/H when identity is shared, or explicitly create a new UID. `name` is never treated as an identity key.
- Manual `S` creation is global/non-domain: an existing wordform reuses its canonical `S`, and additional forms are merged transactionally.
- Legacy persistence produced by the pre-0.7.5 manual `S` bug is repaired during load by merging overlapping `S` records and rewriting `S` references before index rebuild.
- Manual node + optional link creation is one canonical copy-on-write transaction, so validation failure cannot leave a half-created node.
- New `Связи` dock captures source/target from canvas selection and creates/reuses canonical `L`.
- Canvas selection now distinguishes nodes and edges. Node focus highlights its immediate incident edges/neighbours; edge hover/selection highlights the edge and both endpoints. Canonical `L` and diagnostic structural edges are independently selectable.
- Edge picking is screen-space CPU geometry over the VisPy visual-to-canvas transform; it does not mutate AH or participate in cognition.

### Slice 8: weight audit, readable excitation flow and shared-role LLM

- regression tests explicitly prove that inactivity never decays `L.w` and decay of `x` never decays `N.w`;
- pure pacemaker events are excluded from associative plasticity by default (`ignore_pacemaker_only_events=true`);
- `NodeDiagnostic.associative_weight` exposes `N.w` separately from `excitation`, preventing GUI confusion between `x` and `w`;
- excitation uses a domain-independent red heat scale; adjacent relation/structural edges also turn red;
- propagation events are aggregated into persistent directed tracks; moving red head+tail animation is driven by GUI time rather than engine tick rate;
- one `LocalLLMProcessBackend` / one loaded model is shared by two stateless role wrappers: `LLMPerceptionService` and `LLMAgent`;
- `llm.history_messages=0` is enforced: no hidden chat history crosses parser/agent requests; AH `AgentContext` remains explicit cognitive context;
- separate perception probe prompts and `prompts/agent.txt` (single `perception.txt` was later superseded by adaptive_v1);
- GUI LLM dock: start/stop/restart, model/stage/context status, worker log, live prompt editing.


### Slice 9: text-only Qwen3.6 loading and compact parser wire format

- text-agent runtime now defaults to `loader_type=causal_lm`, even when the checkpoint contains a vision encoder;
- normal startup uses `AutoTokenizer + AutoModelForCausalLM` and does not instantiate `AutoProcessor`;
- `transformers>=5.14.1,<6` is required for current Qwen3.6 support;
- explicit multimodal loading remains opt-in via `image_text_to_text` and optional `[llm-vision]` dependencies;
- perception prompt reduced from the verbose full runtime schema to compact `{a,q,c}` JSON;
- deterministic adapter expands compact assertions/queries/commands into the existing `PerceptionResult` dataclasses;
- legacy full perception JSON remains readable;
- one configurable stateless `perception_repair` retry handles malformed JSON without touching AH;
- LLM panel reports actual loader and Transformers version.


## Slice 9.1 diagnostics

The LLM dock exposes Parser RAW, decoded PerceptionResult, Agent RAW, recent requests and worker logs. Transformers generation is configured through one request-local GenerationConfig only.

## CUDA note (slice 9.2)

The bundled local-27B config uses `device_map="cuda:0"` and NF4 4-bit. The LLM dock reports actual CUDA availability, final model placement, and allocated/reserved VRAM. `device_map="auto"` remains supported but may intentionally offload modules to CPU/disk.


### Perception protocol

Исторический `adaptive_v1`: parser делает серию коротких enum/span probes; source spans и итоговый `PerceptionResult` собираются детерминированно. Ответ агента всегда попадает в H, но повторный semantic parser для собственного ответа по умолчанию отключён.

Probe-валидаторы допускают только безопасный форматный шум в конце скалярного ответа (`ASSERTION.`, `SUBJECT:`, `2.`, `0.`), но не извлекают допустимый токен из объяснительного текста вроде `I think ASSERTION`.


## Adaptive perception debugging

`adaptive_v1` uses short stateless probes. Instructions live in `prompts/perception/*.txt` and are appended as the final `TASK` of each user request. `act_type` deliberately receives no token table; numbered tokens are supplied only to span-selection probes. The LLM panel shows each probe input, raw output, normalized answer, and validation error.

## Slice 11 — weak-model Perception

Исторический slice 11 ввёл `adaptive_v2`: no JSON/AST and no unexplained span notation. The local LLM receives one small task at a time and usually returns one integer selected from explicit options. Python owns tokenization, legal candidates, span construction, role mapping and validation. The LLM is not expected to know any AH terminology. See `docs/SLICE_11.md`.


## Perception note

`adaptive_v2` был morphology-assisted для Russian: deterministic POS/lemma narrowing runs before weak-model probes; ambiguous decisions remain discrete LLM choices.

## Perception v3

Default `adaptive_v3` uses deterministic linguistic candidate construction before
calling the LLM. The model only resolves remaining ambiguity through tiny stateless
choices and is never expected to know AH internals. Active micro-prompts contain no
output examples. Coordination can be preserved as canonical `g.AND/g.OR`, and stable
subordinate clauses can be linked through local `candidate_ref` before Integration.


## Slice 12.5 — temporal direction and local coreference

`adaptive_v3` now preserves directional temporal connectives as runtime situation relations that Integration materializes as canonical `FOLLOW` links. Relative antecedents and inherited omitted subjects carry turn-local `entity_ref` labels so repeated mentions resolve to the exact same canonical entity rather than relying on name equality. Prepositional evidence remains verbatim while semantic entity lookup excludes the relation-bearing preposition. See `docs/SLICE_12_5.md`.

## Slice 12.7 — causal situation relations

A nested semantic `CAUSE` actant now also compiles into a canonical directed
`CAUSE` link (`cause situation -> effect situation`). The compiler operates on
the resolved frame relation rather than matching one specific surface phrase.
Integration supports both `FOLLOW` and `CAUSE` situation relations and exposes a
separate `integration.cause_link_weight` setting with backward-compatible
fallback to `follow_link_weight`.

## Slice 12.10 — deterministic shared subjects

`adaptive_v3` now treats subject sharing across coordinated finite predicates as a
structural normalization rule instead of rediscovering the subject from the whole
clause. This keeps frames correct under Russian case ambiguity and adds no LLM call.
Prompt instructions are explicit required files: missing/empty probe prompts fail
fast rather than being replaced by hidden hardcoded instructions. See
`docs/SLICE_12_10.md`.
## Slice 12.12 — file-driven acceptance diagnostics

GUI contains `Прогнать acceptance-файл`. The suite is defined only by
`data/acceptance_cases.txt`: one user request per non-empty line; `#` comments and
blank lines are ignored. Replacing that file is enough to run a different suite.
All requests execute sequentially in one live AH/context session through the normal
sensory/perception/integration/inference/projection path.  The diagnostic runner
stops at `AgentContext`: it does not generate unrelated agent prose, repair or
reinterpret failures.

Each run is saved under `data/acceptance_runs/<timestamp>/` with per-turn
`LinguisticCandidateGraph`, decoded `PerceptionResult` (including runtime
`TemplateCandidate`), integration/query results, full parser/LLM diagnostics,
canonical AH diff, runtime/Workspace summary, InteractionContext and traceback on
failure. The bundle also contains the resolved config, initial/final context and AH
snapshots, final graph, manifest, summary and the exact cases file used. See `docs/SLICE_12_12.md`.

## Slice 12.13 — memory-bounded acceptance runs

Long acceptance batches now suspend live graph/status polling without stopping Ignition or changing cognitive execution. Per-turn runtime diagnostics no longer build a full semantic graph snapshot, JSON is streamed to disk, and complete AH diff snapshots are released before the next turn. The acceptance bundle format is unchanged. See `docs/SLICE_12_13.md`.


## Slice 12.15 — LLM generation memory isolation

Acceptance diagnostics no longer invoke the full LLM Agent after every parser case.
They stop at `AgentContext`, while preserving sequential AH/context, integration,
inference and all parser diagnostics. Perception probes explicitly run with
`use_cache=false`; normal interactive agent generation keeps `use_cache=true`. The
worker drops request-local generation tensors after every call and releases unused
CUDA allocator blocks after cache-enabled generation. See `docs/SLICE_12_15.md`.

## Slice 12.16 — deterministic lexical frames and strict finite probes

`adaptive_v3` now derives predicate `S` identity from deterministic morphology rather
than open-ended LLM naming, classifies obvious speech acts algorithmically, scores
only explicitly allowed answers for every remaining finite LLM probe, and prevents
rare morphology readings from creating structural predicate/subject candidates.
`TemplateCandidate` is finalized after frame normalization, serial comma-separated
predicates can inherit an omitted subject under explicit structural constraints, and
integration-validation failures still preserve the raw external turn in H without
committing rejected semantics. See `docs/SLICE_12_16.md`.

## Slice 12.18 — lexical identity, clause scope and proposition-safe composition

The parser/integration boundary now uses one source-language lexical identity across
Text Sensory and predicate T resolution, resolves turn-local `entity_ref` through a
named anchor before dependency-order integration, builds explicit WH queries, and
handles passive voice, fronted temporal/conditional connectors, relative binding,
control, contrastive negation and proposition-level OR deterministically where the
structure is sufficient. Unresolved pronoun and `с + instrumental` attachment
ambiguity fails explicitly instead of being guessed. Ignition/Hebbian dynamics are
unchanged in this slice. See `docs/SLICE_12_18.md`.


## Slice 12.19 — agreement, ellipsis and self-contained residual probes

The third fixed 40-case acceptance run exposed a small residual set after the broad
12.18 structural fixes. Predicate homographs are now ranked by grammatical sentence
force and explicit subject-number agreement instead of morphology dictionary order;
a remaining lexical tie fails explicitly. A resolved pronominal object can propagate
through a tightly licensed coordinated ellipsis (`открыла её и прочитала [её]`)
without generic previous-object fallback. Control-subject probes now include the full
source text plus known parent/child roles and entity-ref anchors. Copular adverbial
homographs are narrowed to descriptive roles before any LLM call. Explicit discourse
continuation markers may license one finite pronoun-coreference choice with mandatory
abstention, while unmarked genuine ambiguities still fail. See `docs/SLICE_12_19.md`.
