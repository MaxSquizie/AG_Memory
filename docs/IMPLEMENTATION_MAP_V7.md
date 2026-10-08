# V7 — карта production реализации

Дата: 2026-10-08. База последующего прохода temp: `bc820791f02479edd326d49f04d0fda01db99bf6` + исправления текущего коммита. Исходный аудит сверял `63790a6a71c59b6bec94da675df0249b87502fa6`. Источник норм: [архитектура V7](FORMALIZER_ARCHITECTURE_V7.md). Полный реестр I01–I38/A01–A05: [отчёт исполнения аудита](audits/AG_MEMORY_TEMP_REMEDIATION_2026-10-08.md).

Карта описывает исходники и реальные вызовы. Она не использует наличие helper либо результаты старых прогонов как доказательство DONE. Тесты в этой работе не читались и не запускались. Все записи «код подключён» требуют поведенческой проверки; G0–G5 PASS не объявляется.

| Контракт | Production путь / durable записи | Состояние и предел |
|---|---|---|
| Один perception writer | `bootstrap` → `LLMPerceptionService.perceive` → `FormalizerAdapter.interpret` → `v7_pipeline.interpret_full` | Native подключён; `parse` — noncommittable preview. Нет adaptive-parser fallback |
| T0/морфология/frame/TP/T4 | `native_frontend`, `syntax_rules.run_srl/propose_graphs`, `pipeline.t0/t1/td`, `tp_proposer`, `seal`, `ProviderAdapter` | Native SRL/T2 — released data-only AST, whole-variant captures до T3. Пересекающиеся структуры не выбираются по priority; TP для gaps/ambiguity, singleton closed sense может разрешиться без модели. Preview grammar не участвует |
| Grammar trace / граница | `syntax_rules`, `state.syntax_trace`, `seal`, RESOLUTION/BATCH | Feature/constraint/AST результаты с UNKNOWN; bounded matching и отказ от неполного префикса. Только объявленные immutable schema lookups; no callbacks/eval. Текстовый BNF parser/все CandidateSchema остаются PARTIAL |
| Пять T3-источников | PredicateSchema/ValueExpansion, R-S/R-V, released+canonical R-X3, declared W/C reads, OpenTemplatePolicy | Реальные read traces; blocked ≠ empty; FULL coverage не измерено |
| Ресурсная граница | `resources/loader`, `resources/release_cli`; `formalizer_release.json`, `formalizer_reviews.json` | Schema/hash/dependency/review pinning. Подписанные данные/coverage не изготовлены; полный CandidateSchema всех типов ещё не подтверждён |
| C/T5 | `native_plan`, `commit_stage`, `t5_batch` | Typed ops, owners/deps, O/C/W gate, mapping refusal. GATE_PRECHECK — диагностика; precheck_refs в D/terminal |
| T6 / partial admission | `AHStoreAdapter.commit_transaction`; BATCH → canonical_unit(marker + D + plan\E) → terminal | Общий head-only порядок, COW/WAL fsync до публикации, stable candidate×candidate/committed reports; crash/race не прогонялись |
| Canonical truth / SOM | `canonical_ledger`, `graph_ops`, native `M/N/G`, SupportRecord, UsageLink | F/S fixed points; per-parent attitude; typed proposition argument — полное N/G-дерево. UNKNOWN attitude не утверждает содержимое; children не экспортируются как отдельные факты. Own proof paths; no node-terminal liveness flag |
| EVENT / STATE | `native_plan`, `goal_channel`; occurrence key / RelationKey | Прямой EVENT per observation/version; derived EVENT per new proof path; STATE shared. §7.6 требует нового G0 |
| Время | native temporal expressions + TimeAssertion; `temporal_license` | No date → no assertion. POINT/EXISTENTIAL/CONTINUOUS, specific support, explicit timezone/anchor, common AND witness. Сложные temporal/order surfaces частично покрыты |
| Goal execution | `goal_queries`, `goal_channel`, `GoalRequest`; PENDING/GOAL_DECISION/terminal | OR_ELIMINATION/FORALL_INST, 4-part path key, R0/R1/R2 и DB-N; APPLIED pair atomic. Все виды GoalSpec ещё не портированы |
| Отзыв / reports / audit | adapter retraction methods + `CanonicalLedger.refresh` | Per observation/assertion/binding/ATTITUDE; born-closed reports; event identity/order/completeness. Поведенческое доказательство не запускалось |
| R-X | `WRITE_COMMITTED_RX`, `read_cache`, frozen run input snapshot | Committed support-bound stage-isolated entries; STALE при смерти пути; prior only, никаких cache truth grounds |
| Provider / run ownership | `provider_call_log`, `provider_adapter`, `run_binding` | Durable CAS; run/ordinal/attempt; PENDING→RECEIVED/FAILED, replay bytes/failure; frozen observation/context/cache snapshot |
| Recovery | `AHStoreAdapter._refresh/recover_from_head`, `goal_channel.recover` | Импорт точного AH snapshot; D restore без readmission; GOAL decision-first; corruption → INTEGRITY_ERROR. Это код, не PASS crash gates |
| Fact/query readers | `inference/engine`, `inference/formula`, `formalizer/fact_query` | Native proof/time visibility и conflict refs; unsupported query scope → diagnostic/UNKNOWN. Full legacy parity не заявлен |
| Integration / projection | `integration/service`, `projection/agent_context`, naming services | Receipt выключает второй legacy fact writer; commands/queries/SOM не экспортируются как world facts |
| Numeric count reader | `count_reader` | Direction AT_MOST_N исправлено; end-to-end numeric scope ещё требует порта |
| Полные grammar schemas / migration / широкие цели | Целевой контракт архитектуры | PARTIAL; native SyntaxRules AST подключён, но текстовый BNF/all CandidateSchema, temporal operands, migration и все query surfaces остаются отдельным объёмом |

Проверенные в этой работе операции: компиляция Python исходников, импорты ключевых runtime модулей, статическая сверка call sites и `git diff --check`. Никаких результатов тестов/модели/корпуса карта не утверждает.
