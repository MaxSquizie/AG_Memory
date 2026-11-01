# F05 P02 — witnesses всех reading-use producers

Дата: 2026-11-01. Статус: ACCEPT тем же судьёй /root/f05_coordinator.
Финальный focused suite: 69 passed, 11.84 s; пять recovery scenarios PASS.
Область: семь адаптеров P02 и два producer partial-reading domains.
Capabilities: C-READINGS, C-GROUNDS, C-OOV, C-HISTORY, C-ROLES.
P03/P04 и F05 в целом остаются OPEN.

## Причина и общий контракт

Старый selected Decision подтверждал ответ, но не доказывал, что выбранный
payload разрешает конкретное употребление целого чтения. Вне OOV function_use
вообще разрешал такое употребление без проверки соответствия payload.

Теперь producer формирует reading_uses ДО выбора. Binding содержит occurrence,
source range, полное чтение, тип употребления, region/input scope, condition,
source revision и resource version. Общий issuer извлекает именно выбранный
payload, строит P01 witness и требует SELECTED_USE. Старый вызов license_use без
witness отвергается; единственный production callsite — общий issuer.

Для raw component probes payload contract включён в проверяемый signature
preimage исходного вызова. Повторный захват изменённого packet не создаёт новую
лицензию. Для paged selections сохраняется task/domain/page basis. Исторический
адрес без родительского контракта имеет явный NO_PARENT идентификатор области.

## Покрытые переходы

| Producer | Что связывается до выбора | Повторные/частичные пути |
|---|---|---|
| component_predication | bundle → frame → occurrence reading и роль | retained bundles не лицензируются; singleton без новой пробы не переиспользует старый список options |
| composition_children | frame_refs, child contract, reading внутри output | ранний единственный root не выдаёт нового основания; unresolved выбор сохраняется |
| component_dependency_reduction | morph/head_morph, ROOT role либо host/layer, predicate | proposed singleton требует выбора; несколько словарных ROOT readings сохраняются как домен |
| quantifier_composition | head/whole reading, binder slot, marker refs, operator/role и четыре parent proofs | все выбранные uses проверяются до изменения body frames |
| nominal_functions | RELATION→PREP и shared nominal→NOUN с head/function refs | точная проекция из head payload; неизвестные признаки не дополняются |
| qualitative_quantity | внутреннее noun reading, quantity refs; отдельно внешний case/NUMR projection | resolve и general_groups; genitive внутреннего head не заменяется nominative внешнего group |
| contextual_oov | feature-unknown whole reading конкретного POS и occurrence | singleton, несколько POS, inherited parent proof, повторная локальная ревизия |

Синтетический binder Decision/Ground D удалён. Его заменяет существующая
адресная проба с типизированными structural/head/partition/kind proofs.
Детерминированная оптимизация прежнего пути не сохранена и не заявляется.
Это может добавить один запрос для singleton binder. Отзыв каждого parent
проверяется независимо от сохранности выбранного binder.

Оба partial-domain producer (predicate_functions и dependency reduction)
передают typed bindings. retain сохраняет SELECTED_DOMAIN witnesses с правом
DOMAIN_MEMBERSHIP, которое не повышается до SELECTED_USE.

## Область, перенос и кеш

Runtime употребление проверяет текущие input scope/region/condition.
Перенос между областями разрешён только отдельным OOV_POS правилом через
существующий MORPHOLOGY_FUNCTION_IMPORT. Перенос фиксирует исходный restriction
и import, не переписывает выбранное чтение под новую область.

Historical transfer проверяется без активной session. dispatch_history обходит
completion DAG итеративно, проверяет revisions, evidence_reads и probe stamps.
Изменение основания родителя обнаруживается и до явного invalidate.
Runtime subscription выполняется отдельно от historical validator.

Успешные и неуспешные strict assessments наблюдаются как READING_USE.
Отрицательный поиск — как адресованный READING_QUERY. Lookup, query snapshot и
refs для discard используют общий selector, включая доступные imported uses.
Равные повторные trace rows не считаются новым основанием: иначе повторный
импорт сам сбрасывал кеш и порождал цикл повторных вычислений.
Это покрытие новых зависимостей P02, а не завершение полного аудита кешей P04.

## Проверки и границы доказательства

Focused suite: 69 checks в test_reading_witnesses, test_derived_reading_liveness,
test_reading_producers, test_reading_producer_families.

- Actual producer paths всех семи семейств: wrong token, whole reading,
  role/head/use, branch и retirement. Для bundle предшествующий build_clause
  выдаёт подготовленные frames; сам dispatcher/probe/issuer настоящий.
- Raw packet recapture после подмены роли отвергается.
- Cached отсутствие → выдача exact use → true; отзыв → false.
- Actual parent/child morphology prepare: импортированное основание проверяется
  вне session; удаление import и ленивый отзыв независимого ancestor evidence
  без invalidate делают его недействительным.
- Structural binder: четыре настоящих choose proofs; отзыв и supersession
  каждого из них при прежнем выбранном binder; strict/cache false;
  независимый cached proof не пересчитывается.
- Singleton/multiple сохраняют разные полномочия; существующие P01 branch
  и source/address контрасты сохранены.

Пять recovery scenarios: check_oov_contracts, check_oov_inheritance,
check_f05_quantifier_readings, check_partial_readings, check_nominal_probe_chain.
В inheritance обновлён сценарный ответ на structural_group_next: 0 явно
завершает группу, без него сценарий не доходил до проверяемого дочернего пути.
Partial scenario проверяет наличие witnesses обоих producers и запрет записи.

Это статические и сценарные проверки настоящего кода с контролируемыми
ответами. Живого вызова Luna/локальной модели и нового сквозного доказательства
корректной записи произвольных сложных предложений здесь нет. Исходные 19 failures
P00 не объявляются исправленными. Неизменяемость всех morphology sources,
полный обход late consumers и полный аудит кешей остаются в P03/P04.
