# AG Memory v4 progress

## Added runtime formal primitives

- `BoundVar` and `Operand` are runtime logical primitives, not AH nodes.
- Scope containers support future nested logical contexts.
- Existing canonical model `S/M/T/N/L/g/k/H` remains unchanged.

## Invariants

- IS-A, FOLLOW and CAUSE remain core M2 relations.
- Activation is not proof.
- Runtime inference state is not persistent memory.

## Progress 02

Added inference runtime foundations:

- `BindingEnvironment` for scoped variable resolution. Runtime only; never canonical AH memory.
- `ProofSupport` as a separate dependency/provenance layer from `ProofTrace`.
- `InferenceOutcome` can now carry proof support and runtime bindings without changing existing M2 conclusion flow.

Invariants preserved:
- IS-A / FOLLOW / CAUSE semantics unchanged.
- Activation is not proof.
- Runtime inference state is not canonical memory.

## Progress 03 — formula operands, explicit inference schemas, proof dependencies

Этот шаг переводит ранее добавленные заготовки в рабочий контур без изменения обязательной семантики M2.

### Формулы и переменные

- `FunctionSymbol.operands` допускает `Ref | BoundVar`.
- `BoundVar` остаётся scoped descriptor без AH UID и без activation state.
- Добавлены sorts `ENTITY / PROPOSITION / TIME / VALUE / EVENT / UNKNOWN`.
- Persistence сохраняет и восстанавливает `BoundVar` внутри `g`; старый JSON shape для обычных `Ref` остаётся совместимым.
- Все обходы AH (`function_parents`, projection, discourse, clarification, graph diagnostics) учитывают, что `BoundVar` не является canonical ref и не должен индексироваться/возбуждаться.

### Runtime proof context

- `BindingEnvironment` получил parent/child scopes, shadowing и sort checks.
- Добавлен runtime-only `ProofContext` с bindings/assumptions/local-derived/admissibility filters.
- `InferenceOutcome` переносит `proof_context` и bindings только для диагностики/следующих reasoning-расширений; это не canonical memory.

### InferenceSchemaRegistry

- Логические свойства больше не обязаны жить в локальном hardcode reasoner-а.
- Default registry явно фиксирует:
  - `IS-A` — transitive;
  - `FOLLOW` — transitive;
  - `CAUSE` — non-transitive, rule handlers `CAUSE_MP`/`CAUSE_PATH`.
- Неизвестное отношение консервативно получает пустую схему; свойства не угадываются по имени.
- Текущий M2 relation path использует registry для решения, допустима ли транзитивность.

### ProofSupport и materialization

- Успешные proof paths теперь возвращают структурированный `ProofSupport` с premises/rule/relation.
- `TRANSITIVITY`, `DIRECT_RELATION`, `CAUSE_MP`, `EXISTS_WITNESS`, `FACT_MATCH` и explicit refutation различаются в диагностике поддержки.
- Для materialized derived `L` support сохраняется в `SupportLedger` — sidecar metadata, а не новый AH node kind.
- Support ledger поддерживает несколько независимых supports одного conclusion, точечную invalidation по premise и rewiring при merge/link replacement.
- Persistence сохраняет support dependencies внутри `store_metadata`; derived indexes по-прежнему rebuildable и не становятся truth store.
- GC очищает dangling support metadata при физическом удалении canonical UID.

### Регрессия этого шага

- `python -m compileall -q src` — OK.
- 53 targeted tests — PASS, включая core, projection/inference, mixed M2 composition, proof provenance, lifecycle/persistence и новые v4 tests.
- Полный acceptance намеренно не запускался: он остаётся финальным контрольным этапом после завершения архитектурного цикла.


## v0.12.99 — FunctionRegistry становится канонической write-boundary

- Машинная семантика `g.ID` вынесена из projection-only слоя в общий `ah.logic.FunctionRegistry`.
- `AHCore` не записывает незарегистрированный `g`; persistence не загружает незарегистрированный/структурно неверный `g`.
- Зафиксировано минимальное ядро `AND/OR/NOT/FALSE/IMPLIES/FORALL/EXISTS`; `IF` — только backward-compatible alias для старых графов.
- Реестр остаётся code metadata и не расширяет canonical AH.

## v0.13.0 — завершён наземный пропозициональный контур N/g

- ЕЯ-отрицание канонически записывается как `NOT(P)`; `FALSE(N)` оставлен только явному механизму refutation/correction.
- Новые условные конструкции используют `IMPLIES`; старый `IF` остаётся load-compatible alias.
- Ветви `OR` сохраняются scoped и не получают самостоятельный factual occurrence.
- Добавлены `FormulaGoal` и `GroundFormulaReasoner` для asserted N, `NOT/FALSE/AND/OR/IMPLIES`, ground modus ponens и локализованного `P`/`NOT(P)` conflict.
- Открытая семантика сохранена: отсутствие proof даёт `UNKNOWN`, а не `FALSE`.
- Формульный поиск идёт от текущего выражения через rebuildable индексы; при наличии attention подтверждённые шаги проходят через focus/Ignition.
- `IS-A / FOLLOW / CAUSE` и существующий M2 relation path не изменены.
- `FORALL/EXISTS` пока являются валидными canonical containers; quantified execution не объявляется готовым до подключения variable-bearing atoms к `BoundVar/BindingEnvironment` без новой модели данных.

Полное описание: `docs/SLICE_13_0.md`.

Регрессия перед выпуском: `compileall OK`; `604 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.


## v0.14.0 — quantified inference execution

- `N.actants` допускает `Ref | BoundVar`, но `BoundVar` валиден только у scoped formula-pattern `N` с `semantic_scope=QUANTIFIED`; обычный factual `N` с переменной отклоняется на canonical validation boundary.
- `BoundVar` не становится AH UID: persistence кодирует его как operand descriptor, store/diagnostics/ignition/projection не индексируют и не возбуждают его как узел.
- `BindingEnvironment` реализует вложенные lexical scopes, shadowing одинаковых `local_id` и sort validation. Подстановки существуют только в runtime proof context.
- `EXISTS` исполняется через witness search по T-index; один и тот же `BoundVar` во всех conjuncts обязан связываться с одним canonical ref. Отсутствие witness возвращает `UNKNOWN`, не `FALSE`.
- `FORALL` не доказывается перебором известных объектов. Универсальная proposition допустима как premise только при явном assertion/proof support.
- Явно утверждённый `FORALL ... IMPLIES(P(...), Q(...))` применяется goal-directed: ground target -> T-index -> quantified head pattern -> reverse function parents -> FORALL chain -> unification -> proof antecedent -> forward validation target.
- Вложенные `FORALL/EXISTS`, AND/OR внутри quantified body и extra existential variables в antecedent поддерживают backtracking и lexical scope. Фиксированный восьмиуровневый лимит вложенности удалён; ограничением служит runtime proof budget/depth.
- Quantified proof сохраняет runtime bindings и `ProofSupport(rule_id=FORALL_IMPLIES_MP/EXISTS_WITNESS)`, а confirmed canonical refs проходят через `InferenceAttention`/Ignition. `BoundVar` в activation не участвует.
- `ExistingRefConclusion` при materialization получает persisted support records; explicit refutation premise инвалидирует только downstream supports, сохраняя независимые основания.
- `IS-A / FOLLOW / CAUSE` не изменены; `CAUSE` остаётся нетранзитивным по умолчанию.

Полное описание: `docs/SLICE_14_0.md`.

Регрессия перед выпуском: `compileall OK`; `620 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.15.0 — canonical polarity conflicts and premise admissibility

- Добавлен `ConflictEngine`: asserted `P` и asserted `NOT(P)` после фиксации пользовательского occurrence образуют/переиспользуют обычный `k` с `Mt.TYPE=CONFLICT`; новый canonical node kind не вводится.
- Conflict-set не выбирает победителя по новизне, повторам, `x` или `w`. Повторная интеграция только переиспользует существующую группу.
- `FALSE(P)` и `NOT(P)` разделены: explicit refutation может снять текущую допустимость стороны, а исторический `k_CONFLICT` при этом не обязан физически исчезать.
- Конфликтная допустимость подключена ко всем основным proof paths: Formula/quantified reasoning, RoleFill, MultiRoleFill, Exists, Relation и CAUSE. Если clean independent proof отсутствует, возвращается `UNKNOWN / CONFLICTED`.
- Paraconsistency сохранена: конфликт локален и не мешает независимому доказательству `Q`.
- Conflict group получает отдельный activation seed и явно отображается в semantic projection / AgentContext.
- Persistence сохраняет conflict-set как обычную часть AH; runtime admissibility восстанавливается из canonical graph.
- Agent self-output в `H` не создаёт конфликт знаний `C/P`, что сохраняет `generation != confirmation`.
- Автоматический positive-positive conflict по `FUNCTIONAL`/взаимоисключающим схемам оставлен следующим расширением: 0.15.0 закрывает именно полностью определимый полярный вертикальный срез и не угадывает несовместимость.

Полное описание: `docs/SLICE_15_0.md`.

Регрессия перед выпуском: `compileall OK`; `630 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.16.0 — formalization batch boundary and atomic canonical integration

- Введены runtime `FormalizationBatch`, `CandidateIR`, `MutationPlan`, `DiscourseRef`; они не расширяют canonical `q`.
- MESSAGE/DOCUMENT проходят scoping + full candidate validation + dependency ordering до канонической мутации.
- Parser-local IDs окон документа namespaced; source spans переводятся в координаты полного документа. Неопределимое смещение требует explicit `unit_offsets`, а не тихого смешения provenance.
- Все canonical изменения batch выполняются одной транзакцией AH Core; поздняя ошибка откатывает весь документ.
- Неразрешённое третьеличное местоимение остаётся runtime `DiscourseRef`; грамматика только сужает `candidate_entity_refs`, но не доказывает identity. `bind_discourse_ref` применяет уже принятое решение и повторно валидирует staging graph. Неразрешённая ссылка блокирует commit вместо создания `m_ОН/ОНА`.
- Добавлен explicit deterministic `merge_identity`: older UID survives, references/supports rewired, exact N duplicates collapse; merge reason пишется во внешний session audit, не в H/semantic meta.
- `source_ref`/batch kind доходят до H occurrence provenance.
- ЕЯ-lifting истинно неизвестного участника в `EXISTS $0` и произвольная forward-coreference не заявляются готовыми: 0.16.0 закрывает transactional formalization/consolidation boundary без forced guesses.

Полное описание: `docs/SLICE_16_0.md`.

Регрессия перед выпуском: `compileall OK`; `642 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.17.0 — semantic time, temporal relations and state intervals

- Добавлены runtime-контракты `TemporalValue`, `TemporalCandidate`, `TemporalAnchorContext`, `TemporalMode`, `TransitionOperator`; они не являются AH node kinds.
- Semantic TIME materialize как ordinary `m` с `kind/start/end/precision/timezone/temporal_key` и подключается через `N.TIME`. Technical source/H timestamps используются только как anchors/provenance и не копируются во все факты.
- Partial time сохраняет отсутствующие компоненты (`--09`, `T12:30`); relative time применяет приоритет `explicit → source → experience → unresolved`. Неразрешённый relative actant блокирует atomic commit.
- `TemporalReasoner` детерминированно выводит `BEFORE/AFTER/OVERLAP/CONTAINS`; materialized relation — ordinary `N` с `ProofSupport`, не новый `L.ID`. Неупорядочиваемая частичная дата даёт `UNKNOWN`.
- `InferenceSchemaRegistry` явно фиксирует свойства temporal relations; `FOLLOW` не переопределён и остаётся отличным от physical time.
- Temporal mode хранится на occurrence `N`, а не на глобальном `T`.
- `FunctionRegistry` зарегистрировал `START/STOP/CONTINUE/AGAIN/NO_LONGER`; детерминированный `StateTracker` создаёт/закрывает intervals в той же AH transaction.
- Положительная и отрицательная state polarity разделены: open `NOT(P)` не удовлетворяет `CONTINUE(P)`; restart/AGAIN закрывает существующий negative interval и не изобретает промежуточное отрицание, если его не было.
- `current_truth(P,t)` вычисляется по temporal coverage и возвращает `POSITIVE/NEGATIVE/UNKNOWN/CONFLICTED`, а не выбирает последнее textual mention.
- Переход назад во времени отклоняется с полным transaction rollback.
- Temporal/state canonical structures и proof supports проходят JSON persistence/reload.
- Универсальный ЕЯ temporal parser, `NEVER` shortcut и constraint solver не заявляются готовыми; неразрешимые случаи fail closed.

Полное описание: `docs/SLICE_17_0.md`.

Регрессия перед выпуском: `compileall OK`; `656 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.18.0 — branch/counterfactual/meta reasoning

Закрыт следующий архитектурный runtime-контур v4. `ProofContext` получил специализированные `BranchContext` и `CounterfactualContext`; asserted OR теперь допускает детерминированный proof by cases, при котором branch assumptions не становятся independent factual premises и не materialize. `CounterfactualGoal` создаёт overlay над canonical AH, одновременно применяет несколько явных assumptions, сопоставляет scoped ground N с эквивалентными world N через существующий T-index и локально подавляет несовместимые `P/NOT(P)/FALSE(P)`. Derived-support admissibility проверяется рекурсивно, поэтому зависимость от suppressed premise инвалидируется по всей цепочке только внутри overlay, тогда как independent support сохраняется и persisted ledger не изменяется. `InferenceMaterializer` запрещает factual commit любого counterfactual outcome.

Формализация получила явные `HYPOTHETICAL` и `MODAL` assertion scopes наряду с `EMBEDDED`: вложенное proposition content остаётся адресуемым для matrix N, но не становится ordinary factual evidence. Общий `FunctionRegistry` зарегистрировал operational meta-functions `CONTRADICTS` и `CORRECTS`; `SemanticCorrectionService.correct()` создаёт `FALSE(target)` + `CORRECTS(target,replacement)` и инвалидирует только зависимые supports, не удаляя старую proposition и не создавая replacement в обход normal Integration. Self-referential formula fail-closed возвращает `UNKNOWN`. Диагностика показывает `OR_CASES` и counterfactual scope.

Сохранены `AH=<S,C,P,H,L>`, open-world `UNKNOWN`, локализованный conflict, non-transitive CAUSE и запрет на factual pollution из reported/modal/hypothetical/counterfactual content. Полная modal logic и SCM не вводились.

Регрессия перед выпуском: `compileall OK`; `671 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.


## v0.20.0 — associative convergence through ordinary Ignition

Закрыт ассоциативный режим v4 как отдельный от entailment runtime-контур. `AssociationGoal` стал допустимым target общего `GoalSpec(mode=ASSOCIATION)`, но намеренно не входит в `InferenceGoal`; исполняет его новый `AssociationCoordinator`. Оба origin получают `QUERY_RECALL`, обычный `IgnitionEngine` проводит synchronous propagation, а `AssociationSearchState` временно хранит ancestry двух фронтов и считает результатом только фактически активировавшееся пересечение `expand(A) ∩ expand(B)`. Для направлений, которых нет в packet flow, разрешены только goal-derived narrow incidence queries от текущего активного UID: actant→N, operand→g, member→k, incoming L, N→T, T→S, g→operands, k→members. Query-кандидат не становится front node до следующего реального activation event. Reverse activation не создаёт reverse relation; найденная association не создаёт canonical node/L/ProofSupport. Common node может быть S/m/T/N/g/k; mandatory hub-filter отсутствует. H participation остаётся runtime policy (`ALL`/`EXCLUDE_H`). Broad `all_elements/all_uids/elements/links` search не нужен и запрещён regression guard-ом.

Подробности: `docs/SLICE_20_0.md`. Регрессия перед выпуском: `688 passed, 22 subtests passed`, `compileall OK`. Полный hackathon acceptance не запускался.


## v0.19.0 — GoalSpec-driven cognition and proof-through-Ignition

`GoalSpec` теперь сопровождается отдельным runtime `GoalRuntime`, поэтому inference имеет наблюдаемый причинный цикл, а не только итоговый stop-condition. Для каждого запроса фиксируются `GOAL_START / FOCUS / MEMORY_QUERY / SUBGOAL / RULE_SELECTED / GOAL_STOP`; trace диагностический и не становится AH/H. `GoalMode` явно различает factual/proof/association/evidence режимы при сохранении существующих typed goals.

`RoleFill/MultiRoleFill/Exists` теперь начинают поиск с goal-generated focus по canonical `T`, затем используют только T-index и фокусируют найденный `N` до FACT_MATCH/EXISTS_WITNESS. Relation и CAUSE proof фиксируют exact/typed adjacency queries от текущего focus; target-derived reverse distance сохранён только как bounded pruning/order heuristic и отдельно помечен `not proof`. Formula/quantified reasoner отражает reverse function/T-index lookups, backward subgoals и реально выбранные rules. Production/M2 path через `IgnitionInferenceAttention` выполняет каждый focus как `QUERY_RECALL` seed + normal synchronous Ignition tick, поэтому Workspace физически меняется до продолжения proof.

Добавлен regression guard против unrestricted global read: broad store enumerators `all_elements/all_uids/elements/links` запрещаются во время transitive proof, который всё равно проходит через narrow indexes. После `GOAL_SATISFIED` хвост графа не исследуется. `ProofSnapshotBuilder` отображает cognitive cycle отдельно от canonical UID proof trace. `AH=<S,C,P,H,L>`, open-world semantics, conflict policy и `IS-A/FOLLOW/CAUSE` invariants не изменены; `CAUSE` остаётся non-transitive.

Полное описание: `docs/SLICE_19_0.md`.

Регрессия перед выпуском: `compileall OK`; `675 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.21.0 — source-scoped semantic projection and server boundary

Закрыт source/document projection path v4 без hidden raw retrieval. `AHStore` получил rebuildable `source_ref -> H experience` index, а runtime `SourceScopeResolver` восстанавливает semantic roots источника через canonical H OBJECT refs без `elements/all_elements/all_uids/links` scan. `SourceScopeActivator` seed-ит именно semantic roots обычным `QUERY_RECALL` и проводит их через synchronous Ignition; source H occurrence/raw text не используется как memory context.

DOCUMENT ingestion больше не сохраняет полный raw source в `H.text`; legacy document text fail-closed исключается из AgentContext. `ContextProjector` получил source-bounded mode: model-visible roots = `Workspace ∩ source semantic roots`, поэтому тёплая посторонняя память не протекает в summary. Прямые `CAUSE/FOLLOW/IS-A` отношения между видимыми source roots восстанавливаются bounded adjacency queries, чтобы causal/episodic structure не терялась несмотря на отсутствие x у L. Dialogue provenance wording также переведён с broad H enumeration на reverse indexes.

Добавлен deterministic context budget: overflow вызывает `ProjectionBudgetExceeded`, без silent truncation/top-k/raw-chunk fallback; iterative oversized-source protocol остаётся архитектурно ОТКРЫТ. `SourceScopedContextService` объединяет `source → activation → Workspace → projection` как runtime convenience boundary, не создавая новую document ontology. Source indexes rebuild после persistence reload; structural `_replace_hypernode` теперь перестраивает derived indexes только при index-sensitive изменениях, сохраняя hot weight/lifecycle path.

Полное описание: `docs/SLICE_21_0.md`. Регрессия перед выпуском: `compileall OK`; `695 passed, 22 subtests passed`. Полный hackathon acceptance не запускался.

## v0.22.0 — normative physical GC, complete DSL and hackathon structural preflight

Закрыт системный pre-acceptance слой v4. Общий initial-lifetime/GC теперь отделён от дополнительного N lifecycle: после запуска Ignition каждый новый S/C/P/H UID получает технический persisted birth tick и managed flag. `initial_lifetime` — только окно иммунитета от GC; его окончание разрешает structural check, но не является unconditional deletion. После TTL холодные effective components без реального S-anchor и zero-weight lost leaves физически удаляются с referential closure, support invalidation и incident-L cleanup, тогда как S-anchored/структурно живой узел остаётся независимо от возраста. Существующая до запуска Ignition AH считается established snapshot и не ретроактивно маркируется новой, поэтому dirty ~150k M2 graph не вычищается maintenance-механизмом. `QUERY_RECALL`/proof focus больше не стартует NEW lifecycle у proposition без lifecycle-state; только explicit `NEW_FACT` вводит N в NEW→REINFORCED→CONSOLIDATED. Истёкший N-lifecycle перед physical delete проходит тот же structural GC contract. Текущая activation не становится truth/forgetting criterion: активный detached component получает отсрочку. Deletion reasons доступны в GC diagnostics и scheduled runtime пишет их во внешний SessionLogger, не в H.

`DSLInterpreter` фиксирует полный нормативный manifest из 23 операций постановки; `editElement` расширен для m/T/N/g/k и L-weight, mutation по-прежнему проходит только через AH Core. Добавлен read-only `HackathonPreflightInspector` и CLI `preflight`: DAG checks для IS-A и H/FOLLOW, reference typing, non-empty S.R, DSL completeness, graph/S scale flags и ровно пять обязательных hyperparameter records (`initial lifetime`, `g`, `t`, `h`, `ν`). Это structural preflight, не M1–M5 acceptance.

Полное описание: `docs/SLICE_22_0.md`.

Регрессия перед выпуском: `707 passed, 38 subtests passed`, `compileall OK`; dirty-150k M2 operator case отдельно проходит `40/40` (pytest `7.14s` в текущем контейнере). Полный hackathon acceptance не запускался.

## v0.23.0 — executable hackathon metrics and local acceptance harness

После закрытия системной архитектуры добавлен отдельный read-only measurement layer. `hackathon_metrics.py` считает M1 role Precision/Recall/F1 с весами SUBJECT/OBJECT=2, M2 ExplainScore с обязательным trace gate, M3 GC efficiency + live preservation, M4 explainability/hallucination deltas и M5 RobustnessGain. M1 умеет читать реальные `acceptance_runs` bundles; неоднозначность напечатанной в постановке M1 weighted-sum формулы не скрывается — отчёт выдаёт и literal sum, и bounded weighted mean для порога 0.6.

M3 получил committee-shape harness без test-only semantics: 200 orphan и связная live-структура создаются после старта Ignition тем же AH Core API. Дефолтный config удаляет 200/200 на tick 41 и сохраняет 202/202 live UID. Добавлен non-trivial tick benchmark с `N+L >=1000`, lexical S→T→N fanout и обычными synchronous ticks; локальный прогон на 1001 N+L units дал max ~50 ms, что заметно ниже hard limit 500 ms, но не подменяет измерение на стенде оргкомитета.

Внутренний dirty-150k M2 повторно проходит 40/40 на 153599 UID, exact UID trace complete во всех кейсах. Его ExplainScore40=0.6375 является внутренним диагностическим числом, не официальной M2 оценкой скрытых 20 вопросов. M1 фактической модели, M4 RAG baseline и M5 SLM/commercial experiment остаются следующей экспериментальной фазой и не заполняются синтетическими результатами.

CLI: `m1-score`, `m3-acceptance`, `tick-benchmark`. Полное описание: `docs/SLICE_23_0.md`.

Регрессия перед выпуском: `714 passed, 38 subtests passed`, `compileall OK`; M2 stress 40/40; M3 PASS; local 1000 N+L tick benchmark PASS.

## v0.24.0 — capability-frontier acceptance: existential unknowns and functional conflicts

- Закрыт ранее явно оставленный gap истинно неизвестного участника для узкого детерминированного класса explicit indefinite pronouns. `CandidateIR.existential_bindings` хранит runtime-only `ExistentialBinding`; canonical `m_UNKNOWN_PERSON/m_КТО-ТО` не создаётся.
- Assertions с existential batch-local `entity_ref` materialize как `QUANTIFIED` pattern N с `BoundVar`; связанные общими unknown variables assertions объединяются через `AND` и asserted `EXISTS`. Disconnected unknown components остаются независимыми scopes; несколько unknown actants одного fact дают nested EXISTS.
- Существующий `DiscourseRef` может до atomic commit bind-иться к existential local handle, поэтому `Кто-то ... Он ...` сохраняет одну variable identity без forced semantic M. `BoundVar` не попадает в cross-turn pronoun salience cache. H occurrence ссылается на existential root, а quantified pattern N не становится ordinary factual premise.
- `InferenceSchema` получил explicit `functional_role`. Positive-positive `FUNCTIONAL` conflict создаётся только для явно зарегистрированного functional predicate при одном T/domain, равных non-value roles/context и разных значениях output role. Никакого угадывания функциональности по имени predicate нет.
- Третье несовместимое значение расширяет существующий `k_CONFLICT`; разные non-value contexts не дают false positive. FUNCTIONAL conflict использует ту же no-auto-winner/premise-admissibility semantics, что polarity conflict, и переживает persistence/reload.
- Bootstrap передаёт один shared `InferenceSchemaRegistry` в IntegrationService и InferenceEngine.
- Новый `tests/test_v4_capability_frontier_2400.py`: 9 acceptance cases, включая existential persistence и functional-conflict persistence.
- Не заявлены generalized quantifiers, произвольные indefinite NP, automatic semantic discovery функциональности predicate и late identity split.

Полное описание: `docs/SLICE_24_0.md`.

Регрессия перед выпуском: `compileall OK`; `723 passed, 38 subtests passed`.

## v0.25.0 — cross-turn existential discourse and adversarial M1 frontier

- `InteractionContext` получил runtime-only `ExistentialDiscourseAnchor`: одно-переменная existential proposition может продолжаться через последующий turn номинативным местоимением без fake `m_UNKNOWN` и без нового canonical node kind.
- Cross-turn continuation строит новый asserted `EXISTS`, включающий предыдущие quantified members и новый predicate с тем же `BoundVar`. Несколько turns накапливают один participant scope; persistence/reload сохраняет runtime anchor.
- При двух равноправных неизвестных или multi-variable existential arbitrary bind запрещён: остаётся обычный unresolved `DiscourseRef`/fail-closed. Named subject может заменить старую existential salience для будущих pronouns.
- Late grounding вида `Кто-то ... Это был Иван` не заявлен и не подменяется простым salience update.
- Добавлен отдельный 36-case M1 adversarial corpus по прямо заявленным hidden-noise классам постановки: `typo`, `inversion`, `ellipsis`, `mixed`. Oracle задан до запуска parser и включает SUBJECT/OBJECT/LOCATION плюс RECIPIENT/TOOL/MATERIAL/TIME/DURATION/SOURCE.
- CLI `semantic-acceptance` запускает произвольную cases/oracle пару через normal local-LLM pipeline; bundle совместим с существующим `m1-score`. Реальный численный M1 этого corpus не заявляется без прогона подключённой модели.
- Новые regressions: 7 cross-turn existential + 3 corpus-contract tests.

Регрессия перед выпуском: `compileall OK`; `733 passed, 38 subtests passed`. Readiness smoke: dirty M2 `40/40`; M3 `200/200` orphan removed и `202/202` live preserved; 1001 N+L tick benchmark mean `33.91 ms`, p95 `41.66 ms`, max `42.03 ms` (<500 ms).

## v0.25.1 — GUI binding for adversarial M1 acceptance

- Added dedicated `M1: adversarial acceptance` button to the Dialogue dock.
- Bound it to `acceptance_cases_m1_adversarial.txt` / `acceptance_oracle_m1_adversarial.json` through the same real `run_acceptance_suite` pipeline as broad acceptance.
- Isolated output in `acceptance_runs_m1_adversarial` and made the new control participate in existing cognitive-run mutual exclusion.
## v0.25.2 — LM Studio protocol-probe transport hardening

- Investigated user acceptance bundle: adversarial 36/36 and broad 186/200 runtime failures were caused by LM Studio returning reasoning-only output under tiny fixed-choice budgets, not by canonical/parser regressions.
- Verified `config/lmstudio.toml` and LM Studio client/backend code were unchanged between v0.23.0 and v0.25.1; the failure depends on the loaded model/runtime reasoning mode.
- Bounded `perception_*` and `semantic_*` calls now use native `/api/v1/chat` with `reasoning=off`, `store=false`, `stream=false`.
- Main agent/generic generation remains on OpenAI-compatible chat completions.
- Reasoning content is never promoted to a protocol answer; empty message output still fails closed.

