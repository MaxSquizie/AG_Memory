# F05 P04 — чтения оснований и кеш

Статус: **ACCEPT P04, 2026-11-01**, тот же судья `/root/f05_coordinator`.
Судья отдельно выполнил nested-provider контраст: 1 passed, 0.45 с.
Это покрытие объявленных механизмов чтения оснований, не полнота естественного языка.

## Контракт общего контура

`dispatch_evidence.KINDS` — закрытый реестр (18 kinds). `valid` повторяет
проверку исполнителя. `Dispatcher.evidence_valid` и `dispatch_history.valid`
используют один валидатор; историческая проверка не требует активной сессии.
Последняя дополнительно раскрывает hard/soft provider DAG и передаёт результаты
родителей в проверку импортов. Запись `expected=False` — полноценное обязательство.

`observation_address` различает адресованный запрос и точное свидетельство.
Для прямых READING_QUERY / CONSTRAINT_SET / RECOVERY_QUERY меняется результат
`signature`, а адрес остаётся прежним. Для INVENTORY_QUERY signature — часть
адреса входа, поэтому сохраняется. Последнее прямое чтение такого же запроса
замещает предыдущее. Точные свидетельства сохраняют и value, и expected;
несовместимые оценки нельзя молча заменить удобной поздней оценкой.

`producer_reads.capture` сохраняет успешные корневые задачи и их замыкания.
Кешированные дочерние чтения остаются отдельными замороженными обязательствами:
их обход не перезаписывает более позднее прямое чтение. Отклонённая попытка
очищается явно. `discard_reads` удаляет только зависимости названных проб,
как в активной задаче, так и в замороженном capture.

Общий `read_record` сохраняет `probe_refs` **в момент чтения**, вне value/address.
При discard `read_probe_refs` берёт объединение сохранённых и точных текущих
зависимостей: замена A→B не стирает старую A, а публикация recovery может добавить
новую зависимость к продолжающему быть живым ORIGINAL. Повторное exact чтение
накапливает ancestry; повторный прямой query сохраняет последний snapshot.
Legacy-записи без probe_refs используют текущий обход. Извлечение не вызывается
во время evidence validation и без активной задачи/capture. Recovery query
использует один exact declaration selector в inspect и refs, поэтому другая
декларация того же токена не попадает в его зависимости.

`evidence_ancestry.collect` итеративно раскрывает completion DAG импортированных
производителей. Для адресного отзыва нужна точная использованная revision,
включая уже отозванную: происхождение устаревшего результата не исчезает из-за
отзыва. Это **не** разрешение пользоваться старой revision: runtime/history
продолжают проверять актуальную живость. Циклы обхода ancestry ограничены seen.

## Матрица наблюдений

Общие capture/cache-hit replay и runtime/history пути выше применяются ко всем
строкам. В колонке refs перечислены основания для адресного discard; отсутствие
выбора тоже сохраняется и повторно проверяется. G означает использование
read-only validation_graph; остальные проверки не интернируются в его overlay.

| Kind | Исполнитель и повторная проверка (`valid`) | Исторический путь | refs / адресный отзыв | Capture / replay | Evidence view |
|---|---|---|---|---|---|
| MORPHOLOGY_PROVENANCE | morphology_provenance.live / _live | общий + provider_results | точная трансформация, родители, условия, import provider DAG | exact | ledger + source + signed rows; внутренние proofs G |
| MORPHOLOGY_ORIGINAL | original / _original | общий | публикации исходного вхождения и их ancestry | exact | source/manifest/resource + публикации |
| READING_QUERY | observe_query / query_snapshot | общий | те же query_rows, полная morphology ancestry | addressed query | текущие строки по token/reading/scope |
| READING_USE | assessment / evaluate | общий + transfer provider_results | witness, parent proofs, condition, transfer/restriction/provider DAG | exact | frozen witness + текущие selection/import основания |
| READING_DECISION | selected, receipt_live / inspect | общий | key, condition и selected proof prerequisites | exact | decisions/probe record/source/condition |
| BUNDLE_CONSTRAINTS | inspect_bundle / bundle_constraints.inspect | общий | selected role/domain requirements, required inventories, condition | exact | адресованные rows + frames; внутренние proofs G |
| READING_DOMAIN | partial_readings.valid_domain / validate DOMAIN | общий | domain/pages/prerequisites/conditions | exact | G |
| STRUCTURAL_FOREST | structural_forest.live / validate FOREST | общий | membership domain и ancestry | exact | G |
| PARTITION_EXCLUSION | partition_exclusions.live | общий | domain/pages/candidate condition | exact | G |
| CONDITIONAL_PROOF | licensed_in_scope и explicit conditional callers / _licensed | общий | proof/domain/selected task prerequisites + condition | exact | G; None означает безусловную область |
| REFINEMENT_HOST | refinement_host_proof.live | общий | собственный decision + premises ancestry | exact, true/false | fingerprint/source/version + proofs G |
| CONSTRAINT_SET | observe_constraints / constraint_signature | общий | region/scope roles/domains/hosts/condition | addressed query | текущий адресованный набор + liveness |
| PROOF | structural_tasks.licensed / licensed | общий | decision/domain и prerequisites selected STRUCTURAL_TASK и TASK_DOMAIN | exact, true/false | G |
| INVENTORY_QUERY | function_inventory.current / matching live receipt | общий | matching inventory proofs + condition | addressed query | inventory address/signature + current units/proofs |
| INVENTORY | current/frame_live / latest receipt live | общий | inventory proofs + condition | exact, true/false | receipt/current units/source/proofs |
| INVENTORY_UNIT | unit_live / _unit_live | общий | inventory proofs + condition | exact unit, true/false | exact unit hash + current inventory membership |
| NOMINAL_HOST | component_constraints.host_live | общий | decision | exact, true/false | fingerprint/source/selected |
| RECOVERY_QUERY | recovery_constraints.wording / inspect+signature | общий | recovery record ancestry + condition | addressed query | exact token set + recovery declaration + matched rows/liveness |

## Исправленные причины

1. Отрицательные owner/unit проверки не подписывали отсутствие разрешения.
   Кешированный отказ поэтому переживал восстановление основания. Проверяется
   весь предикат, а не только существование inventory ref.
2. CONDITIONAL_PROOF с condition=None при повторной проверке отвергался, хотя
   исполнитель проверял его как безусловное доказательство.
3. Адресный отзыв терял prerequisites выбранного STRUCTURAL_TASK, refinement
   premises, derived query ancestry и import provider parents. Все эти основания
   реально читаются валидаторами, поэтому их обход необходим независимо от текста.
4. Несколько прямых snapshots одного запроса ошибочно становились одновременными
   требованиями. Теперь общий диспетчер и capture используют одинаковый адрес.
5. Общий capture раньше восстанавливал зависимости только из текущего состояния.
   Теперь сохраняется consumed ancestry и учитывается current replay ancestry.
6. `question` мог продолжать утверждать выбранное восстановление после отзыва
   выбора. Recovery wording теперь получает только проверенную проекцию; новый
   RECOVERY_QUERY подписывает также отсутствие recovery и его последующее появление.

## Evidence-view identity

Судья повторно прошёл текущие expand-валидаторы PROOF, EXCLUSION, DOMAIN, FOREST,
CONDITION, SHELL. Новая коллизия не подтверждена. Identity различает decisions,
probe records, latest TASK_DOMAIN, оба порядка lookup STRUCTURAL_TASK, retirement,
морфологический ledger и подписанные строки. Source/context/registry наследуются
от неизменяемого base state. Условие применимости: read-only scope, без мутации
base/payload/уже хешированных объектов. Добавление нового graph validator требует
повторного аудита его чтений. Inventory/recovery/bundle не добавлены в graph.

## Проверки и границы доказательства

- `test_dispatch_evidence_contract.py`: безусловное proof replay; owner false→true;
  exact unit missing→complete→mutation; query empty→populated; sibling isolation;
  runtime/history parity; exact false/true obligations; registry; recovery revoke
  без изменения token; ancestry DAG глубиной 1100; exact query selector, старый
  snapshot после A→B, новая publication dependency и repeated exact ancestry.
- `test_reading_producer_families.py`: реальный OOV import, независимая проба только
  в provider ancestor; runtime и frozen cache discard обоих aggregate kinds.
- Существующие producer_reads, morphology provenance, validation_graph покрывают
  frozen replay, abandon, nested discard, source/ledger mutation, scoped use,
  imports и различение evidence views.

Это проверки реализации и сценарных ответов, не испытание качества локальной LLM.
Конкретный GUI маршрут «на столе стоит арбуз» ещё не исправлен: его причина — раннее
принятие границы служебной части и отсутствие пересмотра при невозможности выбрать
голову. Это P06/P08, а не доказательство нарушения cache-контракта P04.

При расширенном запуске обнаружены 5 падающих старых проверок
`test_composition_dispatcher.py`; те же 5 воспроизведены на чистом HEAD eda7d85:
три используют недекларированный `_probe` slot `test`, одна fixture без sha256,
одна сценарная очередь не допускает structural_revision. Их ожидаемые результаты
не менялись ради зелёного отчёта. Отдельный план обновления таких ресурсов остаётся
вне утверждения о прохождении адресованного набора P04.

## Результат проверки реализации

- Полный целевой набор перед последней правкой вложенного ancestry: **94 passed,
  25.44 с** (семь файлов, перечисленных выше).
- После переключения provider completion на общий frozen∪current helper:
  **26 passed, 5.80 с**, включая новый nested-provider frozen A/current B контраст
  и реальные OOV import adapters. Общий набор содержит теперь 95 случаев;
  утверждается именно выполненная комбинация проверок, не повторный полный run.
- `check_dispatch_evidence.py`: PASS. В fixture добавлен area_inputs=None,
  обязательный атрибут действующего runtime; ожидаемая семантика не менялась.
- `check_inventory_lifecycle.py`: PASS.
- `check_oov_inheritance.py`: PASS до и после общего freeze-at-read; сохранение
  occurrence domains при спуске, local revision без повторного OOV запроса,
  отзыв родителя достигает ребёнка. Это сценарный selector, не живой ответ модели.
- `git diff --check`: PASS.

Состояние baseline-ресурсов и GUI boundary regression явно отделены выше.
Performance длинных цепочек и последующие P05–P20 этим этапом не закрыты.
