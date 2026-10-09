# Oracle нормативной архитектуры V7

Это независимое gold-описание, составленное по приложенному документу. Генератор не импортирует формализатор и не извлекает ожидаемые результаты из его ответов. Все файлы UTF-8. Сборка воспроизводима.

## Состав и назначение

`cases.jsonl` — конкретные входы/сценарии и ожидаемые checkpoint-проверки. `fixtures.json` — декларативные тестовые предпосылки. `mechanisms.json` и `coverage.json` — механизм → кейсы, A01–A39, DR1–DR31. `source_map.json` — заголовки и расположение норм в точном исходном документе. `manifest.json` пинит SHA256 архитектуры, генератора и артефактов. `oracle.schema.json` описывает формат. `SPEC_NOTES.md` отделяет ограничения oracle от статуса архитектуры.

Корпус включает положительные, отрицательные, пограничные, неоднозначные, неразрешённые, конфликтные и crash/recovery ветви. Матрицы времени вычислены независимо от реализации. Все наборы отрицаний n-ary OR для n=2..6 перечислены полностью. Разнообразие языковых входов опубликовано отдельно от количества механических векторов; замена имени не считается новым механизмом.

## Уровни исполнения

- `pipeline`: raw русский текст → все применимые стадии → IR → AH/TemporalLedger/journal. FAKE провайдер фиксирует разрешённые предложения, но не подменяет T0/T1/T2/validators/C/T5/T6.
- `component`: тест одной реальной границы с явно подготовленным входом; проверяет механизм, не end-to-end покрытие языка.
- `durability`: несколько действий над одним persistent store; crash должен завершать процесс/разрывать durable границу, а recovery — читать заново файл, не сохранённый Python объект.

Нельзя засчитать component case в G3/G4 как полный вертикальный прогон. Нельзя засчитать scripted corpus в G5 как ранее не виденный экспертный holdout. Нельзя объявить PASS наличием oracle либо успешной проверкой его JSON.

## Подключение к проекту

1. Реализуйте adapter `module:function(case, fixtures) -> trace` поверх реальных публичных API проекта. Действия и их payload определены в JSONL; `actions.json` перечисляет поля каждой границы. Адаптер не имеет права читать `steps[].checks`. Конкретное начальное состояние строится из EMPTY + setup actions; все identity links даны fixture явно.
2. Свяжите символы (`ivan`, `N`, `S_or`, `A_not`, …) с реальными Ref/UID через независимый fixture builder. Нельзя объединять сущности по одинаковому имени. Known T должны реально существовать в fixture AH; open T создаёт SUT. Релиз тестовый; это не production reviewed release и не подпись человека.
3. Перед запуском compiler/binder должен получить байты fixture release, frozen context/provider/timing и построить ожидаемые canonical IDs и hash структурных snapshots **независимо от SUT**. Получившийся closed `OracleCase` по §11.2 храните вместе с binding manifest: source document/corpus hash, ah commit, concrete resource hashes, model/params, scripts/timing, UID aliases и expected snapshot hashes. Незаполненный binding — BLOCKED, не PASS. Этот пакет содержит символический исполнимый gold, а не выдуманные UID/sha256 будущего release.
4. Exporter возвращает checkpoint для каждой step (включая setup/crash), без фильтрации лишних фактов/узлов. Формулы — typed JSON AST (`predicate/roles` либо `operator/operands`); structural presence не равно asserted truth. Поля `/assertions/ah`, `/assertions/ir`, `/assertions/journal` перечисляют только фактические утверждения соответствующего канала. Дополнительные факты должны остаться в этих списках и провалить exact set check.
5. Нормализация не меняет semantic identity, polarity, mode, temporal bounds, provenance или outcome. Alias unknown UID экспортируется как `unbound:<uid>`. `state.semantic_digest` — SHA256 canonical semantic state всех записей (AH/TL/опоры/links/markers/D/decisions/отчёты/audit/R-X), с исключением лишь documented volatile timings; значение обязан вычислять exporter. Не используйте SUT ответ вместо digest.

Формат trace: `{schema_version:"v7-oracle-trace-1", case_id, checkpoints:[{step_id, actual:{…}}]}`. Каждая `/path` — JSON Pointer в `actual` данного checkpoint. Missing path — FAIL, даже если expected `null`/пусто/UNKNOWN. `/diagnostics/located_multiset` — пары `(code,location)`; byte-for-byte replay проверяется отдельно, не только по перечню кодов.

```
python tools/build_formalizer_v7_oracle.py --architecture /absolute/path/FORMALIZER_ARCHITECTURE_V7.md
python tools/check_formalizer_v7_oracle.py validate data/formalizer_v7_oracle
python tools/verify_formalizer_v7_oracle_artifacts.py
python tools/check_formalizer_v7_oracle.py run data/formalizer_v7_oracle --adapter my_oracle_adapter:run --out /tmp/actual.jsonl
python tools/check_formalizer_v7_oracle.py compare data/formalizer_v7_oracle /tmp/actual.jsonl --report /tmp/oracle_report.json
```

По умолчанию `compare` требует **все** case IDs; пропуск/дубликат/лишний case, checkpoint или required field — FAIL. Для поднабора используйте `--case` явно: отчёт помечен `PARTIAL`, общий PASS запрещён. В `run` adapter получает копию кейса без checks; verifier хранит gold отдельно. Необслуживаемое действие/отсутствие adapter — BLOCKED/ошибка, не безопасный UNKNOWN, засчитанный как успех.

## Сравнение

`eq` точное typed равенство; `set_eq` одинаковые множества без дубликатов; `multiset_eq` учитывает кратность; `contains` требует все заданные элементы и кратности; `excludes` запрещает typed элементы; `count` проверяет длину; `same_as` сверяет выбранное поле с ранее полученным checkpoint. Недостаточно сравнить лишь естественный язык ответа. Forbidden truth не запрещает структурный операнд той же формулы без опоры. Нет подстрочных проверок вида «слово встретилось в журнале».

Важные негативные ветви: M-only fact, missing source ≠ empty, known mapping failure ≠ open fallback, live ledger ≠ effective witness, two candidate reports в partial APPLIED, отсутствующий D при full reject, request_window не dedup ключ, assertion refs входят в ключ, текущая лицензия R1/R2, историческое решение R0, общий witness ≠ одинаковые bounds, EVENT occurrence ≠ content identity, старые migration supports не оживают.

Пакет не меняет архитектуру/G0–G5 и не содержит результатов запуска проектных тестов. После binding запускайте сначала component, затем persistent durability, затем pipeline. Отчёт должен разделять ошибки реализации, реальную неоднозначность спецификации, непривязанный fixture и языковое покрытие.
