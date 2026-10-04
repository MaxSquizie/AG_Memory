# Формализатор V7 — фактический статус и точный список остатка

**Дата:** 2026-10-04. **База:** git HEAD + working tree; полный прогон `unittest` по формализатору = **548/548 OK**.
Норматив: `docs/FORMALIZER_ARCHITECTURE_V7.md`. По-§ карта: `docs/IMPLEMENTATION_MAP_V7.md` (частично устарела — см. §3 ниже).

Документ отвечает на три вопроса: (1) что реально сделано по рантайму и формализатору; (2) что из **старого** формализатора уже переиспользовано для нового, а что ещё только в legacy-пути; (3) что **точно надо сделать** дальше.

---

## 1. Фактический статус (подтверждено прогоном + историей коммитов)

### 1.1 Новый формализатор (`src/ah/formalizer/`, ~40 модулей) — реализован и покрыт тестами
| Блок | Модули | Статус |
|---|---|---|
| Phase 1 T0–T4 (механизм без LLM) | `pipeline.py`, `state.py`, `selection_protocol.py` | ✅ DONE + e2e |
| Источники кандидатов / R-X | `t3_sources.py`, `rx_cache.py` | ✅ DONE |
| TP / structural seal | `tp_proposer.py`, `seal.py` | ✅ DONE |
| Граф: операторы, кванторы, FunctionRegistry v2 | `operator_algebra.py`, `quantifiers.py`, `graph_ops.py`, `ir_to_graph.py` | ✅ DONE |
| Время / coref / modality / goal-транзакция | `temporal*.py`, `inference_engine.py`, `goal_executor.py`, `recovery.py` | ✅ DONE |
| C-consolidation, T5 batch+journal, T6 single-writer, T6b retraction | `c_consolidate.py`, `t5_batch.py`, `t6_admission.py`, `t6_core.py`, `t6b_revision.py`, `retraction.py` | ✅ DONE |
| Support ledger + SOM invariant | `support_som.py`, `usage_layer.py` | ✅ DONE |
| Store contract / memory double / AH adapter | `store_interface.py`, `memory_store.py`, `ah_adapter.py` | ✅ DONE |
| Replay determinism, provider call log, run binding (CAS) | `replay.py`, `provider_call_log.py`, `run_binding.py` | ✅ DONE |
| Oracle A01–A39 (machine-readable), coverage §2.3 | `oracle.py`, `coverage.py` | ✅ DONE |
| Numeral extraction (seed + bounded LLM probe → AT_LEAST_N) | `numeral_extraction.py` | ✅ DONE |
| IF / clause-детекция / tag source / interrogatives / count reader | `if_query.py`, `clause_detection.py`, `tag_source.py`, `interrogatives.py`, `count_reader.py` | ✅ DONE (exp. surface) |
| Legacy behavioral comparison (§12/WP3.5) | `legacy_compare.py` | ✅ DONE |
| Runtime seam (path B) | `runtime_adapter.py`, `ah_adapter.py`, `integration_ir.py` | ⚠️ seam есть, **не вызывается агентным циклом** |

### 1.2 Реальный LLM-бэкенд — подключён и прогнан (эта сессия)
- `lmstudio_selector.py` / `real_backend.py`: тот же интерфейс `select(prompt)->raw JSON`, что у `FakeSelector`.
- Live S1–S6 на `gemma-3n-e4b-it` (LM Studio, temp 0): S3→RESOLVED V1(HAVE), S6→RESOLVED V4(LIKE); S1/S2/S4/S5 UNRESOLVED; coverage 0.22, provider_failures=0 на демо-наборе. Зафиксировано в `docs/PHASE1_VALIDATION_REPORT.md`.

### 1.3 IF-интеграция — сделана (эта сессия)
`src/ah/inference/if_bridge.py`: `if_to_perception()` + `if_verdict_from_goal_result()`, вшиты в production GoalMode (`goal_mode.py`). Сквозной тест: raw text → PROVED. Коммиты `b6b2ce9` / `52476fd` / `d9f40e9`.

---

## 2. Старый формализатор → новый: что уже переиспользовано, а что только в legacy

Legacy-стек живёт в `src/ah/perception/*_formalization.py` + `src/ah/integration/formalization.py` (~7000+ строк). Это то, что V7 заменяет (path B).

| Старый модуль (`perception/`) | Объём | Новый V7-аналог | Статус портирования |
|---|---|---|---|
| `quantifier_formalization.py` | 660 | `quantifiers.py` | ✅ портировано (alpha-norm, on-demand inst) |
| `temporal_mode_formalization.py`, `temporal_scope_formalization.py` | 224+ | `temporal*.py`, `inference_engine.py` | ✅ портировано (ledger, licenses, TimeAssertion) |
| `logical_formalization.py` | 1037 | `operator_algebra.py` (8 операторов + inference rules), `composition.py`, `inference_engine.py` | ✅ ядро покрыто; **остаток**: parity-тест полного набора правил вывода legacy |
| `modal_formalization.py` | 663 | эпистемика в `composition.py` / `temporal_license.py` / `goal_executor.py` | ✅ покрыто (модальные лицензии); **остаток**: dedicated regression на legacy-модалках |
| `semantic_predicates.py` | 422 | T3/T4 + decision schema (`pipeline.py`) | ⚠️ закрытый демо-набор; **аудит** полноты vs legacy-смыслы (см. D) |
| `structural_speech_act.py` | 379 | `speech_act.py` (§18 DR27/A37) + modus в `pipeline.py` | ✅ **ЗАКРЫТО (эта сессия)**: детекция косвенного запроса → linked {QUERY,COMMAND}, действие не утверждается |
| `higher_order_queries.py`, `identity_query.py` | 459+485 | `interrogatives.py` (полный класс + UNKNOWN-fallback), `count_reader.py`, coref в T6b | ✅ заявленный класс покрыт; **остаток**: parity-проверка конкретных legacy-форм запросов/идентичности |
| `generalized_naming.py`, `coordination_normalization.py`, `correlated_alternatives.py`, `association_continuation.py` | 563+274+389+333 | — (heuristics адаптивного парсера) | ❓ **не в скопе V7 явно** — решить: мигрировать или сознательно отбросить при удалении legacy |
| `llm_parser.py` | 1294 | `lmstudio_selector.py`, `real_backend.py`, LLM-проба в `tag_source.py`/`numeral_extraction.py` | ⚠️ **аудит**: что из LLM-ролей ещё не покрыто bounded-пробами |
| `runtime_semantics.py`, `runtime_invariants.py` | 714+ | рантайм-клей (новый: `orchestrator.py`) | ❓ **аудит** |

> **Вывод:** количественно/временно/кванторно/IF — уже портировано. Логика, модальность, speech-act/modus, запросы и LLM-роли требуют **по-модульного аудита покрытия**, прежде чем можно объявить legacy готовым к удалению. Heuristics адаптивного парсера (naming/coordination/correlated_alternatives/continuation) в V7 явно не описаны — это отдельное решение «мигрировать vs отбросить».

---

## 3. Расхождение карты с реальностью
`IMPLEMENTATION_MAP_V7.md` устарела: указывает **467** тестов (факт **548**), а её список «Отложено → план» (#1 count_reader, #2 interrogatives, #3 clause/tag/if_query/coverage) полностью закрыт. **Действие:** обновить карту до актуального состояния и перенести сюда единый источник правды по остатку (этот документ).

---

## 4. Что точно надо сделать (приоритизировано)

### A. Runtime path-B wiring — главный пробел
Новый формализатор пока **standalone-прототип**: вне пакета его импортируют только `core/journal.py` и `inference/if_bridge.py`. `FormalizerAdapter` (`runtime_adapter.py`) существует как шов, но **агентный цикл его не вызывает**.
1. Найти production-точку диспетчеризации perception в агентном цикле.
2. Вшить вызов `FormalizerAdapter` так, чтобы входящий текст шёл через новый формализатор (T0–T6b), а legacy оставался **только** как behavioral reference (`legacy_compare.py`).
3. Тест: сквозной «агент получает текст → факт в каноническом AHStore» через production-путь (не только e2e на фикстурах).

### B. По-модульный аудит покрытия legacy→V7 + миграция неперенесённого
1. ✅ **PARTIAL закрыт (эта сессия)**: speech-act/modus (§18 DR27/A37) → `speech_act.py` + адаптер; 5 тестов доказывают linked {QUERY,COMMAND} и отсутствие фабрикации действия.
2. ✅ **Capability-пробы (эта сession)** подтвердили покрытие ядра: logical (`operator_algebra` 8 операторов + inference rules), modal (`composition`/`temporal_license`/`goal_executor`), queries (`interrogatives` полный класс + UNKNOWN-fallback, `count_reader`).
3. **Остаток B**: dedicated parity-тесты на конкретных legacy-формах (полный набор правил вывода logical_formalization; конкретные модалки modal_formalization; специфичные запросы higher_order_queries/identity_query) — довести «ядро покрыто» до доказанного паритета.
4. **Решение по heuristics адаптивного парсера** (generalized_naming / coordination_normalization / correlated_alternatives / association_continuation): **не мигрировать в V7 как есть**. Это эвристики *поведения* legacy-парсера, а не формальные способности; V7 намеренно заменяет их declared structural rules + bounded LLM-пробами. При удалении `adaptive_parser.py` эти модули отбрасываются; если конкретная способность окажется нужной — она добавляется как явная declared rule/проба с тестом, а не копируется эвристика.

### C. Обновить `IMPLEMENTATION_MAP_V7.md`
Синхронизировать со 548 тестами, пометить закрытые deferred-пункты, переслать остаток на этот документ как единый источник правды.

### D. Open-set генерация значений предиката (отложено)
Триггер по V7 — накопленные miss reports (`coverage.py` уже их агрегирует). Реализовать bounded LLM-пробу нового значения только после накопления данных; до этого out-of-set честно NO_CANDIDATE/UNRESOLVED.

### E. Reader-contract §7.4 (выделенные тесты)
Проверить наличие выделенного свита: HYPOTHETICAL / EMBEDDED / ObservationRecord **не** должны удовлетворять fact-requiring goals без явного разрешения. Если нет — написать.

---

## 5. Рекомендуемый порядок
1. **A** (runtime wiring) — превращает прототип в работающий компонент; даёт реальный сквозной путь.
2. **B** (аудит legacy→V7 + modus PARTIAL) — необходимое условие для удаления `adaptive_parser.py`.
3. **C** (обновить карту) — быстро, держит документацию честной.
4. **E**, затем **D** (по накопленным данным).
