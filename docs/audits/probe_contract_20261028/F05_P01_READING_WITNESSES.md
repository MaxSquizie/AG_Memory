# P01 — строгий контракт основания чтения

База: 87b253c. Capability IDs: C-READINGS, C-GROUNDS, C-OOV, C-HISTORY.
P20-contract: READ by stage T2_TP; доступное исходное чтение, допустимый член
домена и выбранное употребление имеют разные полномочия.

## Реализованный API

`src/ah/formalizer/reading_witnesses.py`:

- Address: source/revision/interpretation/text, region и occurrence set,
  input scope, resource version, condition, stage/profile. Исторический адрес
  передаётся явно; ambient session не используется.
- SourceSnapshot: неизменяемые сериализованные исходные DICTIONARY readings.
  Потребитель не обращается к текущим token.variants для доказательства ORIGINAL.
- Witness: ORIGINAL / DERIVED / SELECTED_DOMAIN, целое reading без score,
  use с точными role/owner полями, выбранный payload и proof/domain,
  замороженный actual task/domain basis, правило и ссылки на родителей.
- Assessment: SUPPORTED / UNKNOWN / STALE / CONFLICT; отдельное `permission`:
  AVAILABLE_READING / DOMAIN_MEMBERSHIP / SELECTED_USE / NONE. `supported` означает
  доказанность заявленного основания; только `selected_use` означает выбранное
  употребление. Ни kind=DERIVED, ни SUPPORTED отдельно не разрешают выбор.
- `historical` использует явный снимок/адрес, `validate` — безусловная публичная
  граница; conditional witness на ней отклоняется. Родительские зависимости
  обходятся явным стеком, отсутствие родителя не заменяется singleton.
- `morphology_domain.strict_use` — явная точка входа. Неуспех strict окончателен;
  вызова legacy function_use в ней нет.

Правила P01: SOURCE_DICTIONARY_V1 подтверждает только AVAILABLE_READING;
SELECTED_READING_USE_V1 требует точное типизированное употребление внутри
фактически выбранного payload либо подтверждённого domain member;
IDENTITY_FROM_PARENT_V1 переносит только то же чтение/адрес/use с тем же
полномочием. Любое другое преобразование даёт UNKNOWN/ADAPTER_MISSING.
Ресурсные и предметные преобразования семи семейств добавляются в P02,
с собственными проверяемыми premises; whitelist названий slot не доказательство.

`reading_uses` внутри payload содержит точные token_ref/source_range/reading/use/address.
Это часть payload, прошедшего существующую структурную пробу, а не post-hoc
утверждение потребителя. Дополнительно проверяются фактические TASK_DOMAIN и
STRUCTURAL_TASK, source basis, context version, scope, область и условие.
Совпадение payload hash без живого task/domain proof не принимается.

Для synthetic deterministic decision без task/domain grounds strict возвращает
UNKNOWN. Его будущий producer обязан предоставить typed parent derivation;
текст Ground D с упоминанием другого decision не является такой цепочкой.
Отсутствие исходного доказательства отличается от утраты уже сохранённого basis:
второе — STALE. Доказанное несовпадение чтения/use при живом proof — CONFLICT.

## Граница миграции (не закрыта этим коммитом)

| Producer family | Strict adapter сейчас | Владелец продолжения |
|---|---|---|
| component_predication | Не переведён; legacy license_use | P02 bundle/frame/occurrence payload |
| composition_children | Не переведён; legacy license_use | P02 child output/slot mapping |
| component_dependency_reduction | Не переведён; legacy license_use | P02 attachment morph/head_morph/role |
| quantifier_composition | Не переведён; synthetic основания остаются legacy | P02 typed head/partition/parent proof |
| nominal_functions | Не переведён; legacy function projections | P02 function/head/marker transformations |
| qualitative_quantity | Не переведён; legacy internal/external readings | P02 quantity/head/external-case separation |
| contextual_oov | Не переведён; существующий scoped POS guard сохранён | P02 POS domain/address → strict witness |

Общий разрешающий `function_use` вне OOV остаётся **известным legacy дефектом**
до P02, а не скрытым fallback нового API. P01 не объявляет исправленным весь
production маршрут. Existing reading_decisions остаётся проверкой lifecycle;
partial_readings и structural_tasks используются как основания, их success
сам по себе не становится reading-use permission.

SourceSnapshot получает original_evidence от доверенного source producer.
В P01 доказана неизменяемость снимка и независимость от overlay потребителя,
но не внедрение его выпуска во все исходные пути. P02/P03 должны выпускать его
до overlay/recovery, связывать с реальным resource/source manifest и не позволять
потребителю переиздавать «оригинал» из изменённых variants. Snapshot digest не
подменяет producer provenance. Durable восстановление/authority — P22.

Валидатор намеренно не кешируется и не подключён к кешируемым production consumers.
Его dependencies — аудитный перечень, **не** установленные dispatcher subscriptions.
P04 подключает positive/negative/empty observations; P03 — всех late consumers.
Ни эти пункты, ни F05 целиком здесь не закрываются.

## Проверка

`tests/test_reading_witnesses.py` использует реальный choose/choose_domain,
selection pages и validation graph, а не вручную подставленный successful proof.
Проверены чужое вхождение/range/whole reading/use/payload; source/resource/revision;
смена task input scope/area/condition при неизменном payload; recapture изменённого
basis; synthetic singleton; отсутствие/отзыв parent; 1100 родительских переносов;
неизменяемость snapshot и запрет recovered-as-original; membership без scalar
permission; отсутствие legacy fallback.

Conditional контрасты строят реальные select_relation → forest → branch →
choose/choose_domain: historical success вне session, отказ public/sibling и
невозможность переносом Address превратить sibling proof в собственный.

Это scripted контрактные проверки. Они не измеряют качество Luna/локальной модели,
не являются сквозной формализацией примеров и не доказывают готовность записи.
Existing `test_derived_reading_liveness.py` отдельно проверяет, что введение
нового API не изменило поведение ещё не переведённых legacy семейств.

Последний целевой прогон: **51 passed in 11.54s** (36 strict + 15 legacy).
Команда: `PYTHONPATH=.:src:tests:/workspace/scratch/cbcb79b8cb00/ag_memory_deps
python -m pytest -q tests/test_reading_witnesses.py tests/test_derived_reading_liveness.py`.
Проверяется также согласованность actual domain/page execution_basis и branch
с raw replay ownership. Повторное снятие snapshot после изменения одной страницы
не превращает противоречивое основание в валидное.

## Приёмка

2026-11-01, `/root/f05_coordinator`: **ACCEPT — узкий P01**. Судья независимо
повторил 36 strict проверок (36 passed, 11.08s). Принят общий строгий API;
P02/P03/P04, P20-validation и все шесть блоков F05 остаются OPEN.
