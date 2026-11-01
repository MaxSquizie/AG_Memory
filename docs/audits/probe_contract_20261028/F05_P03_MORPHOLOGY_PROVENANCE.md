# F05 / P03 — provenance преобразований и потребители морфологии

Статус: **ACCEPT P03** — принят тем же координатором /root/f05_coordinator после повторных review.
Координатор проверял код и отдельные контрасты самостоятельно; полные прогоны принял
по отчёту основного агента.
P04, P20-validation и весь F05 этим документом не закрываются.

## Причина и место исправления

Decision receipt фиксирует ответ, но не доказывает сохранность преобразования,
которое использовало ответ. Ранее изменение trace row или подмена опубликованного
reading в token.variants могли менять attestation без изменения decision stamp.
Исходное reading, предложенное преобразование, выбранное использование и разрешение
на запись теперь проверяются отдельно.

Capture выполняется на границе T1, до overlays. Для native SRL сохраняется manifest
действительного MorphProvider: версия pymorphy3 и dictionary.meta, отдельно от semantic
release. Внешний adapter без provenance имеет явную DECLARED_SOURCE_ADAPTER authority;
класс такого adapter не изображает доказанную версию словаря. Исходные readings,
вхождение, диапазон, текст, source revision и manifest фиксируются отдельно от token,
который позднее может получить опубликованное исправление.

Issue выполняется производителем после сборки полного результата: source inputs,
полный output, resource, interpretation version и condition входят в неизменяемую
JSON-запись. Потребитель не может получить новый witness простым перечитыванием
изменённой trace row. Проверяются наличие исходной строки, содержимое записи,
живость sources и typed родителей. Только score у reading/token исключается из
лингвистической идентичности; вложенные parent refs и остальные признаки сохраняются.

## Производители

| Семейство | Точка выпуска и проверка |
|---|---|
| ORIGINAL DICTIONARY / DECLARED / NONLEXICAL | T1 capture; original сравнивает полное чтение и source header/manifest. NONLEXICAL остаётся исходной пунктуационной/неязыковой записью, не получает роль существительного |
| PREDICTED | Не допускается в captured source variants; morph_guesses остаются отдельно |
| MORPHOLOGY_PROPOSAL | offer: addressed original inputs + фактический input_token; parent_inputs проверяет живость входных derived readings |
| MORPHOLOGY_DOMAIN | contextual_substantives: исходные variants, предложения, task scope; исходное ADJF не заменяется гипотезой NOUN |
| MORPHOLOGY_USE | license_use: frozen row плюс P01/P02 payload witness; наличие предложения не заменяет выбранное употребление |
| MORPHOLOGY_FUNCTION_RESTRICTION | contextual_oov: addressed domain; valid_domain сохраняет альтернативность и происхождение |
| MORPHOLOGY_FUNCTION_IMPORT | composition_morphology: source restriction + parent task/revision; проверяется исторический provider, а не одно совпадение POS |
| MORPHOLOGY_DOMAIN_RESTRICTION | Production writer в текущем контуре отсутствует. Неподписанные legacy rows не отсекают варианты; подписанному adapter нужен selection receipt |
| AGREEMENT_RECOVERY | Полные replacement options перед пробой; результат связан с frozen receipt, head, rule и точной реконструкцией recovered reading |
| MORPHOLOGY_PUBLICATION | Отдельная запись final выбранного исправления; legacy whole-document route тоже выпускает publication. Проверяется родитель recovery, original не заменяется recovered |
| QUANTITY_COMPOSITION | Оба пути qualitative_quantity: internal readings, marker inputs, internal_by_case, external cases, receipt и structural parent proofs |
| NOMINAL_FUNCTION / NOMINAL_REFERENCE_GROUP | Полный output, исходные внутренние чтения и proofs. MARK-проекция восстанавливается из исходного reading, не принимается по одному feature |

## Typed locations и consumers

`reading_locations.locations` — единый обход, используемый и producer bindings, и
проверкой потребителей. Collections сохраняют право рассматриваться как кандидаты;
они не получают фиктивное scalar selected-use.

| Location / route | Проверка |
|---|---|
| morph_bindings, pp_readings | Полное reading; для proposed selected use — адрес, frame, role, predicate и location context |
| nominal_dependencies, attribute_constraints | morph и host_morph; attachment kind/host/layer/case |
| dependency_evidence | Оба конца материализованной зависимости; prepare_candidate также проверяет host |
| group_readings | selected_head_reading и external_reading |
| qualitative_groups | internal_readings, marker_variants, internal_by_case как collections; selected_head/external как selected; неизменность producer group и разрешённая condition |
| control_binding | Чтения каждого member и вложенные qualitative_groups; alias проверяется против родителя; поиск основания идёт итеративно по цепочке control |
| quantifier_restriction | selected_reading и binding slot/marker address; существующий quantifier licensed gate сохраняется |
| Relative marker | Хранится в morph_bindings; существующий relative binding validator сохраняет владельца/роль |
| description_heads / attach_groups | Проверка исходных readings/groups перед дальнейшей сборкой; оба production callers передают state |
| nominal_apposition / dependency materialization | Проверка зависимого и host reading до использования признаков |
| native_frontend → _bindings | Gate до lexical role projection; ошибка основания не маскируется COMPUTATION_LIMIT |
| composition_tree / partial_composition | Проверяется выбранный набор; PARTIAL сохраняет domain membership, не становится scalar use или разрешением записи |
| lexical_issuance.assess | Проверка в восстановленном packet с явной condition; незакрытое основание добавляет obligation |
| structural_seal / native_plan | Повторная проверка перед seal и при построении node; отзыв после seal блокирует операции записи |

Temporary synthetic host из refinement_group_hosts не является persisted reading:
его consumer раскрывает исходных members, которые попадают в обычные typed locations.
Неиспользуемый prefix-descriptions helper также требует state; production residual
route проверен отдельно. Новая typed location требует явного getter/validator;
рекурсивный поиск произвольных dict не заменяет контракт.

## Сохранённые результаты и зависимости

Shell/lexical packets содержат morphology_records. Оба read-only overlays добавляют
отсутствующие records, сохраняя приоритет текущего состояния. View identity включает
и records, и signed trace rows: packet без producer row не переиспользует успешный view.
Resume синхронизирует текущие records; generation snapshot переносит их, но не
переподписывает под новый source/version. Несовпадение основания остаётся stale.

Historical liveness не разрешает unconditional use. Каждая condition проверяется;
available/attested/validate_uses имеют явный condition argument для historical consumer.
Текущая ветка используется только как default у исполняющего producer, а не как
скрытое основание сохранённого результата.

Две новые external observations: MORPHOLOGY_ORIGINAL и MORPHOLOGY_PROVENANCE.
Отрицательный available оставляет addressed READING_QUERY, включая substantive domain.
Адресный discard раскрывает derived родителей, compact conditions, structural proofs,
import ancestry и публикацию recovery. Import-parent tasks включены в soft edges
completion DAG; готовая provider_results map передаётся через оба read маршрута
(MORPHOLOGY_PROVENANCE и READING_USE transfer), без повторного рекурсивного обхода.
Идентичность временной map не является семантическим cache key. Это интеграция новых reads; полный аудит кешей
по остальному контуру остаётся P04.

Цепочка преобразований проверяется trampoline с request-local memo и явным стеком:
длина не ограничивается recursion limit Python; циклы не подтверждают сами себя.
Control transfer также использует итеративный обход. Memo не переживает проверку и
не скрывает последующее изменение state.

## Проверки и границы доказательства

- tests/test_morphology_provenance.py: mutation source/output/resource/header,
  сохранение score, отзыв recovery до/после публикации, derived parent revoke,
  packets и overlay collision, conditional availability/group, exact read dependencies,
  negative cache repair, typed locations, sealed→planner revocation, длинные цепочки.
- tests/test_derived_reading_liveness.py: четыре семейства и два события отзыва;
  fixtures актуализированы под issued records, без ослабления ожидаемого отзыва.
- P01/P02 producer/witness suites и seal tests: обратная совместимость контрактов.
- Recovery scripts: OOV contract, import/revision, nominal chain, binder readings,
  native PARTIAL без записи. Offline PARTIAL fixture гидратирует TokenEvidence;
  ожидания семантики не изменены.
- tests/test_lexical_issuance.py: conditional/historical producer contour.

Это статические, контрактные и сценарные проверки. Живые вызовы модели в P03 не
проводились; результаты не доказывают качество Luna или локальной модели и не
обещают полноту естественного языка.

Итоговые проверки: 108 focused contracts/seal (включая 32 P03) PASS;
12 conditional lexical issuance PASS; после уточнения history-map интеграции
48 затронутых checks и отдельный contrast equivalent maps / provider retirement PASS.
Пять recovery сценариев PASS. Финальный inheritance после history-map изменения
PASS за 90,96 с; эта стоимость не объявляется устранённой (P04/performance OPEN).
Координатор повторно подтвердил ACCEPT после этой интеграции.
