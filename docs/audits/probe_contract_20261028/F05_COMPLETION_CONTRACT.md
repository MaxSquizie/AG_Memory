# F05 P20-contract — основания завершённости v1

Дата: 2026-11-01. База кода: `0a18c6b`. Статус: спецификация для реализации
P05–P20, не реализованный certificate и не закрытие P20-validation.
Capability IDs: C-SOURCES, C-PAGES, C-PARTITION, C-CHILD, C-WINDOW,
C-RETRACT, C-CACHE, C-HISTORY, C-CLOSURE, C-PUBLICATION, C-DURABLE;
применение ко всем R-* и T-* из F05_CAPABILITIES.json.
Нормативная база: FORMALIZER_ARCHITECTURE_V7 §§1.1, 4.0, 4.5, 5.1–5.4,
6.1–6.3, 7.2–7.4. Порядок карточек — F05_IMPLEMENTATION_PLAN.md.

## 1. Утверждения и область доказательства

Объект завершения — адресованная задача на фиксированном снимке и объявленном
домене производителей. Это не полнота естественного языка. Producer обязан
указать покрываемую область; отсутствие реализации применимого producer
не превращает область в исчерпанную. Меню языка интерфейса не является
перечнем всех структурных комбинаций, reading alternatives или источников памяти.

| Утверждение | Что требуется доказать | Чего оно не доказывает |
|---|---|---|
| execution_returned | Invocation вернула результат либо трассированный исход | Исчерпание генератора, корректность результата |
| menu_complete | Все элементы версии конкретного конечного меню предъявимы, включая страницы | Все границы, combinations и вложенные hypotheses |
| enumeration_complete | Генератор исчерпан в объявленной области; нет незавершённого cursor/continuation | Живость payload, семантическая пригодность или закрытие других producers |
| producer_complete | Применимость установлена; перечисление закрыто; каждый выданный кандидат и обязательство имеют итоговую оценку | Полнота объединения sources и выбор единственной интерпретации |
| frontier_complete | Для данной задачи нет неисполненных/непроверенных continuation и child demand | Удовлетворённость constraints и единственность решения |
| propagation_complete | Все объявленные рёбра обработаны на тех же версиях доменов, очередь пуста, нет unknown/dirty edge | Правильность самих правил; полнота языка |
| structure_complete | Все структурные входы, ownership, scope и ссылки выбранной структуры замкнуты | Словарный смысл, семантическое разрешение, допустимость записи |
| semantic_complete | Все применимые semantic validators дали определённый результат по точным входам | Единственный выбранный результат и разрешение публикации |
| interpretation_status | EMPTY / UNIQUE / MULTIPLE / PARTIAL / UNKNOWN / CONFLICT | Разрешение записи по одному имени статуса |
| write_eligible | Отдельный gate проверил выбранный IR, discharge, seal, решения и правила публикации | Факт совершённой транзакции или вечную живость support |

Флаги выше — вычисленные проекции receipts, не входные права вызывающего.
Они привязаны к адресу и не переносятся на родителя автоматически.
Например, у альтернативных деревьев может быть structure_complete, а общий
результат остаётся MULTIPLE. Search closure допускает EMPTY и MULTIPLE;
сертификат выбранной интерпретации требует отдельного selection witness.
PARTIAL может сохранять определённую структуру и неизвестную лексическую часть.

UNKNOWN означает недостаточность доказательств; STALE — доказанную потерю
актуальности старого основания; CONFLICT — доказанное несовпадение адресованных
требований. INVALID_ARTIFACT означает ошибку формата/producer, а не ложность
языковой гипотезы. Эти причины сохраняются раздельно с адресом первого нарушения.

## 2. Единый адрес

Каждый receipt несёт `schema_version`, `kind`, `receipt_ref`, `address`, `claim`,
`basis_refs`, `payload_digest`, `validator_id/version`, `status`, `obligations`.
`receipt_ref` — digest канонической записи без самого receipt_ref. Digest
выявляет изменение, но сам по себе не доказывает истинность утверждения.

`address` содержит `stage` и `claim_profile_id/version` (обязательные поля,
определённые registry, см. §10), а также:

- source_uid, source_revision, interpretation_version и digest исходного текста;
- region_ref, упорядоченные occurrence refs и исходные диапазоны;
- parent task/input scope и digest типизированного входа;
- condition_ref и всю проверяемую ancestry; null только для безусловного адреса;
- resource snapshot/hash и capability-registry version;
- generation/domain refs с revisions; producer_id и его contract version.

Отсутствующее поле не подменяется текущим runtime. Historical validator получает
адрес явно и проверяет соответствующий снимок. Runtime adapter может сформировать
его из текущей задачи. Public unconditional validator отвергает условное основание.
Применение доказанного родительского ограничения в дочерней области требует
типизированного переноса, а не совпадения написания или только token_ref.

## 3. Receipts производителей и зависимостей

### ApplicabilityReceipt

Содержит producer ID, объявленную область входов, APPLICABLE/NOT_APPLICABLE/
UNKNOWN и основания. NOT_APPLICABLE требует проверяемого правила и точного
входа, а не отсутствия кандидатов. UNKNOWN блокирует source union closure.
Для отсутствующего, но применимого producer создаётся MISSING_PRODUCER obligation.
Временное выключение producer политикой не уменьшает семантическую область молча:
сужение области должно быть явно объявлено в ресурсе и результате.

### EnumerationReceipt

Содержит generator contract/version, domain revision, candidate IDs с payload
hashes, страницы/continuations, порядок и их coverage, terminal exhaustion witness,
negative-ground refs, status OPEN/EXHAUSTED/RESOURCE_BLOCKED/STALE.
EXHAUSTED подтверждается реализацией генератора по его declared domain; флаг
`done` вызывающего и отсутствие новых элементов в одной итерации недостаточны.

Для конечного меню — точное множество меню; для декартова/рекурсивного домена —
проверяемое покрытие факторизации и адресованных продолжений без развёртки всех
деревьев. Every candidate accounted for означает: represented, доказанно исключён
или доказанно эквивалентен с сохранением оснований. Отсечённый бюджетом элемент
остаётся obligation. Ответ 0 на странице имеет только page scope; ? не исключает;
несколько альтернатив не равны совместному набору объектов. NONE_FIT для полного
домена требует полного enumeration плюс живого основания отказа для всех вариантов.

### ProducerReceipt

Ссылается на applicability, enumeration, выходные bundles/frames и assessments,
child demands и dependency reads. COMPLETE требует всех обязательств данного
producer, срок проверки которых наступил в указанном stage/profile; поздние
обязательства сохраняются в выходе с due_stage, а не исчезают; COMPLETE_EMPTY допустим при полном пустом домене. INVALID_OUTPUT
не может стать COMPLETE_EMPTY. Выход без provenance не принимается даже при
корректном shape. Один валидный выход не закрывает producer.

### SourceUnionReceipt

Содержит полный список applicable/неприменимых/unknown producers из registry
для этого input sort, их receipts и объединение результатов. Нельзя закрыть
union по receipts только уже вызванных producers. Кандидаты разных producers
сливаются только через доказательство эквивалентности; независимые основания
остаются независимыми путями поддержки. Новая версия registry отзывает оценку.

### ChildDemandReceipt и FrontierReceipt

Demand фиксирует invocation, parent/child адреса, typed input/output sorts,
все необходимые child results, перенесённые grounds и точный continuation.
Статусы: REQUESTED, RUNNING, WAITING, COMPLETED, REJECTED_WITH_PROOF, STALE.
COMPLETED означает удовлетворение объявленного child contract, а не просто return.
REJECTED_WITH_PROOF относится к гипотезе; ошибка исполнения оставляет WAITING.

Frontier связывает root generation, полный набор demands/continuations и состояние
каждого. Окно глубины 3 и расширения +3 — график исполнения, не граница домена.
Соседние операнды не расходуют глубину вложенности. Закрытие возможно без полного
разворачивания доказанно исключённой ветви; exclusion должен покрывать эту ветвь
и все зависимые продолжения. Неисполненная жизнеспособная ветвь остаётся открытой.
Цикл задач без доказанного конечного результата не считается завершением.

### ConstraintReceipt и SemanticAssessmentReceipt

Каждое правило указывает input revisions, exact occurrences, rule version,
результат SATISFIED/CONFLICT/UNKNOWN/NOT_APPLICABLE/STALE и основания.
CONFLICT позволяет исключить только адресованное сочетание, не весь тип чтения.
Все применимые валидаторы берутся из реестра обязательств, а не из списка
успешно вызванных функций. Это включает ownership/relative, control, binder,
reference, temporal/modal, nominal relations и lexical inputs.

PropagationReceipt содержит версии доменов, полный набор applicable constraints,
оценки всех рёбер и отсутствие dirty/queued/unknown edges. Пустая очередь при
неподключённом правиле не является fixed point. Порядок обработки не меняет
поддерживаемый домен; это проверяется контрастными порядками исполнения.

### ReadReceipt и ResourceReceipt

Фиксируются положительные, пустые и отрицательные чтения: адрес запроса, снимок,
область видимости, возвращённая проекция/digest и отсутствие данных. Reader
недоступен — UNKNOWN, а не пустая память. Callback/issuer handle не заменяет
сериализуемое доказательство для restart.

ResourceReceipt содержит начальный budget, ledger расходов, continuation cursor,
причину остановки и незавершённые операции. Нулевой остаток после последней
завершённой операции не аннулирует уже доказанное exhaustion; остановка из-за
лимита до завершения любой обязательной операции блокирует closure. Resume
сохраняет расходы и адрес поколения; старый результат не становится новым основанием.

## 4. Составные сертификаты

`DomainClosureCertificate` связывает SourceUnionReceipt, FrontierReceipt,
PropagationReceipt, schema/registry/resource versions и все отрицательные основания.
У каждого referenced receipt должен быть воспроизводимый validator. Отсутствующий
verifier даёт UNKNOWN. Нельзя выдавать сертификат при открытой применимой обязанности текущего
stage/profile. Состав профиля задаёт registry (§10), не caller; поздние obligations
обязательно переходят в результат и блокируют последующие стадии по своему сроку.
Domain closure может подтвердить ноль, один или несколько поддержанных результатов.

`InterpretationCertificate` дополнительно связывает точный выбранный согласованный
набор решений, structure и semantic assessments, все зависимости и root IR digest.
Selection witness относится ко всей интерпретации: локальные решения не обязаны
образовывать совместное решение. MULTIPLE остаётся в журнале с альтернативами;
не преобразуется в OR событий. Нельзя автоматически выбрать единственного
произведённого кандидата при открытом competing source.

Условные certificates могут использоваться для исследования и сужения своей ветви.
Чтобы получить безусловный результат, P21 проверяет закрытие applicable sources
и constraints всей задачи, выбранную совместную интерпретацию и явный discharge
каждого условного premise. Локальный singleton и конец окна condition не снимают.

`PublicationAssessment` отдельно связывает InterpretationCertificate, lowered IR,
structural seal, semantic decisions, policy version и native plan/read-set.
Это не переносит T3/T4 до structural seal: certificate на структурной границе
содержит только требования этой стадии; семантическая готовность и gate проверяются
после T3/T4. Структура sealed версии неизменяема; пересмотр создаёт новую версию.
Существующий запрет записи PARTIAL сохраняется везде, где отдельная политика
публикации не определена. Запись diagnostic/ambiguity journal не равна утверждению AH.

## 5. Жизненный цикл и доказуемость

1. Producer сохраняет неизменяемые output/evidence и точные dependency receipts.
2. Оценщик сначала проверяет адрес, версии и живость, затем claim по исходным
   payloads/правилу. Digest без validator не считается доказательством.
3. Missing → UNKNOWN; retired/version mismatch → STALE; доказанный semantic
   mismatch → CONFLICT; malformed output → INVALID_ARTIFACT. Нельзя использовать
   последние три статуса как свободный языковой rejection без соответствующего proof.
4. Общий dispatcher подписывает потребителя на ВСЕ чтения, включая negative/empty
   и неуспешную проверку. Cache hit возвращает те же зависимости, что вычисление.
5. При изменении основания инвалидируются certificate и зависимые результаты;
   старые evidence остаются историческими. Отзыв exclusion восстанавливает домен.
6. Несколько независимых путей поддержки хранятся раздельно. Утрата одного не
   отзывает факт, если другой полный актуальный путь сохраняется; смешивать части
   разных несовместимых путей нельзя.
7. После restart P22 валидирует сериализованные основания, а не Python identity.
   Перед commit P21 повторно проверяет актуальность read-set/versions; между проверкой
   и транзакцией нельзя допустить TOCTOU-публикацию устаревшего плана.

Достаточность условная: если registry полон для заявленной механики, каждый
producer/validator выполняет контракт и все связанные receipts проверены на одном
адресе, перечисленные открытые обязанности не могут незаметно стать closure.
Это не доказательство правильности ответов модели, полноты ЕЯ или ещё не написанного
кода. Отдельно необходимы проверки каждого producer и интеграции всех consumers.

## 6. Миграция текущих интерфейсов

| Текущая граница | Допустимое использование | Обязательная работа |
|---|---|---|
| task_contracts.SelectionReceipt.record | Выбор и перечисление CALLER_GENERATOR | P05: отдельные applicability/producer/union receipts; не повышать selection до closure |
| task_contracts.produced / TaskResult.source_complete | Legacy summary доступности; True даже при None/False и INCOMPLETE | P05/P20: никогда не импортировать как источник completion proof |
| task_contracts.child_result | Проверка формы выбранного child tree | P10/P20: demand address, input revisions, source/semantic обязательства отдельно |
| partial_composition.receipt/validate | Замкнутость представленных альтернатив и reading domains | P20: producer_union_closed=True заменить проверяемыми union receipts; choices сохраняют MULTIPLE/PARTIAL |
| structural_lexical.produce | execution_complete, private outputs, явные pending | P05/P09/P10/P16: источники, demands, assessments; не переключать producer_complete по return |
| lexical_issuance.inspect/assess | Происхождение и локальная оценка bundle | P16/P19/P20: все применимые validators, durable provenance; issuer не closure authority |
| structural_frontier.snapshot | Работы, окна, pending/stale, structure/write=False | P11/P20: отдельные projections на проверенных receipts; не снимать guards по пустой очереди |
| partial_readings/structural_tasks | Page/domain proof и conditional ancestry | P01–P04/P08/P19: typed witnesses, негативные reads, отзыв и historical validation |
| composition_tree.finalize / seal.validate_closure | Reading/shape проверка и immutable structural snapshot | P20/P21: независимые stage certificates; shape не semantic readiness |
| native_plan.build_plan / commit_stage | Действующие запреты partial/choice и transactional guards | P21/P22: lowering/discharge, gate, durable dependencies; не обходить текущие запреты |

P20-contract не меняет эти функции. Каждый последующий patch обязан назвать
capability IDs, producer → receipt → consumer → cache → revoke и покрываемые
маршруты. Добавленный, но ещё не подключённый validator не закрывает механику.

## 7. Приёмочная матрица для будущей реализации

| ID | Контраст | Обязательный результат | Карточки |
|---|---|---|---|
| CC01 | Полный пустой generator / недоступный source | EMPTY / UNKNOWN, разные receipts | P05 P20 |
| CC02 | 0 на первой странице / исчерпанный домен с отказами | OPEN / completed NONE_FIT | P05 P06 |
| CC03 | Один кандидат + открытый competing source / закрытый union | Нет closure / можно оценивать UNIQUE | P05 P20 P21 |
| CC04 | Menus исчерпаны, combinations ещё нет | Enumeration OPEN | P06 P09 P20 |
| CC05 | Child вернул frame / все child obligations выполнены | Возврат не closure / typed completion | P10 P16 P20 |
| CC06 | Глубина 3 завершена, глубина 4 ещё нужна / flat siblings | OPEN continuation / глубина не растёт от соседей | P11 P20 |
| CC07 | Очередь пуста, edge UNKNOWN / все правила актуальны | Нет propagation closure / fixed point receipt | P11 P16 P20 |
| CC08 | Resource остановил задачу / ноль budget после terminal exhaustion | BLOCKED / не терять доказанное completion | P05 P11 P20 |
| CC09 | Отозвано positive, negative либо empty read | STALE certificate и все зависимые кеши | P04 P08 P19 |
| CC10 | Singleton в conditional branch / whole interpretation discharge | Не пишет / проходит только P21 gate | P20 P21 |
| CC11 | Замкнутая partial tree / выбранная semantically ready tree | Журнал без AH assertion / отдельный gate | P16 P20 P21 |
| CC12 | Валидный hash с чужим payload или без verifier | CONFLICT/UNKNOWN, никогда trusted by hash | P01 P19 P20 |
| CC13 | Restart без private issuer / сериализованные проверяемые grounds | UNKNOWN / revalidate, без прежнего object identity | P19 P22 |
| CC14 | Отзыв одного / последнего независимого support | Остаться живым / отозвать dependents | P22 |
| CC15 | Другой order, cache hit, resume | Те же supported domains и зависимости | P04 P11 P19 P23 |
| CC16 | Изменение registry/resource/source/condition после проверки | STALE, commit запрещён | P19 P21 P22 |
| CC17 | Нет output от применимого producer / доказано NOT_APPLICABLE | Открытая обязанность / producer исключён из union по proof | P05 P09 |
| CC18 | INVALID_OUTPUT / доказанное противоречие гипотезы | Ошибка реализации / только адресованное исключение | P08 P16 P20 |

Статическая проверка документа подтверждает наличие обязательств и адресов.
Scripted checks проверят обработку заданных ответов; live изолированные пробы —
конкретную модель; native проверки — запись/отзыв. Одно не заменяет другое.

## 8. Identity, issuer и независимая проверка

Стабильный task key адресует source/region/input/producer/branch и не меняется при
добавлении страницы. Revision адресует неизменяемый снимок этого task: source и
interpretation versions, context/read-set, release/registry, domain/input digests.
Receipt identity включает claim, все основания и их revisions. Cursor, расходы,
статус и множество outputs являются состоянием исполнения: новая запись receipt
сохраняет историю, не переписывает выданную. Context включает точный frozen input,
явный discourse context и read receipts памяти; совпадение текста недостаточно.

Внутри неизменного basis прогресс не теряет кандидатов/обязательств без proof:
страницы добавляются, obligations разрешаются, исключения добавляют отрицательные
grounds. Изменение основания создаёт новую оценку/revision и может вернуть
кандидата или obligation; это не «монотонное завершение» прежнего снимка.
Resume не переигрывает неизменный проверенный prefix и не сбрасывает расходы.
Независимая sibling branch не инвалидируется без зависимости на изменённое основание.

| Receipt | Issuer | Validator и разрешение выдачи | Cache dependency / поздний consumer |
|---|---|---|---|
| Applicability | Adapter зарегистрированного producer | Контракт producer + вход + rule proof, никакого inference из empty | Registry/input/rule; source union |
| Enumeration | Генератор страниц/границ/сочетаний | Полное finite coverage либо проверяемый terminal cursor по версии алгоритма; пропуски не допускаются | Domain revision/pages/exclusions; source receipt |
| Producer | Producer после завершения своих фаз | Applicability + enumeration + outputs + child/semantic assessments | Все их receipts; source union |
| Union | Общий диспетчер источников | Точное совпадение registry obligations и полученных producer receipts | Registry и каждый applicable/unknown producer; domain closure |
| Demand/frontier | ChildTasks/StructuralFrontier | Все стадии demand связаны typed input/output; нет ожидаемой живой ветви | Parent/child input, continuation, condition; parent/closure |
| Constraint/semantic | Именованный validator соответствующей механики | Проверяемые rule inputs; известная поддержка либо точный конфликт; обязательства сохраняются | Все positive/empty/negative reads; propagation/interpretation |
| Propagation | Планировщик constraints | Полный применимый набор рёбер + их текущие assessments, нет dirty/unknown | Домены и рёбра; closure, но не global selection |
| Domain closure | Общий evaluator завершения | Все union/frontier/propagation receipts актуальны | Весь dependency DAG; selection/discharge |
| Interpretation | Evaluator совместного выбора | Whole-selection witness и совместимость полного набора, не только попарная | Selection, structure, semantic receipts; lowering/publication |
| Publication | Native planner/gate | Stage certificates, lowered immutable IR, текущие read-set/policy/seal | Plan/batch/ledger versions; transactional writer |

Независимый validator читает immutable evidence и объявленные правила, а не доверяет
issuer status. Для генератора, у которого terminal cursor нельзя проверить без
повторного вычисления, validation обязан повторить соответствующий детерминированный
шаг/coverage check или оставить UNKNOWN. Отсутствие проверяемого метода — задача P05,
не разрешение верить флагу. Ни caller, ни callback не могут объявить собственный
набор producers исчерпывающим в обход registry.

Все traversals receipts/demands используют явную рабочую очередь и visited revisions;
глубина структуры не переносится в Python recursion. Цикл обоснования без внешней
проверяемой опоры остаётся UNKNOWN. Fixed point локальной propagation не означает
глобальную совместимость: например, три переменные с доменами {0,1} и попарными
ограничениями x≠y, y≠z, z≠x сохраняют arc consistency, но не имеют совместного решения.
Доказанное исчерпание совместного домена устанавливает EMPTY/UNIQUE/MULTIPLE
только для DomainClosureCertificate. InterpretationCertificate ВСЕГДА требует
конкретный совместимый selected tuple witness и все проверки своего semantic
profile. Единственность можно вывести из полного singleton, но его tuple всё равно
проверяется. Исчерпание пустого либо неоднозначного домена selection не заменяет.
Нельзя принять первую комбинацию локальных выборов.

## 9. Разобранные контрасты receipts

Имена ниже — символические ссылки на полные записи разделов 2–3, а не готовые
runtime fixtures. Каждый пример фиксирует решение будущего validator.

**E1 — полный пустой источник.** G@r7 имеет applicability=APPLICABLE, enumeration
E@r7 с terminal coverage всех объявленных grammar rules и outputs=[], obligations=[].
Validator G разрешает COMPLETE_EMPTY. Для всей задачи C@r7 остаётся OPEN, поэтому
Union(G,C) OPEN и DomainClosureCertificate отсутствует. Если C тоже COMPLETE_EMPTY
и все другие registry producers доказанно неприменимы, union становится EMPTY;
запись факта всё равно не разрешена. Если E нет, G=UNKNOWN независимо от outputs=[].

**E2 — один результат и остановленный ребёнок.** Grammar выдал A; component producer
зарегистрировал demand D на вложенное описание и остановился по budget. A валиден,
D=WAITING, resource receipt содержит незавершённый continuation. Domain closure
отклоняется по D, даже если A — единственный текущий кандидат. После +3 продолжения
выдан B; нельзя забыть A или выбрать B из-за последнего времени завершения.

**E3 — закрытая неоднозначность.** Все источники и constraints закрыты; A и B совместимы
по отдельности, но являются альтернативными прочтениями. DomainClosureCertificate
подтверждает MULTIPLE. Structural closure каждого дерева не создаёт SelectionWitness.
Partial representation допустима в журнале, write_eligible=False. Ответ модели,
выбирающий A на вопрос о всей оставшейся неоднозначности, разрешает дальнейшую
проверку выбранной интерпретации только вместе с полным актуальным domain proof.

**E4 — отзыв точного исключения.** Разбиение X исключено proof N@r2 на конкретной
комбинации occurrence ownership. Union U использует N и остаётся singleton Y.
DEPENDENCY_REJECTED(N) делает U и certificate STALE; X возвращается в открытый домен.
Кеш ветви Z, не читавшей N и U, сохраняется. Новый пустой ответ reader не заменяет
отозванное доказательство отрицания; нужен новый ReadReceipt и новый assessment.

**E5 — условная поддержка.** A@condition=H содержит selected reading R и полный
локальный child certificate. Validator в исторической H разрешает его использование
в H. Public unconditional validator его отвергает. Даже если H единственная
произведённая ветвь, открытый source второй гипотезы блокирует discharge. После
закрытия общего домена и whole-selection H, P21 выпускает discharge mapping каждого
условного premise в выбранный IR; это новый artifact с проверяемым происхождением.

**E6 — restart и независимость.** Support S имеет две полные цепочки C1 и C2.
После restart отсутствует Python issuer C1; если сериализованных evidence для него
нет, C1=UNKNOWN и не используется. Если C2 полностью проверяется, S сохраняется
на C2. Отзыв последней полной цепочки отзывает S. Certificate hash без evidence
не восстанавливает C1, и вывод о S не является новой независимой опорой самого S.

**E7 — отрицательная совместимость не установлена.** Источники исчерпаны, очередь
propagation пуста, но edge owner/role=UNKNOWN. Источник может иметь готовый finite
inventory, однако producer/propagation closure не выданы. Открытая обязанность
принадлежит P12/P16; нельзя превратить UNKNOWN в rejection и затем объявить Y единственным.


## 10. Обязательные профили стадий и отсутствие цикла seal

`stage` и `claim_profile_id/version` входят в address каждого receipt и в cache key.
Точное множество обязательств задаёт versioned registry по stage, input/output sort,
producer capability и condition. Каждая obligation содержит `owner_capability`,
`introduced_at`, `due_stage`, typed inputs, validator и transfer rule на следующую
стадию. Caller не может произвольно менять due_stage или исключать validator.
Если registry не знает, когда проверять обязательство, readiness=UNKNOWN.

| Stage/profile | Обязательные проверки сейчас | Поздние обязательства в результате | Выход и следующий потребитель |
|---|---|---|---|
| T2_TP / STRUCTURAL_READINESS_V1 | Structural producer union/enumeration; addressed child demands; совместимость целых употребляемых чтений; ownership/границы/области; binder/control/relative структурные связи; типизированные candidate reference edges; покрытие и разрешённые structural alternatives; frontier и structural propagation; источник и условность всех оснований | Словарное значение, выбор entity/content referent из готовых semantic candidates, semantic identity и разрешение отдельных semantic slots по контракту T3/T4. Полный список с due_stage, не потерянные unknown | StructuralReadinessCertificate или OPEN/PARTIAL; вход structural_seal |
| STRUCTURAL_SEAL / STRUCTURAL_FREEZE_V1 | Живой StructuralReadinessCertificate для завершённой структуры либо штатный трассированный incomplete/refusal snapshot; shape/scope/ID closure; structural hash и InterpretationVersion | Все unresolved semantic obligations плюс причины structural partial/refusal | Sealed snapshot; вход T3. Наличие seal не означает успешный разбор либо право записи |
| T3_T4 / SEMANTIC_RESOLUTION_V1 | Sealed graph неизменен; T3 CandidateSourceTrace/known-open semantics; T4 полнота applicable semantic sources и linked tuples; выбор lexical values/references; все semantic constraints; поздние обязательства из T2/T3 | Только obligations публикации/консолидации, не неразрешённый semantic slot | DomainClosureCertificate этого profile + точный selected tuple дают InterpretationCertificate; UNKNOWN/MULTIPLE/CONFLICT не дают selected certificate |
| C_T5_T6 / PUBLICATION_V1 | InterpretationCertificate, conditional discharge, lowered immutable IR/seal, policy разрешения фрагмента; identity/consolidation plan, batch/read-set/versions, transactional guards | Durable lifecycle зависимостей и будущий пересмотр | PublicationAssessment → journal/batch → T6 transaction; после commit отдельные truth supports |

StructuralReadinessCertificate использует тот же формат versioned certificates,
но `claim_profile_id=STRUCTURAL_READINESS_V1` и claim только о структурном результате.
Он ссылается на DomainClosureCertificate структурного профиля, точный выбранный
структурный tuple/разрешённое partial representation и полный список перенесённых
late obligations. Его validator не требует T4-решения, однако проверяет, что каждый
перенос допустим registry. Он не является InterpretationCertificate.

Для явно неразрешённой структуры архитектура допускает seal диагностического
snapshot после трассированного отказа/бюджета. Это отдельный результат
`SEALED_INCOMPLETE`, не StructuralReadinessCertificate и не обход его требований.
Наличие такого snapshot позволяет хранить состояние и продолжать предусмотренные
архитектурой действия, но само по себе не снимает никаких write guards.

Разделение структурной и семантической части reference/control определяется
типизированным контрактом. Например, установленное место ссылочного аргумента и
его область — structural; выбор идентичности из совместимых candidates — T3/T4.
Если semantic результат требует изменения уже sealed структурного ребра, начинается
новая InterpretationVersion и повтор структурного анализа. Запрещено исправлять
sealed tree внутри T4. Если не установлено само место/тип необходимого ребёнка,
обязательство structural и не переносится в T4 ради получения readiness.

Stage переход проверяет conservation obligations: каждое старое обязательство
либо закрыто валидным receipt, либо сохранено по тому же адресу с разрешённым
переходом и due_stage. Новые obligations добавлены registry producer; исчезновение
неразрешённого обязательства — INVALID_ARTIFACT. Ни complete source одной стадии,
ни устаревший source_complete=True не закрывают obligations следующей.

Приёмочные дополнения:

- CC19: lexical sense/reference ещё неизвестны, но структура определена →
  структурный certificate и seal допустимы, interpretation/write запрещены.
- CC20: неизвестна обязательная граница/owner ребёнка → structural readiness нет;
  диагностический seal не повышает статус и не разрешает запись.
- CC21: caller удалил late obligation либо заменил due_stage → INVALID_ARTIFACT.
- CC22: T4 потребовал иное структурное ребро → новая версия; прежний seal неизменен.

## Приёмка

2026-11-01: `/root/f05_coordinator`, **ACCEPT — P20-contract** после двух
исправлений: обязательные stage/profile и selected tuple независимо от exhaustion.
Принята спецификация; P20-validation и все шесть блоков F05 остаются OPEN.
Проверены 22 контраста, 7 примеров, ссылки capability ID и существование модулей
границ миграции. Runtime и тестовые ожидания не изменялись. Следующий пункт — P01.
