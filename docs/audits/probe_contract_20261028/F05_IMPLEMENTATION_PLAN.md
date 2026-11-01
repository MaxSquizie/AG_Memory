# F05 — аудит контура и последовательный план исправлений

Дата: 2026-11-01. Аудируемая версия: `f467d1355fadf0cf9e6f57b95d0948c62069eacb`.
Статус: **план реализации, не отчёт о закрытии F05**. Код в этом аудите не изменялся.

## 1. Что считается контуром и доказательством

Область — шесть блоков F05 из F05_STATUS.md: локальные референты; рекурсивные
группы/структурные альтернативы; описания/владельцы; кванторы/дочерние чтения;
источники/страницы/бюджет; завершение/основания/запись. Сквозные механики —
морфологические основания, типизированные входы, propagation, кеш, resume,
пересмотр, historical validation и поздние потребители. Полнота ЕЯ не заявляется.

Аудит проходил по фактическим границам от `relation_composition.compose` и
`component_refinement.compose_area` через scalar и conditional producers,
source domains, child scheduler, выбор/проверки, native lowering и запись.
Перечень файлов и символов приведён в приложении `F05_AUDIT_SCOPE.json`.
Статические наблюдения ниже не выдаются за сквозные прогоны.

Классы выводов:

- **D — подтверждённое рассогласование:** producer/consumer или проверка читают
  несовместимые данные; указано конкретное условие нарушения.
- **G — подтверждённый пробел реализации:** код явно останавливается/pending либо
  реестр/производитель не содержит заявленную возможность. Pending безопасен,
  но не заменяет реализацию.
- **V — обязательная проверка границы:** есть подозрительный фильтр или несколько
  путей; дефект не доказан. Сначала воспроизвести и определить контракт, затем
  менять код только при подтверждении.
- **A — архитектурный вопрос:** нельзя реализовывать ответ догадкой. Указан
  конкретный вопрос; независимая работа остальных карточек продолжается.

Достаточность плана условная: для каждого заявленного семейства требуется
producer → неизменяемое основание → адресованный consumer → cache/resume →
отзыв → late consumer. Выполнение всех карточек и контрольной матрицы даёт
основание закрыть заявленные механики. Сам статический аудит не доказывает
правильность будущей реализации, ответов LLM или всех языковых разборов.

Согласованный DEFER: арифметические кванторы; переиспользование параметризованных
языковых схем. Не переносить в DEFER остальные заявленные механики. Первичное
окно вложенности — до трёх уровней, затем адресованное расширение; число соседних
операндов не является глубиной и не должно расходовать её как вложенность.

## 2. Карта всего маршрута

| Участок | Действующие места | Главная незакрытая обязанность | Карточки |
|---|---|---|---|
| Морфология/предложения/чтения | morphology_domain, nominal_readings, contextual_* | точный payload разрешает точное употребление; witness не подменяется | P01–P04 |
| Grammar/component domains | grammar_domains, composition_sources, component_predication | живые кандидаты, открытые источники и полнота не смешаны | P05, P15, P16 |
| Выбор отношения/разбиение | relation_composition, PartitionDomain, partition_sequences | альтернативы границ/NEXT, subset sharing, доказанные исключения | P06–P08 |
| Условное исполнение | structural_relations/shells/lexical/frontier | все заявленные producers и staged child demands исполнимы | P09–P11 |
| Описания/владельцы | component_refinement, relative_pronoun, refinement_host_proof/path | совместные домены host/role/reading и scoped proof | P12–P13 |
| Кванторы/control/scope | relation_quantifiers, quantifier_composition, bound_references, control_arguments | typed binder/control; nested scope и совместные чтения | P14–P15 |
| Ссылки/группы | nominal_reference_domain/pages/memory/chain, nominal_group_* | альтернативные рёбра, все объявленные типы targets, независимые основания | P17–P18 |
| Кеш/историческая проверка | dispatcher, producer_reads, validation_graph, issuer, context_receipts | полный набор чтений, empty/negative queries, retraction/rebuild | P04, P19 |
| Closure/seal/native/write | task_contracts.child_result, partial_composition, composition_tree, seal, native_plan, commit_stage | convergence certificate и общий допуск к записи | P20–P22 |
| Проверки/ресурсы | tests, tools/recovery, acceptance/oracle | реальные контракты и различение видов доказательств | P00, P23 |

Названия без расширения в таблице — модули `src/ah/formalizer/`. Таблица —
перечень границ аудита, не заявление о проверке каждой строки всех файлов.

## 3. Порядок работы и зависимости

Выполнять пакетами, сохраняя отдельные reviewable commits. Нельзя закрывать
архитектурную механику по одному пакету.

1. P00: зафиксировать действующие контракты и причины baseline failures.
2. P20-contract (только спецификация completion receipts), затем P01 → P02 → P03 → P04: общий слой оснований и его потребители/кеш.
3. P05 → P06 → P07 → P08: источники, домены, разбиения и пересмотр.
4. P09-contract → P10 → P11: полный реестр producers, staged execution и propagation.
5. P12 → P13; P14 → P15; P17 → P18: предметные механики на общих основаниях.
6. P09-integration после P10–P15, затем P16: закрыть фактически реализованные semantic obligations всех bundles.
7. P19 → P20 → P21 → P22: сквозные зависимости, closure, native и durable отзыв.
8. P23: конечная матрица проверки и сверка всех шести блоков.

Предварительная спецификация P20-contract нужна уже в P05/P09-contract, чтобы producers выдавали
нужные completion receipts. Реализация допуска P20 идёт после producers;
до реализации P20-validation все существующие запреты на публикацию открытого леса сохраняются.
В зависимостях ниже P09 означает P09-contract, P20-contract — только спецификацию.
Готовность P09-integration проверяется после P10–P15, затем P16–P23.
P12/P14/P17 можно проектировать заранее, но не делать свои отдельные stores,
схемы proofs или диспетчеры вместо P01/P05/P09.

## 4. Карточки исправлений

### P00. Зафиксировать входную спецификацию и разделить ошибки проверок

**ACCEPT, 2026-11-01 — только инвентаризация.**
Результат: [F05_P00_BASELINE.md](F05_P00_BASELINE.md),
реестр: [F05_CAPABILITIES.md](F05_CAPABILITIES.md).
Каждая последующая карточка ссылается на capability ID; INVESTIGATE не закрывает runtime.

**Тип:** V. **Блоки:** 1–6. **Зависимости:** нет.
**Места:** F05_STATUS.md, FORMALIZER_ARCHITECTURE_V7.md, F05_MECHANISM_COVERAGE.md;
`tests/test_composition_dispatcher.py`, `test_oov_paradigm_forms.py`,
`test_nominal_predication_tasks.py`; `tools/recovery/check_f05_*.py`.

На предыдущей контрольной точке зарегистрированы 19 failures, воспроизводимых
и на исходном коммите; это не положительное доказательство исправности. Для каждого
записать первый нарушенный переход, окончательный prompt/ответ, фактический результат
и источник ожидания. Разделить: дефект кода, недостаточность контекста, ошибка ответа,
неполный script/oracle и устаревший протокол. Не обновлять ожидаемые значения ради pass.

Составить проверяемый registry заявленных возможностей F05, включая все меню
relations и типы source/target, с исходной архитектурной ссылкой. Артефакт каждой
следующей карточки должен ссылаться на строки этого registry.
**Готовность:** у каждой failure есть причина или явное INVESTIGATE; ни одна не
исчезла из отчёта. Исправления ожиданий обоснованы отдельно от правок реализации.

### P01. Единый адрес основания и типизированный reading-use witness

**Тип:** D/G. **Блоки:** 2–6. **Зависимости:** P00.
**Места:** `morphology_domain.function_use/license_use/attested`,
`reading_decisions.inspect/receipt`, `partial_readings.retain`, `probe_prerequisites`.

`function_use` возвращает True для всех decision slots кроме специального OOV.
Значит существующий selected decision может разрешить предложенное чтение, не
следующее из его payload. `reading_decisions` намеренно проверяет lifecycle,
а не эту семантическую связь. При отсутствии raw record synthetic decision также
не получает машинно проверяемую parent dependency автоматически.

Специфицировать общий witness: source/revision, region/input scope, condition,
occurrence, целое reading, вид использования, выбранный payload и его proof,
правило допустимого преобразования, родительские witnesses, resource version.
Разделить ORIGINAL, DERIVED, SELECTED_DOMAIN; наличие singleton не создаёт proof.
Валидатор должен иметь явные historical адреса; runtime adapter лишь подставляет
текущий адрес. Не делать глобальный whitelist slots доказательством чтения.
**Готовность:** чужой выбранный candidate не лицензирует reading; отсутствие
основания даёт UNKNOWN/STALE, а доказанное несоответствие — conflict; public
безусловный validator отвергает conditional witness.

### P02. Перевести всех производителей reading-use на общий witness

**Тип:** D. **Блоки:** 2–4. **Зависимости:** P01.
**Места и точные адаптеры:**

| Producer | Что должно быть связано с употреблением |
|---|---|
| component_predication._compose_alternatives | выбранный bundle, конкретный frame и occurrence reading |
| composition_children.select_child | выбранные frame_refs, child slot и reading внутри этого output |
| component_dependency_reduction.reduce | выбранный attachment, morph/head_morph, ROOT role либо host/layer |
| quantifier_composition._bind | selected head, целое reading, structural/head/partition proofs |
| nominal_functions.prepositions/shared_nominal_readings | source function, head/function refs, разрешённая проекция без выдуманных признаков |
| qualitative_quantity.resolve/general_groups | quantity expression, внутреннее чтение и внешний падеж как разные значения |
| contextual_oov.resolve | POS domain и адрес; неизвестные lemma/case/number остаются неизвестными |

У deterministic binder сейчас Ground D содержит ссылку head_license текстом.
Заменить её типизированной цепочкой, которую P01 может повторно проверить.
Проверить оба producer partial-reading domains: predicate_functions и
component_dependency_reduction. Role projection уже выровнен; этого недостаточно
без полного payload-to-use соответствия.
**Готовность:** все вызовы license_use либо передают новый witness, либо удалены
с доказательством неприменимости; запрет старого непроверяемого пути без скрытого
fallback. Каждый адаптер проверен на wrong token, whole reading, role/head и branch.

### P03. Неизменяемые morphology witnesses и полный обход потребителей

**Тип:** D/G. **Блоки:** 2–6. **Зависимости:** P01–P02.
**Места:** `morphology_domain.project/attested/function_restrictions`,
`nominal_readings.attested`, `composition_morphology.publish_recoveries`,
`contextual_agreement`, `nominal_apposition`, `component_dependency_materialization`,
`quantifier_composition.licensed`, `composition_tree`.

Decision receipt не связывает изменяемые MORPHOLOGY_PROPOSAL/USE,
MORPHOLOGY_DOMAIN_RESTRICTION, FUNCTION_RESTRICTION/IMPORT, AGREEMENT_RECOVERY,
QUANTITY_COMPOSITION. Правка такой строки может изменить результат attestation
без изменения decision stamp. Нынешний final gate расширен на derived origins,
но это не полнота adapters всех происхождений.

Ввести неизменяемый witness или проверяемую версию каждого преобразования и
его полного входа. Исходные словарные evidence отделить от опубликованных derived
variants; recovery не становится оригиналом при копировании. Для всех typed
locations (`morph_bindings`, `pp_readings`, nominal dependencies, group internal/external
readings и дополнительных мест из inventory) зарегистрировать getter и validator.
**Готовность:** изменение witness row, исходного token или resource отзывает use;
изменение score не меняет лингвистическое reading; остальные признаки не теряются.
Нет непроверенного CONTEXTUAL/RECOVERED пути, включая поздний planner/seal.

### P04. Связать все чтения оснований с кешем, включая отсутствие данных

**Тип:** D/G/V. **Блоки:** 5–6. **Зависимости:** P03.
**Места:** `dispatch_evidence.valid/evidence_probe_refs`,
`composition_dispatcher.observe/evidence_valid`, `producer_reads`,
`validation_graph.overlay/key`, `reading_decisions`, `bundle_constraints`.

READING_DECISION подписывает decision, но не весь witness set из P03. Нужны
наблюдения exact witness и addressed query, включая пустой результат. Добавление
нового ограничения должно отзывать прежнее «ограничений нет». Для каждого нового
observation одновременно реализовать runtime check, historical check, dependency
traversal, capture, cache-hit replay и адресный discard.

В `validation_graph.overlay` identity сейчас строится из decisions/probes,
TASK_DOMAIN/STRUCTURAL_TASK и retirement sets. Не добавлять в graph валидаторы,
читающие новые trace kinds, пока identity не отражает эти чтения. Сам по себе этот
факт ещё не доказывает текущую коллизию — воспроизвести две evidence views.
**Готовность:** cold/cache/resume совпадают; поздний witness/empty-query change
инвалидирует только dependents; mutation в одной ветви не отзывает sibling.

### P05. Общий контракт открытого источника и полноты его перечисления

**Тип:** G/V. **Блоки:** 1, 2, 5, 6. **Зависимости:** P01, проект P20.
**Места:** `composition_domains.DomainNetwork`, `CompositionSources`,
`grammar_domains`, `nominal_reference_domain.inspect`, `nominal_reference_source.eligible_frames`,
`spatial_memory`, `content_sources`, `temporal_sources`.

DomainNetwork уже умеет open_domains, extend и unknown compatibility, но его
наличие не доказывает подключения всех producers. `eligible_frames` отбрасывает
неразрешённые predicate decisions и partial frames; reference union сообщает
неполноту групп/памяти, но не обязательно все пропущенные структурные источники.
Это V: не разрешать partial identity, а отделить incomplete source от его output.

У каждого производителя объявить domain address, supported область, snapshot,
cursor/continuation, produced candidates, completion receipt, open obligations и
причины непригодности конкретного output. Отсутствие применимости доказывать отдельно.
Составить adapter registry для grammar, component, entity/mention/group/variable,
spatial, temporal, content, description и quantifier sources.
**Готовность:** для каждого источника есть empty-complete и empty-incomplete контраст;
source change пересоздаёт зависимый домен, возвращая варианты, отсеянные старыми grounds.

Дополнительные подтверждённые границы: `CompositionSources.complete` проверяет
только `len(alternatives)==1`; переименовать cardinality API после проверки всех
callers, не использовать его как closure receipt. `composition_source_union.merge`
вычисляет `produced('GRAMMAR', None, local)` из общего diagnostics delta обоих
источников. Заменить это отдельными адресованными receipts каждого producer;
unknown одного источника не должен теряться или приписываться другому.

### P06. Разбиения: сохранять альтернативы границ и NEXT как домены

**Тип:** G. **Блоки:** 2, 5. **Зависимости:** P05.
**Места:** `partition_domain`, `partition_sequences.select_parts`,
`relation_partitions`, `direct_partitions`, `structural_tasks.span/source_set`.

Сейчас `select_parts` хранит один список groups/proofs; неопределённый continuation
возвращает None. Repair выбирает одну прежнюю часть и удаляет suffix. Это сохраняет
pending, но не исполняет несколько допустимых границ/NEXT/repairs.

Представлять alternative prefixes с parent proof, ownership и курсором; NEXT
выбирает следующую непосредственную часть, не число частей и не глубину. Каждая
альтернатива имеет отдельный suffix и completion evidence. DONE закрывает сбор
только при выполнении coverage и исчерпании собственного домена задачи.
**Готовность:** две допустимые границы реально исполняются; поздний отказ одной не
уничтожает другую; 0 страницы не закрывает весь домен; длинный плоский список не
превращается в рекурсивную цепочку и не ограничивается тремя элементами.

### P07. Общий материал для произвольного доказанного подмножества частей

**Тип:** G/A. **Блок:** 2. **Зависимости:** P06.
**Места:** `shared_proposition_material.propose/validate`, `source_collections`,
partition ownership consumers и `composition_tree`.

Текущий вопрос требует материал INSIDE EVERY alternative; validator проверяет
`counts[r] == len(groups)`. Для трёх частей материал, общий только первой и второй,
не представляется этим контрактом. Нельзя исправить простым снятием проверки counts.

В witness хранить occurrence → точное множество child addresses с доказательством
принадлежности; отдельно хранить материал внешнего оператора. Разрешать разные
непересекающиеся/пересекающиеся sharing sets при совместимых proofs. Children
получают адреса вхождений, не копии слов и не новые референты.
**Вопрос A:** если архитектура не определяет совместную семантику конкретного
sharing set с GROUP/модальностью, согласовать её до реализации этого случая.
**Готовность:** all/subset/no sharing контрасты; внешний NOT не копируется внутрь;
отзыв membership одного child снимает только зависимые imports.

### P08. Доказанное исключение и пересмотр с восстановлением домена

**Тип:** G/V. **Блоки:** 2, 5, 6. **Зависимости:** P05–P07.
**Места:** `partition_exclusions`, `partition_role_revision`, `partition_sequences`,
`component_refinement.compose_area`, `DomainNetwork`, `dispatcher.discard_reads`.

Сохранить уже существующий exact-combination exclusion. Не превращать диагноз
производителя или отсутствие output в отрицательное языковое свидетельство.
Для каждой операции narrowing сохранять входной домен, constraint/witness и адрес;
при отзыве основания пересчитывать область, а не продолжать из урезанного остатка.
Различать model none-fit, unknown, budget, invalid artifact и known semantic conflict.

Repair должен возвращать к породившему противоречие выбору и отзывать dependent
closures/caches/publication candidates. Обходные ветви и несколько родителей должны
входить в dependency graph. Определить no-progress по неизменившемуся состоянию,
а не использовать повторный вопрос как бесконечный retry.
**Готовность:** исключённый вариант возвращается после отзыва; unrelated sibling
сохраняется; fallback после resource error не создаёт доказанного исключения.

### P09. Полный реестр scalar и conditional producers с фазами подготовки

**Тип:** G. **Блоки:** 2–4, 6. **Зависимости:** P05, проект P20.
**Места:** `relation_composition.compose`, `structural_relations.CONTRACTS`,
`structural_shells`, `structural_lexical`, `relation_quantifiers`,
`content_reference_functions`, `component_refinement`.

CONTRACTS содержит 12 простых отношений; scalar dispatch отдельно поддерживает
CONTENT, CONTENT_REFERENCE, NOMINAL_DESCRIPTION, FORALL/EXISTS и modal пути.
Отсутствие conditional capability сейчас корректно остаётся pending, но заявленная
механика не исполняется. Составить точное соответствие каждому пункту RELATIONS.

Для каждого producer объявить фазы: внешнее отношение → source partition →
owner/binder/controller requirements → необходимые дочерние outputs → оставшиеся
input slots → assembly/validation. Переиспользовать scalar алгоритмы; не создавать
второе дерево правил для комбинаций и глубин. Нельзя передать условный proof через
безусловный licensed; условность сохраняется в каждом record и consumer.
**P09-contract (ранний результат):** конечный registry, phase interfaces, типы
inputs/outputs и адресованные continuation hooks для каждого пункта меню. Это
не готовность самой capability.
**P09-integration (после P10–P15):** каждый не-DEFER пункт меню имеет scalar и
conditional execution либо согласованную неприменимость; singleton внутри
conditional parent не становится глобальным фактом. Приёмка семантики и closure
дополнительно требует P16/P20. Не ожидать полной готовности P09 до начала P10.

### P10. Исполнять LEXICAL_CHILD_DEMAND через общий планировщик

**Тип:** G. **Блоки:** 2, 5, 6. **Зависимости:** P09, P04.
**Места:** `lexical_demands.intercept`, `structural_lexical.produce`,
`structural_frontier`, `composition_tasks.ChildTasks`, `lexical_component`.

intercept сохраняет точную invocation и бросает ChildDemand со статусом
PENDING_SCHEDULER. structural_lexical кладёт invocation в task.demands; это ещё
не enqueue/run/return/reassemble и не доказывает полноту lexical source.

Связать demand с child job по exact parent/condition/input/version; сохранить
call continuation/фазу родителя. После child result возобновить только зависимую
часть производителя, не повторять неизменённые пробы и не сбрасывать бюджет.
Не требовать во всех случаях полного child результата: определить минимальные
данные следующей фазы и оставить явные последующие obligations.
**Готовность:** infinitive/control, description и вложенное содержание проходят
pause → run → return → revalidate → assembly; отменённый parent не принимает
поздний результат, одинаковые тексты разных children не смешиваются.

### P11. Сужение между уровнями и продолжение окон без полной предварительной развёртки

**Тип:** G/V. **Блоки:** 2, 5. **Зависимости:** P06, P09–P10.
**Места:** `structural_frontier`, `structural_windows`, `composition_expansion`,
`composition_domains`, `task_contracts.child_result`, typed InputSlot.

Текущие окна уже дают уровни 1–3 и адресованные +3. Windows.inspect проверяет
ancestor evidence/exclusions, но не заменяет распространение совместимости
между всеми parent/child domains. Расширять следует живые остатки по адресу.

У каждого ребра объявить требуемые типы/роли/reading/ownership и tri-valued
compatibility. Передать ограничения вниз, результаты вверх; различать unknown и
false. Циклы фаз обрабатывать как unresolved dependency, а не recursive crash.
Сохранить BFS/fairness, локальный resource stop, общий бюджет и reader isolation.
Сохранить bounded-stack контракт: глубокая чередующаяся цепь condition→shell→proof/
domain не наращивает Python call stack; diamond sharing не принимается за цикл.
После увеличения бюджета resume не переисполняет неизменившийся prefix. Production
и pure validation измерять отдельно; длинный flat — отдельный профиль.
**Готовность:** глубина >3 продолжается после сужения; 20 плоских частей не требуют
20 уровней; противоречие на 4-м уровне пересматривает причину на предыдущем;
порядок обхода независимых ветвей не меняет множество допустимых результатов.

### P12. Домены владельцев и совместные host/role/reading решения

**Тип:** G/V. **Блок:** 3. **Зависимости:** P02, P05, P09–P11.
**Места:** `component_refinement._compose_lexical_area`, `nominal_host_question`,
`nominal_host_views`, `refinement_group_hosts`, `refinement_host_path.node_path`,
`relative_pronoun.compose`, `relative_composition`, `nominal_usage.validate`,
`implicit_descriptions`, `implicit_plan.emit_implicit_roles`.

Обнаружены scalar choices и проверки единственного child host (`len(hosts)!=1`,
`len(candidates)!=1`, path ambiguity). Они могут безопасно остановить выбор,
но не реализуют домен нескольких совместимых владельцев. Существующую поддержку
group owner/connector не переписывать и не объявлять отсутствующей.

Представлять owner candidate вместе с типом ENTITY/GROUP/BOUND_VARIABLE,
исходной ролью, reading, границами и path. Поддержать домен совместных назначений;
отсечь только доказанно несовместимые combinations. Child и parent должны читать
один owner witness. Не выбирать владельца по соседству/падежу/первому frame.
**Готовность:** два владельца, несколько описаний, nested/verbless/OOV connector,
shared predicate и group owner; изменение host отзывает связанные role/reading/path.

### P13. Scoped owner/relative proofs и проверки всех downstream uses

**Тип:** G/D при conditional подключении. **Блоки:** 3, 6. **Зависимости:** P12, P04.
**Места:** `refinement_host_proof.live/frame_live`, `relative_pronoun.binding_live`,
`component_constraints.frame_hosts_live`, `partial_composition`, `native_plan`.

owner/relative validators вызывают безусловный licensed. Это правильно для public
границы, но недостаточно для historical conditional validation. Кроме того,
owner.live регистрирует observation только при success — проверить отрицательные
и отсутствие-record queries, которые используют кешируемые callers.

Разделить pure addressed validator и runtime/public adapters. Проверить каждое
использование хозяина, connector и relative marker, exact payload/reading/group
members и owner path; добавить complete dependency observation по P04.
**Готовность:** historical валидирует в своей ветви без ambient session; public
не принимает conditional proof; missing/stale/conflict различимы; late revoke
блокирует parent/description/native output, сохраняя независимое описание.

### P14. Совместные binder readings и машинная parent proof

**Тип:** D/G. **Блок:** 4. **Зависимости:** P02, P05, P09–P11.
**Места:** `quantifier_composition._bind/licensed`, `relation_quantifiers.compose`,
`composition_domains.DomainNetwork`, `bound_references`, `partial_readings`.

Binder workflow ограничивает граф по одному chosen варианту; deterministic
head-license путь создаёт Decision/Ground D с текстовой ссылкой. Уже есть обработка
неизвестных признаков и OOV — сохранить её, не заменить падежным prior.

Сохранить совместные альтернативы binder/head/restriction/body reading в общем
domain machinery. Parent proof и transformation должны быть P01/P02 witnesses.
Проверять целые readings; unknown case не доказывает conflict. Переход к body
исполнять staged, не требовать выбрать всё дочернее дерево заранее.
**Готовность:** несколько binders/readings, singleton с действующим head proof,
отзыв parent, неизвестный падеж/OOV и отрицание restriction; arithmetic остаётся DEFER.

### P15. Полные контракты control, bound references, модальности и времени

**Тип:** G/V. **Блоки:** 2–4, 6. **Зависимости:** P09–P14.
**Места:** `control_arguments`, `component_infinitives`, `action_descriptions`,
`bound_references.candidates/resolved`, `coreference`, `scope_assignment`,
`structural_content_time`, `temporal_functions`, `component_temporal_scope`,
`implicit_introduction`, `implicit_descriptions`, `implicit_plan.emit_implicit_roles`.

Bound-variable support уже существует, включая quote boundary; не реализовывать
его заново. Проверить passage через nested binders, nominal descriptions,
modal/content body и группы. Control alias хранит данные родителя; требуется
тот же addressed witness и проверка всех consumers, а не одна parent equality.

Разделить participant identity, grammatical role, controller, governor reading,
modality и factivity. Переносить scope/время при сборке child, включая unknown bounds.
Нельзя превратить возможность/намерение/сообщение о содержании в состоявшийся факт.
**Готовность:** неоднозначный controller остаётся доменом; group controller
не распадается; shadowing/quoted content не захватывают чужую переменную;
смена времени/модальности отзывает зависимые outputs и не меняет независимых.

### P16. Закрыть конкретные semantic obligations lexical bundles

**Тип:** G. **Блоки:** 2–6. **Зависимости:** P03, P10, P12–P15.
**Места:** `lexical_issuance.assess`, `bundle_constraints.inspect`,
`composition_contracts`, `function_inventory`, `composition_source_union`.

assess безусловно добавляет NOMINAL_RELATION, OWNER_RELATIVE, CONTROL и TEMPORAL
CONTRACT_PENDING. Это честная незавершённость, но удалить эти строки без реализации
соответствующих validators нельзя. Общий checker уже различает stale/unknown/conflict.

Создать реестр обязательств по capabilities фактического bundle: applicability
доказывается структурой и inputs. Каждое применимое обязательство получает validator
и dependency list; неприменимое — основание неприменимости. Source obligations
не исчезают от успеха локальной семантики. INVALID_PRODUCER_OUTPUT остаётся отдельным
от языкового conflict; исходная гипотеза может произвести новый исправленный output.
**Готовность:** каждая из четырёх семей проходит positive/negative/unknown/stale
на scalar/conditional пути; неизвестное обязательство не разрешает выбрать соседа
как единственный полный ответ; unused field не становится лишней блокировкой.

### P17. Совместные альтернативные ссылочные рёбра

**Тип:** G; отдельный D ниже. **Блок:** 1. **Зависимости:** P05, P08, P04.
**Места:** `nominal_reference_pages.select`, `nominal_reference_memory.resolve`,
`nominal_reference_chain.finish/check`, `nominal_reference_binding`, `DomainNetwork`.

Pages сохраняет несколько admissible answers, но resolve собирает binding только
для выбранного candidate; chain.finish работает с одним уже выбранным dependency
на mention. Его topological DAG и cycle checks полезны, но не решают совместный
поиск альтернативных рёбер и взаимное сужение identities.

Сохранить typed edge domains, отдельные selected mention и grounded identity,
dependency graph по комбинациям. Не считать shared DAG циклом. Эквивалентные
пути к одной identity сводить только с сохранением независимых support sets;
min candidate ID не должен терять второе основание. Локальная UNKNOWN identity
не означает, что source mention недопустим.
Дополнительный D воспроизведён в этом аудите на изолированном API:
`nominal_reference_pages.live` остаётся True после добавления
`DEPENDENCY_REJECTED(decision_ref=page)` при неизменённых Decision и probe record.
`proof` проверяет superseded_by, но не retirement trace. Исправить page proof
lifecycle через общий validator и протянуть зависимость к aggregate/binding/cache;
проверить оба retirement events и независимые страницы. Это воспроизведение API,
не доказательство, что конкретный native run записал ошибочную identity.

**Готовность:** цепь, diamond, альтернативные родители, цикл с/без независимого
выхода; после отзыва одного пути identity остаётся при другом и исчезает без всех.

### P18. Все заявленные типы ссылок и участников групп

**Тип:** G/V/A. **Блоки:** 1, 4, 5. **Зависимости:** P12, P14–P17.
**Места:** `nominal_reference_domain.inspect`, `nominal_reference_source.rows`,
`nominal_group_source.domain`, `nominal_group_dependency`, `bound_references`,
`spatial_references.prepare/resolve`, `spatial_plan.emit_roles/emit_anchor`,
`nominal_reference_plan/binding`, `narrative_groups`, `narrative_group_plan`.

Reference union состоит из entities/groups/places/memory/mention; chain.rows
исключает bound_arguments, а coreference имеет отдельный bound-variable канал.
Group source разрешает terminal members и REFERENCE_MENTION; другие случаи дают
GROUP_MEMBERS_NOT_TERMINAL. Это gap интеграции типов, не отсутствие всех групп.

Сверить заявленные target types с registry P00. Для каждого добавить source,
представление, runtime/historical validator и native/durable lowering либо
доказать, что данный consumer этому типу не применим. Не превращать переменную
в M-entity и групповой тип в случайную плоскую identity.
Дополнительная V-точка: `narrative_groups.resolved_group` берёт один путь через
`min(grounding_paths)`. Проверить late-revoke при наличии второго независимого
пути; если восстановление/поддержка теряется, перевести на support-set контракт P17/P22.
Существующие open narrative groups нужно сохранить отдельным типом с открытым
составом/свидетельствами, не приводить автоматически к закрытому K. Их prepare/
resolve/plan и durable consumers входят в этот аудит/adaptation.
**Вопрос A:** группы с повторяющейся identity, group-valued member и variable-valued
member требуют согласованной семантики множества/вхождений; проверить архитектуру,
при отсутствии решения спросить пользователя, не сплющивать автоматически.
**Готовность:** полный type dispatch без silent skip, unknown member сохраняется
обязательством; source readiness filter отражён в completion receipt P05.

### P19. Сквозной аудит кеша, source snapshot и исторических evidence views

**Тип:** V/G. **Блоки:** 5–6. **Зависимости:** P04–P18.
**Места:** dispatcher/producer_reads/validation_graph, `CompositionSources`,
`structural_conditions`, `structural_lexical`, `lexical_issuance`,
`attention_context/context_receipts`, `rx_cache`, `t6_core/t6b_revision`.

Использовать таблицу служб из F05_MECHANISM_COVERAGE, но для каждой read/write
точки указать owner/version/address и invalidation event. Отдельно проверить
mutable source caches, source closure receipts, cached failed attempts, snapshot
после repair и mixed evidence views. 390 AST calls — навигация, не доказательство
полноты; пройти attribute calls/callbacks и явно зарегистрировать неприменимость.

Контекстный reader/WAL механизм уже реализован: перепроверить подключение
всех новых producers, не запускать при validation replay/refresh/attention mutations.
Сохранить bounded-stack поведение historical validation при новых validators:
не вводить recursive validation entry через reading/owner/control adapters.
R-X опыт отдельно от runtime memo: stage-specific priors не основания истины,
запись требует живой committed опоры, supersede не удаляет audit history.
**Готовность:** таблица всех классов кеша с cold/hit/resume/historical/revoke;
не осталось чтения, влияющего на output, без dependency либо обоснования чистоты.

### P20. Доказательства полноты producers и сходимости открытого леса

**P20-contract ACCEPT, 2026-11-01:**
[F05_COMPLETION_CONTRACT.md](F05_COMPLETION_CONTRACT.md).
Принята спецификация; реализация P20-validation остаётся OPEN.

**P20-contract** проектируется до P05/P09; **P20-validation** реализуется после
их producers. Разделение спецификации и исполнения устраняет цикл зависимостей.

**Тип:** G. **Блоки:** 2, 5, 6. **Зависимости:** P05–P19.
**Места:** `structural_lexical.produce`, `structural_frontier.snapshot`,
`structural_forest`, `task_contracts.child_result`, `partial_composition`, `lexical_issuance`.

У lexical source producer_complete=False и SOURCE_CLOSURE_UNESTABLISHED;
frontier snapshot сохраняет structure_complete=False/write_eligible=False.
Обычный возврат compute не позволяет заменить эти поля на True.

Специфицировать и вычислять отдельно menu/enumeration/producer/frontier/
propagation/structure completion, interpretation status и write eligibility.
Closure certificate связывает версии всех источников, child demands, constraints,
решений, negative grounds, resource residue и semantic validators. Есть открытая
применимая обязанность — сертификат не выдаётся. Empty complete не равен UNKNOWN.
**Готовность:** реальный исчерпанный supported домен закрывается; открытый источник,
невыполненный child, resource limit, unknown edge и stale proof каждый отдельно
блокируют closure. Изменение любого основания отзывает certificate и dependents.

### P21. Опускание выбранной интерпретации, seal и общий publication gate

**Тип:** G/V. **Блок:** 6. **Зависимости:** P20.
**Места:** `relation_composition.compose` (SupportedDomain path),
`composition_tree`, `seal`, `native_frontend`, `native_plan.build_plan`, `mutation_plan`, `commit_stage`.

Открытый лес сейчас блокируется; native_plan также отвергает partial/choice_ref.
Это не доказательство существования пути закрытого условного леса до native записи.
`seal.validate_closure` проверяет scope/dangling/ID collisions; он не заменяет
семантическую проверку `composition_tree.finalize` и guards `native_plan.build_plan`.
Не снимать эти guards, пока нет проверенной closure и lowering.

Перенести выбранную интерпретацию из private branches в основной immutable IR с
переназначением IDs, scope, ownership и provenance. Альтернативы разбора не OR
событий. Снятие conditional требует отдельной проверяемой цепочки: выбор всей
согласованной интерпретации при закрытых applicable sources/constraints → discharge
её conditional premises → выбранный основной IR. Ни singleton внутри ветви,
ни одна пока произведённая ветвь не снимают condition. Условный внутренний frame не самостоятельный root assertion. Seal фиксирует
структуру; поздний пересмотр создаёт новую версию, не меняет sealed дерево.
Для разрешённой PARTIAL записи требуется отдельная явно определённая политика;
сохранить нынешний запрет там, где её нет.
**Готовность:** единственная произведённая ветвь при открытом конкурирующем
источнике не пишет; закрытая согласованная интерпретация допускается; отзыв её
selection/ancestor отзывает зависимый native support. Native output содержит
ровно ожидаемые roots, связи, scope и truth
supports; false closure, cross-branch proof и mutation after seal блокируются.

### P22. Durable зависимости, отзыв и независимые пути после записи

**Тип:** V/G. **Блоки:** 1, 6. **Зависимости:** P17–P21.
**Места:** `nominal_reference_plan/binding/chain`, `nominal_group_source`,
`refinement_host_path`, `nominal_usage.validate`, `implicit_plan`, `spatial_plan`,
`narrative_group_plan`, `canonical_ledger`, `ah_adapter`, `retraction`, `t6b_revision`.

Проверить все новые witness types и closure certificates на writer boundary:
перед записью live, в записи ссылки на реальные grounds, при отзыве транзитивная
инвалидация. Runtime callback не заменяет durable dependency. Run-local Issuer и bound
context verifier нельзя сериализовать как полномочие на запись: определить
устойчивые source/probe/resource witnesses, WAL references и verifier inputs,
которые можно проверить после process restart без приватного Python объекта. При двух grounds
одной identity/утверждения отзыв одного не должен удалить другое.

Сопоставить native operations с journal/store consumers и replay. Проверить
частично выполненную запись, повторный replay, process restart и смену interpretation revision.
Старый отозванный support не восстанавливается из кеша при провале новой версии.
**Готовность:** write → revoke → replay даёт ожидаемый store/assertion set;
independent sibling и второй support сохранены, все и только dependents сняты.

### P23. Итоговая матрица приёмки F05 и проверка достаточности

**Тип:** V, обязательная приёмка. **Блоки:** 1–6. **Зависимости:** P00–P22.

Не запускать бессистемно весь исторический suite. Для каждой строки capability
registry выполнить конечный набор контрастов из раздела 5; хранить exact inputs,
окончательные probes/ответы, trace, source receipts, native assertion set и причины
всех отсечений. Отдельно статический анализ, scripted selector, живая слабая модель,
сквозное native execution. Ответы модели не подменять знаниями аудитора.

Проверить неизменность candidate domain при перестановке независимых producers,
порядка frames, cache on/off; source change должен восстанавливать domain по новым
grounds. Добавить разговорные примеры с OOV/частичной пунктуацией, но ожидаемый
контракт определять через семейство, не специальное предложение.
**Готовность:** закрываются только строки registry, где все producers/consumers
реализованы, все обязательные контрасты выполнены, нет необъяснённых baseline
failures, dynamic gaps и открытых A-вопросов. Все шесть блоков закрываются отдельно,
после чего проверяется общая цепочка до допустимой записи и отзыва.

## 5. Обязательная матрица проверок

Для каждой применимой capability и каждого producer, а не один тест на общий helper:

| Ось | Обязательные контрасты |
|---|---|
| Домен | пустой полный / пустой незавершённый / singleton / multiple; новая страница |
| Основания | live / отсутствующее / retired / изменённый payload / чужой source/version |
| Смысл | unknown feature / known mismatch / whole alternatives без смешивания |
| Адрес | тот же текст, другое вхождение; sibling; ancestor; global/conditional |
| Композиция | simple / nested >3 / длинный flat / несколько parent uses / OOV |
| Источники | grammar/component disagreement; один incomplete; новые кандидаты после repair |
| Выполнение | cold / hit / interrupted resume / historical вне session |
| Пересмотр | поздний positive/negative revoke; восстановление candidates; независимый путь |
| Результат | output artifact admissibility / interpretation readiness / write eligibility |
| Запись | весь assertion set, отсутствие лишних roots, повторный replay, durable revoke |

Проверка одной страницы или helper не закрывает строку. Для дифференциального теста
нужны сопоставимые входы и явная версия resource/model. Включить deep alternating condition→shell→proof/domain,
проверку bounded Python stack, diamond/cycle и budget-increase resume без
повторного исполнения prefix. Производительность измерять
после корректности: длинная цепочка и плоский список отдельно; оптимизация не может
менять домен, основания или completion. Template reuse остаётся DEFER.

## 6. Архитектурные вопросы, которые нельзя решать молча

A1 (P18): group-valued/variable-valued members и повтор одной identity — множество,
мультимножество или группа употреблений? Сначала найти действующее определение;
если оно отсутствует, запросить решение до конкретного lowering.

A2 (P21): требуется ли durable публикация альтернативной PARTIAL интерпретации,
или лишь хранение диагностического результата? Текущая безопасная граница — не
записывать её как утверждённые факты. Это не мешает работе до closure.

A3 (P20/P23): перечень declared source classes/producer capabilities должен быть
конечным и версионированным для доказательства полноты в его области. Не подменять
его «все возможные языковые интерпретации». Неясные классы оформить явно в P00.

Эти вопросы не разрешают остановить независимые карточки и не дают права выдумать
ответ, удобный для прохождения одного примера.

## 7. Как вести дальнейшие изменения по этому файлу

У каждой карточки сохранять статус PLANNED / IMPLEMENTING / IMPLEMENTED_UNVERIFIED /
VERIFIED_IN_DECLARED_SCOPE, commit, покрытые producers/consumers и остаток.
Начальный статус всех карточек — PLANNED. Архитектурная механика остаётся OPEN,
пока вся её строка маршрута не закрыта. Новый выявленный callsite дополняет карточку,
а не становится незаметным частным исключением.

Перед правкой указать необходимую информацию и уровень её появления. После правки
дать: first bad transition, новый контракт, consumers, invalidation, конкретные
свидетельства и ограничения. Повторные локальные улучшения не называть закрытием
«кеша», «оснований», «генератора» или F05 в целом.


## 8. Источники аудита, контроль состояния и вердикт судьи

Аудируемый runtime commit указан в начале. План опирается на текущий код, а не
на факт наличия старых отчётов. Приложение F05_AUDIT_SCOPE.json содержит адреса
65 адресов статических наблюдений, включая late consumers,
контрольные SHA-256 файлов и разрешённые пути реализации. Plan touchpoint означает
место обязательной работы, не объявление построчного исчерпывающего анализа.

В этом проходе выполнена одна изолированная проверка reference page retirement:
сначала proof/live=True; после DEPENDENCY_REJECTED при неизменённом selected/probe
live=True. Она подтверждает D внутри P17. Новые сквозные модельные прогоны и
изменения runtime не выполнялись. 19 baseline failures из предыдущей контрольной
точки остаются входом P00 и не представлены как заново выполненная приёмка.

Один субагент-судья проверил все шесть блоков и черновик плана. По его замечаниям
разделены P09-contract/integration и P20-contract/validation, добавлены implicit,
open narrative group, spatial и nominal_usage consumers, bounded-stack проверки,
условия discharge условности и durable проверка после restart. Сам судья код
не менял и не запускал полный suite. Итоговый вердикт после повторной сверки: **план принят для публикации,
блокеров не осталось**. Проверены 65 evidence locations, 111 plan touchpoints,
существование путей/символов и SHA-256. Это приёмка плана, а не закрытие F05.
