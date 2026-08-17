# AH Agent MVP — v0.12.58

Накопительный исполняемый проект АГ-памяти для текстового LLM-агента.

`docs/reference/Архитектура_v3.md` — архитектурный источник для реализации. Код строится так, чтобы каноническая память, runtime-динамика, inference и LLM boundary оставались отдельными слоями.

## v0.12.58 — structural ambiguity boundaries, not corpus patches

Этот срез продолжает single-shot `RuntimeRoleCue` из v0.12.57 и исправляет оставшиеся ошибки на границах до/после semantic role decision, не добавляя словарных правил под broad200:

- NOM/ACC и DAT/ACC синкретизм сохраняется как структурная неоднозначность; ordered case precedence больше не назначает `SUBJECT/RECIPIENT` там, где форма допускает конкурирующее чтение;
- postverbal NOM/ACC под устойчиво transitive predicate не считается однозначным `SUBJECT`;
- OR coordination получает ту же object-region структурную обработку, что AND;
- NP-internal genitive absorption выполняется только при отсутствии materially possible non-genitive core case;
- relative PP сохраняет governing preposition и использует тот же one-shot role cue; antecedent matching игнорирует нематериальные homonym readings служебных слов;
- бинарная lexical ambiguity проверяется двумя симметричными `YES/NO` hypothesis probes; ровно одна гипотеза должна подтвердиться;
- numeral включается в `DURATION` только после независимого semantic решения `DURATION`; counted `OBJECT + AMOUNT` не склеивается;
- local `candidate_ref`-content наследует P provenance до dependency-order Integration, если parent прямо anchored к SELF/USER;
- morphology-marked substantivized anaphor может выбрать только turn-local source label (`C1..Cn/UNCLEAR`), никогда canonical UID;
- fronted CONDITION включает contiguous additive consequent siblings.

Из последнего реального v0.12.57 broad200: raw evaluator дал `178/200`. Аудит oracle выявил восемь переограничений, требовавших искусственной noun-normalization для source-denoting adverbial/directional fillers; тот же сохранённый runtime bundle без повторного запуска переоценивается как `186/200` под `broad200-v3`. Это evaluator correction, а не новый product score. Реального broad200 для v0.12.58 ещё нет.

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
- неоднозначная entity/coreference reference после deterministic resolution материализуется как `k_AMBIGUOUS`;
- `k_AMBIGUOUS` запускает explicit clarification path, а не LLM-угадывание canonical entity;
- после явного ответа пользователя deterministic clarification resolver заменяет ссылку `k → m` в фактах;
- attachment ambiguity, которая ещё не выражена runtime alternatives, остаётся explicit error вместо silent commit;
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

- default LLM path `C:/AI/Qwen3.5-21B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking`;
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
    template_hidden_valency.txt       # diagnostics-only capability preflight
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

Since v0.12.38, `data/acceptance_cases.txt` remains the input corpus, while
`data/acceptance_oracle.json` is the separate semantic oracle. Runtime `OK/ERROR`
is retained only as execution diagnostics; acceptance quality is reported as
`SEMANTIC PASS / FAIL / ARCHITECTURE GAP`. Old bundles can be re-graded offline
against the oracle without rerunning the LLM. See `docs/SEMANTIC_ORACLE.md` and
`docs/SLICE_12_38.md`.

Since v0.12.47 the default suite is `broad200-v2`: 200 exact-oracle turns. The first
40 are the frozen corpus that reached real 40/40; 160 new cases add sixteen stress
families. The old corpus remains separately runnable via
`data/acceptance_cases_regression40.txt` + `data/acceptance_oracle_regression40.json`.
Oracle cases carry `family`/`tags`, and acceptance summaries report per-family
PASS/FAIL/GAP so broad failures can be diagnosed by mechanism rather than by one
global percentage. See `docs/ACCEPTANCE_CORPUS.md` and `docs/SLICE_12_47.md`.

Since v0.12.50 broad200 is **scenario-isolated**. The frozen first 40 still run as
one sequential regression scenario, but independent stress examples start from the
same acceptance baseline; only explicit learning/query chains share state. The runner
also restores the user's pre-run AH, InteractionContext and Ignition state after
diagnostics, so acceptance no longer pollutes working memory. See
`docs/SLICE_12_50.md`.

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

## Slice 12.20 — architecture-aligned dynamic T and ambiguity handling

Raw Perception no longer treats the roles filled by one occurrence as the reusable
`TemplateCandidate`. Unknown predicates are detected by deterministic preflight,
routed back to Perception for a finite role-schema proposal, then validated and
registered as one canonical `T`; later role expansion fails explicitly because
valency evolution is deferred. Pronoun/control uncertainty is preserved as runtime
`AssertionCandidate.alternatives` and becomes canonical `k_AMBIGUOUS` only after
deterministic Entity Resolution. Query/Command acts also participate in Predicate/T
Resolution without creating asserted facts. Ignition is unchanged. See
`docs/SLICE_12_20.md`.


## Slice 12.21 — end-to-end clarification lifecycle

Canonical `k_AMBIGUOUS` is no longer only a terminal diagnostic marker. Integration
returns a structured `ClarificationRequest` containing the ambiguous mention,
user-visible candidate labels and affected fact/role positions. In interactive mode
the orchestrator calls a dedicated `agent_clarification` LLM role that may only
verbalize the deterministic options; it cannot select a canonical member itself.

The emitted clarification arms runtime `InteractionContext.pending_clarification_refs`
(and that queue is persisted). The next user utterance is handled as clarification
evidence, not promoted to an independent C/P assertion. Exact candidate-name/number
answers resolve deterministically; otherwise a tiny `perception_clarification_answer`
probe may identify which already-presented option the new answer explicitly names.
Integration validates that option against `k.members` and atomically replaces
`k_AMBIGUOUS → selected m` across canonical uses. If the corrected N collides with an
already canonical fact, domain-local N dedup is preserved and references are redirected.
Diagnostic acceptance runs with `generate_response=False` expose clarification
requests but do not arm pending dialogue state. See `docs/SLICE_12_21.md`.

## Slice 12.22 — structural relation normalization and stronger Perception narrowing

Perception now normalizes inter-situation semantics before Integration: when a
causal child is already represented by canonical `CAUSE` or a directional temporal
clause by `FOLLOW`, the same child is no longer duplicated as `N.CAUSE` / `N.TIME`.
Entity-valued CAUSE/TIME actants are unaffected. Candidate validation rejects an
externally supplied duplicate encoding as malformed input.

Dynamic `TemplateCandidate` discovery is now hierarchical and atomic for weak models:
first a binary omitted-role decision, then role family, then one exact canonical role.
The model is explicitly told to include TIME/LOCATION/CAUSE/PURPOSE only when the
predicate sense lexically selects that complement rather than because every event may
have incidental circumstances. Strict one-`T` reuse and deferred valency evolution
remain unchanged.

Deterministic linguistic narrowing also gains dominant-paradigm lexical normalization
(`Петру → Пётр` while equal-score homonymy remains unresolved), material morphology
filtering for coreference, conservative same-role continuity after explicit discourse
markers (`Потом/Затем/...`), and lexical spatial-adverb recognition (`дома` → LOCATION).
`с + instrumental` noun-vs-predicate attachment remains an explicit Perception error:
the current architecture has no canonical noun-modifier representation that would let
us encode both readings without inventing a false `N`/actant. See `docs/SLICE_12_22.md`.


## v0.12.25

- Restored live VisPy canvas rendering during file-driven acceptance runs.
- Acceptance no longer disables `GraphCanvasWidget` live updates.
- The duplicate heavy runtime/status snapshot poll remains paused during acceptance; LLM diagnostics remain live.
- No semantic/runtime changes relative to v0.12.24.

## v0.12.26

- Replaced recursive TemplateCandidate discovery with one bounded template probe.
- Kept strict existing-T reuse and deferred valency evolution.

## v0.12.27

- Reworked TemplateCandidate discovery for weak SLMs: deterministic code keeps all observed roles and the model may add at most one latent core role from a tiny fixed shortlist.
- `perception_template_hidden_role` uses exact fixed-choice scoring; there is no free schema generation, ontology walk, explanatory output, or recursive follow-up.
- Service prompts and protocol instructions are English. Semantic protocol labels are English; only literal token/span addressing remains numeric.
- Top-level Perception/Agent/System prompts and legacy parser system prompts were translated to English. User text itself remains in its source language.
- Live acceptance canvas behavior from v0.12.25 is unchanged.



## v0.12.28

- Replaced semantic abstention labels in critical SLM probes with pairwise `YES/NO` hypothesis tests.
- Fixed-choice worker now returns per-choice log-likelihood scores and a separation margin; low-margin decisions remain unresolved parser evidence and never become AH truth confidence or `w`.
- Dynamic T discovery tests one deterministic hidden-role hypothesis at a time (`RECIPIENT`, then `SOURCE` where structurally applicable) and stops at the first confident YES.
- Nested-frame semantics are hypothesis-driven: `CONTENT`, `PURPOSE`, `CAUSE`, and `MANNER` are tested independently instead of one multi-class + `NONE` choice.
- Control-subject ambiguity is reduced to one candidate controller per YES/NO probe; one controller remains deterministic.
- Ambiguous role-family / exact-role classification uses ordered pairwise YES/NO hypotheses and stops on the first confident match.
- Discourse sequencing adverbs such as `Потом`/`Затем` compile deterministically to `FOLLOW`; the temporary TIME actant is removed instead of creating `M("Потом")`.
- All critical semantic service prompts remain simple English.

## v0.12.29

- Replaced universal semantic YES/NO with contrastive fixed-choice labels and one direct mutually-exclusive controller choice.
- Acceptance diagnostics now preserve `choice_outputs`, per-choice scores, winner, margin, threshold and accepted/rejected status.
- Existing-T reuse, deferred valency evolution, clarification and live acceptance canvas remain unchanged.

## v0.12.30

- Preserves dictionary grammemes in `MorphInfo` and uses stable `tran/intr` evidence inside Perception to settle the hidden direct-object slot before any SLM call.
- Remaining latent slots use concrete English slot questions (`TAKES_RECEIVER`, `TAKES_SOURCE`, etc.) rather than abstract argument-schema labels.
- Low-margin hidden valency is fail-closed: no narrower canonical T is registered when the reusable schema is unresolved.
- Nested frame attachment now uses relation-specific micro-decisions (`CONTENT_LINK`, `GOAL_LINK`, `CAUSE_LINK`, `MANNER_LINK`).
- Low-margin frame attachment is an explicit Perception ambiguity/error; it can no longer silently degrade into independent events.
- Bare `что` subordinate clauses are narrowed to the CONTENT hypothesis; causal compound markers keep their deterministic CAUSE representation.
- Direct controller choice, score diagnostics, FOLLOW/CAUSE normalization, clarification lifecycle and live VisPy acceptance rendering are preserved.


## v0.12.31

- Removed hidden-role ontology walking from dynamic TemplateCandidate discovery.
- SUBJECT/OBJECT are resolved first by deterministic grammar/dictionary evidence; unknown direct-object grammar uses one English `TAKES_DIRECT_ACCUSATIVE / NO_DIRECT_ACCUSATIVE` probe.
- Russian finite active plural with no overt nominative participant can deterministically contribute an omitted SUBJECT slot to T (for example, `Мне дали книгу`), while the concrete N may leave SUBJECT unfilled.
- Hidden RECIPIENT/SOURCE discovery is gated by one finite event-type cue: `TRANSFER_TO_RECEIVER`, `COMMUNICATE_TO_ADDRESSEE`, `ACQUIRE_FROM_SOURCE`, or `OTHER_EVENT`.
- One event cue can add at most one hidden directional role; if RECIPIENT or SOURCE is already observed, semantic role discovery stops immediately.
- Low-margin event classification remains fail-closed before canonical T creation, preserving deferred valency evolution.
- Relation-specific frame attachment, direct controller choice, score diagnostics, clarification and live VisPy acceptance rendering are unchanged.


## v0.12.32

- Replaced four-way semantic output labels in hidden directional-role discovery with two tiny ordinal `FIRST/SECOND` decisions.
- Each binary semantic cue is scored twice with its option descriptions swapped. Python maps answers back to semantic alternatives and accepts only swap-consistent results; positional/token bias becomes explicit ambiguity rather than canonical T pollution.
- Directional discovery remains bounded: first decide whether a normal receiver/addressee/destination/source/origin participant exists; only then decide recipient-side vs source-side. At most one hidden directional role is added.
- Template transitivity now reuses the predicate lexeme already resolved by raw Perception before considering surface-form homographs. Explicit subject-number agreement further removes grammatically incompatible readings before `tran/intr` consensus.
- `Иван и Мария пришли и ушли` therefore resolves `прийти/уйти` as intransitive without an OBJECT SLM probe when morphology exposes competing singular imperative transitive homographs.
- Relation-specific nested-frame probes, direct controller choice, omitted-agent grammar, fail-closed `[DEFER]`, clarification and live acceptance rendering are unchanged.

## v0.12.33

- Replaced hidden directional-role `FIRST/SECOND` scoring with **semantic completion likelihood**. The model now scores three complete English statements: recipient/addressee/destination, source/origin, or neither.
- Added content-free calibration in the worker: every semantic continuation is scored under the real Russian verb context and under an otherwise identical `UNKNOWN_VERB` context; deterministic Perception ranks `score(real) - score(neutral)`.
- Acceptance diagnostics now persist raw continuation scores, neutral-baseline scores, calibrated scores, raw margin, calibrated margin, and the scoring mode. Parser margin gating uses the calibrated margin only; it remains parser evidence and never maps to AH truth or `w`.
- Added a dedicated semantic-completion system prompt so these likelihood requests are not contaminated by the ordinary “return a protocol label” instruction.
- Removed active `template_event_directionality` / `template_event_direction` prompts and their swap-and-agree runtime path. Directional discovery remains one bounded semantic decision and can add at most one hidden `RECIPIENT` or `SOURCE`.
- `PURPOSE -> infinitive` frames with exactly one parent `OBJECT` now use deterministic object-control inside Perception. This removes the biased ordinal controller probe for `просить X + infinitive` while leaving canonical `N` construction to Integration.
- Existing morphology/lexeme filtering, relation-specific frame attachment, omitted-agent grammar, strict existing-T reuse, `[DEFER]` valency evolution, explicit ambiguity, and live acceptance rendering remain unchanged.


## v0.12.34

- Added predicate-specific source context and noncanonical textual role bindings to dynamic `TemplateRequest` preflight.
- Hidden directional scoring was retargeted from broad event participants to additional valency slots beyond already-known roles.
- Canonical AH UIDs remained outside Perception prompts and low calibrated margins stayed fail-closed under deferred T valency evolution.


## v0.12.39

- Implemented controlled monotonic canonical `T` evolution from validated explicit semantic evidence: `Roles(T_old) ⊆ Roles(T_new)` while the canonical T UID remains stable.
- Existing `N` are not rewritten when `T` expands; concrete hypernodes may continue to leave newly learned roles unfilled, as required by the architecture.
- Query `requested_role` is schema evidence: it may expand `T` without creating a factual actant value or an `N`.
- Production TemplateCandidate construction now contains only roles already present in the parsed assertion/query/command. Hidden SUBJECT/OBJECT/RECIPIENT/SOURCE prediction no longer participates in canonical T creation.
- Removed the retired template-guessing morphology/SLM path and its unused prompt files. `template_hidden_valency` remains only for the standalone model capability diagnostic and has no canonical write authority.
- Speculative extra roles in a runtime `TemplateCandidate` are not committed without current explicit evidence.
- Legacy memories with several incompatible `T` for one lexical `S` remain fail-closed when deterministic Integration cannot choose which frame to expand; that is treated as lexical-sense ambiguity, not valency merging.
- Updated the normative Architecture_v3 reference to working specification v0.5: controlled monotonic T evolution is now part of MVP and removed from `[DEFER]`.
- The semantic oracle remains the acceptance criterion. This slice intentionally does not tune prompts or claim that the remaining control/domain/conditional/attachment errors are solved.

## v0.12.38

- Replaced `no exception = acceptance success` as the quality metric with a curated semantic oracle in `data/acceptance_oracle.json`; the 40 input sentences remain separately editable in `data/acceptance_cases.txt`.
- Acceptance runs now report `SEMANTIC PASS`, `SEMANTIC FAIL`, and `ARCHITECTURE GAP` in addition to runtime `OK/ERROR`, and persist per-check semantic verdicts plus the exact oracle used.
- Added offline re-grading of existing acceptance bundles, so parser/model changes are not required merely to improve the evaluator.
- Added cumulative explicit-role coverage checks for canonical `T`: later explicit assertion/query evidence must be representable by the predicate schema; speculative hidden roles are not required by the oracle.
- Re-graded the supplied v0.12.37 40-case run as `27 PASS / 9 FAIL / 4 GAP` despite `33 OK / 7 ERROR`, exposing semantic defects that the old crash-only counter could not see.
- Added `docs/ARCHITECTURE_AUDIT_01238.md`. The audit keeps the LLM→runtime-candidate→deterministic-Integration boundary, but concludes that one-shot hidden template-valency guessing should leave the production critical path.
- The audit explicitly **un-defers controlled monotonic T valency evolution as the next required implementation**, because concrete `N` may fill only a subset of `T` roles and later validated explicit syntax must not be blocked by a first-use incomplete schema. `[DEFER]` is treated as a scope decision, not an absolute prohibition.
- No production perception/integration behavior is intentionally changed in this slice; v0.12.38 is the measurement and architecture-revision baseline before simplifying the parser.


## v0.12.37

- Added a diagnostics-only hidden-valency capability preflight: 6 semantic cases × both binary label orders = 12 real calls to the same local Qwen backend.
- Each case is classified as `SEMANTIC_OK`, `ORDER_BIAS`, `SEMANTIC_WRONG`, `INCONSISTENT`, or `MALFORMED`; the report also counts first-position selections across all calls.
- The diagnostic uses the exact production hidden-valency prompt shape but may reverse the two choices. Production hidden-valency behavior and strict fail-closed validation are unchanged.
- The already-observed trailing orphan `</think>` is separated from semantic choice only inside diagnostics: protocol compliance remains visible as `EXACT` vs `RECOVERED_ORPHAN_THINK_CLOSE`, while explanations or other extra text stay malformed.
- The preflight never invokes Orchestrator/Integration or AH writes. Ignition is paused and restored around the run, and an exact canonical before/after diff is required to be empty.
- GUI now exposes `Hidden-valency preflight` next to the acceptance button and automatically writes a small timestamped diagnostic directory plus a ZIP bundle for upload/analysis.

## v0.12.36

- Replaced the five-way hidden-valency generation protocol with sequential ordinary binary generation.
- The first call tests only `HAS_RECIPIENT_SLOT` vs `NO_RECIPIENT_SLOT`; only an exact negative reaches a second call testing `HAS_SOURCE_SLOT` vs `NO_SOURCE_SLOT`.
- A positive RECIPIENT answer stops the procedure, so hidden discovery can add at most one directional slot. `RECIPIENT,SOURCE` and `AMBIGUOUS` are no longer active hidden-valency outcomes.
- Both calls use temperature-zero normal generation with no `choice_outputs`, logprob scoring, margins, calibration prompt, token probabilities, or scorer fallback.
- Hidden-valency output is strict fail-closed: after outer whitespace trimming, anything other than the exact expected binary label is rejected before `TemplateCandidate` acceptance.
- The prompt carries only the source sentence, lexical verb, textual known-role bindings, one narrow English question, and two English labels. Canonical AH refs/UIDs remain outside Perception.
- Retired hidden-valency scoring/system prompt files were removed from the active prompt set; deterministic Integration still owns validation, UID allocation, T registration and atomic AH mutation.

## v0.12.35

- Replaced hidden directional-valency logprob/calibration classification with one ordinary bounded generation from the same local Qwen parser model.
- `perception_template_hidden_valency` receives only the source text, predicate surface/lexeme, and textual `ALREADY KNOWN ROLE BINDINGS`.
- The only accepted protocol lines are `NONE`, `RECIPIENT`, `SOURCE`, `RECIPIENT,SOURCE`, and `AMBIGUOUS`; explanatory or unknown output is an explicit Perception protocol error.
- `AMBIGUOUS` remains fail-closed before canonical T creation. `RECIPIENT`/`SOURCE` labels are mapped to runtime roles by Python; Integration still validates/registers canonical T and owns all AH mutation.
- Hidden-valency generation sends no `choice_outputs`, score request, calibration prompt, margin threshold, UID, or canonical AH reference.
- Deterministic morphology, direct-object grammar, omitted-agent handling, nested-frame semantics, object-control, strict existing-T reuse, and live acceptance rendering are unchanged.


## v0.12.40

- The real v0.12.39 semantic run measured `32 PASS / 4 FAIL / 4 GAP`; all template-evolution cases 14–21 passed, validating controlled monotonic T growth.
- Binary semantic decisions now use strict temperature-zero label generation. A valid binary label is no longer vetoed by the legacy continuation-score margin; no `choice_outputs`/score request is sent for two-choice probes.
- Nested wanted/requested/selected situations are represented as `OBJECT -> candidate_ref(child)` content. `PURPOSE` is reserved for the actual goal of performing the parent action.
- Animate accusative participants are narrowed to `OBJECT` versus `RECIPIENT` instead of being forced to OBJECT; controller identity is resolved independently. The retired `PURPOSE + OBJECT` controller shortcut was removed.
- Relative antecedent identity may reuse a containing parent actant span when the normalized semantic head matches, fixing cases such as `рядом с журналом ... который ...` without a domain-specific special case. Shared turn-local identity then preserves P provenance through normal DomainRouter behavior.
- Architecture reference advanced to working specification v0.6. The four current `ARCHITECTURE_GAP` cases (three CONDITION structures and general prepositional attachment clarification) are intentionally untouched in this slice.


## v0.12.42

- Real v0.12.41 semantic acceptance baseline: **34 PASS / 2 FAIL / 4 GAP**. The only two FAIL cases share the same `попросить + infinitive` content/participant reconciliation root.
- A positive `CONTENT_LINK` is now semantically sticky inside one parse hypothesis: later failure to reconcile an occupied entity-valued `OBJECT` cannot silently reinterpret the same child as `PURPOSE`, `CAUSE`, or another relation. The parser fails closed on the unresolved role conflict instead.
- The post-structural participant probe remains binary and is narrower: after proposition-valued `OBJECT` content is already established, it asks only whether the explicit participant is the receiver/addressee/target of the parent action (for example the person being asked or told).
- The default local model remains `C:/AI/Qwen3.5-21B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking`.
- Architecture_v3 is updated to working specification v0.8 with semantic-relation monotonicity inside a parse hypothesis: downstream reconciliation may refine participant roles but may not overwrite an already accepted parent-child relation.

## v0.12.41

- Corrected the v0.12.40 regression that asked the LLM to classify every animate/pronominal accusative as `OBJECT` vs `RECIPIENT`. Ordinary accusatives are deterministic `OBJECT` again.
- Added a much narrower `RECIPIENT / NOT_RECIPIENT` decision only after a nested proposition has independently been classified as semantic `OBJECT` content and creates a real OBJECT-slot conflict.
- Controller `FIRST/SECOND` prompts now keep participant descriptions outside the exact `CHOICES`, preventing descriptive pseudo-label output.
- Entity name/alias lookup is now provenance-aware: strong `SELF/USER`, `candidate_ref`, or turn-local `entity_ref` evidence may lock lexical lookup to a provisional semantic domain, so a same-name entity in another domain cannot hijack identity.
- Global lexical lookup remains available when no strong provenance exists; ambiguity is still explicit rather than silently merged.
- Architecture_v3 is updated to working specification v0.7 with delayed semantic-decision, bare-label protocol, and retrieval-vs-identity invariants.
- Added `tests/test_semantic_roots_1241.py` covering ordinary object pronouns, discourse coreference, request/content recipient reclassification, controller protocol shape, and cross-domain same-name isolation.
- This slice is a regression correction based on the real v0.12.40 result (`31 PASS / 6 FAIL / 3 GAP`), not a claim of a new 40-case result. A fresh model acceptance run is required.


## v0.12.43

- The post-structural content-participant probe no longer asks the model to emit the canonical AH role `RECIPIENT`.
- The bounded semantic cue is now `CONTENT_ADDRESSEE / NOT_CONTENT_ADDRESSEE`: whether already-proven proposition content is directed to the explicit participant as the person being asked/told/advised/instructed/addressed.
- Python maps positive `CONTENT_ADDRESSEE` deterministically to runtime `ActantRole.RECIPIENT`; Integration remains the only canonical writer.
- `CONTENT_LINK` remains sticky: a negative/invalid addressee cue fails closed and cannot reinterpret the child as PURPOSE/CAUSE/HOW_TO.

## v0.12.44 — canonical conditionals + structural clarification

- Real v0.12.43 acceptance baseline is **36 semantic PASS / 0 FAIL / 4 GAP**. The two former `попросить + infinitive` failures are fully resolved by the `CONTENT_ADDRESSEE` cue; no known semantic FAIL remains in the 40-case oracle.
- Conditional branches are now canonical proposition content rather than H-text-only safety placeholders. Each branch is stored as `N` with `meta.semantic_scope = CONDITIONAL`; scoped propositions do not satisfy ordinary `EXISTS` / `ROLE_FILL`.
- Added deterministic `g.IF(antecedent, consequent)` to `FunctionRegistry`. Multi-member antecedent/consequent sides use `g.AND`, preserving `(A AND B) -> C` and `A -> (B AND C)` instead of incorrect pairwise condition links.
- Scoped `N` participates in canonical signatures, so a conditional proposition and a later independently asserted fact with identical T/actants remain distinct semantic objects.
- General `с + instrumental` attachment ambiguity after a direct object now produces an H-level **structural clarification** instead of a parse exception or LLM guess. No C/P reading is committed before explicit user selection.
- Structural clarification replays the original source with a program-owned resolution key and attaches delayed semantics to the **original H experience**, avoiding duplicate source experiences.
- Diagnostic/acceptance turns with `generate_response=False` surface structural clarification in the commit but do not arm pending dialogue state, so the next independent acceptance case is never consumed as a clarification answer.
- `data/acceptance_oracle.json` now treats cases 30–32 as exact canonical IF semantics and case 39 as exact successful clarification behavior. A correct ambiguous result is therefore PASS, not ERROR/GAP.
- Architecture reference advanced to working specification **v0.10** with scoped propositions, canonical IF/AND condition semantics and the general structural-clarification contract.
- No claim of real `40/40` is made until this build is rerun with the selected Qwen model; local tests verify mechanics and oracle contracts only.



## v0.12.45 — case-syncretic morphology + no partial semantic frames

- Real v0.12.44 semantic acceptance reached **39 PASS / 1 FAIL / 0 GAP**; CONDITION cases 30–32 passed.
- Preserves lower-scored case readings when they belong to the same nominal lexeme and differ only in syntactic case-relevant analysis, fixing context-free pymorphy priors such as `Петра` genitive vs accusative.
- A selected semantically relevant actant with unresolved role now fails closed instead of being silently dropped and allowing a partial canonical frame.
- This routes case 39 back into the already implemented H-only structural clarification mechanism without an extra LLM role decision.
- Architecture reference advanced to working specification v0.11.


## v0.12.46 — semantic-oracle H chronology correction

- Real v0.12.45 run: runtime **40/40**, semantic **39 PASS / 1 FAIL / 0 GAP**. The only failing check was evaluator-only: case 39 had correct H-level structural clarification but `cp_semantic_addition_count` treated its normal H→H `FOLLOW` chronology link as a C/P semantic write.
- `cp_semantic_addition_count` now classifies domainless links by their endpoint domains. `FOLLOW(H→H)` is excluded; links touching C/P remain semantic additions.
- The exact saved real run regrades offline as **40 PASS / 0 FAIL / 0 GAP**. Production parser/integration behavior is unchanged.
- `Архитектура_v3.md` remains working specification v0.11 because this slice changes diagnostics only, not the product semantics.




## v0.12.50 — scenario-isolated broad acceptance

- The completed broad200 run (`107 PASS / 93 FAIL`) exposed strong cross-case contamination: independent examples accumulated duplicate same-name entities and generated later `AMBIGUOUS_REFERENCE` structures.
- Oracle cases now carry a `scenario` id. Canonical AH, InteractionContext and Ignition state reset to the run baseline when the scenario changes.
- The frozen 40-case regression remains one sequential scenario; intentional T-evolution and query pairs remain sequential inside their own scenarios.
- Acceptance pauses the Ignition clock for determinism and restores the user's complete pre-run cognitive state when the suite ends. The loaded LLM process is reused and is not restarted.
- Offline re-grading mirrors the same scenario boundaries.
- Production Perception, Integration, AH Core semantics and Architecture v0.11 are unchanged.

## v0.12.49 — acceptance evaluator resilience

- Fixes the broad200 acceptance crash when an inference query record contains `outcome=null`: the semantic oracle now grades it as a normal failed query outcome instead of calling `.get()` on `None`.
- Adds a diagnostics boundary around semantic-oracle evaluation. An evaluator defect is written into the turn bundle as `oracle.evaluation_error` and the remaining corpus continues instead of being truncated.
- Hardens manifest failure extraction against malformed diagnostic checks.
- Production Perception, Integration, AH Core semantics, prompts, broad200 corpus, and Architecture v0.11 are unchanged.

## v0.12.48 — atomic diagnostics snapshots + broad-run graph suspension

- `GraphInspector.snapshot()` now reads the whole canonical/runtime graph under the shared `RuntimeServices.operation_lock`. This prevents GUI snapshots from observing a pre-GC runtime UID together with post-GC canonical indexes.
- `RuntimeDiagnostics.summary()` uses the same read barrier for consistent multi-read summaries.
- `RuntimeServices.build()` wires both diagnostic readers to the same lock already used by IgnitionClock and orchestrator canonical mutations.
- During broad acceptance runs the VisPy graph refresh loop is paused; cognitive runtime and Ignition continue normally. The graph resumes with one fresh snapshot when the run ends.
- Production Perception/Integration/AH semantics and `Архитектура_v3` v0.11 are unchanged.

## v0.12.47 — broad200 semantic acceptance corpus

- Default semantic suite expanded from 40 to **200** sequential exact-oracle cases.
- Original real-40/40 corpus preserved verbatim as `acceptance_*_regression40`.
- Added 160 cases across 16 new stress families: lexical frames, transfer/recipient, adjunct roles, T evolution, coordination, coreference, relative clauses, nested content, temporal/causal, conditionals, negation, passive/impersonal, WH queries, personal provenance, ambiguity and morphology case pressure.
- Oracle cases now support `family` and `tags`; live/offline reports aggregate semantic results by family.
- Production parser, Integration, AH Core and Architecture_v3 are unchanged. The expanded corpus is intentionally expected to discover new FAILs rather than preserve the old score.

## v0.12.51 — broad200 oracle audit correction

The first scenario-isolated broad200 run exposed two diagnostics defects rather than
production semantic defects. `broad200-v2` now expects the explicit `FOLLOW` relation
in case 100 (`затем`) and `cp_semantic_addition_count` no longer counts a canonical T
that exists only as the template wrapper of a newly added H `event_instance`.
Production Perception/Integration/AH semantics remain unchanged.


## v0.12.53 — generic binary semantic role router

v0.12.53 supersedes the over-specialized v0.12.52 role-narrowing attempt. The
production parser no longer contains the broad200-driven temporal word list,
duration-unit list, bare-instrumental TOOL/HOW_TO shortcut, `из` SOURCE/MATERIAL
shortcut, `чем` role whitelist, or morphology filters introduced specifically after
`Анне`/`вазу` failures. Those forms remain regression data, not production rules.

The retained architectural mechanisms are general: finite subject-predicate
agreement may reject a grammatically impossible SUBJECT reading; a governing
preposition is preserved as part of question evidence but is not mapped directly to
an AH role; and unresolved semantic roles are routed through a binary natural-cue
decision tree. Every model decision in role routing has exactly two protocol labels,
uses ordinary deterministic generation, and never invokes the legacy multi-choice
scorer/margin path. Any role subset established by valid earlier structure can only
shrink during this routing. See `docs/SLICE_12_53.md`.

## v0.12.54 — neutral role partitions + contextual lexical disambiguation

The broad200 v0.12.53 run established a stable real baseline of **158/200 semantic PASS** with the frozen regression40 still at **40/40**.  The largest remaining failures showed two architecture-level issues rather than missing word rules:

- intermediate role labels such as `ENTITY_OR_CONTENT_RELATION` and `CIRCUMSTANTIAL_MODIFIER` had their own ordinary-language meaning, which overlapped the hidden canonical partition and could bias a weak local model;
- dictionary morphology could expose two materially plausible lexemes for one surface form, while analyser score/order was being consumed before sentence context could disambiguate lexical identity.

v0.12.54 therefore keeps every role model decision binary but makes the protocol labels semantically neutral: the model returns only `A` or `B`, while the prompt shows the natural-language meanings of the *actual remaining role sets*.  Python alone owns the mapping from A/B to the surviving `ActantRole` candidates.

For genuine two-lexeme morphology ambiguity, Perception now performs one separate A/B `lexeme_identity` probe.  The selected lexeme only filters morphology evidence; it never writes canonical AH semantics.  The same boundary is used for predicate homographs.  More-than-binary lexical ambiguity fails closed instead of being collapsed by dictionary probability.

No broad200 sentence literal was added to production code, and the acceptance corpus/oracle are unchanged.

## v0.12.55 — relation contracts + lexical-decision monotonicity

The real v0.12.54 broad200 run reached **159/200 semantic PASS** with **198/200 runtime OK** and kept the frozen regression40 at **40/40**.  The dominant remaining adjunct failures showed that neutral A/B labels alone were not sufficient: several canonical-role glosses still overlapped in ordinary language (`TOOL` vs `MATERIAL`, `TIME` vs `HOW-TO`, `SOURCE` vs neighboring relations).

v0.12.55 keeps the same binary A/B protocol but turns each role description into a relation contract about the current `TARGET` and event.  Neighboring roles explicitly state their semantic boundary (for example, a TOOL is a separate implement used to perform the event, while MATERIAL is a constituent substance of an affected/result object).  Purely adverbial morphology may now exclude nominal participant/tool/material roles as negative POS evidence, but it never directly assigns TIME/LOCATION/HOW-TO/etc.

Lexical A/B prompts now expose the analyser morphology profile of each candidate (POS/case/number/gender and selected grammeme markers).  Once a nominal lexeme is contextually selected, `normalized_hint` reuses that exact selection instead of reopening homonymy through a later `stable_normal_form()` call.  Predicate lexeme probes receive the same morphology profiles, including passive-participle vs adjective evidence.

A relative-antecedent lookup no longer calls `.casefold()` on a missing normalized form; it falls back to source mention safely.  Finite SUBJECT agreement is also respected when a contextually selected nominative candidate is considered, while AND-coordinated nominative subjects correctly count as plural.

No broad200 sentence literal or new lexical role table was added.  The corpus/oracle remain `broad200-v2`; a fresh real-model run is required before claiming any score above the confirmed 159/200.

## v0.12.56 — semantic-property role routing

The real v0.12.55 broad200-v2 run reached **171/200 semantic PASS**, **199/200 runtime OK**, and kept the frozen regression40 at **40/40**. The remaining adjunct/query traces exposed a general routing defect: even with good relation contracts, an early A/B choice between large heterogeneous role groups could eliminate the correct role before its own relation was directly tested.

v0.12.56 replaces that family partition with independent binary semantic-property probes. Each model call answers only `YES` or `NO` for one natural relation property (temporal, non-temporal measure, cause/goal, means/material/manner, place/transfer endpoint, or predicated state). Python owns the exact canonical-role subset for the property. `NO` removes only that subset; `YES` selects it and any remaining local ambiguity is resolved by a small A/B contrast. A pre-existing `allowed_roles` set can only shrink.
 The obsolete family-router helpers/constants are removed instead of remaining as a dormant second routing path.

The legacy direct `из/от -> SOURCE` shortcut is removed: a governing preposition remains evidence but no longer proves SOURCE by itself. v0.12.56 also adds a generic NUMERAL+nominal structural boundary. One binary cue distinguishes a counted participant from a whole event/state measure; the latter fuses the phrase and routes only within DURATION/AMOUNT. No unit-word lexicon is introduced.

The broad200 corpus/oracle remain `broad200-v2`. No score above the confirmed **171/200** is claimed until a fresh real-model run of v0.12.56.


## v0.12.57 — single-shot runtime role cues

The real v0.12.56 broad200-v2 run regressed to **163/200 semantic PASS** with **199/200 runtime OK** while the frozen regression40 remained **40/40**. Raw traces showed the cause: the semantic-property ladder multiplied false-negative opportunities. A correct TOOL/TIME/SOURCE/MATERIAL reading could be rejected by one early `NO`, after which the residual participant router produced a formally valid but wrong role.

v0.12.57 therefore supersedes the v0.12.56 property ladder. Deterministic morphology/syntax still removes only formally impossible roles, but unresolved role semantics are now delegated as **one bounded decision for one TARGET**. The model returns exactly one non-canonical `RuntimeRoleCue` such as `INSTRUMENT`, `ORIGIN`, `TIME_POINT`, or `CONSTITUENT_MATERIAL`; Python alone maps the cue to an admissible `ActantRole`. The prompt contains only roles that survived deterministic narrowing. Role-cue generation uses ordinary deterministic generation, not likelihood choice scoring, margins, or a hidden tournament. Malformed or out-of-set labels fail closed.

The direct `из/от -> SOURCE` shortcut remains removed, so those prepositions are evidence rather than canonical decisions. The experimental v0.12.56 NUMERAL+nominal post-normalizer is not retained in this slice because the real run showed it could collapse a counted entity into a whole-event measure; quantified structure will be revisited as its own architecture task.

A separate deterministic coreference fix uses explicit grammatical person only as negative compatibility evidence: a `3per` anaphor cannot create a local alternative to an explicit `1per/2per` deictic antecedent. This prevents spurious cross-role correlated alternatives such as treating third-person `её` as potentially identical to the current speaker, without asking the LLM to choose an entity.

Architecture is **v0.16**. The broad200 corpus/oracle remain unchanged. The confirmed real score remains **163/200 for v0.12.56** until v0.12.57 is run on the local model.


## 2026-08-17 MVP freeze / memory-runtime hardening

Formalization is time-boxed for the hackathon MVP after the real Qwen broad200 reached **154/200 semantic PASS with 198/200 runtime OK**. Broad200 is no longer a normal iteration gate; use the deterministic/unit suite and `tests/test_mvp_memory_smoke.py`.

Memory-runtime fixes in the freeze slice:

- pacemaker-only provenance survives causal propagation/residual excitation and never becomes `h`/lifecycle experience;
- H dialogue `event_instance` nodes are protected from ordinary TTL GC, so a slow local LLM cannot delete the current turn while thinking;
- the LLM worker refuses silent left-truncation of AgentContext and enforces the configured context token limit against exact tokenizer output;
- the MVP decay profile uses `alpha=0`, because non-zero asymptotic `x` plus `output=x_act` and additive activation leaves a permanent impulse source and eventually saturates downstream Workspace nodes; long-term memory remains canonical AH/weights/lifecycle, not residual excitation;
- naive reverse `actant→N` hyperedge propagation was experimentally rejected for MVP because it creates uncontrolled recurrent saturation under the current additive activation policy.

See `docs/FORMALIZATION_FREEZE_20260817.md` and `docs/MVP_MEMORY_AUDIT_20260817.md`.
