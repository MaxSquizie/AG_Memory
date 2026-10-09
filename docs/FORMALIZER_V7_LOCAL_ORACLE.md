# Оракул V7: запуск на локальной модели

Единая точка входа — `tools/run_formalizer_v7_oracle.py`. Она читает весь корпус, выполняет привязанные шаги через API проекта и сравнивает наблюдения с неизменённым gold. Перед исполнением из входа удаляются `checks`; binder отклоняет вход, если ожидаемые ответы всё же переданы ему.

Языковые кейсы вызывают настоящий `interpret_full`: T0–T4, T5/T6, AH, журнал провайдера и GoalExecutor. Для компонентных кейсов модель не требуется. Они вызывают конкретную проверяемую границу: валидатор, конструктор, inference, ledger либо файловый WAL. Это разные уровни проверки, отмеченные в binding manifest каждого кейса.

Подключены **все 126 типов действий** корпуса: 2542 кейса, 10902 проверки, 118 механизмов, A01–A39 и DR1–DR31. Реестр доступных действий не означает, что все проверки уже прошли: сравнение сохраняет каждый FAIL и BLOCKED. В том числе подключены reference/context, migration и bulk recovery, scope/compound/count, R-X, временные пути и crash-границы batch/goal.

## Установка

Из корня клона ветки `temp`, Python 3.12+:

```powershell
python -m pip install -e .
python -m pip install pytest
python tools/check_formalizer_v7_oracle.py validate data/formalizer_v7_oracle
```

Команда сама добавляет `src` в import path; переменная `PYTHONPATH` для CLI не нужна. Используйте отдельное окружение проекта. Для pytest без editable install нужен `PYTHONPATH=src:.` в Linux/WSL.

## GUI с локальной моделью

GUI использует `formalizer_release.json` и `formalizer_reviews.json` из `paths.data_dir`. Эти production-файлы не поставляются как фиктивный reviewed release. Для отдельной тестовой сессии подготовьте оба файла вместе с AH-памятью, на шаблоны которой ссылается `TemplateMap`:

```powershell
python tools/prepare_formalizer_v7_gui.py --config config/lmstudio.toml --out artifacts/gui-local
python -m ah.gui.app --config artifacts/gui-local/gui.toml
```

Команда подготовки работает из корня клона без `PYTHONPATH`; для GUI предварительно установите `python -m pip install -e ".[gui]"`. Для Ollama замените исходный конфиг на `config/ollama.toml`. Настройки модели и сервера берутся из вашего конфига; команда сама не запускает сервер модели.

В новом каталоге создаются `formalizer_release.json`, `formalizer_reviews.json`, согласованная `ah_memory.json`, свежий журнал, `gui.toml` и `fixture_manifest.json`. Это те же явно маркированные `TEST_ONLY / ORACLE_FIXTURE_ONLY` ресурсы, что использует языковой runner. GUI показывает этот статус. Исходный конфиг, обычная память и production-ресурсы не изменяются. Существующий каталог назначения отклоняется; для новой сессии выберите новый путь.

Не переносите только два JSON в существующую память: ссылки на T и AH-снимок должны совпадать. Подготовленный профиль — ограниченный тестовый словарь и стенд для ручного ввода; полный корпус архитектуры запускается командами runner ниже, с собственными фикстурами для каждого случая. G0–G5 и production-покрытие этим профилем не подтверждаются.

При запуске обычного GUI без этих ресурсов окно теперь открывается, показывает `RESOURCE_MISSING` и точные пути/команду подготовки. Формализация и ingestion недоступны до корректной настройки. Остальные production-входы сохраняют строгий отказ; скрытого legacy fallback нет.

## LM Studio

Загрузите модель, включите OpenAI-compatible server и укажите **точный идентификатор загруженной модели**. Каждый вызов самодостаточен: история диалога в запрос не добавляется. Параметры генерации фиксируются; temperature=0 не считается доказательством детерминизма модели.

Сначала небольшой языковой кейс:

```powershell
python tools/run_formalizer_v7_oracle.py --provider lmstudio --base-url http://127.0.0.1:1234 --model "ИМЯ_ЗАГРУЖЕННОЙ_МОДЕЛИ" --case LANG-00-0-bare --out artifacts/oracle/lmstudio-smoke
```

Затем весь корпус, включая компонентные и журнальные проверки:

```powershell
python tools/run_formalizer_v7_oracle.py --provider lmstudio --base-url http://127.0.0.1:1234 --model "ИМЯ_ЗАГРУЖЕННОЙ_МОДЕЛИ" --timeout 120 --max-tokens 4096 --out artifacts/oracle/lmstudio-full
```

Для Ollama с OpenAI-compatible endpoint используйте `--provider openai --base-url http://127.0.0.1:11434 --model "имя-модели"`. Если сервер требует авторизацию, задайте `FORMALIZER_ORACLE_API_KEY` в окружении. Ключ не включается в run config или отчёт.

Каждый прогон требует **новый, пустой** каталог `--out`. Повторный запуск не подмешивает старые ответы другой модели. Отсутствующая предпосылка исполнения получает BLOCKED; исполняемые расхождения и исключения — FAIL. Обход валидаторов и подстановка правильного ответа из gold отсутствуют.

## Фильтры и запуск без модели

```powershell
python tools/run_formalizer_v7_oracle.py --out unused --list --tier pipeline
python tools/run_formalizer_v7_oracle.py --out unused --list --mechanism goal_decision
python tools/run_formalizer_v7_oracle.py --provider disabled --acceptance A39 --out artifacts/oracle/a39
python tools/run_formalizer_v7_oracle.py --provider disabled --dry-run DR30 --out artifacts/oracle/dr30
python tools/run_formalizer_v7_oracle.py --provider disabled --out artifacts/oracle/components
```

`--case`, `--tier`, `--mechanism`, `--acceptance`, `--dry-run` можно повторять. `--list` ничего не записывает и не вызывает провайдера. При `disabled` **643 кейса с raw-text формализацией** отмечаются `BLOCKED_LOCAL_PROVIDER_DISABLED` (640 pipeline + 3 component); остальные компоненты исполняются. Для проверки языка нужен live-провайдер. Весь корпус включает и эти языковые кейсы, и детерминированные механические проверки; модель не подменяет коммит, вывод, отзыв или recovery.

## Точное повторение ответов провайдера

```powershell
python tools/run_formalizer_v7_oracle.py --provider replay --replay-from artifacts/oracle/lmstudio-full --out artifacts/oracle/replay-full
```

Replay без фильтров повторяет ровно выбранные кейсы исходного прогона. Можно дополнительно сузить выборку; расширение за пределы исходной выборки отклоняется до записи. Replay использует сохранённые PENDING/RECEIVED и RunMarker. Транспорт не отправляет HTTP-запросы; отсутствие необходимых ответов не вызывает скрытого обращения к модели. Повтор запускает алгоритмы на новой AH, а не читает прошлые фактические checkpoints. Изменение хеша корпуса или исполнявшихся исходников блокирует такой replay.

## Артефакты результата

| Файл | Содержание |
|---|---|
| `comparison.json` | PASS/FAIL/BLOCKED каждого кейса, путь и шаг расхождения |
| `summary.json` | Итог, доступность всех действий, блокеры, исключения и пропуски экспорта |
| `issues.json` | FAIL с ожидаемым/фактическим значением и первичной классификацией причины |
| `runtime_coverage.json` | Покрытие по A, DR, механизму, действию и уровню |
| `bindings.json` | Реестр подключённых действий и результаты привязки кейсов |
| `actual.jsonl.gz` | Фактические checkpoints, UID/Ref-привязки и manifests |
| `cases/<case-hash>/journal.log` | Durable история провайдера, batch/goal и отзыва |
| `resources/` | Подписанные тестовые resource fixtures |
| `run_config.json`, `provenance.json` | Модель, параметры, входные/исходные хеши и воспроизводимость |

Полный `FormalizationState` и `InterpretationReport` сохранены в `runtime.ir/report` языкового checkpoint. `/assertions/ir` и `/assertions/journal` — **проекции допущенных утверждений**, а не весь parser IR. Канонические факты декодируются из фактических N/G и актантов.

Коды завершения: `0` — все выбранные кейсы прошли; `1` — есть FAIL; `3` — нет FAIL, но есть BLOCKED. Сам exit code pytest не заменяет этот статус.

## Границы доказательства

Измеренный прогон всех 2542 кейсов без модели: **1872 PASS / 27 FAIL / 643 BLOCKED**, 0 исключений исполнения, 0 отсутствующих путей наблюдения. Полный список расхождений: [снимок всех привязок](formalizer_v7_complete_bindings_run/README.md). Старый 83-action снимок сохранён [отдельно](formalizer_v7_extended_run/README.md) как исторический результат.

- Все 126 типов действий привязаны. У каждого исполненного кейса сохранены реальные API, Ref/UID, хеши и уровень исполнения. Наличие binding не равно PASS проверки.
- `issues.json` различает исключения исполнения, недостающий экспорт, некорректный исходный стимул и прочее несовпадение с gold. Это первичная классификация, а не автоматическое признание ошибки production-кода. Все ожидаемые и фактические значения сохраняются.
- Resource fixtures имеют публичный ключ `TEST_ONLY` и атрибуцию `ORACLE_FIXTURE_ONLY`; это не reviewed production release и не оценка реального лексического покрытия. TemplateMap проверяется на T подготовленной AH. Явные identity bindings заданы фикстурой; production linking по совпадению имён не включается.
- В исходном корпусе выявлены 27 некорректных/недостаточных стимулов: 15 DSL-кейсов с невалидным baseline, 10 изменений rule/conclusion без второго лицензированного доказательства, 2 OPEN-key мутации, не соответствующие объявленной сигнатуре. Runner исполняет предоставленные данные, сохраняет фактический отказ и отмечает их FAIL; отрицательный отказ на более ранней границе не засчитывается за проверку нужной мутации. Точные case ID и причины приведены в отчёте. Gold и архитектура не изменяются.
- Crash точки моделируются на durable API-границах с последующим восстановлением AH, включая marker+COMMIT_DECISION, GOAL_DECISION, bulk migration и каскад. Принудительное завершение процесса ОС этим runner не доказано.
- Реальный HTTP и offline replay проверены с локальным сервером независимо заданных ответов, включая CLI и сохранение исходной выборки. Качество вашей модели можно оценить только live-прогоном на ней.
- Изменение исполняемых исходников во время прогона делает отчёт FAIL. Replay требует совпадения хешей корпуса и исходников; API-ключ не сохраняется в артефактах.
- `coverage_report` считает фактические категории отдельно от surface-only хранения; `G5=false / NOT_EVALUATED` означает отсутствие reviewed evidence для ворот, а не измеренное низкое качество модели.
- G0–G5 этим инструментом не переводятся в PASS. Исходные данные и ожидаемые ответы не исправляются ради зелёного результата.

Старый 16-action компонентный runner и его опубликованный снимок остаются отдельным воспроизводимым результатом: [инструкция](FORMALIZER_V7_ORACLE_INTEGRATION.md). Для текущего локального запуска используйте команды этого документа.
