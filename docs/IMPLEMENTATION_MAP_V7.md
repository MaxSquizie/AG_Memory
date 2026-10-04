# Карта соответствия V7 → код (статус реализации)

Нормативный документ: `docs/FORMALIZER_ARCHITECTURE_V7.md` (V4 устарел).
Пакет: `src/ah/formalizer/`. Базовый прогон (2026-10): unittest **558 OK** по формализатору + pytest composition/formalization 246 passed / 1 xfailed.

> **Единый источник правды по остатку:** `docs/FORMALIZER_STATUS_AND_REMAINING_WORK.md` (runtime wiring, legacy→V7 аудит, open-set генерация). Эта карта — по-§ статус; устаревшие deferred-пункты ниже закрыты.

Статусы: **DONE** — реализовано и покрыто тестами; **PARTIAL** — ядро есть, часть контракта не закрыта; **DEFERRED** — отложено по V7 (явно), план ниже.

## §0–§2: границы, каналы, ресурсы
| Раздел | Модуль(и) | Тест(ы) | Статус |
|---|---|---|---|
| §0.5 три писателя / §7.3 single-writer | `commit_stage.py`, `t6_admission.py`, `t6_core.py` | test_formalizer_commit_stage, _t6_admission | DONE |
| §0.8 run binding / CAS / replay | `run_binding.py`, `replay.py`, `provider_call_log.py` | test_formalizer_run_and_provider, _replay | DONE |
| §1.3 provenance R/C/D/M/A/P/W | `state.py`, `t4_sources`(тест) | test_formalizer_t4_sources | DONE |
| §2.1 resource registry / signed release | `store_interface.py`, `memory_store.py` | test_formalizer_store_p0, _registry | DONE |
| §2.3 miss-аккумулятор (покрытие ≠ механизм) | `coverage.py`, `oracle.py` | test_formalizer_coverage, _oracle | **DONE** (CoverageReport: honest_gaps vs provider_failures) |

## §3–§5: T1/T2/T3, источники кандидатов, R-X
| Раздел | Модуль(и) | Тест(ы) | Статус |
|---|---|---|---|
| §4.x TP / structural seal | `tp_proposer.py`, `seal.py` | test_formalizer_tp_proposer, _seal | DONE |
| §5.1 5 источников кандидатов (исчерпанность) | `t3_sources.py` | test_formalizer_t3_sources | DONE |
| §5.2/§5.4 bounded selection / oscillation | `selection_protocol.py`, `pipeline.py` | test_formalizer_selection_protocol, _phase1 | DONE |
| §5.10 FormalizationCache (R-X) | `rx_cache.py` | test_formalizer_rx_cache | DONE |

## §6: граф, операторы, запросы, goal-транзакция
| Раздел | Модуль(и) | Тест(ы) | Статус |
|---|---|---|---|
| §6.2 operator algebra / FunctionRegistry v2 | `operator_algebra.py`, `graph_ops.py` | test_formalizer_operator_algebra, _op_graph | DONE |
| §6.2 quantifiers (alpha-norm, on-demand inst) | `quantifiers.py` | test_formalizer_quantifiers | DONE |
| §6.3 temporal ledger / TimeAssertion | `temporal.py`, `inference_engine.py` | test_formalizer_temporal, _inference_engine | DONE |
| §6.3/§7.4 temporal license algebra | `temporal_license.py` | test_formalizer_temporal_license | DONE |
| §6.4 goal transaction (append-only) | `goal_executor.py`, `recovery.py` | test_formalizer_goal_executor, _crash_stop | DONE |
| **§6.3 bounded-count reader** («как минимум N») | `count_reader.py` (новый) | test_formalizer_query_surfaces | **DEFERRED→DONE (этот ход)** |
| **§6.3 широкий реестр интеррогативов** | `interrogatives.py` (новый) | test_formalizer_query_surfaces | **DEFERRED→DONE (этот ход)** |
| §6.2/§15 IF-области / вложенные (clause-детекция) | `clause_detection.py` (новый) | test_formalizer_clause_detection | **DONE** |
| §6.2/§15 источник тегов (pymorphy3 + LLM-проба) | `tag_source.py` (новый) | test_formalizer_tag_source | **DONE** |
| §6.2/§6.3 IF-ответ (склейка clause→goal path) | `if_query.py` (новый, exp.) | test_formalizer_if_query | **DONE (этот ход)** |

## §7: commit, retraction, recovery
| Раздел | Модуль(и) | Тест(ы) | Статус |
|---|---|---|---|
| §7.1 C-consolidation (T4→commit) | `c_consolidate.py` | test_formalizer_c_consolidate | DONE |
| §7.2 T5 batch + journal / commit gate | `t5_batch.py` | test_formalizer_t5_batch | DONE |
| §7.3/§8.x retraction cascade, two-level | `retraction.py`, `t6b_revision.py`, `temporal_adapter.py` | test_formalizer_retraction, _t6b_revision, _temporal_adapter | DONE |
| §7.4/§7.5 support ledger + SOM invariant | `support_som.py`, `usage_layer.py` | test_formalizer_support_som, _audit_rev18 | DONE |

## §9–§20: replay, oracle, интеграция, границы
| Раздел | Модуль(и) | Тест(ы) | Статус |
|---|---|---|---|
| §9 determinism / StageTimingLog | `replay.py` | test_formalizer_replay | DONE |
| §11.2 acceptance oracle (machine-readable) | `oracle.py` | test_formalizer_oracle, _g1_adapters | DONE |
| §12 legacy behavioral comparison | `legacy_compare.py` | test_formalizer_legacy_compare, _legacy_parity | DONE |
| §14 runtime adapter / path B seam | `runtime_adapter.py`, `ah_adapter.py`, `integration_ir.py` | test_formalizer_runtime_adapter, _ah_adapter, _integration_e2e | DONE |
| §15 FunctionRegistry / serialization | `operator_algebra.py`, `ir_to_graph.py` | test_formalizer_ir_to_graph, _registry | DONE |
| §17 goal channel end-to-end | `goal_executor.py`, `inference_engine.py` | test_formalizer_goal_executor, e2e suites | DONE |
| §18 speech-act / modus (DR27/A37) | `speech_act.py`, `pipeline.py` (modus), composition | test_formalizer_speech_act, test_ambiguity_semantic_composition_02529 | **DONE** (эта сессия: косвенный запрос → linked {QUERY,COMMAND}, действие не утверждается) |

## Отложено → план реализации (все пункты ниже закрыты; остаток — в статус-доке)
1. ~~**Bounded-count reader**~~ (§6.3/§17.3) — **DONE**: `count_reader.py` + test_formalizer_query_surfaces. читать утверждённый bound квантора и рендерить «как минимум N» / «ровно N» / «не более N»; UNKNOWN+reason без bound / без DomainCertificate для EXACTLY_N/AT_MOST_N. → `count_reader.py` (реализуется в этом ходе).
2. **Широкий реестр интеррогативов** (§6.3): полный request_kind → goal kind + answer surface с UNKNOWN-fallback; запрет произвольного EXISTS; IF требует clause-детекции. → `interrogatives.py` (реализуется в этом ходе).
3. ~~Clause-детекция~~ — **DONE (этот ход)**: `clause_detection.py` + `tests/test_formalizer_clause_detection.py`. Границы clauses из морф-тегов (подчинительный союз / относительное местоимение) + объявленная пунктуация как разделитель; untagged fallback = маленький объявленный набор однозначных subordinators (`если/когда/хотя/пока/чтобы`) + stem `котор-`; неоднозначное «что» — только по тегу. Парные границы (antecedent, consequent) для IMPLIES/TD; single-clause → честно UNRESOLVED. Сквозной тест: IF компилируется только при реальных парных границах.
   - **DONE (этот ход)** — `tag_source.py` + `tests/test_formalizer_tag_source.py`: адаптер источника тегов. pymorphy3 (+ опциональная bounded LLM-проба) → `list[Token]` с тегами для `detect_clauses`. Основано на фактах pymorphy3: однозначные subordinators (`если/хотя/чтобы/дабы`) → авто `CONJ_SUB`; относительные (`который` = ADJF+Subx) → `RELPRON`; сочинительные (`и/а/но`) → plain CONJ (не открывают); неоднозначные (`когда/пока/что`) → только через LLM-пробу, иначе честно content. Тег кэшируется на слово; пунктуация сохраняется как отдельные разделители.
   - **DONE (этот ход)** — `if_query.py` + `tests/test_formalizer_if_query.py`: экспериментальная Phase-1 поверхность IF. Склейка: текст → `TagSource.detect()` (pymorphy3) → парные границы `if_pairs()` → гейт через `interrogatives.compile` → оценка по injectable fact-store. Честные исходы: UNBOUND (нет пары — single-clause), NOT_ASSERTED (премисса не установлена), INSUFFICIENT (консеквент не выведен), ANSWERED (оба установлены, holds=True). Соединительное слово (`если/когда/...`) — объявленный структурный маркер: снимается перед матчем по store, но сохраняется в отчёте. Осознанно отделена от канала OR_ELIM/FORALL_INST GoalExecutor (у него свой temporal-контракт) — чтобы валидировать изолированно и позже встроить в production GoalMode без переписывания.
   - **DONE (этот ход)** — `coverage.py` + `tests/test_formalizer_coverage.py`: явный miss-аккумулятор §2.3. `summarize(states) -> CoverageReport` агрегирует батч: `honest_gaps` (NO_CANDIDATE / COMPUTATION_LIMIT / REFERENCE_UNKNOWN / STRUCTURE_NOT_COVERED — механизм сработал, ресурса нет → сигнал «расширить здесь», а не выдумать ответ) отделены от `provider_failures` (PROVIDER_UNAVAILABLE / PROTOCOL_ERROR — инфраструктура, НЕ семантический gap; §0.8: сбой модели никогда не становится AMBIGUOUS). `coverage_ratio` = доля предложений с доказанным исходом предиката.
   - **DONE (этот ход)** — live-верификация на реальной модели: `scripts/verify_gemma.py` + `tests/test_formalizer_gemma_e2e.py`. Тот же путь `run()`, но selector = `LMStudioSelector(model="gemma-3n-e4b-it")`. E2E-тест network-guarded (skip, если LM Studio/модель недоступны) и проверяет инварианты независимо от качества модели: RESOLVED никогда не выдумывается (нужен выбор + value-specific positive ground); infra-sбой оставляет решение не-оценённым (`outcome=None`, lifecycle OPEN), а не подменяется семантическим вердиктом. Живой прогон S1–S6 + произвольных примеров печатает §2.3 отчёт.
   - Остаток: интеграция `if_query` в production GoalMode (экспериментальная поверхность готова, склейка с production-каналом — позже).
4. ~~**Явный miss-аккумулятор**~~ (§2.3) — **DONE (этот ход)**: `coverage.py` + тесты (см. выше).
