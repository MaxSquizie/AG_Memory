# V7 — фактический статус temp

Дата: 2026-10-08. Последний проход начат на `59fc13ec415809a9b262fd72a0b5ed5594de285a`. [Полный реестр аудита](audits/AG_MEMORY_TEMP_REMEDIATION_2026-10-08.md), [дельта по пяти последним пунктам](audits/AG_MEMORY_TEMP_REMAINING_FIVE_ITEMS_2026-10-08.md), [карта production](IMPLEMENTATION_MAP_V7.md).

## Подключено в коде

Native input проходит released morphology/syntax/TP/T3/T4 → C/T5/T6. SOM, UsageLink, concrete root/derived supports, time, identity bindings, markers и decisions фиксируются canonical WAL boundary; legacy integration не пишет факты второй раз. Admission/retraction/goal решения и replay используют canonical proof/time/audit, а не LIVE-флаг или отсутствие факта.

Последняя дельта: текстовый DSL, closed schema validation, Ed25519 trust boundary, actual-T catalog/release builder/coverage/sign tools; bounded R-X index и profile/counters; CountLiteral и numeric G, bounds reader, full-scope compound WH/COUNT, nested EXISTS и temporal proposition operands; frozen grounded CorefPolicy и resumable declared mass migration с резервированием версий. [Подробности и причины](audits/AG_MEMORY_TEMP_REMAINING_FIVE_ITEMS_2026-10-08.md).

## Что осталось фактически

1. **Данные:** authored lexicon/valencies/TemplateMap текущих T, фиксированный корпус, реальный reviewer key/trust registry и независимо подписанный release не предоставлены. CLI готовит/проверяет эти артефакты; демо не подставляется. Лексическая availability не выдаётся за execution coverage.
2. **Покрытие и semantics:** native counterfactual path filtering; недостающие causal/comparative/superlative/manner goals; произвольные restrictions в count body и отдельная aggregate CountDomain по временному окну. Общие trees/queries сохранены, но безопасный UNKNOWN ещё не выполняет G5.
3. **Измерения:** profile-rx и session metrics показывают actual retrieval/index/liveness cost. Большая production память и benefit на фиксированном корпусе не измерены. Snapshot WAL и paths могут оставаться дорогими.
4. **Проверка:** пользователь отложил тесты. Криптографическое/поведенческое соответствие, DR/oracle/crash/race и модельный корпус не прогонялись.
5. **Identity по дизайну:** entity references требуют explicit window/context/evidence. Event identity/report bridging выключены; массовая миграция не угадывает тождество по написанию и не переинтерпретирует контекст зависимых источников автоматически.

## Архитектура и ворота

§16 заменяет недоопределённый BNF исполнимым контрактом; уточнены registered CandidateSchema, trust envelope, numeric/time operands, runtime query targets и migration/reference workflow. A01–A39/DR1–DR31 сохраняются. G0 BLOCKED: изменились нормативные байты, необходим новый SHA256 и независимый review manifest. G1–G5 BLOCKED до фактических доказательств. Старые PASS и чужие исторические прогоны не подтверждают этот код.

Проверено в этой работе: source compile, импорты, JSON Schema meta-validation, статическая сверка и git diff --check. Тесты не читались, не запускались и не изменялись.
