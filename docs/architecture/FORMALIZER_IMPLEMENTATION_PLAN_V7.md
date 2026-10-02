# План и структура реализации формализатора (к V7)

Статус: рабочий план. Нормативный контракт — `FORMALIZER_ARCHITECTURE_V7.md` (G0 PASS, заморожен).
Этот документ не переопределяет контракт; он переводит его в инженерные пакеты работ, структуру кода и порядок фаз P0–P4 с воротами G1–G5.

---

## 1. Исходная точка: что уже есть (измерено, не предположено)

Прототип собран аудитом через эру V5 (Rev16/Rev18). Текущее состояние пакета `src/ah/formalizer/`:

| Модуль | Строк | Что реализует | V7-раздел |
|---|---|---|---|
| `state.py` | 345 | Ground, MorphVariant, TokenEvidence, Decision, Diagnostic, Budget, FormalizationState(context_facts) | §1.3/§5 |
| `pipeline.py` | 949 | монолит T0–T4: MorphProvider, SRL-ядро, TD, T2(OP1–OP5), T3, T4, OscillationDetector, bounded_search, run() | §4/§5 |
| `rules.py` | 157 | декларативный реестр SRL-правил (generic evaluator + объявленные правила) | §4.0/§16 |
| `composition.py` | 359 | детерминированный слой композиции: CONNECTIVES_V1, SCOPE_LEXICON_V1, операторы | §6.2 |
| `candidate_ir.py` | 177 | CandidateIR + семантические объекты (ArgumentSpec, PropositionNode, EventFrame) | §3/§15/§16 |
| `selection_protocol.py` | 201 | bounded selection: build_selection_prompt(+contextual_statements), validate_selection_response, DecisionSchema | §5.2 |
| `fake_selector.py` | 138 | FakeSelector.demo(baseline/augmented) с provenance-заметками | §9/§11.1 |

Тесты: **79 зелёных** (phase1=486, contracts_v4=742, selection_protocol=160, rev16=186, audit_rev16=216, audit_rev18=212 строк).

### Gap-карта против V7 (по наличию в коде)

| Компонент V7 | Статус | Фаза |
|---|---|---|
| T0/SRL/TD/TP/T3/T4 (структурное ядро) | ✓ есть (srl/td/tp/t3/t4 по 6 файлов) | P1 (доработка) |
| CandidateIR + семантические объекты | ✓ есть (`candidate_ir.py`) | P1 |
| Слой композиции (операторы, ресурсы) | ◐ частично (`composition.py`; кванторы/вывод нет) | P3 |
| `structural_seal` как отдельная стадия | ✗ нет | P1 |
| Контракт 5 источников T3 + `CandidateSourceTrace` (§5.1) | ✗ не выделен явно | P1 |
| TP-протокол локальных гипотез + валидатор (§4.5/§5.2) | ◐ частично (tp=4 файла, протокол/валидатор не формализованы) | P1 |
| `InterpretationRunBinding` (§0.8/§14) | ✗ нет | P0 |
| `ProviderCallLog` + BudgetSnapshot (§9/§14) | ✗ нет | P0 |
| Канал журнала (append+fsync, два канала) (§7.2/§14) | ◐ зачатки (journal=6 файлов) | P0/P2 |
| EnsureOpenTemplate / RoleRegistry / ProposalPolicy (§14) | ✗ нет | P0 |
| Materialization marker + COMMIT_DECISION (§7.3/§14) | ✗ нет | P0/P2 |
| C-консолидация, T5 batch, T6 single-writer+admission (§7) | ✗ нет | P2 |
| Типы опор (root/structural/derived), SOM (§7.4/§7.5) | ✗ нет | P2 |
| UsageLink layer + S-access/F-visible (§3/§7.5) | ✗ нет | P2 |
| TemporalLedger + TimeAssertions, интервалы (§6.3) | ✗ нет | P2/P3 |
| T6b ревизия/отзыв/recovery (§8) | ✗ нет | P2 |
| Goal-транзакция + GoalExecutor (§6.4) | ✗ нет | P2 |
| Кванторы + inference engine (AND/OR_ELIM/FORALL_INST) + временные лицензии (§6.2/§7.4) | ✗ нет | P3 |
| FunctionRegistry v2 + SupportLedger binding_refs (§14/§7.3) | ✗ нет | P0/P2 |
| R-X store (R-X1/2/3, supersede→STALE) (§5.10-аналог) | ✗ нет в пакете | P2 |

**Вывод:** структурное ядро (P1) на ~80% готово; остаётся формализовать `seal`, контракт 5 источников T3 и TP-протокол. Весь слой коммита/ревизии/целей/времени (P2/P3) — основная оставшаяся постройка.

---

## 2. Целевая структура кода (module map)

Декомпозиция монолита `pipeline.py` на стадии + новые модули P0–P4. Каждый модуль привязан к V7-разделу и статусу.

```
src/ah/formalizer/
├── __init__.py
│  # ── типы и сериализация (§1.3, §3) ──
├── state.py                 # ✓ есть: Ground/MorphVariant/TokenEvidence/Decision/Diagnostic/Budget/FormalizationState
├── ir.py                    # ✗ новый: SemanticGraphCandidate, EventFrame, PropositionNode, UsageLink, Operand(Ref|BoundVar), CoverageStatus
├── canonical.py             # ✗ новый: Ref/RefKind/Domain, FunctionSymbol, hypernode_signature, ensure_function (§15)
│  # ── ресурсы (§2) ──
├── resources/
│   ├── loader.py            # ✗ новый: манифест, подписанный релиз, coverage report (G2), валидация до T0
│   └── registry.py          # ✗ новый: R-V/R-S/RoleRegistry/ScopeLexicon/FunctionRegistry v2/IncompatibilityRules/OpenTemplatePolicy/ProposalPolicy
│  # ── структурный пайплайн (§4) — декомпозиция pipeline.py ──
├── t0_srl.py               # ◐ из pipeline: T0 + SRL (через rules.py)
├── t1_td.py                # ◐ из pipeline: T1 + TD (морфофильтр, ScopeTreeCandidate)
├── t2_frames.py            # ◐ из pipeline: T2 OP1–OP5, MissingArgument, Frame↔Scope↔Clause
├── tp_proposer.py          # ✗ новый: StructureProposalRequest/Reply + детерминированный валидатор (a–f) + SURFACE_ARG (§4.5)
├── seal.py                 # ✗ новый: structural_seal(snapshot_id, structural_hash), closure-валидация, заморозка (§4.3)
│  # ── семантическое разрешение (§5) — декомпозиция pipeline.py ──
├── t3_candidates.py        # ◐ из pipeline: слоты + 5 источников в стабильном порядке + CandidateSourceTrace (§5.1)
├── t4_resolution.py        # ◐ из pipeline: arc-consistency fixpoint + bounded DFS, три условия RESOLVED, осцилляция (§5.3/§5.4)
├── assemble_ir.py          # ◐ из candidate_ir: FormalizerCandidateIR (immutable, единственный выход), closure+coverage
│  # ── протокол селектора и провайдер (§5.2, §9) ──
├── selection_protocol.py   # ✓ есть: bounded selection; расширить LexicalProposalRequest/Reply + TP-валидатор
├── provider_adapter.py     # ✗ новый: ProviderAdapter{select,propose_local} + ProviderCallLog(ordinal/attempt) + BudgetSnapshot (§9)
├── fake_selector.py        # ✓ есть: FakeSelector; расширить до FakeProposer (TP) для тестов
│  # ── консолидация и коммит (§7) ──
├── c_consolidate.py        # ✗ новый: identity-планы/дедуп/каноническая привязка, RelationKey, STATE-дедуп, isolation key (§7.1)
├── t5_batch.py             # ✗ новый: 5 условий (i–v), resolution_log, durable miss, commit eligibility, idempotent by batch_hash (§7.2)
├── t6_commit.py            # ✗ новый: single writer, шаги 1–8, head-only admission, plan\E, COMMIT_DECISION+APPLIED, STALE_SUPERSEDED (§7.3/§6.3)
├── support.py              # ✗ новый: SupportRecord (root/structural/derived), AND_ELIMINATION commit-time, NOT-root own O-ground (§7.4)
├── som.py                  # ✗ новый: материализация неутверждённых структурных операндов + UsageLink layer (§7.5/§3)
│  # ── время и цели (§6.3, §6.4) ──
├── temporal_ledger.py      # ✗ новый: TimeAssertions, POINT/EXISTENTIAL/CONTINUOUS, guaranteed simultaneity, conflict contract (§6.3)
├── goal_executor.py        # ✗ новый: append-only derived N/G, OR_ELIMINATION/FORALL_INST on-demand, GOAL_DECISION, DB-N race (§6.4)
│  # ── ревизия/отзыв/восстановление (§8) ──
├── t6b_revision.py         # ✗ новый: триггеры, пересчёт видимости, атомарная смена версии, таблицы переходов, crash recovery drain (§8)
│  # ── адаптивный кэш (§5.10-аналог) ──
├── rx_cache.py             # ✗ новый: один store, stage-dependent reads R-X1/2/3, supersede→STALE без удаления
│  # ── store abstraction (R1): один интерфейс, две реализации ──
├── store_interface.py      # ✗ новый: StoreInterface — append_journal / read_global_head / commit_txn(ops+marker+D) / append_terminal / retract / recover_from_head (§7.3/§8.3)
├── memory_store.py         # ✗ новый: test double того же интерфейса; проверяет ТОЛЬКО чистые решения (head-only admission, E/plan\E, terminal outcome), НЕ атомарность и recovery-from-D
├── ah_adapter.py           # ✗ новый (P0): минимальный AH-адаптер того же StoreInterface — append журнала, чтение global head, атомарная запись plan\E+marker+D, статусный отзыв; полный формализатор не требуется
```

### AH-side интеграционная поверхность (P0 workstream, §12 `required_ah_changes`)

Живут в ядре AH (`src/ah/core/`, `src/ah/model/`), не в formalizer. P0 создаёт/адаптирует:

| Изменение | Назначение | V7 |
|---|---|---|
| `journal_channel` | append-only + fsync, два канала (наблюдения / resolution_log) | §7.2/§14 |
| `materialization_marker` | маркер (observation_id, version) в той же транзакции, что и AH-элементы | §7.3/§14 |
| `commit_decision_record` | COMMIT_DECISION D атомарно с маркером; recovery дописывает ровно один APPLIED из D | §6.3/§7.3 |
| `goal_decision_record` | GOAL_DECISION{goal_run_id, outcome}; R0 различает APPLIED/APPLIED_NOOP | §6.4/§14 |
| `retraction_protocol` | статусные переходы ledger без физического удаления; отзыв по assertion_id | §8/§14 |
| `function_registry_v2` | отклонение неизвестных ID (REGISTRY_REJECT); роли = порядок операндов + commutativity | §6.2/§15/§14 |
| `support_ledger_binding_refs` | add_root/add_derived_support; живость пути по premises + binding_refs[] | §7.3/§7.4/§14 |
| `temporal_ledger` | TimeAssertions, две оси provenance source×support, эффективная видимость | §6.3/§14 |
| `run_marker_provider_call_log` | InterpretationRunBinding (CAS) + ProviderCallLog PENDING→RECEIVED | §0.8/§9/§14 |
| `incompatibility_rules_release` | версионированный ресурс, семантика отсутствия, INTERVAL_BOUNDARY_UNKNOWN | §2.1/§6.3 |
| `rx_store` | один физический store, stage-dependent reads, supersede→STALE | §5.10-аналог/§14 |
| `ensure_open_template` | изолированный T с isolation key, semantic_status=UNLINKED, EXACT_ATTESTATION | §7.1/§14 |
| `role_registry_proposal_provenance` | RoleRegistry (EXPERIENCER), отклонение недоказанных alias | §4.5/§14 |
| `usage_link_layer` | kind=ATTITUDE/OPERATOR, MaterializeUsageLink + RetractUsageLink | §3/§7.5/§14 |

---

## 3. Фазовый план P0–P4 (work packages)

Фазы и их минимальная достаточность — по §12/§11.1. Полный вертикальный прогон A01–A39/DR1–DR31 — ворот **после** всех стадий (G3/G4), не требование P1.

### P0 — Compatibility foundation → **ворот G1**
Цель: AH-side целевые интерфейсы + spine детерминизма/replay + **зафиксированный store-контракт (StoreInterface)**, на которых стоят все следующие фазы. Сквозных A/DR-случаев нет; доказательство = адаптерные тесты G1. Полный формализатор в P0 не нужен.

| WP | Содержание | Модули | V7 |
|---|---|---|---|
| WP0.1 | InterpretationRunBinding: атомарный CAS на (observation_id, version) до TP/T3; recovery повторяет canonical_run_id; чужой run_id → investigation-only | provider_adapter + AH `run_marker_provider_call_log` | §0.8/§14 |
| WP0.2 | ProviderCallLog (PENDING→RECEIVED ordinal/attempt, fsync) + BudgetSnapshot (tp_calls/lexical_calls/max_nodes/edges/depth/tokens); ProviderAdapter{select,propose_local} | provider_adapter.py | §9/§14 |
| WP0.3 | Канал журнала: append-only+fsync; T5 pre-commit записи + терминальные исходы; два канала (наблюдения / resolution_log) | AH `journal_channel` | §7.2/§14 |
| WP0.4 | Новые контракты: EnsureOpenTemplate + RoleRegistry(EXPERIENCER) + ProposalPolicy/OpenTemplatePolicy; isolation key; REGISTRY_REJECT на write boundary | resources/registry.py + AH ensure_open_template/role_registry/function_registry_v2 | §7.1/§14 |
| WP0.5 | Materialization marker + COMMIT_DECISION record: маркер в той же транзакции, что и AH-элементы; idempotent recommit по batch_hash | AH materialization_marker/commit_decision_record | §7.3/§14 |
| WP0.6 | Адаптерные тесты G1: legacy_roundtrip, v2_integration, idempotent_recommit, open_template_isolation, known_mapping_failure, proposal_validation, concurrent_run_binding, unresolved_replay, crash_recovery | tests/oracle/adapters | §12/§20(G1) |
| WP0.7 | StoreInterface (общий контракт): append_journal / read_global_head / commit_txn(ops+marker+D атомарно) / append_terminal / retract / recover_from_head; + memory_store double для чистых решений | store_interface.py, memory_store.py | §7.3/§8.3 |
| WP0.8 | Минимальный AH-адаптер того же StoreInterface: append журнала, чтение global head, атомарная запись plan\E+marker+D, статусный отзыв (полный формализатор не требуется) | ah_adapter.py + AH journal/marker/ledger | §7.3/§8.3/§14 |

**Статус реализации (по состоянию на текущий коммит, измерено):**
- ✅ WP0.1 `run_binding.py` (InterpretationRunBinding CAS); ✅ WP0.2 `provider_call_log.py` + `provider_adapter.py` (BudgetSnapshot, ProviderAdapter{select,propose_local}, replay/INTEGRITY_ERROR); ✅ WP0.4 `resources/registry.py` (RoleRegistry обязательные роли, ProposalPolicy/OpenTemplatePolicy, EnsureOpenTemplate isolation key, REGISTRY_REJECT/OPEN_TEMPLATE_INVALID на write boundary); ✅ WP0.7 `store_interface.py` + `memory_store.py`; ✅ WP0.8 `ah_adapter.py`.
- ✅ WP0.3 — два канала (observation / resolution_log): явная независимость + единый глобальный admission order покрыты `TestTwoChannelJournal`.
- ◐ WP0.5 — контракт маркера материализации + COMMIT_DECISION D атомен в `store_interface.commit_transaction`/`recover_from_head`; реальная AH-side интеграция (materialization_marker/commit_decision_record) отнесена к G1/P2.
- ◐ WP0.6 — `tests/test_formalizer_g1_adapters.py`: готовы 5 из 9 (concurrent_run_binding, idempotent_recommit, unresolved_replay, open_template_isolation, crash_recovery на реальном файле); 4 (legacy_roundtrip, v2_integration, known_mapping_failure, proposal_validation) требуют C/T6 и отнесены к P2.

### P1 — Structural pipeline T0–TP–T4 (расширение существующего ядра)
Статус: ✅ завершено (WP1.1–WP1.6). `seal.py`, `t3_candidates.py`, `tp_proposer.py`, `t4_resolution.py`, `candidate_ir.py`, `oracle.py` + тесты; A-случаи исполняемы через oracle harness.

| WP | Содержание | Модули | V7 |
|---|---|---|---|
| WP1.1 | `structural_seal` как отдельная стадия: structural_hash, closure-валидация всех ссылок, заморозка Clause/Frame/Scope/Reference/edges для T3/T4/C; INTEGRITY_ERROR на незамкнутой ссылке | seal.py (из pipeline) | §4.3 |
| WP1.2 | Контракт 5 источников T3 + `CandidateSourceTrace` {frame_id,slot_id,source_id:1..5,status,candidate_ids,reason}: стабильный порядок, NOT_APPLICABLE с причиной, CHECKED_EMPTY vs BLOCKED, NONE_FIT не выбирает произвольный T | t3_candidates.py (из pipeline) | §5.1 |
| WP1.3 | TP-протокол: StructureProposalRequest/Reply + детерминированный валидатор (a–f), SURFACE_ARG, budget pre-check; FakeProposer для тестов | tp_proposer.py, selection_protocol(расш.), fake_selector(FakeProposer) | §4.5/§5.2 |
| WP1.4 | T4 финализация: arc-consistency до fixpoint + bounded DFS в стабильном порядке (cluster_id,slot_id,candidate_id); три условия RESOLVED; per-value AMBIGUOUS else UNRESOLVED+NO_GROUNDED_CANDIDATE; NO_CANDIDATE только после 5 терминальных traces; осцилляция = повтор состояния (§5.4) | t4_resolution.py (из pipeline) | §5.3/§5.4 |
| WP1.5 | assemble FormalizerCandidateIR: immutable единственный выход, closure + CoverageStatus(FULL/OPEN/PARTIAL/NONE), surface_role_count | assemble_ir.py (из candidate_ir) | §3/§1.3 |
| WP1.6 | Oracle harness skeleton (§11.2): схема OracleCase + правила сравнения (id-множества, diagnostics multiset, forbidden conclusions, state-delta по canonical hash); прогон применимых P1-случаев A02/A10/A16–A20/A25/A28/A29/DR5–DR6 на FakeSelector/FakeProposer | tests/oracle/* | §11.2/§11.1 |

Приёмка: частичный G3 (P1-применимые A/DR) + доказанный replay через ProviderCallLog.

### P2 — Commit & revision C/T5/T6/T6b + goal + temporal (основная постройка)
Статус: ◐ (WP2.1–WP2.4 готовы). Самая большая фаза; даёт вертикальные трассы DR1–DR31.

| WP | Содержание | Модули | V7 |
|---|---|---|---|
| WP2.1 ✅ | C-консолидация: identity-планы/дедуп/каноническая привязка; RelationKey=(S,роли,value); STATE-временная дедуп (EVENT/UNKNOWN не сливаются); OPEN_LEXICAL isolation key (переживает re-analysis, не коллайдит кросс-наблюдения); CANONICAL_MAPPING_MISSING блокирует фрагмент (не обходится open path) | c_consolidate.py + test_formalizer_c_consolidate.py (11 тестов) | §7.1 |
| WP2.2 ✅ | T5 batch + журнал: 5 условий (i–v) incl. truth-ground O/C/W; resolution_log на несостоявшемся условии (по номеру); durable miss при NO_CANDIDATE; commit eligibility через InterpretationRunBinding (INTEGRITY_ERROR / investigation-only); marker early-refusal; idempotent по batch_hash | t5_batch.py + test_formalizer_t5_batch.py (10 тестов) | §7.2 |
| WP2.3 ✅ | T6 single-writer claim/admission: PENDING_ADMISSION_ORDER (меньший seq, ничего не пишется); idempotent no-op; marker match→idempotent / mismatch→INTEGRITY_ERROR+REJECTED_COMMIT_ELIGIBILITY; foreign run_id→REJECTED_COMMIT_ELIGIBILITY без AH; STALE_SUPERSEDED только mark_stale; drain_order head-ascending skip-terminal; plan\E/terminal — t6_core.py | t6_admission.py + test_formalizer_t6_admission.py (8 тестов) | §7.3 |
| WP2.4 ✅ | Опоры + SOM-инвариант: add_root_support только O/C/W (R/D/M/A/P → InvalidFactGround); add_derived_support валидна пока живы premises; F-visible vs S-accessible (итеративные fixpoint, cycle-safe); retract → каскад SUPERSEDED орфанированных asserted + структурных операндов; независимый путь выживает; som_violations | support_som.py + test_formalizer_support_som.py (10 тестов) | §7.4/§7.5 |
| WP2.5 | SOM + UsageLink layer: неутверждённые структурные операнды как типизированные N/G/M без truth-support; ATTITUDE vs OPERATOR links; S-access/F-visible; MaterializeUsageLink/RetractUsageLink | som.py, ir.py | §7.5/§3 |
| WP2.6 | TemporalLedger + TimeAssertions: POINT/EXISTENTIAL(по умолч.)/CONTINUOUS; таблица guaranteed simultaneity; conflict contract (IncompatibilityRule+одновременность); двухуровневый отзыв (наблюдение vs смерть пути) | temporal_ledger.py | §6.3 |
| WP2.7 | T6b ревизия/отзыв/recovery: триггеры, пересчёт видимости по путям, атомарная смена видимой версии, таблицы переходов состояний, crash recovery drain от head'а | t6b_revision.py | §8 |
| WP2.8 | Goal-транзакция + GoalExecutor: append-only derived N/G; OR_ELIMINATION/FORALL_INST on-demand (без новой версии/SetMarker); GOAL_DECISION record; DB-N race; временные лицензии | goal_executor.py | §6.4 |
| WP2.9 | **Crash-stop runs на AH — единственный прогон, засчитывающий коммит/recovery:** те же сценарии с остановками после T5 / после D-транзакции / до APPLIED; проверка атомарности marker+D и recovery-from-D (§7.3/§8.3). Результаты memory double НЕ засчитываются для G4 | ah_adapter.py, tests/oracle/crash | §7.3/§8.3 |

Приёмка: **G3** (ораклы A01–A39) + **G4** (вертикальные трассы DR1–DR31, включая crash points). Коммит и recovery засчитываются только по WP2.9 на AH; зелёные юнит-тесты на memory double G4 не заменяют.

### P3 — Full §6 composition + replay + legacy comparison
Статус: `composition.py` есть, но кванторы/inference engine/временные лицензии отсутствуют.

| WP | Содержание | Модули | V7 |
|---|---|---|---|
| WP3.1 | Алгебра операторов: полная таблица (NOT/AND/OR/XOR/IMPLIES/POSSIBLE/NECESSARY/COUNTERFACTUAL/ASSOCIATION) — scope-построение, каноническая G-форма, правила вывода + запреты; FunctionRegistry v2 с commutativity и порядком аргументов | composition.py, canonical.py, resources/registry.py | §6.2/§15 |
| WP3.2 | Кванторы: α-нормализация (pre-order x0,x1..), EVERY/SOME/NONE/числовые канонические формы; инстанцирование только по запросу (не при коммите); closed domain для числовых притязаний | composition.py, goal_executor.py | §6.2 |
| WP3.3 | Inference engine + временные лицензии: AND/OR_ELIMINATION/FORALL_INST с таблицами лицензий; производные TimeAssertions в goal-транзакции; OR_ELIMINATION_INCOMPLETE/TEMPORAL_MISMATCH | composition.py, temporal_ledger.py, goal_executor.py | §7.4/§6.3 |
| WP3.4 | Replay-детерминизм end-to-end: идентичный вход + canonical_run_id → идентичный выход через весь пайплайн; StageTimingLog для budget-исходов | provider_adapter.py, tests/oracle | §0.8/§9 |
| WP3.5 | Поведенческое сравнение с legacy `adaptive_parser.py` (только как поведенческий эталон, не безусловный reference) | tests/comparison | §12 |

Приёмка: завершение **G4** + доказанная replay-инвариантность.

### P4 — Real provider + generalization → **ворот G5**
| WP | Содержание | Модули | V7 |
|---|---|---|---|
| WP4.1 | Подключить реальный локальный LLM-бэкенд (Ollama/LMStudio) через ProviderAdapter{select,propose_local}; прогон S1–S6 + A-случаев с C3-метрикой реального селектора | provider_adapter.py (реальная реализация) | §9/§20(G5) |
| WP4.2 | Корпус обобщения: ≥500 невидимых входов (≥100 nonfinite/impersonal/nominal, 100 unfamiliar lexicon, 100 scope/modus/discourse, 100 paraphrase/temporal); экспертная разметка; **до** прогона зафиксировать release/model_key/prompts/budgets/code/corpus SHA256 и запретить правки SyntaxRules/ScopeLexicon/графовых операций | tests/oracle/g5_corpus | §20(G5) |
| WP4.3 | Регрессия без example-specific patches: ≥95% FULL/OPEN кандидат, ≥95% gold-структур выживают до seal, 0 ложных asserted facts, 0 правок механизма под пример | tests/oracle/g5_report | §20(G5) |

Приёмка: **G5 PASS** (инженерные пороги).

---

## 4. Критический путь и зависимости

```
G0 (PASS, готово)
   │
   ▼
P0 ──► G1 (adapter tests)          [spine: InterpretationRunBinding + ProviderCallLog]
   │            ▲
   │            │ (oracle harness WC1 + resource loader WC2 стартуют параллельно с P0/P1)
   ▼
P1 ──► частичный G3 (P1-случаи)    [seal + 5-source T3 + TP protocol]
   │
   ▼
P2 ──► G3 (A01–A39) + G4 (DR1–DR31)  [C/T5/T6/T6b + goal + temporal — самая большая]
   │
   ▼
P3 ──► завершение G4              [full §6 composition + replay + legacy comparison]
   │
   ▼
P4 ──► G5 (generalization)        [real provider + ≥500 unseen corpus]
```

Порядок жёсткий: P2 не тестируется против реального store, пока P0 не дал journal/marker/COMMIT_DECISION/run-binding. P3 кванторы/вывод зависят от P2 goal-транзакции и TemporalLedger (временные лицензии). P4 зависит от всего выше + доступного бэкенда.

---

## 5. Поперечные workstreams (параллельно фазам)

| WS | Содержание | Старт |
|---|---|---|
| WC1 Oracle harness (§11.2) | Спин тестов: OracleCase + правила сравнения; исполняет A/DR-случаи и сверяет state-delta по canonical hash, diagnostics multiset, forbidden conclusions, crash points | P0/P1 (растёт до P4) |
| WC2 Resource release pipeline (G2) | Подписанные релизы + coverage reports для R-V/R-S/RoleRegistry/ScopeLexicon/FunctionRegistry v2/IncompatibilityRules/OpenTemplatePolicy/ProposalPolicy; loader валидирует до T0, несовпадение → RESOURCE_MISSING | P1 (ворот G2 перед P3/P4) |
| WC3 Determinism/replay infra (§0.8/§9) | InterpretationRunBinding + ProviderCallLog + StageTimingLog; используется всеми стадиями и oracle | P0 |

---

## 6. Риски и открытые решения

1. **AH-интеграционная поверхность (14 required_ah_changes)** — крупнейший одиночный риск. Коммитная логика P2 не тестируется против реального store, пока P0 не дал адаптеры.
   *Митигация (R1 решено):* AH-контракт фиксируется сразу в P0 (StoreInterface + минимальный AH-адаптер); in-memory double того же интерфейса — только быстрый двойник для чистых решений. Атомарность «marker+D» и recovery-from-D доказываются ТОЛЬКО прогоном на AH с остановками (P2), не юнит-тестами.
2. **Временная семантика (§6.3)** — самая intricate часть (interval simultaneity, лицензии элиминации).
   *Митигация:* canary-ораклы DR7/DR12/DR16/DR28–DR30 до обобщения; смешанные датированные/недатированные premises → UNKNOWN по умолчанию.
3. **Декомпозиция монолита `pipeline.py` (949 строк)** на стадии без поломки 79 зелёных тестов.
   *Митигация:* инкрементально в P1 — выносить стадию за раз, каждый шаг держит suite зелёным.
4. **Доступность реального бэкенда** для P4 (Ollama/LMStudio).
5. **R1 решено:** фиксировать AH-контракт сразу (StoreInterface + минимальный AH-адаптер в P0), а не портировать готовый in-memory store. Память — быстрый тестовый двойник того же интерфейса для чистых решений; транзакционные гарантии (атомарность marker+D, recovery-from-D) засчитываются только прогоном на AH с остановками после T5 / после D-транзакции / до APPLIED. Это сохраняет скорость разработки, не подменяя G1/G4 зелёными юнит-тестами.

---

## 7. Немедленные следующие шаги

R1 решено (см. §6 п.5): AH-контракт фиксируется сразу, память — двойник для чистых решений.

**Выполнено в текущем коммите:** WP0.1/0.2/0.3/0.4/0.7/0.8 (spine детерминизма + store-контракт + два канала), весь P1 (WP1.1–WP1.6) и skeleton oracle harness (WC1), **WP2.1** (C-консолидация), **WP2.2** (T5 batch + журнал), **WP2.3** (T6 claim/admission) и **WP2.4** (опоры/SOM). 308 тест зелёных.

**Осталось до G1:**
1. **WP0.6 (остаток)** — 4 оставшихся G1-адаптерных теста (§12/§20): legacy_roundtrip, v2_integration, known_mapping_failure, proposal_validation — все требуют C/T6 и пишутся в P2. Готовы уже: concurrent_run_binding, idempotent_recommit, unresolved_replay, open_template_isolation, crash_recovery.
2. **WP0.5 (AH-side)** — реальная интеграция маркера/COMMIT_DECISION в AHStore + crash-stop прогоны (WP2.9); контракт уже атомен в `store_interface`.
3. **P2 (остаток)** — WP2.5–WP2.9: temporal/T6b/goal + crash-stop runs; вертикальные трассы DR1–DR31. (WP2.1 C-консолидация, WP2.2 T5 batch, WP2.3 T6 claim/admission и WP2.4 опоры/SOM готовы.)
