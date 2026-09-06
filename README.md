# AH Agent MVP — v0.25.13

## v0.25.13 — границы эллипсиса и посылок М2

Исправлено восстановление antecedent, сохранение provenance/scope, обработка координированного отрицания и защита от частичного успешного разбора. Добавлены 106 проверок; целевой набор с прежними тестами: 114 PASS. Полный прогон имеет исходные failures: см. `TEST_RESULTS_02513.md`.

Запуск: `run_formalization_tests.bat` либо команды из `VERSION_02513.md`.
Последний живой acceptance — 25/100 PASS; нового живого результата пока нет.
Разбор: `docs/ACCEPTANCE_REVIEW_02513.md`.

## v4 development alignment — v0.25.9

Рабочая архитектурная база: `docs/ARCHITECTURE_V4_DEV.md`.

Текущая реализация последовательно закрывает контракты архитектуры v4: формальная логика и кванторы, proof-support lifecycle, конфликты, пакетная граница `CandidateIR → MutationPlan → atomic AH commit`, delayed discourse state, deterministic identity merge, temporal/state tracking, сложные proof-overlays, GoalSpec-driven proof-through-Ignition, отдельный ассоциативный режим и AH-only source projection. В 0.22.0 закрыт системный контур перед acceptance: общий initial-lifetime/physical GC для новых S/C/P/H элементов, удаление холодных detached-from-S подграфов без использования inactivity как semantic criterion, persistence технического lifetime-state, полный нормативный DSL surface и детерминированный hackathon preflight с ровно пятью обязательными гиперпараметрами. Существовавшая до запуска Ignition AH считается установленным snapshot и не уничтожается ретроактивным GC — это сохраняет dirty-150k M2 semantics. Семантика `IS-A / FOLLOW / CAUSE` не менялась. Подробности: `docs/ARCH_V4_PROGRESS.md`.

Накопительный исполняемый проект АГ-памяти для текстового LLM-агента.

## v0.25.9 — 100-case composite ellipsis acceptance

- `M1: ellipsis acceptance` expanded from **22 to 100 EXACT cases**; the original 22 remain unchanged at positions 1..22 for longitudinal comparison.
- New cases focus on **interactions**, not shallow paraphrase repetition: long ellipsis chains, coordinated subjects/objects, mixed `тоже/нет/не`, rich roles, TIME+LOCATION+DURATION, explicit predicate reset, nominal-predicate boundaries, semicolon/cross-sentence recovery, embedded/control scope, coreference, inversion and typo+ellipsis.
- Added the requested hard cases `Иван купил журнал, а Мария и Пётр - нет.` and `Иван живёт в Москве, Мария - в Казани, Пётр - в Париже, а Слава - бродяга.` with explicit semantic oracle structures.
- The corpus remains loaded by the same production GUI/runner path; no parser logic was changed in this slice.
- Corpus regression now enforces 100/100 case-oracle alignment and the new interaction families.

Подробности: `docs/SLICE_25_9.md`, `docs/ACCEPTANCE_ELLIPSIS_V2.md`.

## v0.25.8 — ellipsis hardening after live acceptance

- Live `M1: ellipsis acceptance` improved from `0/22` before the first reconstruction layer to `11/22` on v0.25.7.
- Fixed dash-ellipsis contamination: lexical/nominal predicate candidates inside a clause already licensed as ellipsis are removed from the ordinary predicate work queue. This prevents `Мария — журнал`, `журнал — на полке`, `Мария — в Казани` from being committed as unrelated nominal predications before frame completion.
- Fixed a diagnostic false negative: semantic oracle canonical matching now unwraps object-level `g_NOT` for predicate/role checks and treats `NOT`, not meta-level `FALSE(N)`, as the meaning of expected `negated=true`. The live proposition-negation cases were already correct in perception/integration.
- Added deterministic ellipsis slot alignment by **source-grounded realization signatures**. It does not introduce generic `NOM→SUBJECT` / `DAT→RECIPIENT` rules; target fillers may inherit a role only when their morphology/preposition signature uniquely matches the same realized slot in the already parsed antecedent frame. This repairs role swaps such as `Анна отправила письмо Сергею, а Ольга сообщение Петру`.
- Remaining live gaps are intentionally not hidden: material attachment clarification (`из дерева`), relative TIME without a current/source/experience anchor, and lexical typo recovery remain separate mechanisms.
- Regression after the slice: `749 passed, 38 subtests passed`.

Подробности: `docs/SLICE_25_8.md`.

## v0.25.7 — ellipsis frame completion

- Clause segmentation теперь выделяет координированный zero-predicate tail как отдельный runtime clause для конструкций вида `X VERB Y, а Z W` и `X VERB Y, а Z — W`.
- Добавлен runtime `EllipsisKind`: обычное frame completion, proposition-level negation (`... а Мария — нет`) и confirmation (`... и Ольга тоже`).
- `нет` в доказанном ellipsis-shell больше не остаётся в predicate work queue как самостоятельный PRED.
- После разбора antecedent frame выполняется bounded `ellipsis_recovery`: target clause может заполнять только роли, уже лицензированные antecedent frame; явные fillers заменяют старые, действительно опущенные наследуются.
- Для temporal/locative ellipsis это позволяет сохранить SUBJECT при замене TIME/LOCATION, а для proposition negation — восстановить пропущенный OBJECT и выставить negation без создания отдельного lexical predicate `нет`.
- В `docs/ARCHITECTURE_V4_DEV.md` заново внесён нормативный Lexical Recovery contract: Levenshtein для генерации кандидатов, embeddings для contextual rerank, morphology validation, без semantic commitment до обычной formalization/consolidation.
- Добавлено 4 regression tests на structural split, marker modes, role-limited frame completion и proposition negation. Полная регрессия: `746 passed, 38 subtests passed`.

Подробности: `docs/SLICE_25_7.md`.

## v0.25.2 — LM Studio bounded-probe reasoning isolation

Diagnostic acceptance runs exposed a transport failure: reasoning-capable LM Studio models could ignore non-standard `enable_thinking=false` fields on the OpenAI-compatible `/v1/chat/completions` endpoint, spend the complete 2–10 token probe budget in `reasoning_content`, and return empty assistant `content`. This made previously stable acceptance cases fail before semantic parsing.

Bounded `perception_*` / `semantic_*` probes now use LM Studio's native stateless `/api/v1/chat` endpoint with explicit `reasoning=off`, `store=false`, and `stream=false`. Generic/agent generation remains on `/v1/chat/completions`; hidden reasoning is still never consumed as a semantic answer.

## v0.25.1 — GUI binding for M1 adversarial acceptance

- В dock «Диалог» добавлена отдельная кнопка `M1: adversarial acceptance`.
- Кнопка запускает реальный `run_acceptance_suite` на `acceptance_cases_m1_adversarial.txt` + `acceptance_oracle_m1_adversarial.json`.
- Результаты пишутся отдельно в `data/acceptance_runs_m1_adversarial/`, поэтому broad acceptance и M1 breaker-run не смешиваются.
- Обычная кнопка `Прогнать acceptance-файл` по-прежнему запускает исходные `acceptance_cases.txt` / `acceptance_oracle.json`.
- Во время любого cognitive/diagnostic run обе acceptance-кнопки взаимно блокируются; tooltip пересчитывается при смене `data_dir` в конфигурации.

## v0.25.0 — cross-turn existential discourse + adversarial M1 frontier

Продолжен capability-frontier acceptance вместо наращивания вариаций уже зелёных тестов. Runtime `InteractionContext` получил `ExistentialDiscourseAnchor`: одно-переменная existential proposition из предыдущего turn может быть продолжена последующим номинативным местоимением без создания фиктивного `m_UNKNOWN` и без превращения runtime anchor в canonical node. `«Кто-то вошёл.» → «Он сел.»` теперь даёт новую asserted `EXISTS`-формулу, объединяющую старый и новый quantified member с тем же `BoundVar`; цепочка может продолжаться через несколько turns и переживает persistence/reload контекста. При нескольких равноправных неизвестных или multi-variable existential система fail-closed и не угадывает referent. Более свежий обычный именованный SUBJECT заменяет existential salience для последующих местоимений. Это **не** late grounding: `«Кто-то вошёл. Это был Иван.»` пока не перепривязывает старые existential facts к `m_ИВАН`.

Отдельно добавлен диагностический M1 adversarial corpus из 36 `EXACT` cases, построенный из классов скрытого контрольного корпуса постановки: опечатки, синтаксическая инверсия и эллипсис, плюс их смешанные варианты. Oracle задан от требуемой семантики до запуска текущего parser-а; обязательные SUBJECT/OBJECT/LOCATION дополнены RECIPIENT/TOOL/MATERIAL/TIME/DURATION/SOURCE. Эллиптические примеры требуют восстановления двух assertions, а не снижения ожидания под текущую реализацию. Новый CLI `semantic-acceptance` запускает произвольную пару cases/oracle через обычный local-LLM pipeline; результат затем можно оценить существующим `m1-score`. В этом срезе 36-case corpus **не объявляется пройденным**: реальный M1 score зависит от подключённой локальной модели и должен быть измерен отдельным запуском.

Добавлено 10 regression tests: 7 на cross-turn existential discourse и 3 на контракт нового M1 corpus. Полная регрессия: `733 passed, 38 subtests passed`, `compileall OK`. Readiness после изменений: dirty M2 `40/40`, M3 `200/200` orphan removed при `202/202` live preserved, tick benchmark на `1001 N+L` units: mean `33.91 ms`, p95 `41.66 ms`, max `42.03 ms` (<500 ms). Подробности: `docs/SLICE_25_0.md`.

## v0.24.0 — capability-frontier acceptance: EXISTS для истинно неизвестных и FUNCTIONAL conflicts

После измерительного среза M1–M5 acceptance расширен в двух местах, которые архитектура уже требовала, а предыдущие версии явно оставляли незакрытыми. Истинно неизвестный участник с batch-local `entity_ref` теперь не превращается в фиктивный `m_UNKNOWN`: assertions с ним становятся `QUANTIFIED` pattern N с `BoundVar`, связанные assertions собираются в `AND` и asserted `EXISTS`, а H occurrence указывает на existential proposition. Существующий `DiscourseRef` может до atomic commit связать последующее местоимение с тем же existential anchor. Текущий recognizer намеренно ограничен явными indefinite pronouns (`кто-то/что-то/...`); generalized quantifiers не заявляются.

Conflict Engine расширен positive-positive конфликтом только для явно зарегистрированной functional semantics. `InferenceSchema` теперь может задавать `functional_role`; conflict возникает лишь для одного T/domain при одинаковых non-value actants и разных значениях functional slot. Разный LOCATION/другой контекст не конфликтует, третье значение расширяет один `k_CONFLICT`, winner по recency/x/w не выбирается. Bootstrap использует общий `InferenceSchemaRegistry` для integration и inference.

Добавлено 9 capability-frontier regression cases, включая persistence/reload. Полная регрессия: `723 passed, 38 subtests passed`, `compileall OK`. Подробности: `docs/SLICE_24_0.md`.


## v0.23.0 — измеримый acceptance-контур M1–M5 и hard-requirement benchmark

После закрытия основных архитектурных срезов добавлена отдельная диагностическая граница, которая считает метрики постановки, но не меняет canonical AH и не подменяет скрытый комитетский acceptance. `hackathon_metrics.py` реализует M1 weighted role F1, точную формулу M2 ExplainScore, M3 GC efficiency/live-preservation, M4 deltas и M5 RobustnessGain. M1 умеет считать результат прямо из существующего `acceptance_runs` bundle; при этом отчёт сохраняет буквально напечатанную в постановке weighted sum и отдельно bounded weighted mean, пригодный для порога 0.6, не маскируя неоднозначность формулы.

Добавлен committee-shape локальный M3 harness: Ignition запускается до инъекции, затем через обычный AH Core создаются 200 изолированных узлов и связная живая структура. Никакого test-only GC path нет. На дефолтном `initial_lifetime_ticks=40` текущий прогон удаляет 200/200 orphan на 41-м tick и сохраняет 202/202 live UID (`GC_efficiency=1.0`, live preservation `1.0`). Добавлен отдельный `tick-benchmark` для жёсткого требования <=500 ms: fixture содержит >=1000 `N+L` graph units и реальный lexical fanout через Ignition; локальный прогон текущего контейнера на 1001 N+L units дал mean ~30.01 ms, max ~50.18 ms за 20 measured ticks. Это readiness-измерение, не замена референсного стенда оргкомитета.

M2 повторно прогнан на dirty stress AH: `40/40`, `153599 UID`, около `5.82 s` на полный внутренний набор; точный UID trace присутствует во всех случаях. Внутренний ExplainScore по этим 40 собственным кейсам равен `0.6375`; он не называется официальным M2, потому что постановка использует скрытые 20 вопросов. M1 свежим LLM-прогоном, M4 RAG baseline и M5 SLM/commercial experiment в этом срезе не подменяются синтетическими числами — для них теперь есть расчётный контракт и CLI/данные должны поступить из реального эксперимента.

Новые CLI: `m1-score <acceptance_run_dir>`, `m3-acceptance`, `tick-benchmark`. Полное описание: `docs/SLICE_23_0.md`.

## v0.22.0 — normative GC, полный DSL и hackathon preflight

Закрыт системный слой v4 перед переходом к acceptance. Общий GC теперь имеет отдельную от N-lifecycle техническую initial-lifetime регистрацию для всех **новых после запуска Ignition** S/C/P/H элементов. `initial_lifetime` трактуется именно как окно иммунитета, а не как срок жизни: после TTL элемент только становится допустимым для structural check. S-anchored/структурно живой узел сохраняется независимо от возраста; холодный effective-component удаляется лишь если он отвязан от сенсорной базы S либо является реально потерянным zero-weight leaf. Положительные L/N задают effective weighted edges, T→S и g/k containment остаются structural edges. Изолированный S после TTL также считается потерянным. Текущая активация сама по себе не является основанием удаления: активный detached component временно защищён и будет перепроверен позже. Существующая до старта Ignition память не ретроактивно маркируется «новой», поэтому большой dirty snapshot M2 не вычищается GC; новые committee/API injections получают lifetime автоматически. Birth/managed metadata сохраняются отдельно от canonical AH и переживают persistence/reload. Отдельный N-lifecycle больше не запускается от простого `QUERY_RECALL`: фокус proof/association не превращает старое утверждение в `NEW`. Истечение N-lifecycle также является только сигналом проверки и не обходит structural GC. GC инвалидирует только зависимые proof supports, удаляет incident L вместе с endpoint и выдаёт причины удаления во внешний diagnostic/audit channel, не в H.

DSL теперь публикует полный нормативный manifest из 23 операций и исполняет все mutation/query primitives постановки; `editElement` покрывает m/T/N/g/k и L-weight через AH Core, а pipeline composition (`findRoles | findLists | where ...`) остаётся детерминированной. Добавлен `HackathonPreflightInspector` и CLI `preflight`: он проверяет DAG для IS-A и H/FOLLOW, типизированные ссылки, непустой R_text, полный DSL surface, размеры графа/S и выдаёт **ровно пять** обязательных параметров: initial lifetime, decay g, Workspace threshold t, weight update h, rhythm frequency ν. Это structural preflight, а не подмена M1–M5.

Подробности: `docs/SLICE_22_0.md`. Регрессия перед выпуском: `707 passed, 38 subtests passed`, `compileall OK`; отдельный dirty-150k M2 operator regression — `40/40` (pytest case `7.14s` в текущем контейнере). Полный hackathon acceptance не запускается в рамках этого среза.


## v0.21.0 — Context Projector, source scope и AH-only документы

Закрыт runtime-контур v4 `source provenance → activation → Workspace → compact AgentContext`. Добавлены `SourceScopeResolver/SourceScopeActivator/SourceScopedContextService`: технический `source_ref` через rebuildable индекс находит H-occurrence источника и его canonical semantic OBJECT roots без broad scan; seed получает именно семантика, а не сырой текст или H-событие. `ContextProjector` умеет source-bounded projection: тёплая посторонняя память не протекает в summary, а прямые `CAUSE/FOLLOW/IS-A` отношения между видимыми source roots добавляются через bounded outgoing adjacency, несмотря на то что L не имеет собственного x. DOCUMENT occurrence больше не сохраняет raw source в `H.text`; legacy document text также fail-closed исключается из model-facing projection. Введён deterministic context-budget guard `ProjectionBudgetExceeded`: превышение бюджета не вызывает silent top-k/truncation и не превращается в hidden raw-chunk RAG. Runtime `source_scope_ref` и estimated token count доступны только диагностике и не сериализуются в prompt.

Подробности: `docs/SLICE_21_0.md`. Регрессия перед выпуском: `695 passed, 22 subtests passed`, `compileall OK`.


## v0.20.0 — ассоциативный режим `expand(A) ∩ expand(B)`

Закрыт специализированный association path v4. `AssociationGoal` является отдельным target для `GoalSpec(mode=ASSOCIATION)`, но не `InferenceGoal`: `AssociationCoordinator` seed-ит обе стороны через `QUERY_RECALL`, использует обычные synchronous Ignition ticks и хранит ancestry двух фронтов только в runtime `AssociationSearchState`. Направленный packet flow дополняется только narrow queries из текущего активированного focus (`actant→N`, `operand→g`, `member→k`, incoming `L`, `N→T`, `T→S`, `g→operands`, `k→members`); найденный кандидат должен реально активироваться на следующем tick до включения во front. Convergence не materialize, не создаёт `ProofSupport` и не считается entailment. Common node может быть `S/m/T/N/g/k/...`; generic `T` не фильтруется. Обратное возбуждение по directed `L` не создаёт обратный relation. H-domain оставлен runtime option `ALL/EXCLUDE_H`. Поиск не использует broad full-store enumerators.

Подробности: `docs/SLICE_20_0.md`. Регрессия перед выпуском: `688 passed, 22 subtests passed`, `compileall OK`.


## v0.19.0 — GoalSpec-driven cognition и proof-through-Ignition

Закрыт runtime-срез целевого рассуждения v4. `GoalSpec` теперь несёт явный `GoalMode`, а `GoalRuntime` сопровождает один запрос от постановки цели до termination и сохраняет диагностический `cognitive_trace`: начало цели, focus shifts, goal-derived narrow memory queries, subgoals, выбранные правила и причину остановки. `RoleFill/MultiRoleFill/Exists` получили настоящий goal-generated T seed через `InferenceAttention`; relation/CAUSE proof читает только typed adjacency/index queries текущего focus, а formula/quantified proof отражает reverse function/T-index lookups и backward subgoals. При подключённом `IgnitionInferenceAttention` каждый подтверждённый proof proposition получает `QUERY_RECALL` seed и обычный synchronous tick до продолжения вывода. Reverse-distance по target сохраняется исключительно как bounded pruning/order heuristic и явно помечается в trace как `not proof`. Reasoner не нуждается в `all_elements/all_uids/elements/links` для transitive proof; регрессия это запрещает monkeypatch-guard'ом. После `GOAL_SATISFIED` хвост цепи не раскрывается. `ProofSnapshotBuilder` показывает когнитивный цикл отдельно от канонического proof trace.

Подробности: `docs/SLICE_19_0.md`. Регрессия перед выпуском: `675 passed, 22 subtests passed`, `compileall OK`.


## v0.18.0 — ветвящееся, контрфактуальное и мета-рассуждение

Закрыт runtime-срез сложного proof layer из v4: asserted `OR` поддерживает proof by cases через изолированные `BranchContext`; `CounterfactualGoal` исполняется в `CounterfactualContext` без копирования/изменения AH и рекурсивно фильтрует derived supports, зависящие от локально подавленных premises. Несколько assumptions применяются одновременно; scoped hypothetical N сопоставляется с эквивалентным world N через T-index. Counterfactual conclusion не materialize в factual AH. `EMBEDDED/HYPOTHETICAL/MODAL` content остаётся адресуемым proposition content, но не ordinary premise. Зарегистрированы operational meta-functions `CONTRADICTS` и `CORRECTS` поверх уже существующего `FALSE`; correction инвалидирует только зависимые supports и сохраняет историю. Self-reference fail-closed исключается из ordinary proof.

Подробности: `docs/SLICE_18_0.md`. Регрессия перед выпуском: `671 passed, 22 subtests passed`, `compileall OK`.


## v0.17.0 — семантическое время и интервалы состояний

Закрыта архитектурная граница времени/state tracking: semantic TIME materialize как обычный `m` и подключается к `N` ролью `TIME`; partial time не получает выдуманных компонентов, а relative time разрешается строго по `explicit → source → experience` anchor и остаётся unresolved без допустимого anchor. `TemporalReasoner` детерминированно выводит `BEFORE/AFTER/OVERLAP/CONTAINS` и materialize результат обычным `N` с proof support, не новым `L`. Реализован `StateTracker` с интервалами и `START/STOP/CONTINUE/AGAIN/NO_LONGER`; текущая полярность определяется temporal coverage, а не последним упоминанием. `FOLLOW` остаётся эпизодической последовательностью и не трактуется как timestamp.

Подробности: `docs/SLICE_17_0.md`. Регрессия перед выпуском: `656 passed, 22 subtests passed`, `compileall OK`.


## v0.16.0 — пакетная формализация, CandidateIR и атомарная интеграция

Закрыта явная runtime-граница между восприятием и canonical AH: `FormalizationBatch → SemanticConsolidator → CandidateIR → MutationPlan → AHCore.transaction()`. Документ может состоять из нескольких bounded perception windows, но их локальные `A/E` идентификаторы namespaced, evidence spans переводятся в координаты полного источника, а весь batch коммитится одной транзакцией. Неразрешённые third-person references сохраняются как `DiscourseRef` без AH UID; они могут быть связаны только после отдельного детерминированного/ bounded решения и блокируют canonical commit, пока не разрешены. Добавлен explicit `merge_identity`: старший canonical UID выживает, ссылки/supports rewired, эквивалентные N дедуплицируются, событие merge пишется только во внешний audit log. `IS-A/FOLLOW/CAUSE` и M2 не изменены.

Подробности: `docs/SLICE_16_0.md`. Регрессия перед выпуском: `642 passed, 22 subtests passed`, `compileall OK`.

## v0.15.0 — канонические конфликты полярности и допустимость посылок

Закрыт первый полный исполняемый контур `Conflict Engine` для формально взаимоисключающих утверждений `P` / `NOT(P)`. Конфликт сохраняется как обычная адресуемая группа `k` с `Mt.TYPE=CONFLICT`; сама группа не становится логическим оператором. Интеграция создаёт или переиспользует conflict-set после фиксации пользовательского события в `H`, а reasoner проверяет допустимость его членов перед использованием в доказательстве.

Свойства среза:

- ни новизна, ни повтор, ни `x`, ни `w` не выбирают сторону конфликта;
- `FormulaGoal`, `RoleFill`, `MultiRoleFill`, `Exists`, relation proof и `CAUSE` не используют неразрешённый конфликт как безусловную посылку;
- независимые непротиворечивые доказательства продолжают работать;
- явный `FALSE(N)` снимает допустимость соответствующей версии без уничтожения исторического conflict-set;
- конфликт сохраняется/восстанавливается persistence и явно отображается в semantic projection / AgentContext;
- ответ самой Main LLM, записанный только как пережитое событие в `H`, не создаёт конфликт знаний `C/P`.

Граница этого среза: автоматически обнаруживается строгий полярный конфликт `P` против asserted `NOT(P)`. Положительные конфликты значений по `FUNCTIONAL`/взаимоисключающим схемам остаются следующим расширением общего `Conflict Engine`; текущая версия их не угадывает.

Подробности: `docs/SLICE_15_0.md`.

## v0.14.0 — исполнение кванторов и универсальных правил

Закрыт следующий цельный слой логического контура v4: `BoundVar` теперь может использоваться в актантах только у scoped-шаблонов `N` с `semantic_scope=QUANTIFIED`; такая переменная не получает UID, activation state или Hebbian semantics. Реализованы runtime-подстановки с лексическими областями видимости, `EXISTS` с поиском конкретного witness, open-world `FORALL`, вложенные кванторы без фиксированного восьмиуровневого семантического ограничения и goal-directed применение явно утверждённых правил `FORALL ... IMPLIES(...)`. Поиск кандидатов начинается от T текущей цели и rebuildable reverse function indexes, а не от полного сканирования AH. Вывод сохраняет bindings и `ProofSupport`, проходит через `InferenceAttention/Ignition`, а явное refutation premise инвалидирует только зависимые supports materialized conclusion. Канонические `IS-A / FOLLOW / CAUSE` и их M2-семантика не изменены. Подробности: `docs/SLICE_14_0.md`. Регрессия перед выпуском: `620 passed, 22 subtests passed`, `compileall OK`.


## v0.13.0 — каноническая наземная пропозициональная логика

Закрыт цельный исполняемый слой для наземных формул `N/g`: объектное отрицание хранится как `NOT(P)`, явное опровержение конкретного утверждения — как `FALSE(N)`, новые условные конструкции канонизируются в `IMPLIES`, а ветви `OR` остаются scoped и не становятся самостоятельными фактами. Добавлен `FormulaGoal` и детерминированный `GroundFormulaReasoner` с открытой семантикой мира, локализованными конфликтами, `AND/OR/NOT/IMPLIES` и наземным modus ponens. Поиск опирается на rebuildable индексы от текущей цели и при наличии attention проводит подтверждённые шаги через focus/Ignition. `IS-A / FOLLOW / CAUSE` не изменены. Выполнение кванторов пока не заявляется: `FORALL/EXISTS` уже имеют канонический контейнер, но variable-bearing atoms остаются следующим архитектурным срезом. Подробности: `docs/SLICE_13_0.md`.


## v0.12.99 — deterministic FunctionRegistry boundary

Архитектурный `FunctionRegistry` вынесен в общий слой `ah.logic` и стал обязательной границей записи/загрузки `g`: неизвестный `g.ID` больше нельзя канонически записать или восстановить из persistence. Зарегистрированы `AND / OR / NOT / FALSE / IMPLIES / FORALL / EXISTS`; старый `IF` сохранён как совместимый alias `IMPLIES`. AHCore проверяет арность/форму операндов, persistence повторяет проверку на load. Подробности: `docs/SLICE_12_99.md`.

## v0.12.98 — factive proposition content and active-history discourse relations

Live `Document acceptance` on v0.12.97 remained fully runtime-stable (`98/98` paragraph semantic, `0` Runtime ERROR) and reached `4/6` document passes: cooling station `18/18`, greenhouse `18/18`, archive leak `19/19`, house-by-pier `56/56`, Belyaev `26/36`, old observatory `59/61`. The remaining failures exposed three semantic-boundary defects and one missing cross-turn relation mechanism.

- **Factive proposition content is separated from generic embedded content.** `увидел, что ... приближалась подводная лодка` already produced `SEE.OBJECT -> N_APPROACH`, but the child was conservatively marked `EMBEDDED`; that blocked its ordinary nominal relation (`лодка --NOMINAL_MODIFIER--> подводный`) and semantic seed. A tiny UID-free `FACTIVE | NONFACTIVE | UNCLEAR` probe now promotes only factive proposition complements back to ordinary `ASSERTED`. Speech/thought/hope/intention/quotation remain embedded unless the concrete matrix use commits to the child proposition as true.
- **PP attachment uses the coherent nominal head case rather than any ambiguous modifier reading.** In `в дальней комнате`, the adjective `дальней` exposes multiple morphology readings while the noun head `комнате` is strongly locative. Instrumental ambiguity is now determined from the nominal head, so this locative no longer rolls back the whole turn. Genuine `с биноклем` attachment still requires clarification.
- **Same-sentence CAUSE asks the right semantic question.** The deterministic gate remains narrow, but the model now decides `CAUSAL_RESPONSE | NO_CAUSAL_RESPONSE | UNCLEAR`: whether B is narrated as a direct reaction/response/consequence/result of A. This covers adversative reactions such as `матрос ухватил ... но Зурита ударил ...` without turning ordinary sequential coordination into CAUSE.
- **Cross-turn discourse relations now have an architectural path.** A `DiscourseRelationRefiner` walks backward only through the active H/FOLLOW experience chain and considers only active ordinary C/P event roots. It serializes UID-free event semantics within the existing context budget, asks three bounded choices (current event, prior source event, `CAUSE/FOLLOW`), and maps local indexes back through `IntegrationService.integrate_discourse_relation`. The model never sees canonical UIDs and never writes AH. There is no global AH scan or hidden semantic reranker; inactive history is inaccessible to this refiner. FOLLOW cycles and non-asserted/embedded/H-event endpoints are rejected deterministically at the Integration boundary.

Focused regressions cover factive vs non-factive complements, narrative-response causality, locative-head morphology, UID-free discourse selection, active-H-only access, canonical relation materialization, and rejection of embedded discourse endpoints.

Regression: `586 passed, 22 subtests passed`, `compileall OK`.

Подробности: `docs/SLICE_12_98.md`.

## v0.12.97 — proposition content and local narrative causality

- subordinate proposition content can now be represented canonically as `N.OBJECT -> N` instead of forcing the child SUBJECT into the matrix OBJECT slot;
- same-sentence narrative CAUSE remains source-only and model-gated, with a sparse review gate for SUBJECT↔OBJECT role transitions and passive-result re-mentions;
- serial perfective pairs retain conservative FOLLOW and add a non-canonical causal hypothesis only for participant continuity or a passive-result subject;
- pre-predicate bare locative PPs use deterministic event-location normalization, while the genuine instrumental attachment ambiguity remains a clarification.

Подробности: `docs/SLICE_12_97.md`.

## v0.12.96 — discourse and temporal refinement

Live `Document acceptance` on v0.12.95 remained runtime-stable (`98/98` paragraph semantic, `0` Runtime ERROR) and improved the literary graph to `house_by_pier 53/56`, Belyaev `25/36`, `old_observatory 45/61`. The remaining failures exposed four general mechanisms rather than transport/runtime faults.

- **Local pronoun identity is reopened after structural propagation.** Subject-control and coordination may temporarily copy an unresolved third-person pronoun into several frames with a synthetic local `entity_ref`. A pronoun-only ref is no longer mistaken for a resolved antecedent: it is reopened before the source-local coreference pass, while refs shared with a real non-pronominal mention remain intact. This targets patterns such as `Алексей ... Отперев калитку, он ...` and `стояла Вера ... Сняв плащ, она ...` without consulting global AH state during perception.
- **Cross-turn salience distinguishes a stable named subject from incidental common-noun subjects.** If exactly one source-grounded proper-name subject exists for a pronoun signature, it remains the discourse anchor; several distinct named subjects clear the anchor. With no named subject, ordinary source recency still wins. Proper-name status is morphology-driven and requires the best proper reading to be at least as strong as competing common-noun readings, so weak surname homographs do not become protagonists. This fixes `Марина ... Бумага ... печь ... Она ...` without a global animacy preference.
- **Clause CAUSE/FOLLOW attaches to the real source predicate.** Structural nominal helpers can share a host parse span. Relation derivation now compares each assertion predicate's own evidence with the clause predicate-head token instead of using the host assertion span. Thus `Бумага ... намокла, потому что вода просочилась` links `просочиться -> намокнуть`, not `просочиться -> structural-helper`.
- **Postnominal possessive detection is stricter at the morphology boundary.** The possessive adjective reading now requires the explicit `Anph+Apro+Fixd` signature. `Subx` by itself is insufficient because demonstrative/correlative forms can expose it too; this prevents constructions such as `то дрожала, то замирала` from being swallowed into the preceding NP.
- **Serial perfective narration gets conservative FOLLOW recovery.** Consecutive top-level asserted finite perfective events in one sentence receive FOLLOW when source order is explicit through additive `и/да`, or through a comma chain with exactly the same SUBJECT identity. Adversative/disjunctive coordination, semicolons, subordinate/relative/quoted clauses are excluded. This recovers literary sequences that the frame graph intentionally leaves as sibling clauses or that are interrupted by a gerund. No CAUSE is asserted by this rule; shared-participant pairs only receive a runtime causal candidate.
- Two oracle entries were corrected to reflect canonical memory rather than surface spelling: `увидел ... пачку писем` is disambiguated by its structured OBJECT (`пачка --GENITIVE_DEP--> письмо`), and `закрыла глаза` expects canonical `глаз[plur]`. These are stricter structural checks, not weakened literary expectations.

Focused regressions cover provisional pronoun reopening, non-possessive demonstrative morphology, source-predicate relation anchoring, comma/additive serial perfectives, and named-subject discourse salience.

Regression: `577 passed, 22 subtests passed`, `compileall OK`.

Подробности: `docs/SLICE_12_96.md`.


## v0.12.95 — narrative graph refinement

Live `Document acceptance` on v0.12.94 reached `98/98` paragraph semantic with `0` Runtime ERROR; the remaining failures were therefore graph semantics rather than transport/parser stability: `house_by_pier 51/56`, Belyaev `25/36`, `old_observatory 45/61`. This slice strengthens canonical event identity and performs only narrowly gated semantic causal enrichment. No literary oracle expectations were weakened.

- Canonical N writes now use monotonic **unique-match enrichment**. A repeated proposition with the same T/scope and non-conflicting shared role fillers reuses its existing UID and adds newly observed roles (`ветер усилился` + `ветер усилился над бухтой`). If zero or several compatible N exist, Integration creates/keeps a separate N instead of guessing event identity. Existing L links remain valid because enrichment edits the same UID.
- Broad `CAUSAL_CANDIDATE` hints remain runtime-only by default. A semantic `CAUSE` probe is now allowed only for a high-information local reaction pattern already fixed by syntax: in one non-relative finite sentence, an OBJECT/RECIPIENT of event A becomes the SUBJECT of the following event B. The probe sees only the source text and two events and returns `ENTAILED | NOT_ENTAILED | UNCLEAR`; only `ENTAILED` becomes canonical `L(CAUSE)`. Ordinary adjacency, relative clauses, nominal helpers and generic coordination do not trigger a semantic second pass.
- The Belyaev failure around `увидел, что ... приближалась подводная лодка` was reclassified correctly: `подводная лодка` was already a structured NP (`M_лодка --NOMINAL_MODIFIER--> M_подводный`); the missing piece was the matrix actant. A new orphan-subordinate participant refinement handles comma-heavy cases where a recognized subordinate connector is separated from its finite child by a detached parenthetical. Python narrows this to one matrix frame, one nearest asserted finite child and one child SUBJECT; a tiny `OBJECT | NO_DIRECT_OBJECT | UNCLEAR` probe may project that same structured participant into the free matrix OBJECT slot. The child assertion remains independently asserted; NO/UNCLEAR changes nothing.
- Reused copies of an unresolved third-person personal pronoun no longer receive a fresh local entity id before coreference. Structural inheritance/coordination gets one additional deterministic coreference pass before exact-source-span coalescing, allowing patterns like `Алексей ... . Он ...` / `Вера ... . Она ...` to retain the real antecedent instead of freezing a synthetic pronoun entity.
- Added focused regressions for ambiguous enrichment, template-valency growth with existing links, narrow causal promotion/uncertainty, generic adjacency non-probing, orphan subordinate participant projection, and delayed pronoun identity.

Regression: `571 passed, 22 subtests passed`, `compileall OK`.

Подробности: `docs/SLICE_12_95.md`.


## v0.12.94 — morphology boundary normalization

Live `Document acceptance` on v0.12.93 reached `98/98` paragraph semantic with `7` Runtime ERROR. All seven failures had the same integration traceback: pymorphy3's `tag.number` grammeme object escaped the morphology adapter despite `MorphInfo.number` being declared as `str | None`. Its overloaded equality then raised `ValueError` while EntityResolver compared canonical singular/plural identity metadata. The failure therefore was not literary semantics and not the new event-status probe; it was a type-boundary contract violation.

- `Pymorphy3Morphology` now converts every scalar tag attribute (`POS`, `case`, `number`, `gender`, `mood`, `animacy`) to an exact built-in Python `str` before creating `MorphInfo`. Library-specific grammeme scalar objects no longer cross the perception adapter boundary.
- `_grammatical_number_for_span` and `ActantCandidate.__post_init__` defensively normalize grammatical number again, so custom morphology implementations cannot leak a string subclass into Integration accidentally.
- `EntityResolver._filter_by_grammatical_number` also normalizes both the source constraint and legacy/in-memory entity metadata before comparison. This protects already-running/imported state created by older builds without weakening singular/plural identity separation.
- Added regressions with a fake grammeme scalar whose equality deliberately raises on unrelated values. The tests exercise the adapter boundary, `ActantCandidate`, and EntityResolver independently of whether pymorphy3 is installed in CI.

The live run itself already showed useful semantic progress before the crashes: `house_by_pier` reached `47/56`, and Belyaev reached `23/36`; most of the old-observatory deficit is contaminated by six of the seven runtime aborts and should be re-evaluated only after this fix. No oracle expectations or literary semantics were weakened in v0.12.94.

Regression: `563 passed, 22 subtests passed`, `compileall OK`.

Подробности: `docs/SLICE_12_94.md`.


## v0.12.93 — narrative identity + infinitive assertion status

Последний live `Document acceptance` на v0.12.92 стабилизировал runtime полностью (`98/98` paragraph semantic, `0` Runtime ERROR), поэтому этот срез исправляет уже собственно структурно-семантические ошибки литературного текста.

- Межпредложные/межклаузные connectives больше не связываются с предыдущим предложением только из-за линейной близости: parent для фронтального `После того как...` ищется внутри того же sentence.
- `CAUSE`/`FOLLOW` от clause markers теперь ориентируются на source predicate head, а не на вспомогательный structural fact, который мог быть материализован внутри той же клаузы.
- Omitted-subject inheritance и coordinated predicate sharing повторяются после non-finite control до fixed point, что закрывает случаи, где субъект появляется только после разрешения control.
- Singular/plural source morphology стала identity-relevant метаданными `M`: одинаковая lemma больше не схлопывает `матрос` и `матросы` в одну глобальную сущность. Quantified NP вроде `несколько матросов` сохраняет common-noun lemma и plural cardinality вместо surname-homograph.
- Case-syncretic N+N (`кусок штукатурки`, `стекло лампы`) разрешается только одним локальным bounded attachment probe: `GENITIVE_DEP | SEPARATE | UNCLEAR`. Постпозитивное `его/её/их` при реально возможной participant-интерпретации аналогично получает локальный `POSSESSOR | SEPARATE_PARTICIPANT | UNCLEAR`, поэтому `падение штукатурки его испугало` не обязано поглощать `его` внутрь NP.
- Слабая predicative morphology внутри явно управляемой PP больше не создаёт ложный predicate head, если та же source form имеет oblique nominal reading (`с крючков`-класс homograph-ов).
- Для `NONFINITE` теперь отдельно решается truth status вложенного INFN. После того как Python уже установил одну конкретную matrix/infinitive пару, tiny source-only probe выбирает `ASSERTED_EVENT`, `NONASSERTED_CONTENT` или `UNCLEAR`. Это различает `продолжала идти / начала просачиваться / успел подняться` и `хотел уйти / попросил уйти` без словаря фазовых/модальных глаголов. `ASSERTED_EVENT` не переводится в `EMBEDDED`; `UNCLEAR` и protocol failure остаются conservative embedded.
- Новый semantic probe не видит AH UID, Workspace, canonical entity candidates или proof state и принудительно работает с thinking off; он является post-parse semantic enrichment, а не вторым parser-ом.
- Document oracle теперь умеет проверять `grammatical_number` canonical entity, чтобы literary acceptance различал singular instance и plural/group identity на текущем уровне модели.

Подробности: `docs/SLICE_12_93.md`. Regression: `560 passed, 22 subtests passed`, `compileall OK`.



## v0.12.92 — structured nominal heads + discourse control

Последний live `Document acceptance` на v0.12.91 дал `3/6` документов, `97/98` paragraph semantic и один Runtime ERROR. Три технических документа остались полностью зелёными; литературные документы теперь в основном показывают не runtime-падения, а качество событийного/дискурсивного графа. Разбор этого прогона выявил несколько общих механизмов, которые были исправлены без словарных патчей под конкретные фразы.

- Реальная morphology текущего pymorphy для постпозитивного `его/её/их` использует possessive-adjective signature `Apro+Anph+Fixd`, тогда как старые unit fixtures проверяли только `Subx`. Оба явных структурных варианта теперь поддерживаются; `торжество его` остаётся одной NP на perception-границе и затем декомпозируется в head + `POSSESSOR`, а не оставляет `его` ложным отдельным actant.
- Обычные атрибутивные NP больше не становятся opaque M: `сухая ветка`, `керосиновая лампа`, `старая обсерватория`, `разбухшая створка` используют canonical identity головного nominal и source-grounded `NOMINAL_MODIFIER(head, modifier)`. Это слабая структурная L: она не превращает прилагательное автоматически в MATERIAL/STATE/CAUSE или скрытое событие. Модификаторы вложенного генитива остаются на собственном head (`нижний ящик письменного стола` -> modifier(ящик, нижний), genitive(ящик, стол), modifier(стол, письменный)).
- Coreference agreement теперь проверяет source-inflected nominal head прежде canonical lookup lemma. Поэтому plural source `письма/документы` не становится грамматически singular только из-за `normalized_hint=письмо/документ`, а локальное `их` может связаться с фактически plural antecedent вместо падения в устаревший cross-turn anchor.
- Для `FrameDependencyKind.NONFINITE` добавлен отдельный deterministic control только для GRND: matrix SUBJECT наследуется деепричастным frame (`Отперев калитку, Алексей вошёл`). На INFN правило намеренно не распространяется, поскольку в `попросил его уйти` controller может быть другим участником.
- `InteractionContext.pronoun_refs` теперь обновляется по source-recency SUBJECT внутри turn. При двух одинаковых по роду субъектах ранний больше не стирает поздний: `Лампа погасла. Точка появилась.` оставляет `она -> точка`. При реальной ничьей разных canonical refs anchor по-прежнему удаляется. Это только runtime salience cache, не canonical truth.
- Document oracle научился проверять structured NP напрямую: expected participant может требовать canonical head и конкретные NP-internal L edges. Поэтому `стекло лампы` и `подводная лодка` больше не вынуждают тест ожидать старую opaque строку после перехода памяти на структурное представление.

Отдельно не объявляется решённой проблема instance/plural individuation: head normalization структурирует описание, но существующая M-identity модель всё ещё не различает автоматически два разных экземпляра одного и того же nominal head и не представляет неопределённую plural group как отдельную исчислимую группу. Это следующий уровень identity semantics, а не повод снова хранить NP одной строкой. Causal induction из литературной последовательности также не менялся в этом срезе.

Подробности: `docs/SLICE_12_92.md`. Regression: `549 passed, 22 subtests passed`, `compileall OK`.


## v0.12.91 — LM Studio protocol-output guard

This release hardens the LM Studio transport for bounded perception/semantic probes.

- `llm.enable_thinking=false` is now actually propagated to LM Studio on every chat request through both the top-level `enable_thinking` field and `chat_template_kwargs.enable_thinking`.
- Empty `message.content` is no longer accepted as a valid model answer. The client fails closed with `finish_reason`, completion/reasoning token counts (when available), and a flag indicating whether a hidden reasoning channel was present.
- Hidden `reasoning_content` is deliberately **not** consumed as a parser answer: deterministic AH probes require the requested protocol label in ordinary assistant content.
- The change is transport-only; canonical AH, nominal relations, EventNormalizer, Integration, Ignition, and inference semantics are unchanged from v0.12.90.

The guard addresses LM Studio reasoning-mode failures where a small `max_tokens` budget is spent entirely on hidden reasoning, leaving the OpenAI-compatible `message.content` empty. If the LM Studio build ignores per-request reasoning controls, disable the model's **Enable Thinking** setting in LM Studio; v0.12.91 will now report that condition directly instead of surfacing dozens of misleading parser protocol errors.

## v0.12.90 — structural nominal relations in canonical AH

Исправлено плоское хранение многословных именных групп вроде `торжество его`, `мой проект`, `дверь здания`. Perception теперь отделяет identity головного существительного от внутренней структуры NP и передаёт runtime-only `NominalRelationCandidate`. Явная possessive morphology становится `POSSESSOR`, обычная генитивная зависимость — более слабым `GENITIVE_DEP` без догадки, что любой родительный падеж означает владение.

Integration материализует эти отношения как типизированные canonical `L` только для обычного ASSERTED content: `HEAD --POSSESSOR--> owner` и `HEAD --GENITIVE_DEP--> dependent`. Embedded/quoted/conditional/negated content не протекает в world graph. Вложенные генитивы сохраняются цепочкой (`дверь дома брата` → `дверь→дом→брат`), а main `N` ссылается на `M_дверь`, а не на opaque `M_"дверь дома брата"`. Постпозитивный third-person possessor может переиспользовать уникальный turn-local antecedent; first/second-person possessives разрешаются через deixis.

Подробности: `docs/SLICE_12_90.md`. Regression: `537 passed, 22 subtests passed`, `compileall OK`.


## v0.12.89 — source-bounded perception + literary anaphora

Убран `max_acts` как семантический потолок perception. Parser больше не ограничивает число событий константой: он последовательно потребляет все конечные predicate/implicit frames, которые реально присутствуют в source candidate graph. Если модель отвечает `NONE`, пока deterministic frames ещё остались, parser по-прежнему fail-closed и не коммитит частичный смысл. Поле `llm.perception.max_acts` удалено из config/runtime/GUI; GUI показывает `acts=source-bounded`.

По live literary run дополнительно закрыты два общих грамматико-дискурсивных дефекта: deterministic copular holder теперь включает непосредственно постпозитивный possessive anaphor (`торжество его`), а local personal-pronoun resolver больше не считает обычный adjectival STATE референтной сущностью. Для явно связанного `NONFINITE -> matrix` frame добавлено безопасное same-role continuity: если у матричного местоимения существует ровно один совместимый участник той же роли в non-finite child, используется его source identity (`Сняв плащ, она повесила его`).

Подробности: `docs/SLICE_12_89.md`.


## v0.12.88 — literary reliability: grammar, discourse and acceptance boundary

Разбор live document-run `20260823_041519_+0300` показал два разных класса проблем. Первые три технических документа сохранили итоговые графы без единой ошибки (`18/18`, `18/18`, `19/19`), но новый runtime-only `relation_hints` ошибочно учитывался старым exact-oracle как обязательный канал. Теперь semantic oracle проверяет hints только если поле `relation_hints` явно присутствует в oracle.

Лимит perception `max_acts=4` оказался ресурсным потолком, а не семантическим ограничением: 13 из 14 runtime failures реальной прозы возникли на предложениях с более чем четырьмя meaningful predicate frames. Shipped/default budget поднят до 12 (валидатор по-прежнему ограничивает его сверху 16); explicit test settings `max_acts=4` продолжают проверять fail-closed поведение.

Cross-turn coreference усилен общими русскими грамматическими правилами без словарей по персонажам:

- discourse signature SUBJECT сначала использует число/род finite predicate agreement, затем только при отсутствии такого сигнала — morphology самого nominal. Это покрывает неизменяемые/неоднозначные имена и количественные NP (`... стоял` → `он`, `... вошли` → `они`);
- oblique third-person paradigm (`его/ему/ей/их/...`) может детерминированно dereference nominative anchors из `InteractionContext`, но только если все грамматически совместимые anchors сводятся к одному canonical Ref;
- локальный third-person oblique pronoun не может bind-иться к SUBJECT той же клаузы (`X схватил его` требует другого antecedent; самореференция по-русски выражается `себя`);
- postnominal possessive anaphor остаётся частью NP (`решение его`, `торжество его`) и больше не становится ложным отдельным copular actant;
- explicit predicate coordination теперь переносит постпозитивный общий SUBJECT вправо (`выпустили матросы ... и упали`) при отсутствии нового nominative subject shell.

Ручной oracle Беляева также исправлен как oracle, а не как parser patch: ранний `Педро` больше не требует скрытого знания `Педро == Зурита` до того, как сам фрагмент позже произнесёт полное имя `Педро Зурита`; проверки группы матросов меньше зависят от одного upstream `same_as` anchor, чтобы event extraction не маскировался каскадом diagnostic failures.

Regression: `526 passed, 22 subtests passed`, `compileall OK`.

Подробности: `docs/SLICE_12_88.md`.


## v0.12.87 — event normalization + third literary monolith

После первого литературного document-run добавлен отдельный deterministic `EventNormalizer` между разобранным linguistic frame graph и canonical Integration. Он восстанавливает independently asserted gerund events, консервативный `FOLLOW` для безопасной временной последовательности, result-state из пассивных полных причастий и runtime-only `CAUSAL_CANDIDATE`/temporal hints. Narrative adjacency сама по себе не становится `CAUSE`; `relation_hints` валидируются, но Integration их не материализует.

Исправлен общий дефект correlated pronoun alternatives: все потенциальные antecedent source mentions получают стабильные turn-local `entity_ref` до ветвления, поэтому альтернативы отличаются только anaphoric role binding, а не случайными мутациями других ролей. После EventNormalizer повторно запускается exact-source-span identity binding, чтобы вновь созданный result-state и исходный факт ссылались на одну сущность.

Document graph oracle получил `forbidden_facts` и scoped matching (`ASSERTED` против `EMBEDDED/QUOTED/...`), а итоговый отчёт теперь отдельно показывает event extraction, temporal graph, causal graph и negative constraints.

Добавлен третий литературный монолит `old_observatory_monolith`: 34 предложения / 17 bounded ingestion windows, написанный вручную как связная проза с деепричастиями, причастиями, прямой речью, двумя персонажами, subjective-content эпизодом и естественной событийной последовательностью. Oracle написан вручную: 40 фактов, 16 FOLLOW, 3 forbidden CAUSE, 2 forbidden asserted-world facts, 4 будущих M2 paths. `Document acceptance` теперь прогоняет шесть документов за один запуск.

Подробности: `docs/SLICE_12_87.md`. Regression: `519 passed, 22 subtests passed`.


## v0.12.86 — public-domain literary monolith (Belyaev)

Document acceptance adds a second real literary monolith: an unadapted public-domain excerpt from A. R. Belyaev's 1928 novel `Человек-амфибия`, chapter `Покинутая «Медуза»`. Unlike the hand-authored `house_by_pier_monolith`, this source was not written around parser-friendly causal connectives. It contains combat, pronoun continuity, embedded thought, dialogue, implicit motivation and causal transitions expressed through narrative rather than repeated `потому что`.

The source stays one continuous file and is ingested as one document scenario. Because literary dialogue exposes boundaries not covered by the previous sentence splitter, monolith ingestion now also recognizes a new dialogue turn after terminal punctuation plus an em dash when the next token begins a new utterance; author-attribution continuations with a lowercase token remain inside the same sentence. This is an ingestion-only rule and does not inspect AH, oracle labels or semantics.

The hand-written final oracle checks 25 canonical events, cross-sentence identity (`Педро`/`Зурита`, crew references and pronouns), seven typed CAUSE/FOLLOW expectations, three forbidden causal edges and three predeclared M2 questions. A two-edge implicit physical CAUSE chain (`матрос схватил → Зурита ударил → матрос упал`) is intentionally required without an explicit causal connective.

Regression: `511 passed, 22 subtests passed`.

## v0.12.85 — literary monolith document acceptance

Document acceptance now also accepts a source file as one continuous monolithic text. The source is deterministically split only at explicit sentence boundaries into bounded perception windows; the source itself is not pre-summarized or semantically rewritten, and one scenario keeps AH/InteractionContext/Ignition continuous across every window. The exact ingest plan is saved as `document_ingest_plan.json`.

A new hand-written literary scenario, `house_by_pier_monolith`, contains 30 connected sentences in one paragraph and a manually authored final graph oracle. It checks cross-window entity identity, CAUSE/FOLLOW structure, forbidden causal edges, and a six-edge CAUSE path reserved for M2. See `docs/SLICE_12_85.md`.

## v0.12.84 — document reliability fixes

Разбор первого ручного document acceptance (15/21 paragraph PASS, 0 runtime errors) выявил четыре общих класса ошибок. Исправления сделаны как архитектурные механизмы, без словарей под конкретные тексты:

- подавление ложного non-finite predicate head, когда GRND/INFN-гомограф одновременно является согласованным номинативным участником следующего сильного finite predicate без границы/координатора;
- deterministic SUBJECT для единственного согласованного номинатива активного intransitive finite frame (совместное ограничение валентности+согласования, не общий NOM→SUBJECT shortcut);
- cross-turn discourse anchoring для `он/она/оно/они` через уникальный same-role SUBJECT предыдущего внешнего turn; при нескольких совместимых кандидатах anchor удаляется, а не угадывается;
- role-conditioned lexical normalization bare SUBJECT/OBJECT: уже установленная семантическая роль может выбрать редкое, но грамматически совместимое NOM/ACC чтение вместо top-score homograph;
- уточнено различие OBJECT vs RECIPIENT для адресата речи/телефона/сообщений в bounded role cue.

Regression: `507 passed, 22 subtests passed`.

## v0.12.83 — manual document-level acceptance

Добавлен второй acceptance-слой для связных текстов. Он намеренно не использует генератор синтетических сценариев: корпус состоит из трёх вручную написанных многоабзацных документов (`data/document_acceptance/texts/`) и отдельного hand-authored oracle (`data/document_acceptance/oracle.json`).

Каждый документ прогоняется как один scenario: между его абзацами сохраняются AH, InteractionContext и Ignition state, а между разными документами runner возвращается к исходному baseline. Абзац является только технической границей одного perception-вызова; причинная цепь проверяется уже на итоговом canonical graph и обязана сшиваться через повторное использование тех же N/M между абзацами.

Текущий набор:

- `cooling_station` — CAUSE-цепь глубины 6 + независимые наблюдения/distractors;
- `greenhouse_control` — CAUSE-цепь глубины 6 + cross-paragraph coreference (`Она` → `Анна`) + distractors;
- `archive_leak` — CAUSE-цепь глубины 5, затем два FOLLOW шага; это заранее подготовленный mixed proof path для следующего этапа M2.

Для каждого абзаца используется тот же строгий semantic oracle, что и в broad-200: exact assertions/roles/relations, canonical integration и отсутствие лишних query outcomes. После последнего абзаца дополнительный graph oracle проверяет ключевые canonical N, направление CAUSE/FOLLOW, длину причинной цепочки и явно запрещённые ложные causal edges. В oracle также сохранены typed `m2_questions` с ожидаемыми путями; v0.12.83 их пока не исполняет — они предназначены для следующего этапа M2, чтобы inference тестировался на графе, реально построенном из текста.

В GUI добавлена кнопка `Document acceptance`. Результаты пишутся в `data/document_acceptance_runs/<timestamp>/`, включая обычные turn diagnostics, `document_report.json`, `document_summary.txt` и сопоставление oracle fact IDs с фактическими canonical UID. Живое состояние пользователя после диагностики восстанавливается, как и в обычном acceptance.

Regression: `501 passed, 22 subtests passed`.

## v0.12.82 — bare-PP ambiguity boundary

Live LM Studio acceptance on v0.12.81 reached `Runtime OK 200/200`, `Semantic PASS 198/200`. Both remaining FAILs were the same grammatical class: a larger adverbially headed relational modifier containing an internal instrumental PP (for example, `ADVB + PREP + instrumental`) was incorrectly promoted to the hard postnominal-PP ambiguity path.

The structural rule is narrowed generically:

- hard clarification from instrumental morphology is allowed only for a **bare postnominal PP** whose selected modifier span itself starts with `PREP`;
- if the instrumental PP is embedded inside a larger lexically headed modifier, instrumental case alone is not sufficient evidence that the whole modifier can attach to the adjacent nominal;
- such larger modifiers return to the existing bounded `EVENT / NOMINAL_n / UNCLEAR` attachment decision;
- genuine bare cases such as `NP + с + instrumental` retain the deterministic clarification path; no predicate/noun/fixed-sentence dictionary was added.

A lexical-independent regression fixture uses a different predicate and nouns and verifies that `ADVB + PREP + instrumental` is not blanket-classified as ambiguity, while the existing bare instrumental ambiguity test remains unchanged.

Full regression suite: `496 passed, 22 subtests passed`.

## v0.12.81 — semantic-boundary reliability before M2

Этот срез закрывает системные причины 31 FAIL из live acceptance `20260822_211650`, не добавляя словарных правил под отдельные предложения:

- `EMBEDDED`-факт сам по себе больше не становится inference goal: goal compiler строит цели только от явных `QUERY/COMMAND` roots; это отделяет внутреннее содержание утверждения от пользовательского запроса и убирает ложные `query_outcomes`;
- coreference сохраняет все грамматические чтения закрытого класса местоимений и учитывает синкретизм косвенных форм третьего лица до same-role/discourse resolution;
- неоднозначное post-nominal PP с инструментальным дополнением определяется по морфосинтаксису как структурная attachment ambiguity и требует clarification вместо LLM-vote по правдоподобию; directional/non-instrumental PP не попадают под это правило автоматически;
- `NUMR + nominal` после semantic role resolution нормализуется в counted participant + `AMOUNT`; уже распознанный `DURATION` остаётся единым временным значением;
- известный query filler, ошибочно размеченный ролью вне выбранного T, повторно решается только среди свободных UID-free ролей уже выбранного шаблона; query-side filler не может молча расширить canonical T неверной ролью;
- noun-headed `NOMINAL_PREDICATION` больше не отправляется в общий binary `IS-A` classifier по паре SUBJECT/OBJECT, поэтому complement отношения имени/названия/свойства не превращается в ложную taxonomy link;
- nominal label projection prompt усилен явным контрастом `name/title/label of Y` против прочих nominal relations, оставаясь одним локальным `YES/NO/UNCLEAR` semantic probe.

Новые regression-тесты проверяют свойства на других лексемах и конструкциях, а не на acceptance-фразах. Полный suite: `495 passed, 22 subtests passed`.


## v0.12.78 — LM Studio server backend

Этот срез добавляет третий LLM transport без изменения AH Core / Perception / Agent contracts:

- `llm.backend = "lmstudio"` подключается к локальному LM Studio server (по умолчанию `http://127.0.0.1:1234`);
- модель остаётся загруженной и управляется самим LM Studio, AH runtime не создаёт второй process и не трогает VRAM/offload policy;
- discovery идёт через `/api/v1/models`, inference — через stateless OpenAI-compatible `/v1/chat/completions`;
- каждый запрос явно содержит только `system + current user payload`, `history_messages=0`, `stream=false`;
- если `lmstudio_model` пуст/`auto`, backend выбирает единственную загруженную LLM; при нескольких загруженных моделях fail-closed требует exact model key;
- `temperature/top_p/top_k/repetition_penalty/max_new_tokens` прокидываются в LM Studio request;
- machine-protocol роли дополнительно очищаются от Qwen-style `<think>...</think>`;
- добавлены `config/lmstudio.toml` и `run_gui_lmstudio.bat`;
- backend сохраняет существующие runtime diagnostics, request trace и единый shared-model contract для Perception + Agent.

Быстрый запуск: включить Local Server в LM Studio, загрузить нужную модель и запустить `run_gui_lmstudio.bat`. Если в LM Studio загружено несколько LLM, вписать точный model key в `config/lmstudio.toml -> llm.lmstudio_model`.

`docs/reference/Архитектура_v3.md` — архитектурный источник для реализации. Код строится так, чтобы каноническая память, runtime-динамика, inference и LLM boundary оставались отдельными слоями.

## v0.12.60 — Proof Explorer / transparent M2

Этот срез добавляет runtime-only визуализацию логического вывода, не превращая trace в семантическую память.

- отдельное окно `Логический вывод — Proof Explorer` хранит session-history live, acceptance и M2 inference outcomes;
- выбранная цепочка имеет собственный proof-canvas: только реально использованные propositions и canonical links;
- вкладка `Семантика / логика` показывает Goal, правило и человеческое объяснение каждого шага, а затем итоговое заключение;
- вкладка `UID trace` показывает точный canonical trace рядом с зафиксированной семантикой;
- вкладка `Проверки M2` раскрывает каждую acceptance-инварианту отдельно вместо одного агрегата 32/32;
- live/acceptance proof можно подсветить поверх основного canvas без изменения AH; M2 sandbox не материализуется в live memory и отображается в собственном proof-canvas;
- M2 `result.json` теперь содержит полный замороженный ProofSnapshot каждого case, а `report.txt` — семантические шаги и PASS/FAIL каждой проверки;
- ordinary GUI turns и general acceptance suite используют тот же `ProofSnapshotBuilder`, то есть viewer не является отдельной тестовой логикой.

GUI toolbar: `Логический вывод`. После M2-прогона окно открывается автоматически и получает все 32 cases.

## v0.12.59 — M2 inference attention on arbitrary AH

Этот срез исправляет границу между M2 inference и Ignition. Холодный Workspace теперь используется только как контроль чистоты первого acceptance-case: он доказывает, что Goal не был заранее доступен как активный контекст. Сам inference не требует холодной памяти и работает при произвольном текущем Workspace.

- `CAUSE / FOLLOW / IS-A` proof search переносит фокус через `QUERY_RECALL` и обычный synchronous Ignition tick перед расширением текущей proposition;
- rule-driven proof и `GOAL_SATISFIED` остаются логическими критериями: excitation влияет на доступ/приоритет, но не делает proposition истинной;
- sparse Ignition tick обрабатывает активный/incoming frontier вместо deep-copy полного runtime-state на каждом шаге;
- inference использует локальные canonical indexes для role lookup, `FALSE(...)` и adjacency, а bounded reverse-goal reachability только отсекает структурно мёртвые ветви до расходования proof budget;
- M2 operator runner работает на snapshot текущей AH без мутации live memory, дополняет sandbox до минимум `150000` canonical UIDs и прогоняет 32 cold/warm/branched cases;
- acceptance проверяет exact proof UID trace, exact attention sequence, реальное изменение `x`, отсутствие tail-after-Goal и отсутствие утечки в независимые/ложные ветви;
- архитектурный reference восстановлен ровно из пользовательской спецификации v0.4 без отдельной «чистой AH» как runtime-требования.

GUI: `M2: inference attention`. CLI остаётся `ah-agent --config config/default.toml m2-acceptance`.

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


## v0.25.5 changes
- Added GUI button `M1: ellipsis acceptance` wired to `data/acceptance_ellipsis/cases.txt` and `oracle.json`.
- Added separate output folder `acceptance_runs_m1_ellipsis`.


## v0.25.6 — ellipsis acceptance oracle hotfix

- Fixed `data/acceptance_ellipsis/oracle.json` to the real semantic-oracle schema (`version: 1`, `cases: [...]`).
- Fixed `cases.txt`: one utterance per line; removed `[ELL_*]` labels that the runner was incorrectly counting as test requests.
- Expanded the runnable ellipsis suite to 22 real cases across predicate/frame inheritance, proposition negation/confirmation, temporal and locative ellipsis.
- Added regression that loads both files through the production loaders and validates exact alignment.
