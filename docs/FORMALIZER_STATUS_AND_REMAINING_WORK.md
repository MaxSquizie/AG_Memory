# V7 — фактический статус после исправления аудита temp

Дата: 2026-10-08. Все пункты и причины: [I01–I38/A01–A05](audits/AG_MEMORY_TEMP_REMEDIATION_2026-10-08.md). [Карта production пути](IMPLEMENTATION_MAP_V7.md). Исторические blanket DONE и численные результаты прежних прогонов не являются подтверждением нынешнего кода.

## Реализовано и подключено

Production принимает реальный RawInput через native frontend, typed TP/T3/T4 и C/T5/T6. Каноническая память содержит типизированные M/N/G, concrete root/derived SupportRecords, IdentityBindings, TimeAssertions, UsageLinks и marker/COMMIT_DECISION. Native receipt предотвращает повторную запись тех же фактов legacy integration. Вопрос, команда и цитата не превращаются в действие мира.

AH writer готовит COW draft; точка коммита — fsync canonical WAL unit с полным AH snapshot. До неё live AH не меняется; после неё recovery восстанавливает точные UID, graph и ledger. Допущенное plan\E + marker + D атомарны. CandidateEvidence и отчёты восстанавливаются из D; уже отозванные источники создают born-closed evidence. Полный конфликтный отказ — один durable unit без facts/marker/D. GATE_PRECHECK диагностичен и не решает admission.

Goal channel применяет OR_ELIMINATION/FORALL_INST по concrete support/assertion ID. Dedup включает temporal assertion refs. APPLIED support+evidence+decision атомарны; NOOP/ABORTED — только durable goal decision под общей DB-N блокировкой. R0 сохраняет исторический исход; R1/R2 проверяют текущие premises и лицензию. Canonical visibility и audit event разделены; re-accession не оживляет старую отозванную запись.

R-X опыт пишется только с committed support, с раздельными T1/T2/T3 payloads и resource version; reads возвращают только живые соответствующие версии и свой stage. Cache не является truth ground. Использованные cache reads сохраняются в immutable run snapshot, чтобы replay не прочитал новый опыт той же пары.

Resource loader проверяет подписываемый content hash (включая coverage), зависимости и внешний review pin. CLI умеет создать unsigned draft и проверить snapshot; не подписывает и не выдаёт PASS.

## Что реально осталось

1. **Данные G2:** заполненный reviewed resource release, согласованные реальные TemplateMap refs, внешний review record и coverage corpus/report. Без них production выдаёт RESOURCE_MISSING; демо values не служат автоматическим fallback.
2. **Общий grammar DSL:** перенос полного `SyntaxRules` AST и resource schemas §2.1 в production вместо оставшихся встроенных SRL demo declarations. Сейчас общий typed TP может покрыть пробел, а при отказе безопасно блокирует фрагмент; это не замена всем данным грамматики.
3. **Запросы и время:** композиционный compiler всех GoalSpec (logical/quantified/IF/count/multi-scope), typed temporal/order anchors и end-to-end numeric scopes. Сейчас unsupported class помечается, а не упрощается до ложного положительного факта. Старые helpers не означают интеграцию.
4. **Миграция знаний:** полный declared open→known linking/reinterpretation и широкая identity policy с основаниями. По-source supersede есть; совпадение написания не доказывает identity. Не вводить handlers под отдельные примеры.
5. **Проверка:** пользователь отложил тесты. Race/crash/DR/oracle/live-model/unseen corpus не выполнялись. Источники компилируются и ключевые модули импортируются; это не валидация поведения.
6. **Масштабирование:** snapshot-WAL выбран ради одной очевидной durable границы; размер журнала и стоимость full-snapshot/ledger scans необходимо измерить и при необходимости заменить delta-WAL/checkpoint, сохранив контракт. Очистка/перезапись audit при этом запрещена.

## Архитектура и G0

Уточнены две принципиальные нормы (§7.6): formula content ≠ derived EVENT occurrence и общий existential AND witness ≠ два независимых existential окна. Принятые границы TIMELESS, OPEN identity и earliest-admission описаны явно. SHA текущего документа — в отчёте аудита.

Исторический G0 review подписывал другие байты; он помечен VOID для текущей редакции. **G0 BLOCKED до нового независимого review. G1–G5 BLOCKED до собственных доказательств.** В этой работе не создавались подпись, oracle outputs, resource coverage или PASS.

## Подготовка ресурсов

См. [runtime resource boundary](FORMALIZER_RUNTIME_RESOURCES.md). Не считать unsigned draft рабочим релизом. Не добавлять автоматический alias неизвестного слова или fallback known sense без TemplateMap ради запуска.
