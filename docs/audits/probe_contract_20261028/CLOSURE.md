# Границы и закрытие статического аудита

Дата: 2026-10-28. Исследована база 6515de5d0bbb820c28a6bc2ed72ccada465453de с исходными незакоммиченными исправлениями. SHA256 всех 477 файлов src в inventory_v2.json; 259 из них относятся к formalizer. Исправления производственного кода не выполнялись.

## Что закрыто

1. AST разобран у всех 477 файлов src без ошибок. Поиск границ выполнен от смысловых helper-вызовов и от нижних select/propose/transport/backend вызовов; дополнительно проверены импорты, aliases и callback-поля. Реестр v2 содержит 116 мест, а не 116 уникальных смысловых вопросов. Все 99 старых мест включены; добавлено 17.
2. Для всех 116 мест есть точное выражение вызова, функция-владелец, найденные статические callers (CALLSITE_CARDS.md / inventory_v2.json), индивидуальная запись проверки (review_ledger.json) и семейное заключение (FAMILY_REVIEW.md). Нет оставшихся записей REQUIRES_PER_SITE_PROOF без вынесенного заключения: недостаточность доказательств оформлена как конкретный открытый контракт, а не автоматически PASS.
3. Проверены common codec, пагинация, optional-empty, последовательный source_set, replay, dispatcher, именные/временные inventories, child resume, source reuse, уточнение, лексическая приёмка, сборка плана и write gate. Существующие защиты учтены; общее утверждение «запись не проверяется» отвергнуто.
4. Прослежены оба режима native region_probes и legacy_proposal; вспомогательный schema pipeline и public APIs выделены отдельно. Имена select, span, probe не приняты за доказательство смысловой одинаковости.
5. Для найденных недостатков сформулированы необходимые свойства, локальные условия достаточности и границы, за которыми вывод не доказан. Итог: FINAL_AUDIT.md.

## Точки входа и режимы

| Вход | Путь | Итог и границы |
|---|---|---|
| GUI runtime | bootstrap._build_formalizer_adapter → FormalizerAdapter.interpret → v7_pipeline.interpret_full → run_native | Ресурсный релиз и structure_mode задают набор достижимых producers; отсутствие ресурсов не включает старый parser fallback |
| Встраиваемое ядро | kernel.interpret → BoundedExecutor → run_native | Возвращает интерпретацию/метрики, записи нет |
| region_probes | _interpret_state → components → source_areas/compose_area → relation или ресурсные ветки по policy | Грамматика и компоненты дают объединяемые домены; `_literal_relation` выключает часть ресурсных обходов |
| legacy_proposal | _interpret_state → _propose → propose_local → parser/TD → optional structure selector | Генерация графа, не обычный closed relation selector; bounded syntax validation не доказывает семантическую полноту |
| После структуры | discourse/implicit/reference preparation → content/quantifier licence checks → seal → explicit/implicit refs → lexical selection → spatial/nominal/source assertions | Seal предшествует части смысловых решений и не является общей готовностью |
| Долговременная запись | v7_pipeline.run_from_state → native_plan.build_plan → commit_stage.commit → store.gate_precheck/commit_transaction | Каждый корень собирается отдельно; PARTIAL/structural_unresolved блокируется; references, roles, scope, templates и journal bindings имеют дополнительные gates |
| Старый schema API | pipeline.run → T3 select → T4 cluster validation | Отдельное понятие domain/search_complete; не вызывается вместо native path из bootstrap |
| naming/open-set | run_naming/naming_probe; maybe_extend/propose_value | В src не найден внешний production caller; public import остаётся возможным. Naming возвращает чтение, extension — provisional proposal |
| TagSource | if_bridge создаёт TagSource без subord_probe | Пользователь public API может подключить callback; его bool-протокол не равен SELECT_LABELS_V1 |
| Region compatibility | region_probes.select_generated | Сохранённый compatibility API; активный caller в src не найден. Это не математическое доказательство недостижимости |

## Динамические рёбра, раскрытые вручную

Статические рёбра с разрешёнными именами сохранены в static_edges.json. Следующие рёбра нельзя терять из-за отсутствия обычного именованного вызова:

| Callback/обёртка | Реальный поставщик в исследованном пути | Контракт |
|---|---|---|
| PartitionDomain.resolve(propose,on_check) | relation_partitions.unary/binary/content/group; relation_quantifiers.compose.propose; content_checked | PartitionProposal или неполнота; coverage/owner/shared-functions проверяет confirm_partition |
| partition_sequences.select_parts(select) | вложенные select в relation_partitions.binary/content | Одна следующая source group; функция не является LLM transport |
| composition_morphology.domain → select() | локальная функция select → contextual_oov.resolve | Не прямой вызов selector.select; слово select само по себе не определяет границу |
| compose_child/child_composer | lambdas в component_refinement и его рекурсивных ветках | Сохранение InputSlot/attachment/controller; возврат списка frame, затем select_child и partial propagation |
| dispatcher.run(compute) | callbacks child/morphology/partition/probe/context | Cached result и зависимости; side effects state не транзакционно откатываются универсально |
| component_probe_replay.execute(live) | component_probe._live_probe | Повторный raw outcome не наследует SEMANTIC_VALIDATION; signature включает dependency signature |
| kernel.BoundedExecutor.executor | host ProbeExecutor, штатно RealBackendSelector | Лимиты до вызова; качество смыслового ответа — внешняя предпосылка |
| ProviderAdapter.transport | RealBackendSelector._transport или lexical rank transport | Replay/WAL/raw str; НЕ семантический validator |
| RealBackendSelector.backend.generate | настроенный backend сервиса | system + prompt + параметры; конкретная реализация/модель вне доказательства языковой корректности |
| AUX1: LexicalEmbeddingRanker.client.embed | настроенный embedding client | Векторное ранжирование, никакого удаления кандидатов/автовыбора |
| TagSource._probe | внешний subord_probe, штатный if_bridge не подключает | bool; внешняя функция неизвестна статическому анализу |

Дополнительные интерфейсы provider_adapter.propose_lexical → _exchange присутствуют как API транспорта; собственного вызывающего семантического producer в src не найдено. Внешнее подключение не домысливается.

## Матрица покрытия свойств

| Свойство | Вердикт по всему контуру | Основание |
|---|---|---|
| Строго различать 0 и ? на общей wire-границе | Реализовано | selection_labels/selection_protocol, _live_probe |
| Один ID только из предъявленного множества | Реализовано на общем codec | Внешние bool/JSON API имеют отдельные контракты |
| Ответ selector сам даёт RESOLVED | Не допускается common helper | Native consumers валидируют собственные постусловия; generic API не общий semantic verifier |
| Полнота всех языковых генераторов | Не доказана, часть областей явно ограничена | F05/F09; ресурсные ограничения, перечисленные semantic types, unsupported outcomes |
| Singleton всегда имеет достаточное основание | Не обеспечено общим контрактом | F01; при этом quantifier head/context binding/OPEN имеют отдельные основания |
| Полнота и актуальность отрицательного завершения | Нарушено | F14: реальный controlled witness лицензирует EMPTY после retirement страницы |
| Актуальность производных inventories | Нарушено на локальных интерфейсах | F11/F12; compensating prepare не закрывает весь retirement closure |
| Информационная достаточность всех запросов | Не обеспечена | F03/F04/F13/F15; потеря различий/данных, не просто длина текста |
| Все later constraints относятся к текущей гипотезе | Не обеспечено общим проверяемым механизмом | R4; строковые журналы без одинаковых проверок liveness |
| Пересмотр покрывает любой причинный отказ | Не доказано | F07; конкретные triggers, finite budget, unknown не запускает revision |
| Предпочтение не теряет допустимые прочтения | Не обеспечено как единая семантика | F16; shared scope preference и отдельная явная scope assumption |
| Нет никакой защиты долговременной записи | Опровергнуто | native_plan guards, native_frontend licences, binding validators, T5/T6 |
| Все лингвистические proof-dependencies проверяются до записи | Не доказано | Разные receipts; universal transitive semantic closure отсутствует в проверенных gates |
| Любая слабая модель ответит верно | Не выводится из кода | F10; требуется отдельное эмпирическое испытание реального final system+prompt |

## Что означает «завершён аудит»

Завершён статический проход по всем выявленным границам проб исследованной версии и их главным производителям/потребителям, с закрытым реестром рассмотренных мест и отрицательными/условными заключениями. Это **не сертификат отсутствия иных дефектов** и не доказательство всех исполнений Python, произвольных внешних callback или любых русских текстов.

Не исполнялись все ресурсные конфигурации, GUI-варианты и все возможные ответы модели. Не доказан сквозной stale-write для каждого локального дефекта. Эти ограничения входят в результат аудита: без них обещание достаточности было бы ложным. Аудит не откладывает их молча и не записывает PASS вместо неизвестности.

Для перехода от аудита к доказательству контура потребуется конечная спецификация поддерживаемой семантики D, обязательства генераторов, полностью адресованные receipts, единая актуальность и проверяемая готовность каждого записываемого корня. Конкретный класс/формат реализации этими условиями не предрешён.
