# Подключение oracle V7 к AG_Memory

Проверка выполнена на исходном коммите `12976bf388ef2b77f06b174eab27f60e49db31dc` ветки `temp` с изменениями, перечисленными в [отчёте об исправлениях](FORMALIZER_V7_ORACLE_RUNTIME_FIXES.md). Точные SHA256 исполнявшихся исходников, корпуса, подписанных тестовых ресурсов и результатов записаны в [provenance.json](formalizer_v7_oracle_run/provenance.json).

## Измеренный результат

Символический корпус содержит 2542 кейса, 10902 проверки и 118 механизмов. Ожидаемые результаты не изменялись для прохождения реализации. Конкретный адаптер исполнил 1319 кейсов: **1319 PASS / 0 FAIL / 1223 BLOCKED**. Статус полного прогона — **BLOCKED**.

| Уровень корпуса | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|
| component | 1310 | 0 | 521 |
| durability | 9 | 0 | 62 |
| pipeline | 0 | 0 | 640 |

Привязаны 16 из 126 видов действий; некоторые комбинации параметров этих действий также остаются BLOCKED. По наборам кейсов корпуса: у 4 механизмов исполнены все связанные кейсы, у 28 — часть, у 86 — ни одного. Это покрытие данного корпуса, а не доказательство полноты механизма или русского языка. A01–A39 и DR1–DR31 представлены в gold; наличие кейса не означает его исполнение.

Отдельная проверка валидатора подтвердила внутреннюю согласованность 2542 кейсов, 15 негативных проверок сравнения и 169 независимых пар временных реализаций. Эта проверка не исполняет проект.

Целевая pytest-команда ниже завершилась с **1399 passed / 1223 skipped / 0 failed**. Четыре первоначально проблемных файла (`oracle`, `v7_pipeline`, `runtime_adapter`, `ah_adapter`) отдельно дали **26 passed**. Это выбранный набор проверок, а не результат всех тестов репозитория.

Gold-манифест закрепляет SHA256 приложенного документа с CRLF: `a334e8d11837255577dfddf0a37bf30c41c7cee47b16ed1995d05cab87e70948`. Репозиторный `.md` имеет LF и hash `932fc1a9495a59418810a4164ea74ebd1657f4ca0f9a3aa8a8b8d7aff0668d2a`; после нормализации переносов строки тексты совпадают. Байтовая идентичность этих двух файлов не заявляется.

## Что именно подключено

`tools/formalizer_v7_runtime_adapter.py` строит типизированные входные фикстуры, вызывает реальные границы AH и возвращает наблюдения из созданных записей. `tools/check_formalizer_v7_oracle.py` сравнивает их с gold, сохранённым отдельно. Перед вызовом адаптера из всех шагов удаляются `checks`; адаптер не получает ожидаемые ответы.

| Действия | Реальная граница |
|---|---|
| `query_time`, `check_simultaneity` | TemporalLedger и временная алгебра admission |
| `derive_or`, `derive_forall`, `nary_or_query`, `repeat_goal` | Валидация лицензии и GoalExecutor; AddDerivedSupport/TimeAssertion/GOAL_DECISION |
| `commit_grounded_fragment`, `admit_batch` | Проверка truth-grounds, типизированный T5-план и AHStoreAdapter |
| `journal_batch`, `journal_batches`, `execute_head_calls`, `crash`, `recover` | Реальный файловый WAL, глобальный admission, маркер и COMMIT_DECISION; новый экземпляр AH при recovery |
| `function_identity`, `numeric_scope_literal` | Типизированные канонические конструкторы и FunctionRegistry |
| `validate_selector_reply` | Закрытая схема ответа selector; положительные случаи проходят native T4 |

Символические предикаты, сущности и роли связываются с реальными T/M/Ref. Для каждого набора ролей проверяется инъективность отображения: два разных аргумента не могут незаметно стать одним слотом. TemplateMap ссылается на существующие T подготовленной AH. Формулы результата декодируются из фактических N/G и их актантов, а не возвращаются из входного AST. Дополнительный регрессионный тест меняет актант в AH и проверяет изменение экспортируемой формулы.

Два вида дедупликации проверяются отдельно: канонический узел и путь вывода. В `repeat_goal` смена временного запроса оставляет ключ пути прежним, смена конкретного TimeAssertion или SupportRecord создаёт другой путь. Смена правила или заключения пока блокируется: для неё ещё не подготовлен самостоятельный типизированный proof fixture. Режим STATE/EVENT/PROCESS/TRANSITION/UNKNOWN в этой компонентной фикстуре задаётся явно и записывается в binding manifest; это не проверка определения режима из языка.

Все исполненные случаи содержат `binding_manifest`: API, UID aliases, реальные опоры/свидетельства, ресурсные и исходные хеши, снимки AH до/после. Полный канонический экспорт AH участвует в `semantic_digest`. Подписанные resource fixture файлы сохранены рядом с результатом. Их ключ `TEST_ONLY` публичный и фиксированный; reviewer `ORACLE_FIXTURE_ONLY` обозначает тестовую атрибуцию, а не человеческий production review. Production-проверки подписи и TemplateMap не отключаются.

Общий набор исходных SHA256 хранится один раз в `provenance.json`; каждый case manifest содержит его `source_snapshot_ref`. Это убирает повторение одного и того же набора файлов в 1319 трассах без удаления checkpoints или изменения результатов сравнения.

## Честные ограничения

- Все 640 `pipeline` кейсов пока BLOCKED: полного binder для raw text, proposal/provider scripts, ресурсов и ожидаемых IR/ID ещё нет. Небольшие native pipeline регрессии запускаются отдельно и не заменяют эти 640 кейсов.
- Девять кейсов `durability` проверяют файловый WAL и восстановление в новом объекте AH. Действие `crash` уничтожает экземпляр адаптера; процесс ОС не убивается. Эти PASS подтверждают проверенные состояния WAL, но не выполнение полного crash-протокола уровня durability, требуемого README корпуса.
- `/assertions/ir` сейчас экспортирует принятые типизированные планы T5, а не полный parser IR. Самостоятельный compiler ожидаемых snapshot hashes по §11.2 ещё не реализован: `closed_oracle_expected_snapshot_hashes=NOT_COMPILED`.
- Неизвестные/символические временные границы остаются неизвестными; адаптер не подставляет время. Реальные ресурсные данные, внешний провайдер и reviewed production release этим прогоном не валидируются.
- Для недоступного действия весь кейс блокируется до записи. Ошибка исполнения считается FAIL, а не UNKNOWN/BLOCKED. BLOCKED не засчитывается как PASS; итоговый код возврата полного прогона — 3.

G0–G5 не оценивались и этим отчётом не переводятся в PASS. Следующая работа: остальные компонентные API-привязки; процессные crash-точки; полный binder исходного текста с независимыми ожидаемыми ID/IR/снимками. Подробные блокеры каждого кейса доступны в [comparison.json](formalizer_v7_oracle_run/comparison.json), покрытие — в [runtime_coverage.json](formalizer_v7_oracle_run/runtime_coverage.json).

## Воспроизведение

Из корня репозитория с установленными зависимостями проекта и `pytest`, `pymorphy3`, `jsonschema`, `cryptography`:

```bash
PYTHONPATH=src:. python tools/check_formalizer_v7_oracle.py validate data/formalizer_v7_oracle
python tools/verify_formalizer_v7_oracle_artifacts.py
PYTHONPATH=src:. python tools/run_formalizer_v7_bound_oracle.py --out /tmp/formalizer_v7_oracle_run
```

Последняя команда возвращает 3 при неполном покрытии, 1 при ошибке сравнения/исполнения, 0 при полном прохождении корпуса. Публикуемый файл `actual.jsonl.gz` содержит все фактические checkpoints; SHA256 распакованных байтов закреплён в provenance. Для повторного сравнения:

```bash
gzip -dc docs/formalizer_v7_oracle_run/actual.jsonl.gz > /tmp/formalizer_v7_actual.jsonl
python tools/check_formalizer_v7_oracle.py compare data/formalizer_v7_oracle /tmp/formalizer_v7_actual.jsonl --report /tmp/formalizer_v7_comparison.json
```

Для проверки целевых регрессий:

```bash
PYTHONPATH=src:. python -m pytest -q tests/test_formalizer_oracle.py tests/test_formalizer_v7_pipeline.py tests/test_formalizer_runtime_adapter.py tests/test_formalizer_ah_adapter.py tests/test_formalizer_goal_executor.py tests/test_formalizer_temporal_license.py tests/test_formalizer_runtime_binding_regressions.py tests/test_formalizer_v7_bound_oracle.py
```

Корпус может оставлять `pytest.skip` только с явным BLOCKED и списком причин; число skip публикуется отдельно. Отчёт CLI, в отличие от общего exit code pytest, сохраняет общий статус BLOCKED.
