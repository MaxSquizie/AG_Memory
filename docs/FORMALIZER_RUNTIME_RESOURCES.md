# V7 — ресурсная граница текущего runtime

Это формат реализации, не утверждение полноты всех CandidateSchema архитектуры. Production читает файлы из `config.paths.data_dir`: `formalizer_release.json` и `formalizer_reviews.json`; имена настраиваются в разделе `formalizer`. `native_commit` должен быть true. Legacy preview не является production writer.

## Создание черновика

Из корня репозитория (PYTHONPATH должен содержать `src`):

```bash
PYTHONPATH=src python -m ah.formalizer.resources.release_cli init data/formalizer_release.json
PYTHONPATH=src python -m ah.formalizer.resources.release_cli check data/formalizer_release.json --draft
```

`init` не перезаписывает существующий файл. Черновик содержит пустые ресурсы и отключённую OpenTemplatePolicy; RoleRegistry и bounded ProposalPolicy заполнены только схемными defaults. Это **не подписанный релиз, не corpus coverage и не G2 PASS**.

## Контейнер

Manifest: `kind=FORMALIZER_RESOURCE_RELEASE`, `version`, `schema_version=v7`, `entries[]`, `dependency_versions{}`; у каждого ресурса такие же version/schema/entries/dependencies. Все resource versions закреплены верхним manifest. Зависимости должны замыкаться внутри текущего поддержанного bundle, без cycles. Runtime hash — SHA256 канонического JSON с sorted keys, компактными separators и UTF-8 (`ensure_ascii=false`): `{kind,version,schema_version,entries,dependency_versions,coverage_report}`; отсутствующий coverage допустим только для draft. Review metadata не хеширует сам себя.

Обязательные resource kinds runtime: R-S, R-V, TemplateMap, RoleRegistry, PredicateSchema, R-X3, DeclaredReads, SyntaxRules, ScopeLexicon, AttitudeMap, TemporalRules, OpenTemplatePolicy, ProposalPolicy, IncompatibilityRules. Отсутствующий контейнер не подменяется CHECKED_EMPTY.

| Вид | Поддержанный payload |
|---|---|
| R-S | `lemma`, `POS`, `sense_id`, optional `label`, `anchor_pattern:[{lemma?,POS?},…]` для многословной единицы; sense IDs уникальны |
| R-V | `sense_id`, optional `construction_id`, `temporal_mode_hint` (STATE/EVENT/PROCESS/TRANSITION), `roles[]`; роль: `role_id`, `allowed_cases[]`, `allowed_preps[]`, `argument_types[]`, `cardinality{min,max}`. Legacy `state_class` STATE/EVENT — только hint |
| TemplateMap | `sense_id`, реальные `template_ref`, `roles[]`; known mapping должен ссылаться на T текущей AH, open fallback запрещён |
| PredicateSchema | `lemma`, `value_ids[]`, optional `value_expansions[{rule_id,value_ids[]}]`; expansion считается один раз |
| R-X3 | `lemma`, `sense_id`; released prior, дополненный support-backed committed cache. Не truth ground |
| DeclaredReads | `read_id`, `lemma`, `snapshot_version`; RawInput содержит `declared_reads[read_id]` с `source_kind=W/C`, `source_ref`, `snapshot_version`, `candidate_sense_ids[]`. Нет чтения → BLOCKED |
| RoleRegistry | `role_id` из поддержанного ActantRole; обязательно EXPERIENCER/SURFACE_ARG. Неизвестный core role — ADAPTER_NOT_COVERED |
| SyntaxRules | data-only capture/predicate AST и typed output; полный формат и ограничения ниже. SRL и T2 читают только текущий released snapshot |
| ScopeLexicon | regex `pattern`, `operator`; реальный lexical trigger не может исчезнуть из grammar/TP tree. Clause boundary задаётся через SyntaxRules |
| AttitudeMap | `lemma`, `argument_role`, `attitude` QUOTED/EMBEDDED/HYPOTHETICAL/UNKNOWN, optional `holder_role`; ключ (lemma, argument_role) уникален |
| TemporalRules | regex `pattern`, kind POINT_CLOCK/DAY_INTERVAL/INTERVAL_CLOCK, `day_offset`, `interval_semantics` (default EXISTENTIAL). Named clock groups: hour/minute или start_hour/start_minute/end_hour/end_minute. CONTINUOUS pattern требует реального маркера/основания непрерывности, не голого «вчера» |
| ProposalPolicy | одна запись: `max_nodes`, `max_edges`, `max_depth`, `max_source_tokens`; `max_rule_steps` (default 20000), `max_rule_matches` (default 256), `verify_deterministic` (default false) |
| OpenTemplatePolicy | одна запись: `allow`; OPEN не создаёт alias/taxonomy к known sense |
| DomainCertificate (опц.) | `domain_id`, `template_ref`, `count_role`, `known_roles{role_id:M_uid}`, `request_window: null|[lo,hi]`, `completeness_evidence:[support_id,…]`, `version`. Это точный scope полноты; references должны быть живыми canonical proof paths. Point window = [t,t]. Запрос может выбрать domain_id, но не объявить полноту |
| IncompatibilityRules | поддержан `kind=ROLE_EXCLUSIVE`, `rule_id`, `sense_id`, `key_roles[]`, `role_id`; расширения DSL не исполняются произвольным callback |

Ресурсное покрытие всех §2.1 и semantic correctness записей подтверждает отдельный review/G2, а не таблица выше.

## Исполняемый SyntaxRules AST

Native путь использует `syntax_rules.py`, а не Python callbacks из preview `rules.py`. Правило содержит `rule_id`, `input_feature_pattern`, `output_kind`, `output`, `constraints[]`, `priority`, `min_evidence`, `coverage_tag`; optional `stage` должен совпадать с видом выхода. Это JSON-сериализация поддержанной части DSL, а не парсер текстового BNF §16 и не заявление о поддержке всех CandidateSchema.

`input_feature_pattern = {captures: {alias: feature_pattern}, window?: SENTENCE|CLAUSE, distinct?: true, where?: predicate_AST}`. Имена captures — ASCII identifiers; `item` зарезервирован для WINDOW_HAS. Feature pattern проверяет `lemma`, `POS`, `cases`, `number`, `gender`, `person`, `tense`, `mood`, `features`, `surface` (списки значений), `oov` (boolean); допускаются вложенные `all`, `any`, `not`. Проверяются целые R1 variants. Отсутствующий признак даёт UNKNOWN, в том числе под NOT. Лексический matcher не принимает строку с пробелами как «правило под предложение».

`where` — AST с `op`: AND/OR (`args[]`), NOT (`arg`), feature_eq (`field`, `value`), feature_in (`field`, `values[]`), span_relation (`left`, `right`, `relation`), agreement (`left`, `right`, optional `features[]`), window_has (`source=TOKEN|R1`, `expr`), schema_lookup (`resource`, `key{}`). Field имеет форму `capture.feature`; внутри WINDOW_HAS `item` обозначает текущий целый разбор токена ограниченного окна. Lookup keys — пути в resource rows, значения — literal или `{field: capture.feature}`; ресурс обязан быть объявлен в `SyntaxRules.dependency_versions`. NOT_FOUND не становится семантическим false. AND/OR/NOT используют трёхзначную логику.

`constraints[]` содержит `{kind, left, right, features?}`. Отношения: BEFORE, AFTER, ADJACENT, OVERLAPS, CONTAINS, AGREES; для AGREES явно задаётся непустой список number/gender/person/cases. Ни приоритет, ни порядок слов не выбирают победителя интерпретации. Если `distinct=false` разрешает повторный capture токена, все captures этого токена всё равно должны ссылаться на один и тот же целый разбор.

Выходы:

| output_kind / stage | output |
|---|---|
| CANDIDATE_GRAPH / T2 | `nodes[{id,kind,anchors:[capture...],head?:capture}]`, `edges[{kind,from,to,role_id?,scope?}]`; типы/арность/циклы/границы проверяются общим TP validator. ARGUMENT/ATTITUDE может ссылаться на целое пропозициональное дерево N/G |
| CLAUSE_BOUNDARY / SRL | `{capture, side?: BEFORE|AFTER}`; каждый boundary остаётся альтернативой, unsegmented вариант сохраняется |
| ELLIPSIS / SRL | `{capture, gap_kind: PREDICATE_GAP|ARGUMENT_GAP|SUBORDINATOR_GAP, antecedent?: capture}` |
| TOKEN_HYPOTHESIS / SRL | `{capture, variants:[...]}`; обязательно `keep_as_is`, исправление не подтверждается дистанцией |

Перебор aliases и ресурсов канонически упорядочен. Каждый capture сохраняет целый морфологический вариант в гипотезе и sealed frame; T3/R-V не возвращается к объединению признаков разных разборов. Одинаковые графы с теми же variant bindings объединяются с сохранением всех rule IDs; действительно разные пересекающиеся структуры остаются LinkedAlternative до разрешённого выбора. TP вызывается для незакрытой области/неоднозначности; `verify_deterministic=true` дополнительно запрашивает его проверку уже покрытого ввода.

Бюджет действует отдельно для SRL и T2: проверки признаков/constraints/AST/lookup rows/joins учитываются в `max_rule_steps`; число matches ограничено `max_rule_matches`, окно — `max_source_tokens`. При превышении весь незавершённый набор соответствующего этапа отбрасывается, остаются trace + COMPUTATION_LIMIT и переход к bounded TP. Успешный префикс поиска не выдаётся за исчерпанность. Положительные, отрицательные и UNKNOWN результаты пишутся в `syntax_trace`, входят в structural seal и durable RESOLUTION/BATCH; ресурсные callbacks/eval не исполняются. TP alternatives тоже остаются адресными; выбор/исключение имеет trace и причину. Selection protocol запрещает посторонние поля, пропущенные outcome/selected и дубли ID.

PREDICATE/ENTITY может иметь несколько raw anchors; в этом случае `head` в SyntaxRules / `head_anchor` в TP обязателен и входит в собственные anchors. Unit surface сохраняется целиком; известный смысл должен соответствовать R-S anchor_pattern для всех anchors. Head-only R-X/AttitudeMap не доказывает смысл/attitude всей фразы. TIME — raw temporal anchors, TIME_SCOPE — proposition→TIME; численные bounds вычисляет только released TemporalRules с declared time_anchor. BEFORE/AFTER/DURING используют типизированные TimeLiteral. QUERY_SLOT — PREDICATE→WH/COUNT_REQUEST с registered role; смешанный/неоднозначный владелец блока не уплощается. SRL альтернативы орфографии/эллипсиса сохраняются как кандидаты, а не превращаются автоматически в выбранный текст/подставленное событие. Все данные и coverage остаются предметом G2/G5.

Прежний release без SyntaxRules теперь получает RESOURCE_MISSING. Добавление этого ресурса/зависимостей требует новой версии, нового content hash и внешнего review pin; незаметная вставка defaults в подписанный snapshot запрещена. Загруженный manifest копируется в каноническом порядке; native вход и C проверяют неизменность его hash перед использованием.

## Review и доверие

Release содержит `signed_review_id={reviewer,reviewed_sha256,signature,timestamp}` и реальный `coverage_report={corpus_id,corpus_sha256,units_by_kind,categories}`. Внешний `formalizer_reviews.json` — map: `release_sha256 → та же review-запись`. Не копировать выдуманную подпись в оба файла: этот файл является доверенным входом оператора, вне предложений модели и текста пользователя.

```bash
PYTHONPATH=src python -m ah.formalizer.resources.release_cli check data/formalizer_release.json --trusted-reviews data/formalizer_reviews.json
```

Текущая проверка — pinning внешней review-атрибуции и content hash. Она **не криптографическая проверка подписи** и не заменяет доверенное получение файла reviewer records. Изменение entries/dependencies/coverage меняет hash и требует нового review. Команда check не утверждает G0/G1/G2 PASS.

## RawInput, replay и память

Передаются text/source_id/revision/range, context snapshot, declared time_anchor (ISO8601 с timezone либо отдельной явно объявленной timezone), entity bindings с основаниями и declared W/C reads. Без anchor/timezone относительная дата остаётся UNKNOWN. R-X reads фиксируются в immutable snapshot запуска; root facts никогда не подтверждаются кэшем. У той же пары observation/version сохраняется canonical run_id. Изменение контекста, ресурсов либо смысла требует declared trigger и новой версии; проигравший/отозванный путь не оживляется скрыто.

AH JSON snapshot теперь содержит `store_metadata.formalizer_state`; journal canonical_unit содержит точное AH+ledger состояние и checksum. Старый JSON и его journal необходимо сохранять совместно. Возврат snapshot без согласованного WAL не является разрешённым rollback: snapshot ahead/journal corruption → INTEGRITY_ERROR. Только incomplete последний journal frame допускает отсечение; audit не чинится вставкой событий вне порядка.

## Native запросы и declared миграция

RawInput optional `goal_request` содержит `mode=FORMULA|WH|COUNT`, `requested_roles[]` либо `count_role`, optional `expected_count`, `comparison=EXACTLY_N|AT_LEAST_N|AT_MOST_N`, `domain_certificate` (ID релизного сертификата, не bool). Эти поля задаёт host, TP даёт только типизированные query slots. WH/COUNT для атома требуют согласованного TemplateMap/R-V с полным набором ролей, включая query gap. `query_source_scope:[observation_id,…]` (не более 16) разрешает только точную open-attestation из живых опор названных источников; canonical identity не выводится из написания.

Для replacement используется `migration.reinterpret_observation(store,binding,selector,release, observation_id=…, previous_version=…, trigger_ref=…, open_template_links=[{source_t_ref,canonical_t_ref,evidence_refs:[support_id,…]}])`. Старый RawInput берётся из binding snapshot; run v+1 получает новый reviewed release. C проверяет source anchors/mapping, T6 повторно проверяет live evidence и атомарно фиксирует новую версию вместе с supersede старой. Failed T4/T5/полный отказ не отзывают старую версию. LinkOpenTemplate — audit relation, не reasoner alias и не скрытый перенос truth grounds. Повтор завершённой миграции требует прежних frozen входов; отозванные пути не оживают.

Текстовый Rule DSL не импортируется как Python и не считается реализованным JSON AST. В §16 BNF недоопределены capture declarations и payload Emit.fields; расширение parser требует сначала однозначного нормативного синтаксиса. Полный numeric scope и counterfactual proof не подменяются обычным count/мировым EXISTS.
