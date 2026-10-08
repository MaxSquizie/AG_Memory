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

Обязательные resource kinds runtime: R-S, R-V, TemplateMap, RoleRegistry, PredicateSchema, R-X3, DeclaredReads, ScopeLexicon, AttitudeMap, TemporalRules, OpenTemplatePolicy, ProposalPolicy, IncompatibilityRules. Отсутствующий контейнер не подменяется CHECKED_EMPTY.

| Вид | Поддержанный payload |
|---|---|
| R-S | `lemma`, `POS`, `sense_id`, optional `label`; sense IDs уникальны |
| R-V | `sense_id`, optional `construction_id`, `temporal_mode_hint` (STATE/EVENT/PROCESS/TRANSITION), `roles[]`; роль: `role_id`, `allowed_cases[]`, `allowed_preps[]`, `argument_types[]`, `cardinality{min,max}`. Legacy `state_class` STATE/EVENT — только hint |
| TemplateMap | `sense_id`, реальные `template_ref`, `roles[]`; known mapping должен ссылаться на T текущей AH, open fallback запрещён |
| PredicateSchema | `lemma`, `value_ids[]`, optional `value_expansions[{rule_id,value_ids[]}]`; expansion считается один раз |
| R-X3 | `lemma`, `sense_id`; released prior, дополненный support-backed committed cache. Не truth ground |
| DeclaredReads | `read_id`, `lemma`, `snapshot_version`; RawInput содержит `declared_reads[read_id]` с `source_kind=W/C`, `source_ref`, `snapshot_version`, `candidate_sense_ids[]`. Нет чтения → BLOCKED |
| RoleRegistry | `role_id` из поддержанного ActantRole; обязательно EXPERIENCER/SURFACE_ARG. Неизвестный core role — ADAPTER_NOT_COVERED |
| ScopeLexicon | regex `pattern`, `operator`; для clause boundary — `kind=CLAUSE_BOUNDARY`, `trigger`. Реальный lexical trigger не может исчезнуть из TP tree |
| AttitudeMap | `lemma`, `argument_role`, `attitude` QUOTED/EMBEDDED/HYPOTHETICAL/UNKNOWN, optional `holder_role` |
| TemporalRules | regex `pattern`, kind POINT_CLOCK/DAY_INTERVAL/INTERVAL_CLOCK, `day_offset`, `interval_semantics` (default EXISTENTIAL). Named clock groups: hour/minute или start_hour/start_minute/end_hour/end_minute. CONTINUOUS pattern требует реального маркера/основания непрерывности, не голого «вчера» |
| ProposalPolicy | одна запись: `max_nodes`, `max_edges`, `max_depth`, `max_source_tokens`, `verify_deterministic` (default true) |
| OpenTemplatePolicy | одна запись: `allow`; OPEN не создаёт alias/taxonomy к known sense |
| IncompatibilityRules | поддержан `kind=ROLE_EXCLUSIVE`, `rule_id`, `sense_id`, `key_roles[]`, `role_id`; расширения DSL не исполняются произвольным callback |

Ресурсное покрытие всех §2.1 и semantic correctness записей подтверждает отдельный review/G2, а не таблица выше.

## Review и доверие

Release содержит `signed_review_id={reviewer,reviewed_sha256,signature,timestamp}` и реальный `coverage_report={corpus_id,corpus_sha256,units_by_kind,categories}`. Внешний `formalizer_reviews.json` — map: `release_sha256 → та же review-запись`. Не копировать выдуманную подпись в оба файла: этот файл является доверенным входом оператора, вне предложений модели и текста пользователя.

```bash
PYTHONPATH=src python -m ah.formalizer.resources.release_cli check data/formalizer_release.json --trusted-reviews data/formalizer_reviews.json
```

Текущая проверка — pinning внешней review-атрибуции и content hash. Она **не криптографическая проверка подписи** и не заменяет доверенное получение файла reviewer records. Изменение entries/dependencies/coverage меняет hash и требует нового review. Команда check не утверждает G0/G1/G2 PASS.

## RawInput, replay и память

Передаются text/source_id/revision/range, context snapshot, declared time_anchor (ISO8601 с timezone либо отдельной явно объявленной timezone), entity bindings с основаниями и declared W/C reads. Без anchor/timezone относительная дата остаётся UNKNOWN. R-X reads фиксируются в immutable snapshot запуска; root facts никогда не подтверждаются кэшем. У той же пары observation/version сохраняется canonical run_id. Изменение контекста, ресурсов либо смысла требует declared trigger и новой версии; проигравший/отозванный путь не оживляется скрыто.

AH JSON snapshot теперь содержит `store_metadata.formalizer_state`; journal canonical_unit содержит точное AH+ledger состояние и checksum. Старый JSON и его journal необходимо сохранять совместно. Возврат snapshot без согласованного WAL не является разрешённым rollback: snapshot ahead/journal corruption → INTEGRITY_ERROR. Только incomplete последний journal frame допускает отсечение; audit не чинится вставкой событий вне порядка.
