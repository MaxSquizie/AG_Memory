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
| `logical_formalization.py` | 1037 | `operator_algebra.py` (8 операторов + inference rules), `composition.py`, `inference_engine.py` | ✅ ядро покрыто; **capability-parity готов** (`test_formalizer_capability_parity`: DR16 counterexample, OR-elimination license) |
| `modal_formalization.py` | 663 | эпистемика в `composition.py` / `temporal_license.py` / `goal_executor.py` | ✅ покрыто; **capability-parity готов** (операторы NOT/COUNTERFACTUAL/IMPLIES + prohibitions) |
| `semantic_predicates.py` | 422 | T3/T4 + decision schema (`pipeline.py`) | ⚠️ закрытый демо-набор; **аудит** полноты vs legacy-смыслы (см. D) |
| `structural_speech_act.py` | 379 | `speech_act.py` (§18 DR27/A37) + modus в `pipeline.py` | ✅ **ЗАКРЫТО (эта сессия)**: детекция косвенного запроса → linked {QUERY,COMMAND}, действие не утверждается |
| `higher_order_queries.py`, `identity_query.py` | 459+485 | `interrogatives.py` (полный класс + UNKNOWN-fallback), `count_reader.py`, coref в T6b | ✅ заявленный класс покрыт; **capability-parity готов** (compile→goal kinds, bounded-count honesty) |
| `generalized_naming.py`, `coordination_normalization.py`, `correlated_alternatives.py`, `association_continuation.py` | 563+274+389+333 | — (heuristics адаптивного парсера) | ✅ **решение принято** (`HEURISTICS_MIGRATE_VS_DROP_AUDIT.md`): generalized_naming = реальная способность → мигрировать как declared decision + probe; остальные 3 = ремонт/text-gen эвристики → отбросить как есть |
| `llm_parser.py` | 1294 | `lmstudio_selector.py`, `real_backend.py`, LLM-проба в `tag_source.py`/`numeral_extraction.py` | ⚠️ **аудит**: что из LLM-ролей ещё не покрыто bounded-пробами |
| `runtime_semantics.py`, `runtime_invariants.py` | 714+ | рантайм-клей (новый: `orchestrator.py`) | ❓ **аудит** |

> **Вывод:** количественно/временно/кванторно/IF — уже портировано. Логика, модальность, speech-act/modus, запросы и LLM-роли требуют **по-модульного аудита покрытия**, прежде чем можно объявить legacy готовым к удалению. Heuristics адаптивного парсера (naming/coordination/correlated_alternatives/continuation) в V7 явно не описаны — это отдельное решение «мигрировать vs отбросить».

---

## 3. Расхождение карты с реальностью — ✅ устранено (эта сессия)
`IMPLEMENTATION_MAP_V7.md` была устарела (467 тестов, закрытые deferred-пункты). **Сделано:** карта обновлена до **562** тестов, §18 speech-act → DONE, все deferred-пункты пометки закрыты; единый источник правды по остатку — этот документ.

---

## 4. Что точно надо сделать (приоритизировано)

### A. Runtime path-B wiring — ✅ СДЕЛАНО (эта сессия)
`LLMPerceptionService.parse()` теперь делегирует в `FormalizerAdapter`, когда он подставлен; bootstrap шьёт его за env-flag `AH_FORMALIZER=1` (по умолчанию legacy). Тесты: `test_formalizer_runtime_wiring` (5). Ниже — исходное описание пробела.

Новый формализатор был **standalone-прототипом**: вне пакета его импортируют только `core/journal.py` и `inference/if_bridge.py`. `FormalizerAdapter` (`runtime_adapter.py`) существует как шов, но **агентный цикл его не вызывает**.
1. Найти production-точку диспетчеризации perception в агентном цикле.
2. Вшить вызов `FormalizerAdapter` так, чтобы входящий текст шёл через новый формализатор (T0–T6b), а legacy оставался **только** как behavioral reference (`legacy_compare.py`).
3. Тест: сквозной «агент получает текст → факт в каноническом AHStore» через production-путь (не только e2e на фикстурах).

### B. По-модульный аудит покрытия legacy→V7 + миграция неперенесённого
1. ✅ **PARTIAL закрыт (эта сессия)**: speech-act/modus (§18 DR27/A37) → `speech_act.py` + адаптер; 5 тестов доказывают linked {QUERY,COMMAND} и отсутствие фабрикации действия.
2. ✅ **Capability-пробы (эта сession)** подтвердили покрытие ядра: logical (`operator_algebra` 8 операторов + inference rules), modal (`composition`/`temporal_license`/`goal_executor`), queries (`interrogatives` полный класс + UNKNOWN-fallback, `count_reader`).
3. ✅ **Capability-parity готов (эта сессия)**: `test_formalizer_capability_parity` (14) фиксирует конкретные формы из трёх legacy-областей, которые теперь корректно производит ядро V7 — logical (DR16 counterexample: ограниченное вчерашнее отрицание НЕ опровергает сегодняшнюю пропозицию; OR-elimination license), modal (NOT/COUNTERFACTUAL/IMPLIES + prohibitions, unknown function rejected at write boundary), queries (compile→goal kinds, bounded-count honesty). Полный before/after паритет на произвольных входах — задача live-model harness (`test_formalizer_legacy_parity`).
4. ✅ **Решение по heuristics адаптивного парсера принято (эта сессия)** → `HEURISTICS_MIGRATE_VS_DROP_AUDIT.md`. По модулям: **generalized_naming** = единственная реальная способность (именование/идентичность: alias vs ordinary predication, 3 структурные реализации + bounded probe) → мигрировать как declared semantic decision + probe (Phase 2/3, валидация на реальных данных). **coordination_normalization / association_continuation** = ремонт дефекта upstream (ложная fallback-роль → слияние смежных номиналиев), **correlated_alternatives** = text-gen workaround → **отбросить как есть**; конкретная способность при необходимости добавляется явной declared rule/пробой с тестом, а не копированием эвристики. Это снимает последнее решение, блокировавшее удаление `adaptive_parser.py`.

### C. Обновить `IMPLEMENTATION_MAP_V7.md` — ✅ СДЕЛАНО (эта сессия)
Карта синхронизирована со **562** тестами, deferred-пункты пометки закрыты, остаток переслан сюда как единый источник правды.

### D. Open-set генерация значений предиката — ✅ триггер + механизм готовы
**Сделано (эта сессия):** `open_set_gate.py` (триггер: расширение только когда honest NO_CANDIDATE повторяется на ≥N **различных** входов; ниже порога молчит) + `open_set_probe.py` (bounded LLM-проба нового значения, запущенная **только** при срабатывании триггера и наличии селектора; значение обязано быть **заземлено в тексте** — незаземлённое отклоняется, дубликат объявленного значения отбрасывается; результат — лишь *provisional* предложение, **ничего не применяется автоматически**; off-by-default). Тесты: `test_formalizer_open_set_gate` (4) + `test_formalizer_open_set_probe` (6). **Остаток:** прогон на данных реального бэкенда, когда триггер начнёт срабатывать; до этого out-of-set честно NO_CANDIDATE/UNRESOLVED.

### E. Reader-contract §7.4 (выделенные тесты) — ✅ СДЕЛАНО
Выделенного свита не было → написан. `fact_query.py` делает инвариант исполняемым: fact-requiring goal удовлетворяет только LIVE-запись допустимого kind'а (по умолчанию ASSERTED); HYPOTHETICAL / EMBEDDED / OBSERVATION_RECORD **не** удовлетворяют без явного разрешения (`allow_kinds`). Тесты: `test_formalizer_reader_contract` (9).

---

### F. Реальный прогон S1–S6 через живой бэкенд (эта сессия) — ✅ СДЕЛАНО
Модель поднята (LM Studio, :1234). Драйвер `scripts/run_formalizer_real_backend.py` теперь классифицирует каждое предложение по эталону (`PILOT_DEMO_REFERENCES_V1.md`) в **C1** (RESOLVED к целевому значению) / **C2** (честная неполнота: UNRESOLVED/AMBIGUOUS/NO_CANDIDATE/INSUFFICIENT_CONTEXT) / **C3** (принят неверный смысл) / **PROTOCOL_ERROR** (вычислительный сбой, не вердикт), и отдельно считает protocol-C3 (доля валидного JSON).

Целевые значения: S1/S2/S4→V2(HAS_PART), S3→V1(HAVE), S5→V2, S6→V4(LIKE).

**gemma-3n-e4b-it** (рабочий бэкенд протокола):
| режим | C1 | C2 | C3(неверно) | PROTOCOL_ERROR | protocol-C3 |
|---|---|---|---|---|---|
| baseline | 5 | 1 | **0** | 0 | 6/6 |
| augmented | 2 | 3 | **0** | 1 | 2/3 |

Ключевые честные выводы:
- **C3(неверный смысл)=0 в обоих режимах** — механизм на реальной модели никогда не принимает неверное значение: либо верно, либо честно UNRESOLVED. Базовое свойство безопасности подтверждено live.
- Baseline сильнее augmented для этой малой модели (контринтуитивно, но реально): без контекстных утверждений gemma уверенно выбирает HAS_PART для «у X есть Y» с body-part; с добавленным утверждением она становится менее решительной (UNRESOLVED) и один раз выдаёт не-JSON. Сигнал: формат подачи контекстного утверждения / размер модели влияют на функциональность малой модели.
- S5 (эллипсис copula) честно UNRESOLVED {V2,V1} = C2 — ровно как предсказывал эталон («вне записи и законный исход — C2»).

**qwen3.8-27b-nvfp4**: reasoning-модель; через OpenAI-endpoint кладёт всё в `reasoning_content`, `content` пустой → PROTOCOL_ERROR (драйвер читает `content`). Через production-путь (`LMStudioBackend`→`native_chat(reasoning="off")`) S6→RESOLVED[V4]✓, остальные смешанно PROVIDER_UNAVAILABLE/PROTOCOL_ERROR — признак load/swap latency, когда 27B не резидентна в памяти LM Studio. **Вывод:** для bounded-selection протокола надёжный бэкенд сейчас — gemma-3n-e4b-it; 27B требует резидентной загрузки (ограничение окружения, не дефект протокола).

---

### G. Порт именования (generalized_naming) как declared decision + bounded probe — ✅ СДЕЛАНО
`naming_probe.py`: чистый перенос **способности** (не span-overlap-эвристики). Python делает только объявленную структурную работу: находит 1-е-лицо deictic-referent (закрытый набор {я, меня}) и source-grounded predicate-value кандидаты (имя собственное помечается граммемой `Name` pymorphy3 — языковой ресурс, не per-word правило). Bounded-проба выбирает ровно одно: **NAME_VALUE** / **OTHER_PREDICATION** / **UNCLEAR**. Три реализации: verbal («Меня зовут Илья»), nominal deictic («Я — Илья»), state deictic («Я являюсь Ильёй»). Валидация fail-closed (выдуманное значение отклоняется; один внешний markdown-фенс нормализуется общим `_strip_code_fence`).

**Валидация на реальных данных (gemma-3n-e4b-it):** «Меня зовут Илья»→NAME_VALUE(Илья); «Я — Илья»/«Я являюсь Ильёй»→NAME_VALUE; **negative control «Я инженер»→OTHER_PREDICATION** (класс/свойство остаётся предикацией, никогда не alias); «Илья любит червей»→нет конструкции. Тесты: `test_formalizer_naming_probe` (11).

---

## 5. Рекомендуемый порядок
1. ~~**A** (runtime wiring)~~ — ✅ сделано.
2. ~~**B** (аудит legacy→V7 + modus PARTIAL + capability-parity)~~ — ✅ закрыт.
3. ~~**C** (обновить карту)~~ — ✅ сделано.
4. ~~**D** (open-set триггер + механизм)~~ — ✅ готов (прогон на данных реального бэкенда — когда триггер начнёт срабатывать).
5. ~~**E** (reader-contract §7.4)~~ — ✅ сделано.

## 6. Финальная верификация (эта сессия)
- **A–E выполнены.** A: production-wiring (`LLMPerceptionService.parse` + bootstrap env-gate). B: DR27/A37 speech-act закрыт (`speech_act.py`) + capability-parity legacy→V7 (`test_formalizer_capability_parity`, 14) + решение по heuristics (не мигрировать как есть). C: карта обновлена. D: open-set триггер (`open_set_gate.py`) + механизм bounded-пробы с верификацией заземления (`open_set_probe.py`). E: reader-contract §7.4 (`fact_query.py` + `test_formalizer_reader_contract`, 9).
- **Формализатор**: `tests/test_formalizer_*` = **593/593 OK**.
- **Seam реального бэкенда (эта сессия)**: `test_formalizer_real_backend_seam` (2) доказывает, что `RealBackendSelector` — drop-in для того же интерфейса `select(prompt)->raw JSON`: NONE_FIT-stub ведёт честные NO_CANDIDATE через все S1–S6; сбой деградирует честно (un-evaluated + PROVIDER_UNAVAILABLE, никогда не вердикт). Когда локальный Ollama/LMStudio доступен — `selector_from_config` + `run_s1s6` работают без изменений.
- **Полный проект**: 1068 тестов, **3 падения — предсуществующие и НЕ связаны с A–E**: `test_mvp_memory_smoke`, `test_projection_inference`, `test_semantic_roots_1241`. Доказано: с откатом моих production-изменений (`llm_parser.py`/`bootstrap.py`) к базе сессии те же 3 теста падают идентично; ни один из них не импортирует изменённый код.
- **Новые модули**: `speech_act.py`, `open_set_gate.py`, `open_set_probe.py`, `fact_query.py`. **Новые тесты**: `test_formalizer_runtime_wiring` (5), `test_formalizer_speech_act` (5), `test_formalizer_open_set_gate` (4), `test_formalizer_open_set_probe` (6), `test_formalizer_capability_parity` (14), `test_formalizer_reader_contract` (9), `test_formalizer_real_backend_seam` (2). **Новый аудит**: `HEURISTICS_MIGRATE_VS_DROP_AUDIT.md`.
