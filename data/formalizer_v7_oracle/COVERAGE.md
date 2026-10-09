# Покрытие oracle

Кейсов: **2542**. Механизмов: **118**. A01–A39 и DR1–DR31 связаны с кейсами.

Это проектные gold-сценарии; результаты исполнения и статусы G0–G5 не утверждаются.

| Механизм | Норма | Кейсов | Первые примеры |
|---|---|---:|---|
| `input` — Валидация RawInput и отсутствие побочных записей при отказе | §1.1 | 9 | INPUT-source_id-, INPUT-revision-0, INPUT-revision--1, INPUT-revision-True |
| `observation_key` — Ключ observation не содержит source_revision | §1.1 | 1 | A25 |
| `revision` — Повтор, конфликт байтов и declared v+1 | §1.1 §8.1 | 5 | A25, A26, INPUT-CONFLICT-same_revision_different_text, INPUT-CONFLICT-same_pair_different_context_hash |
| `canonical_ids` — Стабильные IDs, canonical serialization и коллизии | §1.3 | 6 | ID-COLLISION, META-R_entries_order, META-source_iteration_order, META-constraint_iteration_order |
| `contexts` — GenerationContext и ResolutionContext; frozen declared reads | §1.2 | 16 | A27, INPUT-CONFLICT-same_revision_different_text, INPUT-CONFLICT-same_pair_different_context_hash, INPUT-CONFLICT-same_pair_different_resource_hash |
| `grounds` — Truth O/C/W отдельно от interpretation R/D/M/A/P | §1.3 §7.2 §7.4 | 52 | GRD-O, GRD-C, GRD-W, GRD-R |
| `source_trace` — Ровно пять CandidateSourceTrace на слот | §5.1 | 7 | A20, A39, SRC-MISSING-1, SRC-MISSING-2 |
| `source_exhaustion` — FOUND=0, пять терминальных traces, честное исчерпание | §5.1 §10 | 53 | A39, T4-0-0-0-0, T4-0-0-0-1, T4-0-0-1-0 |
| `source_blocked` — BLOCKED не равен пустоте и запрещает RESOLVED | §5.1 §5.3 | 53 | A20, T4-0-0-0-0, T4-0-0-0-1, T4-0-0-1-0 |
| `selector` — ID-selector ONE/MULTIPLE/NONE и проверка протокола | §5.2 | 9 | SELECTOR-unknown_id, SELECTOR-duplicate_id, SELECTOR-wrong_shape, SELECTOR-non_json |
| `value_grounds` — Ground каждого выбранного/выжившего значения | §5.3 | 37 | A09, A32, T4-0-0-0-0, T4-0-0-0-1 |
| `constraint_search` — Arc consistency, циклические кластеры, полный bounded search | §5.3 | 34 | A17, A28, T4-0-0-0-0, T4-0-0-0-1 |
| `alternatives` — LinkedAlternative не теряется без RejectionRecord | §3 §5.3 | 15 | A04, A09, A32, OPEN-KEY-context_version |
| `oscillation` — Freeze повторного состояния, M не re-arm | §5.4 | 2 | OSCILLATION-M, OSCILLATION-REAL |
| `budget` — Независимые лимиты, FROZEN, timing replay | §0 §9 | 19 | A28, BUDGET-tp_calls-0, BUDGET-tp_calls-1, BUDGET-lexical_calls-0 |
| `resource_schema` — Закрытые CandidateSchema, IDs, enums, dependencies, cycles | §2.1 §2.4 | 86 | RES-R1-missing_required_field, RES-R1-unknown_field, RES-R1-wrong_field_type, RES-R1-duplicate_id |
| `release_trust` — Подпись, trust registry, timestamp, content/coverage hash | §2.4 | 13 | TRUST-signature_bytes, TRUST-public_key_length, TRUST-signature_length, TRUST-untrusted_reviewer |
| `resource_missing` — RESOURCE_MISSING не CHECKED_EMPTY | §2.1 §5.1 | 79 | A20, RES-R1-missing_required_field, RES-R1-unknown_field, RES-R1-wrong_field_type |
| `resource_permutation` — Перестановки entries не меняют результат | §2.2 | 4 | META-R_entries_order, META-source_iteration_order, META-constraint_iteration_order, META-replay_provider_bytes |
| `coverage_report` — Фиксированный корпус и раздельные ресурсные/семантические категории | §2.3 §2.4 | 14 | TRUST-signature_bytes, TRUST-public_key_length, TRUST-signature_length, TRUST-untrusted_reviewer |
| `morph_unknown` — UNKNOWN-признак не отрицание; hard morph agreement | §2.1 §4.1 §4.3 | 13 | A08, A10, A20, MORPH-UNKNOWN-gender |
| `raw_alignment` — Полное исходное покрытие токенами, пробелами, пунктуацией | §4.1 | 469 | A29, LANG-00-0-bare, LANG-00-0-not, LANG-00-0-possible |
| `srl_boundary` — SRL не создаёт смысл/факты; typo prior и KEEP_AS_IS | §4.1 | 2 | A10, A29 |
| `structural_heads` — Глагольные, nonfinite, nominal, impersonal, elliptic centers | §4.2 §4.5 | 499 | A02, A31, A32, LANG-00-0-bare |
| `multi_anchor` — Несколько lexical anchors; запрет opaque целой строки | §4.5 | 131 | A19, A35, OPEN-00-0-asserted, OPEN-00-0-not |
| `attachment` — Только проверенные attachment и SURFACE_ARG | §4.2 §4.3 | 1 | A31 |
| `proposal_validation` — Типы, anchors, cycles, локальные roles, никакого UID/g/truth | §4.5 §5.2 | 13 | TP-INVALID-canonical_uid, TP-INVALID-new_g_id, TP-INVALID-truth_claim, TP-INVALID-out_of_bounds_anchor |
| `proposal_bounds` — Finite proposal budget и полный отказ неполного префикса | §4.5 §9 | 12 | BUDGET-tp_calls-0, BUDGET-tp_calls-1, BUDGET-lexical_calls-0, BUDGET-lexical_calls-1 |
| `seal` — Structural seal; T3 не меняет структуру | §4.3 §4.5 | 10 | TP-INVALID-canonical_uid, TP-INVALID-new_g_id, TP-INVALID-truth_claim, TP-INVALID-out_of_bounds_anchor |
| `scopes` — Вложенность, depth/source order, OR/XOR/NOT/quantifiers | §4.3 §6.2 | 12 | A02, A03, A04, A06 |
| `coreference` — Адресная coreference, окно, собственные binding paths | §4.3 §7.3 | 14 | A08, A09, A11, MORPH-HARD-gender |
| `existential_ref` — Локальный ExistentialRef вместо фиктивного M | §3 §6.2 | 1 | A11 |
| `open_lexical` — Изолированный UNLINKED T; exact attestation, no alias | §5.1 §7.1 | 154 | A10, A31, A33, A38-NOT |
| `open_key` — Occurrence-local key, роли/attachment/spans, контекстный replay | §7.1 | 136 | A33, OPEN-00-0-asserted, OPEN-00-0-not, OPEN-00-0-quoted |
| `known_mapping` — Известный sense без TemplateMap не обходится open | §7.1 §7.2 | 3 | A21, A33, A34 |
| `coverage` — FULL/OPEN/PARTIAL/NONE ортогональны outcome | §1.3 §2.3 | 3 | A19, A36, DR5-PARTIAL |
| `partial` — Независимые ASSERTED фрагменты, нет скрытой полной opaque интерпретации | §7.2 | 3 | A19, DR5-PARTIAL, STATE-MIXED |
| `modus` — ASSERTION/QUERY/COMMAND/MIXED и косвенный speech act | §0 §6.1 | 469 | A37, LANG-00-0-bare, LANG-00-0-not, LANG-00-0-possible |
| `som` — Материализация структурных N/G/M без truth-support | §7.5 | 185 | A01, A06, A13, A32 |
| `attitude_links` — ATTITUDE per-observation/holder, UNKNOWN map | §3 §7.5 | 45 | A01, A38-NOT, A38-QUOTED, NONFINITE-00-base |
| `operator_links` — Канонические OPERATOR ссылки только proposition slots | §3 §7.5 §17 | 16 | A38-NOT, A38-QUOTED, SOM-DEPTH-1, SOM-DEPTH-2 |
| `s_access` — Транзитивная S-access от F-visible, нет самоподдерживающего цикла | §7.5 §8.2 | 39 | NONFINITE-00-base, NONFINITE-00-quote, NONFINITE-00-nested_quote, NONFINITE-00-question |
| `reaccess` — Старые опоры мертвы, узлы переиспользуются и REACCESSIBLE | §3 §8.2 | 6 | SOM-DEPTH-1, SOM-DEPTH-2, SOM-DEPTH-3, SOM-DEPTH-4 |
| `node_events` — Type-dependent identity, support_id, T/seq, атомарный audit | §3 §8.3 | 10 | SOM-DEPTH-1, SOM-DEPTH-2, SOM-DEPTH-3, SOM-DEPTH-4 |
| `event_audit_integrity` — Неповреждаемый audit; индекс rebuild, corruption fail-safe | §3 §8.3 | 12 | RECONCILE-EXACT-VERSION, AUDIT-missing_event, AUDIT-extra_event, AUDIT-wrong_order |
| `state_identity` — RelationKey без времени, STATE один N и независимые опоры | §6.3 §7.1 | 43 | A07, A23, A36, SOM-INDEPENDENT-STATE |
| `occurrence_identity` — EVENT/PROCESS/TRANSITION/UNKNOWN разные occurrences | §7.1 §7.6 | 44 | A24, A36, SOM-INDEPENDENT-STATE, SOM-INDEPENDENT-EVENT |
| `function_identity` — Синтаксический typed порядок, commutative только AND/OR/XOR | §7.3 §15 | 18 | FUNC-AND, FUNC-OR, FUNC-XOR, FUNC-NOT |
| `and_commit` — AND_ELIMINATION commit-time, корень ROOT, дети DERIVED | §7.4 §15 | 6 | A02, A03, DR12-FULL, DERIVED-G-AND_ELIMINATION |
| `or_demand` — N-ary OR on-demand, все n−1 отрицаний | §7.4 §15 | 67 | A04, OR-N2-00, OR-N2-01, OR-N3-00 |
| `forall_demand` — Два операнда FORALL; root-only commit; instance on-demand | §6.2 §7.4 | 5 | A06, DR11-FULL, DERIVED-G-AND_ELIMINATION, DERIVED-G-OR_ELIMINATION |
| `modus_ponens` — IMPLIES+antecedent, без converse/contraposition | §15 | 3 | A13, MP-NO-CONVERSE, MP-BOTH-PREMISES |
| `modal_guard` — Модальность, отрицание, цитата и hypothetical не утверждают операнд | §6.1 §15 | 721 | A01, A06, A12, A13 |
| `association` — ASSOCIATION не CAUSE/IMPLIES | §6.3 §15 | 1 | A15 |
| `registered_ops` — g/L лишь с полным handler/schema/codec; rollback неизвестных | §15 §17 | 54 | A21, A35, LINK-SLOTS-FORALL, LINK-SLOTS-EXISTS |
| `time_absent` — Недатированный SupportRecord без TimeAssertion | §6.3 §7.1 | 511 | A23, TQ-00-00-0, TQ-00-00-1, TQ-00-01-0 |
| `time_default` — POINT/EXISTENTIAL/CONTINUOUS, явное время и source timestamp | §6.3 | 465 | A16, LANG-00-0-bare, LANG-00-0-not, LANG-00-0-possible |
| `time_symbolic` — Символические границы без runtime now и без угадывания | §6.3 | 961 | A16, ORT-00-00, FAT-00-00, ORT-00-01 |
| `simultaneity` — ∀ независимых реализаций, все комбинации и singleton | §6.3 | 196 | SIM-01-01, SIM-01-02, SIM-01-03, SIM-01-04 |
| `query_time` — Точечный и экзистенциальный запрос, bounds/coverage | §6.3 | 526 | TQ-00-00-0, TQ-00-00-1, TQ-00-01-0, TQ-00-01-1 |
| `query_not_time` — NOT-root область отрицания; Q subset I для NO | §6.3 | 510 | TQ-00-00-0, TQ-00-00-1, TQ-00-01-0, TQ-00-01-1 |
| `no_interpolation` — Два point witness не доказывают между ними | §6.3 | 1 | A23 |
| `or_time` — Каждая реализация OR покрыта NOT, mixed unknown | §7.4 | 234 | ORT-00-00, ORT-00-01, ORT-00-02, ORT-00-03 |
| `forall_time` — Симметричная temporal license и вычисленная область | §6.3 | 234 | FAT-00-00, FAT-00-01, FAT-00-02, FAT-00-03 |
| `multi_premise_time` — Общее пересечение всех premises, не попарная лицензия | §6.3 | 1 | WIT-NO-REGION |
| `witness_correlation` — AND наследует общий witness; равные bounds не корреляция | §7.6 | 9 | WIT-OR_ELIMINATION-0-0, WIT-OR_ELIMINATION-0-1, WIT-OR_ELIMINATION-1-0, WIT-OR_ELIMINATION-1-1 |
| `time_provenance` — source×support, матрица ROOT/DERIVED, атомарная пара | §17 | 30 | A03, WIT-OR_ELIMINATION-0-0, WIT-OR_ELIMINATION-0-1, WIT-OR_ELIMINATION-1-0 |
| `assertion_retraction` — По assertion_id любой source, SupportRecord жив, durable dedup | §8.2 §17 | 17 | RET-OBSERVATION_ROOT-OBSERVATION, RET-OBSERVATION_ROOT-ASSERTION, RET-OBSERVATION_ROOT-BINDING, RET-OBSERVATION_ROOT-PREMISE |
| `effective_time` — Ledger LIVE при мёртвом пути; effective visibility | §6.3 §8.2 | 15 | RET-OBSERVATION_ROOT-OBSERVATION, RET-OBSERVATION_ROOT-ASSERTION, RET-OBSERVATION_ROOT-BINDING, RET-OBSERVATION_ROOT-PREMISE |
| `conflict_admission` — Текущий AH и взаимные конфликты внутри batch | §6.3 §7.3 | 226 | A18, SIM-01-01, SIM-01-02, SIM-01-03 |
| `conflict_pairs` — Один отчёт на пару; CandidateCommitted и TwoCandidate | §6.3 | 10 | A18, REPORT-PAIRS-1, REPORT-PAIRS-2, REPORT-PAIRS-3 |
| `conflict_open` — Все evidences эффективны, REPORT_CLOSED, born closed | §6.3 §8.2 | 6 | REPORT-PAIRS-1, REPORT-PAIRS-2, REPORT-PAIRS-3, LATE-CONFLICT |
| `conflict_late` — Новый ресурс: поздний отчёт, no auto-retract | §6.3 | 1 | LATE-CONFLICT |
| `precheck` — GATE_PRECHECK только диагностика, не отчёт и не terminal | §6.3 §7.2 | 2 | PRECHECK-RETRACT, PLAN-E-SHARED |
| `fragment_plan` — plan\E closure; общие ops сохранены, исключённые опоры отсутствуют | §6.3 §7.3 | 7 | REPORT-TWO-0-BEFORE_DECISION, REPORT-TWO-0-AFTER_DECISION, REPORT-TWO-0-AFTER_TERMINAL, REPORT-TWO-1-BEFORE_DECISION |
| `writers` — C read-only, T6/Goal/status права дизъюнктны | §0 §7.3 §17 | 57 | GRD-O, GRD-C, GRD-W, GRD-R |
| `batch_idempotence` — batch hash и marker; повтор без новых операций | §7.2 §7.3 | 4 | A05, A22, DR9-MARKER-SAME, DR9-MARKER-DIFFERENT |
| `head_order` — Глобальный head-only, PENDING_ADMISSION_ORDER не durable | §7.3 §8.3 | 25 | HEAD-1-2-3-NONE, HEAD-1-2-3-BEFORE_T6, HEAD-1-2-3-AFTER_FIRST_COMMIT, HEAD-1-2-3-AFTER_MARKER_BEFORE_APPLIED |
| `stale_plan` — STALE_SUPERSEDED terminal; следующий head продолжает | §7.3 §8.3 | 1 | STALE-HEAD |
| `commit_decision` — Marker+D атомарны; APPLIED из D без re-admission | §7.3 §8.3 | 10 | A22, REPORT-TWO-0-BEFORE_DECISION, REPORT-TWO-0-AFTER_DECISION, REPORT-TWO-0-AFTER_TERMINAL |
| `full_reject` — Полный отказ: один append с кандидатами/отчётами, без D/marker | §7.3 | 31 | A18, REPORT-TWO-0-BEFORE_DECISION, REPORT-TWO-0-AFTER_DECISION, REPORT-TWO-0-AFTER_TERMINAL |
| `batch_recovery` — Все crash-окна и точная пара version/marker | §8.3 | 39 | A05, REPORT-TWO-0-BEFORE_DECISION, REPORT-TWO-0-AFTER_DECISION, REPORT-TWO-0-AFTER_TERMINAL |
| `run_binding` — CAS run до первого вывода; чужой run investigation-only | §0 §7.2 | 19 | INPUT-CONFLICT-same_revision_different_text, INPUT-CONFLICT-same_pair_different_context_hash, INPUT-CONFLICT-same_pair_different_resource_hash, CALL-CRASH-BEFORE_RUNMARKER |
| `provider_log` — PENDING/RECEIVED fsync, ordinal≠attempt, replay byte-identical | §0 §9 | 16 | SELECTOR-unknown_id, SELECTOR-duplicate_id, SELECTOR-wrong_shape, SELECTOR-non_json |
| `goal_dedup` — Четыре компонента; request_window не ключ | §8.3 §17 | 32 | RET-INDEPENDENT-same_support_different_assertions, RET-INDEPENDENT-different_supports_same_node, DEDUP-STATE-none, DEDUP-STATE-request_window |
| `goal_decision` — Решение атомарно с эффектом; created = путь, не узел | §8.3 §17 | 57 | DEDUP-STATE-none, DEDUP-STATE-request_window, DEDUP-STATE-temporal_assertion, DEDUP-STATE-support |
| `goal_dbn` — DB-N общая сериализация с отзывом для NOOP/ABORTED | §8.3 §18 | 28 | GREC-NONE-0-0-0, GREC-NONE-0-0-1, GREC-NONE-0-1-0, GREC-NONE-0-1-1 |
| `goal_recovery` — R0 historical, R1/R2 STALE/LICENSE/NOOP/APPLIED | §8.3 | 28 | GREC-NONE-0-0-0, GREC-NONE-0-0-1, GREC-NONE-0-1-0, GREC-NONE-0-1-1 |
| `goal_license_race` — До PENDING mismatch без GOAL, после GOAL_LICENSE_FAILED | §8.3 §10 | 479 | ORT-00-00, FAT-00-00, ORT-00-01, FAT-00-01 |
| `support_paths` — Любой полный путь достаточен; частичные не склеиваются | §7.4 §8.2 | 70 | A07, OR-N2-00, OR-N2-01, OR-N3-00 |
| `binding_paths` — Отзыв antecedent инвалидирует только зависимые binding paths | §7.3 §8.2 | 14 | A08, RET-OBSERVATION_ROOT-OBSERVATION, RET-OBSERVATION_ROOT-ASSERTION, RET-OBSERVATION_ROOT-BINDING |
| `source_retraction` — Всё observation vs одна версия, audit сохраняется | §8.2 | 24 | A07, A26, RET-OBSERVATION_ROOT-OBSERVATION, RET-OBSERVATION_ROOT-ASSERTION |
| `closure_independence` — Общее R не зависимость, общий W/C factual зависимость | §8.2 | 4 | A07, CLOSURE-R, CLOSURE-W, CLOSURE-C |
| `states` — SEALED только version; outcomes/coverage отдельно от machine state | §8.4 | 41 | A28, T4-0-0-0-0, T4-0-0-0-1, T4-0-0-1-0 |
| `rx` — Stage-isolated prior, только committed/live writes, frozen replay | §2.1 §7.3 | 13 | RX-COMMITTED_LIVE-SRL, RX-COMMITTED_LIVE-T2, RX-COMMITTED_LIVE-T3, RX-SUPERSEDED-SRL |
| `declared_trigger` — Изменение declared read подписка и recompute, не обязательная смена исхода | §1.2 §8.1 | 12 | A26, A27, DECLARED-0, DECLARED-1 |
| `migration` — Open→known явные evidence, новые пути и атомарный visibility switch | §14 §17 | 10 | MIG-NONE, MIG-BEFORE_STORE_COMMIT, MIG-AFTER_STORE_BEFORE_TERMINAL, MIG-AFTER_SUCCESS_RETRACT_V2 |
| `migration_bulk` — Frozen per-source CAS targets, receipt, per-item atomicity | §14 | 8 | MIG-BULK-BEFORE_PLAN, MIG-BULK-AFTER_RESERVE, MIG-BULK-AFTER_ITEM_COMMIT_BEFORE_RECEIPT, MIG-BULK-AFTER_RECEIPT |
| `migration_failure` — Rollback до commit; после commit старые опоры не оживают | §14 | 10 | MIG-NONE, MIG-BEFORE_STORE_COMMIT, MIG-AFTER_STORE_BEFORE_TERMINAL, MIG-AFTER_SUCCESS_RETRACT_V2 |
| `legacy_adapter` — Lossless V2/legacy только representable; ADAPTER_NOT_COVERED | §12 §17 | 6 | ADAPTER-representable_graph, ADAPTER-open_template, ADAPTER-nested_scope, ADAPTER-surface_arg |
| `dsl` — Текст BNF↔JSON AST, precedence, typed emits, closed data-only DSL | §16 | 28 | RES-GRAPH-dependency_cycle, RES-GRAPH-conflicting_entries, RES-GRAPH-unregistered_emit_kind, RES-GRAPH-emit_arity |
| `dsl_limits` — Chars/rules/depth/joins, UNKNOWN не eval, invalid whole release | §16 | 17 | DSL-REJECT-duplicate_stage, DSL-REJECT-missing_reads, DSL-REJECT-unknown_field, DSL-REJECT-unknown_candidate_kind |
| `goal_compile` — WH/YESNO/COUNT/CAUSE/ASSOC/COUNTERFACTUAL разные targets | §6.3 §17 | 15 | A14, A15, A30, A37 |
| `workspace` — Только возбуждённые источники, cold activation, no global scan | §6.3 | 9 | A30, EXACT-none, EXACT-verb, EXACT-role |
| `exact_attestation` — Все lexical/role/scope fields, source scope, no derived write | §6.3 §17 | 8 | EXACT-none, EXACT-verb, EXACT-role, EXACT-scope |
| `numeric_scope` — BoundVar+body+CountLiteral, int bounds, no fake n facts | §6.3 §17 | 34 | LINK-SLOTS-FORALL, LINK-SLOTS-EXISTS, LINK-SLOTS-AT_LEAST_N, LINK-SLOTS-BEFORE_TIME |
| `count_domain` — Distinct M, lower bound, DomainCertificate для exact/atmost | §6.3 §17 | 37 | COUNT-1-NONE, COUNT-1-VALID, COUNT-1-WRONG_BODY, COUNT-1-WRONG_WINDOW |
| `compound_binding` — Полный WH/COUNT scope, QueryVar без AH UID | §6.3 §17.3 | 18 | CERT-ALPHA, BIND-AND-0, BIND-AND-1, BIND-OR-0 |
| `formula_domain` — Alpha-normalized formula certificate и live completeness | §6.3 | 37 | COUNT-1-NONE, COUNT-1-VALID, COUNT-1-WRONG_BODY, COUNT-1-WRONG_WINDOW |
| `ordering_goal` — BEFORE max<min, DURING coverage, no possible overlap proof | §17.3 | 16 | A17, ORDER-BEFORE-16d7c935, ORDER-BEFORE-762c1bfe, ORDER-BEFORE-69e56639 |
| `query_budget` — 1024 combinations, incomplete enumeration не closed domain | §6.3 | 3 | QUERY-BUDGET-1023, QUERY-BUDGET-1024, QUERY-BUDGET-1025 |
| `query_readonly` — Runtime results не facts/versions/markers | §6.3 §17 | 514 | A30, LANG-00-0-bare, LANG-00-0-not, LANG-00-0-possible |
| `oracle_replay` — Exact IDs/diagnostics/structural delta/replay, no learned gold | §11.2 | 4 | META-R_entries_order, META-source_iteration_order, META-constraint_iteration_order, META-replay_provider_bytes |
| `coverage_gate` — G5 unknown corpus ≥500 и пороги; oracle не proof универсальности | §20 | 1 | COVERAGE-NOT-G5 |
| `alpha_scope` — Alpha capture, binder uniqueness, tree/graph roundtrip | §6.2 §17 | 7 | SCOPE-INVALID-free_variable, SCOPE-INVALID-double_binder, SCOPE-INVALID-capture_after_substitution, SCOPE-INVALID-string_restriction |
| `disabled_bridges` — ReportBridgingRule/EventIdentityRule disabled defaults | §2.1 §20 | 2 | DISABLED-ReportBridgingRule, DISABLED-EventIdentityRule |
| `registry_rollback` — Unknown ID/role/support variant rolls back whole transaction | §7.3 §17 | 7 | WRITE-ROLLBACK-unknown_g, WRITE-ROLLBACK-unknown_L, WRITE-ROLLBACK-open_role_mismatch, WRITE-ROLLBACK-GOAL_RUN_ROOT |
| `open_world` — Отсутствие доказательства не явное отрицание | §6.2 §15 | 2 | OWA-ABSENT-POSITIVE, OWA-ABSENT-NEGATIVE |

## Acceptance

| Требование | Кейсы |
|---|---|
| A01 | A01 |
| A02 | A02 |
| A03 | A03 |
| A04 | A04 |
| A05 | A05 |
| A06 | A06 |
| A07 | A07 |
| A08 | A08 |
| A09 | A09, GRD-A, GRD-A-P, GRD-C, GRD-C-A, GRD-C-D, GRD-C-M, GRD-C-P, GRD-C-R, GRD-C-W, GRD-D, GRD-D-A … |
| A10 | A10 |
| A11 | A11 |
| A12 | A12 |
| A13 | A13 |
| A14 | A14 |
| A15 | A15 |
| A16 | A16 |
| A17 | A17 |
| A18 | A18, SIM-01-01, SIM-01-02, SIM-01-03, SIM-01-04, SIM-01-05, SIM-01-06, SIM-01-07, SIM-01-08, SIM-01-09, SIM-01-10, SIM-01-11 … |
| A19 | A19 |
| A20 | A20 |
| A21 | A21 |
| A22 | A22 |
| A23 | A23 |
| A24 | A24 |
| A25 | A25 |
| A26 | A26 |
| A27 | A27 |
| A28 | A28 |
| A29 | A29 |
| A30 | A30 |
| A31 | A31 |
| A32 | A32 |
| A33 | A33 |
| A34 | A34 |
| A35 | A35 |
| A36 | A36 |
| A37 | A37 |
| A38 | A38-NOT, A38-QUOTED |
| A39 | A39, SRC-BLOCK-1-COMPUTATION_LIMIT, SRC-BLOCK-1-PROTOCOL_ERROR, SRC-BLOCK-1-PROVIDER_UNAVAILABLE, SRC-BLOCK-1-RESOURCE_MISSING, SRC-BLOCK-2-COMPUTATION_LIMIT, SRC-BLOCK-2-PROTOCOL_ERROR, SRC-BLOCK-2-PROVIDER_UNAVAILABLE, SRC-BLOCK-2-RESOURCE_MISSING, SRC-BLOCK-3-COMPUTATION_LIMIT, SRC-BLOCK-3-PROTOCOL_ERROR, SRC-BLOCK-3-PROVIDER_UNAVAILABLE … |

## Dry-runs

| Трасса | Кейсов | Примеры ветвей |
|---|---:|---|
| DR1 | 1 | A06 |
| DR2 | 2 | A08, DR2-FULL |
| DR3 | 1 | A05 |
| DR4 | 7 | A01, SOM-INDEPENDENT-EVENT, SOM-INDEPENDENT-PROCESS, SOM-INDEPENDENT-STATE, SOM-INDEPENDENT-TRANSITION, SOM-INDEPENDENT-UNKNOWN |
| DR5 | 1 | DR5-PARTIAL |
| DR6 | 3 | A20, A21, A39 |
| DR7 | 512 | A07, A23, TQ-00-00-0, TQ-00-00-1, TQ-00-01-0, TQ-00-01-1 |
| DR8 | 208 | RET-GOAL_RUN_DERIVED-ASSERTION, RET-GOAL_RUN_DERIVED-BINDING, RET-GOAL_RUN_DERIVED-OBSERVATION, RET-GOAL_RUN_DERIVED-PREMISE, RET-OBSERVATION_AND_DERIVED-ASSERTION, RET-OBSERVATION_AND_DERIVED-BINDING |
| DR9 | 12 | CALL-CRASH-AFTER_PENDING_BEFORE_SEND, CALL-CRASH-AFTER_RECEIVED_BEFORE_VALIDATION, CALL-CRASH-AFTER_RESPONSE_BEFORE_RECEIVED, CALL-CRASH-AFTER_SEND_BEFORE_RESPONSE, CALL-CRASH-AFTER_VALIDATION, CALL-CRASH-BEFORE_RUNMARKER |
| DR10 | 62 | OR-N2-00, OR-N2-01, OR-N3-00, OR-N3-01, OR-N3-02, OR-N3-03 |
| DR11 | 9 | DR11-FULL, WIT-FORALL_INST-0-0, WIT-FORALL_INST-0-1, WIT-FORALL_INST-1-0, WIT-FORALL_INST-1-1, WIT-OR_ELIMINATION-0-0 |
| DR12 | 217 | DR12-FULL, RET-GOAL_RUN_DERIVED-ASSERTION, RET-GOAL_RUN_DERIVED-BINDING, RET-GOAL_RUN_DERIVED-OBSERVATION, RET-GOAL_RUN_DERIVED-PREMISE, RET-OBSERVATION_AND_DERIVED-ASSERTION |
| DR13 | 32 | A18, HEAD-1-2-3-AFTER_FIRST_COMMIT, HEAD-1-2-3-AFTER_MARKER_BEFORE_APPLIED, HEAD-1-2-3-BEFORE_T6, HEAD-1-2-3-NONE, HEAD-1-3-2-AFTER_FIRST_COMMIT |
| DR14 | 1 | PRECHECK-RETRACT |
| DR15 | 3 | PARTIAL-D-CHANGED-0, PARTIAL-D-CHANGED-1, PLAN-E-SHARED |
| DR16 | 736 | DR16-FULL, ORT-00-00, ORT-00-01, ORT-00-02, ORT-00-03, ORT-00-04 |
| DR17 | 20 | FUNC-AFTER, FUNC-AND, FUNC-ASSOCIATION, FUNC-AT_LEAST_N, FUNC-AT_MOST_N, FUNC-BEFORE |
| DR18 | 30 | DEDUP-EVENT-conclusion, DEDUP-EVENT-none, DEDUP-EVENT-request_window, DEDUP-EVENT-rule, DEDUP-EVENT-support, DEDUP-EVENT-temporal_assertion |
| DR19 | 249 | GREC-ABORTED-0-0-0, GREC-ABORTED-0-0-1, GREC-ABORTED-0-1-0, GREC-ABORTED-0-1-1, GREC-ABORTED-1-0-0, GREC-ABORTED-1-0-1 |
| DR20 | 28 | DBN-DECISION_FIRST-ASSERTION, DBN-DECISION_FIRST-SUPPORT, DBN-RETRACTION_FIRST-ASSERTION, DBN-RETRACTION_FIRST-SUPPORT, GREC-ABORTED-0-0-0, GREC-ABORTED-0-0-1 |
| DR21 | 1 | A31 |
| DR22 | 1 | A32 |
| DR23 | 24 | A33, EXACT-absolute_query_token_position, EXACT-dead_proof, EXACT-none, EXACT-role, EXACT-scope |
| DR24 | 2 | A21, A34 |
| DR25 | 6 | A35, SOM-INDEPENDENT-EVENT, SOM-INDEPENDENT-PROCESS, SOM-INDEPENDENT-STATE, SOM-INDEPENDENT-TRANSITION, SOM-INDEPENDENT-UNKNOWN |
| DR26 | 6 | A36, FRAME-EVENT, FRAME-PROCESS, FRAME-STATE, FRAME-TRANSITION, FRAME-UNKNOWN |
| DR27 | 1 | A37 |
| DR28 | 240 | FAT-00-00, FAT-00-01, FAT-00-02, FAT-00-03, FAT-00-04, FAT-00-05 |
| DR29 | 257 | DEDUP-EVENT-conclusion, DEDUP-EVENT-none, DEDUP-EVENT-request_window, DEDUP-EVENT-rule, DEDUP-EVENT-support, DEDUP-EVENT-temporal_assertion |
| DR30 | 73 | DBN-DECISION_FIRST-ASSERTION, DBN-DECISION_FIRST-SUPPORT, DBN-RETRACTION_FIRST-ASSERTION, DBN-RETRACTION_FIRST-SUPPORT, DEDUP-EVENT-conclusion, DEDUP-EVENT-none |
| DR31 | 8 | A12, A38-NOT, A38-QUOTED, SOM-DEPTH-1, SOM-DEPTH-2, SOM-DEPTH-3 |
