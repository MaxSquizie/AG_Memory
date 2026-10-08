# V7 — фактический статус после исправления аудита temp

Дата: 2026-10-08. Все пункты и причины: [I01–I38/A01–A05](audits/AG_MEMORY_TEMP_REMEDIATION_2026-10-08.md). [Карта production пути](IMPLEMENTATION_MAP_V7.md). Исторические blanket DONE и численные результаты прежних прогонов не являются подтверждением нынешнего кода.

## Реализовано и подключено

Production принимает реальный RawInput через native frontend, typed TP/T3/T4 и C/T5/T6. Каноническая память содержит типизированные M/N/G, concrete root/derived SupportRecords, IdentityBindings, TimeAssertions, UsageLinks и marker/COMMIT_DECISION. Native receipt предотвращает повторную запись тех же фактов legacy integration. Вопрос, команда и цитата не превращаются в действие мира.

AH writer готовит COW draft; точка коммита — fsync canonical WAL unit с полным AH snapshot. До неё live AH не меняется; после неё recovery восстанавливает точные UID, graph и ledger. Допущенное plan\E + marker + D атомарны. CandidateEvidence и отчёты восстанавливаются из D; уже отозванные источники создают born-closed evidence. Полный конфликтный отказ — один durable unit без facts/marker/D. GATE_PRECHECK диагностичен и не решает admission.

Goal channel применяет OR_ELIMINATION/FORALL_INST по concrete support/assertion ID. Dedup включает temporal assertion refs. APPLIED support+evidence+decision атомарны; NOOP/ABORTED — только durable goal decision под общей DB-N блокировкой. R0 сохраняет исторический исход; R1/R2 проверяют текущие premises и лицензию. Canonical visibility и audit event разделены; re-accession не оживляет старую отозванную запись.

R-X опыт пишется только с committed support, с раздельными T1/T2/T3 payloads и resource version; reads возвращают только живые соответствующие версии и свой stage. Cache не является truth ground. Использованные cache reads сохраняются в immutable run snapshot, чтобы replay не прочитал новый опыт той же пары.

Resource loader проверяет подписываемый content hash (включая coverage), зависимости и внешний review pin. CLI умеет создать unsigned draft и проверить snapshot; не подписывает и не выдаёт PASS.

Ресурсный SyntaxRules interpreter теперь подключён к SRL/T2 native-входа: data-only AST, целые R1 variants, bounded joins, трёхзначные проверки, schema lookups только по объявленным зависимостям, typed graph emission и durable trace. Встроенный preview SRL/FrameGen не участвует в native. При неоднозначности/неполном поиске работает TP до seal; приоритет не выбирает смысл. Prop-аргумент SOM принимает целое N/G-дерево (в том числе NOT/OR), не выдавая его детям root truth-support. Explicit request_kind QUERY/COMMAND/UNKNOWN проходит factual gate и compatibility projection.

## Дополнительно подключено в последнем проходе

`FormalizerAdapter` передаёт sealed дерево вопроса в `AssociationSessionTurnGoalCompiler` → `native_queries` → `InferenceEngine`. Native roots владеют своими листьями: второй legacy EXISTS для них не строится. NOT/AND/OR/XOR сохраняют композицию и open-world семантику; известные FORALL/EXISTS/modal/IMPLIES roots читаются по каноническому доказательству, положительный EXISTS допускает bounded join свидетеля. FORALL не доказывается перебором нескольких примеров. OR_ELIMINATION/FORALL_INST по-прежнему пишут только через durable goal channel. WH/COUNT имеют типизированные query slots, а многословная лексическая единица — raw anchors и явно объявленную морфологическую вершину. Для known sense всей фразы требуется released R-S anchor_pattern; значение одного слова не подставляется. Комплексная attitude без собственного правила остаётся UNKNOWN.

TIME/TIME_SCOPE сохраняют область действия датировки. BEFORE/AFTER/DURING принимают закрытые TimeLiteral без UID/UsageLink, входят в persistence и читаются как runtime comparison. Ложное отношение якорей отклоняется ещё при C; неизвестный порядок не подменяется датой. AND с независимыми existential окнами не доказывает одновременность. Недатированная оболочка не покрывает произвольно датированные query operands.

CountGoal считает разные M-свидетели по заданной роли, а не записи SupportRecord или повторные упоминания. Без полноты ответ содержит доказанную нижнюю границу. Optional reviewed DomainCertificate именует точные template/role/known_roles/window и живые completeness_evidence support IDs; смена snapshot или отзыв источника снимают право точного счёта. Bool из запроса не является сертификатом. Count/formula/time результаты не материализуются как факты мира.

`migration.reinterpret_observation` запускает frozen input под v+1 с declared trigger и новым release. T6 атомарно фиксирует допущенную замену, supersede старой версии, marker/D и audit-link open→known. Провал до коммита не отзывает прежнюю версию. Link не создаёт alias/taxonomy; отозванные опоры не оживают. Повторные отзывы не меняют уже терминальные статусы свидетельств.

## Что реально осталось

1. **Данные G2:** заполненный reviewed resource release, реальные TemplateMap refs, внешний review record и coverage corpus/report. Без них production выдаёт RESOURCE_MISSING. Новые anchor_pattern, TIME_SCOPE, QUERY_SLOT и certificates требуют версии/hash/review, а не вставки defaults в старый релиз.
2. **DSL/CandidateSchema — SPEC_GAP и реализация:** §16 называет BNF полной, но Emit повторно использует production `fields` для stage/reads/when, не задавая fields полезной нагрузки и объявления captures. Поэтому JSON AST не выдаётся за текстовый BNF parser. Нужна однозначная нормативная грамматика captures/output fields и manifest CandidateSchema всех emit kinds; затем — parser/loader. SRL orthography/ellipsis proposals сохраняются, но полного разрешения всех реконструкций ещё нет.
3. **Специальные цели:** native counterfactual proof должен фильтровать canonical derived paths по runtime assumptions, а не спрашивать старый reasoner о реальном мире; текущий compiler выдаёт COUNTERFACTUAL_NATIVE_SCOPE_NOT_IMPLEMENTED. CAUSAL mapping, произвольные WH под несколькими операторами, general nested quantifier joins и end-to-end AT_LEAST_N/EXACTLY_N/AT_MOST_N scope-reader ещё не завершены. Модальное/IMPLIES утверждение читается, но это не общий вывод его операнда. Неизвестная цель не превращается в EXISTS.
4. **Identity policy:** host bindings с конкретными основаниями поддержаны; общего Resource/CorefPolicy resolver ещё нет. Совпадение имён или написаний не доказывает identity. Без разрешения сущностей cross-observation вывод может честно остаться UNKNOWN.
5. **Проверка:** пользователь отложил тесты. Race/crash/DR/oracle/live-model/unseen corpus не выполнялись. Компиляция, импорты, сверка исходников и diff не валидируют поведение.
6. **Масштабирование:** snapshot-WAL и bounded ledger/index reads требуют измерения на большой памяти. Delta-WAL/checkpoint допускаются только при сохранении атомарности, replay и неизменяемого audit.

## Архитектура и G0

Уточнены две принципиальные нормы (§7.6): formula content ≠ derived EVENT occurrence и общий existential AND witness ≠ два независимых existential окна. Принятые границы TIMELESS, OPEN identity и earliest-admission описаны явно. SHA текущего документа — в отчёте аудита.

Исторический G0 review подписывал другие байты; он помечен VOID для текущей редакции. **G0 BLOCKED до нового независимого review. G1–G5 BLOCKED до собственных доказательств.** В этой работе не создавались подпись, oracle outputs, resource coverage или PASS.

## Подготовка ресурсов

См. [runtime resource boundary](FORMALIZER_RUNTIME_RESOURCES.md). Не считать unsigned draft рабочим релизом. Не добавлять автоматический alias неизвестного слова или fallback known sense без TemplateMap ради запуска.
