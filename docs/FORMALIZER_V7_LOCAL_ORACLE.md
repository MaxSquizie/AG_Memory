# Оракул V7: запуск на локальной модели

Единая точка входа — `tools/run_formalizer_v7_oracle.py`. Она читает весь корпус, выполняет привязанные шаги через API проекта и сравнивает наблюдения с неизменённым gold. Перед исполнением из входа удаляются `checks`; binder отклоняет вход, если ожидаемые ответы всё же переданы ему.

Языковые кейсы вызывают настоящий `interpret_full`: T0–T4, T5/T6, AH, журнал провайдера и GoalExecutor. Для компонентных кейсов модель не требуется. Они вызывают конкретную проверяемую границу: валидатор, конструктор, inference, ledger либо файловый WAL. Это разные уровни проверки, отмеченные в binding manifest каждого кейса.

## Установка

Из корня клона ветки `temp`, Python 3.12+:

```powershell
python -m pip install -e .
python -m pip install pytest
python tools/check_formalizer_v7_oracle.py validate data/formalizer_v7_oracle
```

Команда сама добавляет `src` в import path; переменная `PYTHONPATH` для CLI не нужна. Используйте отдельное окружение проекта. Для pytest без editable install нужен `PYTHONPATH=src:.` в Linux/WSL.

## LM Studio

Загрузите модель, включите OpenAI-compatible server и укажите **точный идентификатор загруженной модели**. Каждый вызов самодостаточен: история диалога в запрос не добавляется. Параметры генерации фиксируются; temperature=0 не считается доказательством детерминизма модели.

Сначала небольшой языковой кейс:

```powershell
python tools/run_formalizer_v7_oracle.py --provider lmstudio --base-url http://127.0.0.1:1234 --model "ИМЯ_ЗАГРУЖЕННОЙ_МОДЕЛИ" --case A01 --out artifacts/oracle/lmstudio-smoke
```

Затем весь корпус, включая компонентные и журнальные проверки:

```powershell
python tools/run_formalizer_v7_oracle.py --provider lmstudio --base-url http://127.0.0.1:1234 --model "ИМЯ_ЗАГРУЖЕННОЙ_МОДЕЛИ" --timeout 120 --max-tokens 4096 --out artifacts/oracle/lmstudio-full
```

Для Ollama с OpenAI-compatible endpoint используйте `--provider openai --base-url http://127.0.0.1:11434 --model "имя-модели"`. Если сервер требует авторизацию, задайте `FORMALIZER_ORACLE_API_KEY` в окружении. Ключ не включается в run config или отчёт.

Каждый прогон требует **новый, пустой** каталог `--out`. Повторный запуск не подмешивает старые ответы другой модели. Непривязанные действия получают BLOCKED; исполняемые расхождения и исключения — FAIL. Обход валидаторов и подстановка правильного ответа из gold отсутствуют.

## Фильтры и запуск без модели

```powershell
python tools/run_formalizer_v7_oracle.py --out unused --list --tier pipeline
python tools/run_formalizer_v7_oracle.py --out unused --list --mechanism goal_decision
python tools/run_formalizer_v7_oracle.py --provider disabled --out artifacts/oracle/components
```

`--case`, `--tier`, `--mechanism` можно повторять. `--list` ничего не записывает и не вызывает провайдера. При `disabled` языковые кейсы отмечаются `BLOCKED_LOCAL_PROVIDER_DISABLED`, а доступные компоненты исполняются.

## Точное повторение ответов провайдера

```powershell
python tools/run_formalizer_v7_oracle.py --provider replay --replay-from artifacts/oracle/lmstudio-full --out artifacts/oracle/replay-full
```

Replay использует сохранённые PENDING/RECEIVED и RunMarker. Транспорт не отправляет HTTP-запросы; отсутствие необходимых ответов не вызывает скрытого обращения к модели. Повтор запускает алгоритмы на новой AH, а не читает прошлые фактические checkpoints. Изменение хеша корпуса или исполнявшихся исходников блокирует такой replay.

## Артефакты результата

| Файл | Содержание |
|---|---|
| `comparison.json` | PASS/FAIL/BLOCKED каждого кейса, путь и шаг расхождения |
| `runtime_coverage.json` | Покрытие по A, DR, механизму, действию и уровню |
| `bindings.json` | Реестр подключённых действий и результаты привязки кейсов |
| `actual.jsonl.gz` | Фактические checkpoints, UID/Ref-привязки и manifests |
| `cases/<case-hash>/journal.log` | Durable история провайдера, batch/goal и отзыва |
| `resources/` | Подписанные тестовые resource fixtures |
| `run_config.json`, `provenance.json` | Модель, параметры, входные/исходные хеши и воспроизводимость |

Полный `FormalizationState` и `InterpretationReport` сохранены в `runtime.ir/report` языкового checkpoint. `/assertions/ir` и `/assertions/journal` — **проекции допущенных утверждений**, а не весь parser IR. Канонические факты декодируются из фактических N/G и актантов.

Коды завершения: `0` — все выбранные кейсы прошли; `1` — есть FAIL; `3` — нет FAIL, но есть BLOCKED. Сам exit code pytest не заменяет этот статус.

## Границы доказательства

Измеренный прогон без модели и полный список расхождений: [расширенный runtime-снимок](formalizer_v7_extended_run/README.md). Итог этого снимка — 1634 PASS / 89 FAIL / 819 BLOCKED; исключений исполнения нет. Это незавершённое покрытие, а не заявление о готовности всех механизмов.

- Resource fixtures имеют публичный ключ `TEST_ONLY` и атрибуцию `ORACLE_FIXTURE_ONLY`; это не reviewed production release и не оценка реального лексического покрытия. TemplateMap проверяется на T подготовленной AH. Явные identity bindings заданы фикстурой; production linking по совпадению имён не включается.
- Набор ACTION bindings неполон. Запуск **всего корпуса** не означает исполнение всех его механик: конкретные блокеры публикуются отдельно. В частности, общая migration workflow, часть reference/context сценариев и некоторые составные crash stimuli требуют дополнительных fixtures/bindings.
- Отрицательные DSL-кейсы с невалидным исходным, ещё не мутированным правилом блокируются как `BLOCKED_INVALID_ORACLE_DSL_BASELINE`: их отказ не доказывает проверку заявленной мутации. Положительная DSL-эквивалентность сравнивается с текущим компилятором и может дать FAIL.
- Crash точки моделируются на durable API-границах с последующим восстановлением AH. Принудительное завершение процесса ОС этим runner не доказано.
- Проверка реального HTTP и offline replay покрыта отдельной регрессией с локальным сервером фиксированных ответов. Качество вашей модели можно оценить только вашим live прогоном.
- G0–G5 этим инструментом не переводятся в PASS. Gold не редактируется ради зелёного результата. Расхождения требуют отдельной проверки: виноваты могут быть код, fixture, экспорт наблюдений либо сам gold.

Старый 16-action компонентный runner и его опубликованный снимок остаются отдельным воспроизводимым результатом: [инструкция](FORMALIZER_V7_ORACLE_INTEGRATION.md). Для текущего локального запуска используйте команды этого документа.
