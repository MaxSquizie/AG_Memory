# V7 — карта production реализации

Дата: 2026-10-08. База этой доработки temp: `59fc13ec415809a9b262fd72a0b5ed5594de285a`. Исходный аудит сверял `63790a6a71c59b6bec94da675df0249b87502fa6`. Источник норм: [архитектура V7](FORMALIZER_ARCHITECTURE_V7.md). Полный реестр I01–I38/A01–A05: [отчёт исполнения аудита](audits/AG_MEMORY_TEMP_REMEDIATION_2026-10-08.md).

Карта описывает исходники и реальные вызовы. Она не использует наличие helper либо результаты старых прогонов как доказательство DONE. Тесты в этой работе не читались и не запускались. Все записи «код подключён» требуют поведенческой проверки; G0–G5 PASS не объявляется.

| Контракт | Production путь / durable записи | Состояние и предел |
|---|---|---|
| Один perception writer | `bootstrap` → `LLMPerceptionService.perceive` → `FormalizerAdapter.interpret` → `v7_pipeline.interpret_full` | Native подключён; `parse` — noncommittable preview. Нет adaptive-parser fallback |
| T0/морфология/frame/TP/T4 | native_frontend, syntax_rules, rule_dsl, tp_proposer, seal, ProviderAdapter | Released AST либо textual compiler; whole-variant captures, multi-token lexical units, numeric/time anchors; alternatives до выбора. Surface coverage требует G5 |
| Grammar trace / граница | syntax_rules, resources/schemas/loader/rule_dsl, RESOLUTION/BATCH | Registered Emit JSON Schema + semantic graph/role/arity/read validation; bounded joins без успешного префикса; no eval/callback |
| Пять T3-источников | PredicateSchema/ValueExpansion, R-S/R-V, released+canonical R-X3, declared W/C reads, OpenTemplatePolicy | Реальные read traces; blocked ≠ empty; FULL coverage не измерено |
| Ресурсная граница | `resources/loader`, `resources/release_cli`; `formalizer_release.json`, `formalizer_reviews.json` | Schema/hash/dependency/review pinning. Подписанные данные/coverage не изготовлены; полный CandidateSchema всех типов ещё не подтверждён |
| C/T5 | `native_plan`, `commit_stage`, `t5_batch` | Typed ops, owners/deps, O/C/W gate, mapping refusal. GATE_PRECHECK — диагностика; precheck_refs в D/terminal |
| T6 / partial admission | `AHStoreAdapter.commit_transaction`; BATCH → canonical_unit(marker + D + plan\E) → terminal | Общий head-only порядок, COW/WAL fsync до публикации, stable candidate×candidate/committed reports; crash/race не прогонялись |
| Canonical truth / SOM | `canonical_ledger`, `graph_ops`, native `M/N/G`, SupportRecord, UsageLink | F/S fixed points; per-parent attitude; typed proposition argument — полное N/G-дерево. UNKNOWN attitude не утверждает содержимое; children не экспортируются как отдельные факты. Own proof paths; no node-terminal liveness flag |
| EVENT / STATE | `native_plan`, `goal_channel`; occurrence key / RelationKey | Прямой EVENT per observation/version; derived EVENT per new proof path; STATE shared. §7.6 требует нового G0 |
| Время | native temporal expressions + TimeAssertion; `temporal_license` | No date → no assertion. POINT/EXISTENTIAL/CONTINUOUS, specific support, explicit timezone/anchor, common AND witness. TIME_SCOPE — точная область; TimeLiteral для BEFORE/AFTER/DURING без UsageLink, persistence и runtime comparison. Неизвестный anchor → отказ; нет произвольного времени |
| Goal execution | `goal_queries`, `goal_channel`, `GoalRequest`; PENDING/GOAL_DECISION/terminal | OR_ELIMINATION/FORALL_INST, 4-part path key, R0/R1/R2 и DB-N; APPLIED pair atomic. NativeFormulaGoal сохраняет NOT/AND/OR/XOR и known quantified/modal roots; EXISTS positive join, WH/COUNT, narrow association bridge. CAUSAL, general counterfactual/nested WH/numeric scope остаются PARTIAL |
| Отзыв / reports / audit | adapter retraction methods + `CanonicalLedger.refresh` | Per observation/assertion/binding/ATTITUDE; born-closed reports; event identity/order/completeness. Поведенческое доказательство не запускалось |
| R-X | WRITE_COMMITTED_RX, rx_observability, frozen input snapshot | Stage-isolated immutable content; lexical index, bounded optional retrieval, liveness/cost counters и actual-snapshot profile; benefit/large memory не измерены |
| Provider / run ownership | `provider_call_log`, `provider_adapter`, `run_binding` | Durable CAS; run/ordinal/attempt; PENDING→RECEIVED/FAILED, replay bytes/failure; frozen observation/context/cache snapshot |
| Recovery | `AHStoreAdapter._refresh/recover_from_head`, `goal_channel.recover` | Импорт точного AH snapshot; D restore без readmission; GOAL decision-first; corruption → INTEGRITY_ERROR. Это код, не PASS crash gates |
| Fact/query readers | inference/engine, native_queries/query_bindings, fact_query | Full typed scope, concrete proof/time/conflict; candidate bindings не facts; counterfactual не делегируется WORLD proof. Полнота специальных goals не заявлена |
| Integration / projection | `integration/service`, `projection/agent_context`, naming services | Receipt выключает второй legacy fact writer; commands/queries/SOM не экспортируются как world facts |
| Numeric count reader | CountLiteral, FunctionRegistry, native_plan/queries/query_bindings, certificates | Numeric G и bounds reader; distinct-M lower; exact только с scoped completeness. Полное restricted body не уплощается; aggregate-window CountDomain ещё не задана |
| Identity/ref resolution | coreference.freeze_context/prepare_references/resolve_references, IdentityBinding | Explicit context/window + morphology + grounded bounded selector; no name-based merge; selected support paths отзываются обычным каскадом |
| Миграция release / open→known | migration, run_binding reservations, native T6 | Durable mass plan и resumable per-source receipts; replacement+retirement атомарны на observation, explicit links без alias |
| Лексические единицы | TP/SyntaxRules head_anchor + anchors, R-S anchor_pattern | Raw anchors не подменяются искусственным токеном; known phrase требует отдельного released pattern. Head-only attitude/prior не переносится на фразу |
| Остальные схемы/цели | Контракт §2/§4.2/§6.3/§14/§16/§17.3 | Registered runtime schemas закрыты; CorefPolicy entity references grounded по frozen window. Event identity/report bridging выключены; arbitrary counterfactual/causal/superlative/aggregate count не завершены |

Проверенные в этой работе операции: компиляция Python исходников, импорты ключевых runtime модулей, статическая сверка call sites и `git diff --check`. Никаких результатов тестов/модели/корпуса карта не утверждает.

Точная дельта и остающиеся внешние/семантические блокеры: [пять направлений](audits/AG_MEMORY_TEMP_REMAINING_FIVE_ITEMS_2026-10-08.md).
