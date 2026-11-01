# F05: покрытие заявленных механизмов, 2026-11-01

**Передача оснований чтений: OPEN. Зависимости кеша: OPEN. Все шесть блоков F05: OPEN.**
Единица закрытия — заявленная архитектурная механика через всех производителей,
потребителей, ветви, кеши и отзыв. Полнота естественного языка не требуется.
L3-S и прежние этапы — контрольные точки реализации, не закрытые механики.

Нормативная основа: FORMALIZER_ARCHITECTURE_V7.md, требования к whole readings,
основаниям O/C/R/D/M/A/P/W, R-X по стадиям, dispatcher, seal и пересмотру.
Ни return, ни singleton, ни отсутствие diagnostics не доказывают готовность.

## Карта границ проверки

Пути далее относительно src/ah/formalizer. Вся таблица имеет статус OPEN;
перечисление файла не означает, что все его исполнения проверены.

| Семейство | Производители / передача | Потребители / продолжение | Что требуется проверить по всей цепочке |
|---|---|---|---|
| Исходная морфология, OOV | morph_evidence, contextual_oov, morphology_domain | grammar/component, nominal_readings, seal | исходное свидетельство отдельно от предложения и лицензированного употребления |
| Роль и whole reading | predicate_functions, component_dependency_reduction, partial_readings | bundle_constraints, component_predication, source union | singleton/multiple, все uses, собственное основание reading |
| Именные зависимости | phrase_readings, component_phrases, component_nominal_tree | nominal_apposition, nominal_host_question, parent slots | граница, хозяин, чтение, зависимый пересмотр |
| Производные чтения | contextual_substantives/agreement/name_case/preposition_case, qualitative_quantity | morphology_domain, nominal_readings, composition_tree | точное преобразование и его основания; отсутствие обхода через token.variants |
| Инвентари функций | nominal_functions, temporal_functions, function_inventory | grammar/component, historical assess | положительное membership, пустота, завершение, scope, отзыв unit |
| REFERENCE / QUANTITY | nominal_reference_groups, qualitative_quantity | lexical_units, qualitative_group_entity | head/function occurrences, identity, внутреннее чтение и внешний падеж |
| Предлоги / пространство | nominal_functions, contextual_preposition_case | PP attachment, spatial_references, spatial_plan | source/head/government/owner/anchor как отдельные основания |
| Координация / общий материал | nominal_coordination_source, partition_sequences, shared_proposition_material | relation_composition, shells/frontier | границы, NEXT, ownership, альтернативы, отзыв suffix |
| Владельцы / relative | relative_composition, relative_pronoun, refinement_host_proof/path | nominal_usage, parent/child, native | единый выбранный host и зависимые readings |
| Control / неявные участники | component_infinitives, control_arguments, action_descriptions | parent/body slots, implicit_plan | governor reading, control и identity раздельны |
| Содержание / scope | content_sources, relation_composition, scope_assignment | child requests, native_scope, source_assertions | owner/modus/scope; вложенность не создаёт truth-support |
| Кванторы | relation_quantifiers, quantifier_composition | restriction/body, bound_references, native | binder/head/body/uses; машинно проверяемое производное основание |
| Референты / группы | nominal_reference_domain/pages/local/memory, nominal_group_source | chain/binding/plan | альтернативные пути, exact targets, independent supports |
| Время | temporal_functions, component_temporal_scope, document_scopes | temporal constraints/adapters | source/owner, unknown bounds, nested content time |
| Источники / bundles | grammar_domains, composition_sources, lexical_component | source_union, structural_lexical, lexical_issuance | точный output и obligations; полнота каждого источника отдельно |
| Forest / resume | structural_forest/shells, lexical_demands | frontier, windows, partial_composition | сохранение остатка и условные producers, child scheduling |
| Seal / запись / отзыв | seal, native_frontend, планы | canonical_ledger, commit_stage, retraction, t6b_revision | актуальность оснований до записи, независимые пути, весь assertion set |

## Кеши — отдельные обязанности, не одно слово «кеш»

| Семейство | Реализация | Обязательство и текущая граница |
|---|---|---|
| Probe replay | component_probe, component_probe_replay, selection_domains | payload/input/branch, страницы, premises; raw и paged paths |
| Runtime memo | composition_dispatcher, dispatch_evidence | положительные и отрицательные чтения, пустые queries, cached child closure |
| Source reads | producer_reads, lexical_issuance | точные ревизии, successful attempt, адресный discard |
| Historical memo | validation_graph, structural_conditions | все читаемые виды evidence в identity; без ambient branch |
| Memory context | attention_context, context_receipts | originating reader, frozen memory/release, WAL projection; без replay side effects |
| Resume/windows | composition_tasks, structural_frontier | typed inputs, feedback, morphology/context, незавершённый остаток |
| Отрицательные основания | partition_exclusions, partition_domain | exact rejected combination, актуальное доказательство отказа |
| R-X опыт | rx_cache, t6_core, t6b_revision | stage isolation, COMMITTED support, supersession; не truth-ground |

## Подтверждённые дефекты и сделанный объём

1. **Отзыв производного чтения.** morphology_domain и nominal_readings читали
   Decision.selected, не учитывая DEPENDENCY_REJECTED / COMPOSITION_PROBE_SUPERSEDED.
   Добавлен общий reading_decisions: отзыв, superseded record, branch permission,
   structural proof, decision/source stamp. MORPHOLOGY_USE хранит receipt; его
   замена не лицензирует старое употребление. Это проверка жизнеспособности решения,
   ещё не доказательство права конкретного payload на произвольное reading.
2. **Кеш потребителя.** Чтение существующего основания не создавало зависимости,
   если сама probe не исполнялась внутри потребителя. READING_DECISION теперь
   наблюдается dispatcher/source-read capture и участвует в discard traversal.
   Изменения самих morphology witness rows ещё требуют отдельного контракта (п. 6).
3. **Самоподтверждение recovery.** Копирование RECOVERED в token.variants обходило
   проверку основания через раннее equality. Shortcut исключён для derived origins;
   publish_recoveries проверяет attestation. Final validate_uses проверяет также
   RECOVERED и legacy CONTEXTUAL. Исправлено сравнение tuple/list evidence_refs.
4. **Ветвь raw probe.** Branch condition теперь сохраняется в replay record и
   обоих input signatures. Reading decision validator не допускает его как
   безусловное основание или основание sibling.
5. **Два производителя partial reading domain.** predicate_functions передавал role
   верхним полем, nominal_dependency — только внутри attachment. Последний теперь
   передаёт тот же explicit role вместе с исходным attachment, до выбора/хеширования.
   Это исправление контракта двух известных producers, не полнота всего formalizer.
6. **OPEN: immutable reading witnesses.** Decision receipt не связывает содержимое
   MORPHOLOGY_PROPOSAL/USE, AGREEMENT_RECOVERY, QUANTITY_COMPOSITION и ограничения
   домена с точным преобразованием. Нужно хранить/проверять эти зависимости и пустые
   запросы; нельзя объявить «зависимости кеша исправлены» по одному decision observer.
7. **OPEN: exact payload → use adapters.** function_use вне OOV возвращает True.
   Требуются adapters для всех текущих callers license_use:
   component_predication (bundle), composition_children (frame_refs),
   component_dependency_reduction (morph/head_morph attachment), quantifier_composition
   (binder head), nominal_functions (RELATION/shared head), qualitative_quantity
   (quantity/case), contextual_oov (POS domain). Точные token/reading/use должны
   следовать из выбранного payload, не просто из существования selected decision.
8. **OPEN: отсутствие probe record / deterministic support.** quantifier_composition
   создаёт Decision с Ground D, ссылаясь на head_license текстом. Необходимо передать
   машинно проверяемую parent dependency. Общий helper пока различает lifecycle,
   но не доказывает произвольный synthetic decision без record. Нельзя просто
   запретить все такие решения и потерять действующий deterministic producer.
9. **OPEN: весь остальной контур.** Проверить все строки двух таблиц, включая
   immutable source evidence, seal/native/write, cache resume и независимые пути.
   DEFER арифметических кванторов и параметризованных схем не закрывает эти обязанности.

## Воспроизводимая навигация и граница доказательств

`tools/recovery/inventory_reading_mechanisms.py` создаёт `F05_READING_CALLS.json`:
390 AST-кандидатов вызовов выбранных служб и 68 файлов-кандидатов cache/memo на
момент проверки. Это navigation inventory, **не доказательство полной достижимости**.
Локальные alias shadowing, attribute/dynamic calls и callbacks требуют ручной сверки.

Для закрытия каждой строки требуются: исчерпывающий перечень действующих реализаций,
общий контракт, producers/consumers/cache/revoke evidence, simple/nested,
singleton/multiple, empty/incomplete, unknown/conflict/stale, cold/cache-hit/resume,
historical/native, late revoke и сохранение sibling. Pending при нехватке данных
допустим; pending вместо нереализованного заявленного producer не закрывает механику.

## Адресные обязанности следующей работы

Статусы «часть» означают сделанные переходы, не закрытие всей строки.
«Нет» означает отсутствие положительного доказательства, а не недостижимость кода.

| ID | Переход / контракт | Реализация | Cold/cache | Historical | Late revoke | Native |
|---|---|---|---|---|---|---|
| RG-01 | decision → derived-reading liveness → cached consumer | часть: reading_decisions, morphology_domain, nominal_readings, dispatch_evidence | контрасты test_derived_reading_liveness | только текущие scoped checks; полный обход OPEN | четыре семейства, оба retirement event | smoke, не все producers |
| RG-02 | selected payload → exact token/reading/use | OPEN: семь групп callers в п. 7 | нет | нет | нет | нет полного доказательства |
| RG-03 | proposal/recovery/quantity/restriction → immutable witness → consumer | OPEN: п. 6 | нет полного hash/query contract | нет | decision revoke не заменяет witness revoke | нет полного доказательства |
| RG-04 | deterministic binder head proof → derived decision → use | OPEN: quantifier_composition._bind | нет | нет | текст Ground D не typed dependency | нет |
| RG-05 | reading domain producers → role projection → bundle checker | часть: predicate_functions + component_dependency_reduction | predicate path есть; dependency multiple требует native contrast | часть L3-S | domain/page lifecycle проверяется существующим validator | не все producers |
| CA-01 | raw/paged probe branch → replay / dependency signature | часть: component_probe/replay + reading_decisions | scoped test + smoke | нет полного обхода | branch revoked/sibling unit contrast | условные NOMINAL smoke |
| CA-02 | witness-set negative/empty query → dispatcher invalidation | OPEN | decision absence != witness-set absence | нет | нет | нет |
| CA-03 | весь реестр runtime/source/history/context/resume/R-X | OPEN: таблица служб выше | разрозненные проверки | разрозненные проверки | разрозненные проверки | нет общего покрытия |

AST-инвентарь фиксирует base commit и SHA-256 всех сканируемых исходников, включая
незакоммиченные изменения снимка. Это воспроизводимая версия навигации.

## Проверки этой контрольной точки и отрицательные результаты

Новые tests/test_derived_reading_liveness.py: 15 passed. Проверены четыре семейства,
отзыв/замена, published recovery, outcome eligibility, замена основания, source
revision, branch/sibling/global, cached consumer, допустимое semantic promotion.
Сценарный пакет semantic requirements + scalar REFERENCE/QUANTITY: 14 passed.
Дополнительные dispatcher/producer_reads/OOV проверки: 22 passed, 10 failed.
Сравнение с нетронутым 9b15de4: тот же список 10 failed, 22 passed.

Baseline failures **не считаются успешной приёмкой**. Остаются незакрытыми:
- test_composition_dispatcher: resolved_probe_rechecks_changed_parent_and_retains_exact_attempt;
  new_context_reopens_child_and_probe_but_unchanged_unknown_is_cached;
  real_agreement_repair_reaches_native_memory; parent_feedback_does_not_reask_unchanged_descendant.
- test_oov_paradigm_forms: native_unproved_forms_do_not_merge_symbols_or_events;
  analyzer_predictions_never_enter_semantic_prompts; predicted_lemma_and_features_cannot_change_the_interpretation
  (оба варианта); surface_lexeme_keeps_negation_and_query_anchor;
  nominal_oov_preserves_mention_without_inventing_a_paradigm.
Причины этих baseline failures в этой контрольной точке не установлены; нельзя
списать их на «старые тесты» или объявить подтверждением корректности механики.

Дополнительно historical lexical issuance smoke прошёл (1). В nominal_predication
пакете 1 passed / 9 failed; на нетронутом 9b15de4 те же девять failures. Они также
остаются OPEN, а не исключаются из приёмки. Отдельно: четыре nominal_predicate_uses_subject_and_copula_agreement,
nominal_predicate_under_question_is_not_forced_to_be_event_noun,
reported_nominal_predicate_is_only_content, два incomplete_or_mismatched сценария
(«Мария врачом.», «Врач.»), model_can_reject_nominal_predication.
Итого 19 baseline failures зафиксированы отдельно; их причины ещё не установлены.
