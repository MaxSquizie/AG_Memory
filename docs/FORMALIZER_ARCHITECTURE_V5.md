# Техническая спецификация формализатора АГ-памяти (V5)

Статус: **полная техническая спецификация, rev16** — углубление FORMALIZER_ARCHITECTURE_V4 (rev2–8). Rev9 закрывает дефекты dry-run D1–D10; Rev10 — финальный аудит; Rev11 — декларативный редизайн T1 MentionBuilder (HeadRule/ExpansionRule, типы mention, самоаудит); Rev12 — семантический слой композиции: DependencyComposition (TD), лексические смыслы, единая ScopeOperator-архитектура, coreference, WorldKnowledge, время, запросы, UnknownReason, EvidencePriorityPolicy, learning loop (§15); Rev13 — правки stress-audita: локальная привязка операторов (target_slot_ref/local_variable_id/restriction_ref), OperatorCompositionEngine (единое разрешение вложенности), enum DecisionType, версионная CoreferencePolicy, граница multiword-единиц, разведение UnknownReason, набор TemporalOperators с anchor-зависимостью, domain-dependent EvidencePriorityPolicy, декларативный QueryKind {WH, YESNO, COUNT, CAUSAL}, acceptance-сценарии (§15.11); Rev13a — метрика depth_rank + детерминированный tie-break, межклаузные TEMPORAL-якоря, неизменяемость WK записей C-утверждением, DecisionType в §6; Rev13b — обязательный provenance layer: ProvenanceRecord + правило P1/P2 + I23 (§2.5); Rev14 — универсальный semantic core без частных языковых правил: CandidateIR и граница Local Formalization / Semantic Consolidation (§2.6–2.7), PropositionNode/SemanticExpression, ArgumentType, EventFrame, Attribute model, запрет phrase-level identity, existential unknowns, SemanticGraphCandidate (§16); Rev14.1 — аудит после Semantic Core (без расширения функциональности): immutability CandidateIR + I25, CandidateStatus и confidence≠truth value (§2.3), epistemic layer PropositionNode (§16.1), слот PredicateSchema (§16.9), детализация QueryFrame (§15.7), acceptance-проверки A–D (§16.10); Rev14.2 — Semantic Core Closure Audit: 6 acceptance-тестов против M1/M2 без новых специальных правил, закрыты пробелы G1 (триггерный паттерн existential + producer ExistentialRef), G2 (коммит и epistemics в T5), G3 (ответственность за instantiation квантованных propositions) (§16.11); Rev15 — Structural Reconstruction Layer (SRL): отдельная lifecycle-стадия между T0 и T1, структурные кандидаты TokenHypothesis/BoundaryCandidate/ClauseCandidate/EllipsisCandidate/MissingArgumentCandidate + интеграция ReferenceCandidate с grounds-категориями, каналы памяти до семантического выбора, I26–I29, acceptance-тесты (§17); Rev16 — стресс-аудит после SRL: границы ответственности (H1–H3), traceability (версии ресурсов в provenance Decision/Candidate), структурное закрытие I30, каналы памяти и межнаблюдательное окно, LLM-граница, end-to-end acceptance A–E × версии памяти (§18). V5 не меняет ни одного
замороженного контракта V4; он заменяет декларативные описания алгоритмами. Там, где V4 говорит «что должно быть
верно», V5 говорит «какой именно алгоритм это реализует». При расхождении формулировок V5 приоритетен как более
конкретный документ; при противоречии контрактам — контракт V4 остаётся в силе и расхождение считается дефектом V5.

Критерий достаточности: инженер, читающий только этот документ + исходные типы AG_Memory (§2.1–2.5 V4), реализует
каждый компонент без самостоятельных архитектурных решений. Остатки выбора зафиксированы как значения по умолчанию
в §13 (Open questions) и помечены **[default]**.

Метки ограничений: **[A]** — фундаментальный контракт; **[B]** — ограничение Фазы 1 (может сняться после данных);
**[C]** — демонстрационное ограничение (S1–S6, демо-схема). Полные списки — §1.3.

---

## 1. Scope документа

### 1.1 Что специфицируется
Полный путь формализации RAW INPUT → T0 → T1 → T2 → T3 → T4 → T5 → T6 → T6b → материализация в AH: структуры входа/выхода
каждого этапа, алгоритмы, state machine решений, модель кандидатов, механизм кластеров и constraint-распространения,
граница LLM (контракт, не подключение), интеграция с каноническим слоем, модель ревизии, обработка отказов.

### 1.2 Что НЕ входит
Подключение реального бэкенда; расширение FrameGen за OP1–OP5 [B]; открытое множество значений предикатов (отложено до
miss-отчётов); скалярные импликатуры (отдельный workstream); числовые значения бюджетов (после данных, §13).

### 1.3 Классификация ограничений

**A) Фундаментальный контракт [A]** — не снимается:
1. Две независимые системы состояний: жизненный цикл решения и семантический outcome; RESOLVED ≠ COMMITTED.
2. Валидатор протокола выдаёт только верифицированный ПРОТОКОЛЬНЫЙ исход; семантический исход присуждает исключительно T4.
3. Скрытого перехода candidate → fact не существует: единственный путь — §2.5, каждая стрелка — процедура с владельцем и записью аудита.
4. Запись в канонический слой — только через integrate_plan (единственная граница записи); FunctionRegistry отклоняет неизвестные ID на этой границе.
5. Два независимых канала персистентности: журнал наблюдений (append-only, write-through + fsync) и канал материализации (атомарный маркер в том же комите).
6. Идентичность наблюдения = hash(source_id + span); сверка каналов — по ТОЧНОЙ паре (observation_id, interpretation_version).
7. Отзыв двух уровней не взаимозаменяем: уровень наблюдения всегда первый; уровень элемента — только когда отозваны ВСЕ его опоры уровня наблюдения и независимого полного доказательства нет.
8. Осцилляция = повторение состояния без новых оснований R/C/D/A (сигнатура по содержанию); M-повторение не размораживает; идемпотентное подтверждение того же значения осцилляцией не является.
9. AMBIGUOUS требует по-значенческого положительного основания у КАЖДОГО выжившего кандидата; slot-level основание (value=None) не обосновывает ни одно конкретное значение.
10. Типы оснований R/C/D/M/A с анти-утечками: A не ссылается на собственное решение; модельные догадки не переименовываются в D; повторение идентичного M не добавляет доказательности и не является новым основанием для ревизии.
11. Коммит — единственный момент видимости канонического слоя; четыре условия §9.2.
12. Читатели: HYPOTHETICAL/EMBEDDED/ObservationRecord не удовлетворяют fact-целям без явного допуска; SUPERSEDED фильтруется по умолчанию, STALE-выводы не используются как опора.

**B) Ограничения Фазы 1 [B]** — снимаются после данных:
1. Грамматика FrameGen = конечный набор OP1–OP5; остальное → STRUCTURE_NOT_COVERED (честная неполнота).
2. LLM — только bounded selection по замкнутому множеству; произвольной генерации нет.
3. Однопоточный детерминированный порядок обхода (воспроизводимость); параллелизация запрещена до доказательства идентичного порядка перечисления.
4. Закрытое множество кандидатов решения выводится объявленным правилом генерации схемы; id вне множества = протокольная ошибка.
5. R-X: три канала чтения по этапам (R-X1/R-X2/R-X3), запись только из закоммиченных решений, нет права запрещать новые интерпретации.
6. Тихого score-cutoff нет: все парсы ресурса сохраняются; лимит ресурса → диагностика.
7. Бессоюзное вложение без связующей словоформы — вне скоупа (OP4/OP5 — объявленные заглушки).
8. Модель единиц: RawInput → SentenceUnit (T0) → ClauseUnit + Mention (T1) → FrameCandidate (T2); границы clause и NP-grouping — объявленные правила (§5.1–5.3) [B8].
9. Scope-операторы детектируются только объявленными surface-паттернами; неподдерживаемый оператор → SCOPE_NOT_COVERED, молчаливая потеря запрещена (§5.2 п.10) [B9].
10. NONE_FIT → UNRESOLVED + VALUE_OUT_OF_SET + miss-отчёт; повторный расширенный запрос запрещён (§5.4 п.5); открытое множество значений отложено (Q7b).
11. Материализация scope-операторов в AH: только N.meta["scope"] + журнал наблюдений; канонические G/BoundVar — Фаза 2 (§9.3) [B11].
12. Coreference — first-class стадия TD (§15.4): ReferenceCandidate с ограничениями, основаниями и AMBIGUOUS как легитимным исходом; demo v1 ships минимальный salience-набор [C]; унификация в AH при коммите через merge_identity (V4 §7.2) [B12].
13. Полярность рамки (POS/NEG) вычисляется из copula-леммы «нет» или объявленных отрицателей и персистится в N.meta["polarity"]; отрицательных значений в demo v1 нет — NEG-рамка при только положительных кандидатах → NONE_FIT, а не молчаливое положительное значение [B13].
14. Декларативная расширяемость T1: новые типы голов / mention-типы / паттерны расширения = новая декларация HeadRule/ExpansionRule или запись ресурса; ядровой алгоритм (оценка правил, сборка кандидатов) не изменяется [B14]; дефолтный ruleset demo v1 — §5.2 п.9d [C].
15. Числовые значения бюджетов — после данных Фазы 1 [default: llm_limit=8, search_step_limit=200 на фрагмент].

**C) Демонстрационные ограничения [C]** — параметры эксперимента, не архитектура:
1. Закрытый набор значений {HAVE, HAS_PART, LOCATIVE, LIKE} в демо-схеме v1 (вне набора → NO_CANDIDATE + miss).
2. Конвенция HAS_PART(whole, part) — нотация эталона.
3. Сентенции S1–S6 и порядок пилота; baseline/augmented с контекстными утверждениями F1/F2/F3.
4. Английский протокол bounded selection (язык промпта/ответа).
5. Прототипный FrameGen разрешён исключительно для валидации V4/V5 до полного freeze.

---

## 2. Термины и модели данных

### 2.1 Реестр объектов: владелец, мутаторы, неизменяемость

Для каждого объекта зафиксированы: **creator** (единственный создатель), **mutators** (кто может изменять),
**immutable fields** (поля, не изменяемые после создания — изменение = новый объект с новой версией).

| Объект | Creator | Mutators | Immutable fields | Версионируется как |
|---|---|---|---|---|
| RawInput {input_id, source_id, text, received_at} | входной адаптер | — (immutable) | все | не версионируется; повторный ввод = новый input_id |
| TokenSpan {span_id, input_id, start, end, surface} | T0 | — | все | не версионируется |
| SentenceUnit {unit_id, input_id, start, end, terminal_punct?} | T0 (§5.1 п.5) | — | все | не версионируется; пересчитывается при новом входе |
| ClauseUnit {clause_id, unit_id, spans[], connective_span?, inherited_spans[]} | T1 (§5.2 п.8) | — | clause_id, unit_id | не версионируется; пересчитывается при новой версии свидетельств |
| HeadRule {rule_id, version, source (RESOURCE\|SCHEMA), activation (декларативный предикат по признакам R1 + объявленной локальной структуре), head_type, compatibility constraints, priority} | декларация ресурса/схемы — вне пайплайна | — (immutable; новое правило = новая запись) | все | версия ruleset (часть formalizer_schema_version) |
| HeadCandidate {candidate_id, clause_id, span(s), head_type, rule_id, evidence (refs MorphVariant + совпавшие признаки), constraints{} (напр. case_index), source_links[]} | T1 HeadCandidateGenerator (§5.2 п.9a) | — | все | не версионируется; пересчитывается при новой версии свидетельств |
| ExpansionRule {rule_id, version, source, applicable head_types, pattern (последовательность feature-предикатов по смежным span'ам + направление), produces (members\|constraint\|альтернативный анализ)} | декларация ресурса/схемы — вне пайплайна | — (immutable) | все | версия ruleset |
| MentionCandidate {mention_id, clause_id, mention_type ∈ объявленный набор (§5.2 п.9c), head (ref HeadCandidate), member_spans[], constraints{} (напр. number_constraint), case_index?, provenance {head_rule_id, expansion_rules_applied[]}} | T1 MentionCandidateBuilder (§5.2 п.9b) | — | все | не версионируется; пересчитывается при новой версии свидетельств |
| SurfaceOperatorCandidate {candidate_id, mention_id, op_type ∈ объявленные OperatorTypes (§15.3), pattern_id, source=SCHEMA} | T1 (surface-паттерны §5.2 п.10) | TD / T3,T4 (статус scope-решения) | все | не версионируется; кандидат типа SCOPE_OP (§2.3) |
| OperatorAttachmentCandidate {attachment_id, surface_op_id, target (frame_ref\|slot_ref\|anchor_ref), depth_rank (близость триггера к предикату в ClauseUnit), evidence[], provenance} | TD OperatorCompositionEngine (§15.3 п.2) | T3,T4 | все | не версионируется; пересчитывается при новых свидетельствах |
| ScopeConstraintGraph {graph_id, unit_id, nodes (surface_op ids), edges (INNER/OUTER/SAME_FRAME по объявленным правилам композиции §15.3 п.2)} | TD OperatorCompositionEngine (§15.3 п.2) | T3,T4 | все | не версионируется; пересчитывается при новых свидетельствах |
| ScopeTreeCandidate {tree_id, graph_id, root, nodes (ScopeOperatorNode с полями локальной привязки), provenance} | TD OperatorCompositionEngine (§15.3 п.2) | T3,T4 (статус scope-решения) / AH N.meta["scope"] [B11] | все | InterpretationVersion; каноническая сериализация round-trip |
| DecisionType ∈ {PREDICATE_VALUE, TEMPLATE_SELECTION, SCOPE, REFERENCE, TEMPORAL, QUERY; Rev15 декларирует BOUNDARY и ELLIPSIS} — замкнутый enum (§6); расширение = декларация схемы | реестр решений | T3/T4 | все | версия decision schema |
| ScopeOperatorBinding {binding_id, operator (op_id), anchor_mention, restriction_span?, governed_frame_id?} | T4 (при RESOLVED scope-решении); в batch — T5 | — | все | InterpretationVersion; в Фазе 1 материализуется только как N.meta["scope"] [B11] (§9.3) |
| ScopeOperatorNode {operator_id, operator_type ∈ объявленный набор (§15.3), operand (ref: frame\|slot\|под-узел), scope_span(s), binding (ScopeOperatorBinding), provenance} | T1 (leaf по surface-паттернам §5.2 п.10) + TD (вложенность §15.3) | — | все | InterpretationVersion; сериализуется в N.meta["scope"] [B11] |
| DependencyRule {rule_id, version, source, activation (feature-предикаты по паре mention/token + объявленная локальная структура), relation_type ∈ закрытый структурный набор (§15.1), direction, constraints} | декларация ресурса/схемы — вне пайплайна | — (immutable) | все | версия ruleset |
| DependencyCandidate {dependency_id, source_mention/span, target_mention/span, relation_type, direction, evidence (R1-признаки + совпадение правила), provenance {rule_id}, constraints{}} | TD DependencyComposer (§5.2b/§15.1) | — | все | не версионируется; пересчитывается при новой версии свидетельств |
| LexicalResource record {record_id, version, lemma, sense_index, semantic_type, syntactic compatibility (POS-паттерны), typical government} + LexSenseCandidate {sense_id, lemma, sense_index, semantic_type, constraints{}, source (resource id+version), provenance} | ресурс (версионный) / T1 п.6b (§15.2) | — | все | версия lexical_resource |
| ReferenceCandidate {mention_id, antecedent_id, constraints{} (согласование), evidence[] (traces feature-совпадений + salience-rule ids; grounds-категории {morphology, syntax, discourse, memory} §17.4), provenance} | TD ReferenceResolver (§15.4) — НЕ SRL [Rev16/H2] | T3/T4 (статус ReferenceDecision) | mention_id, antecedent_id | InterpretationVersion; решение типа REFERENCE (§6); канонический identity link — только T6/Consolidator |
| TokenHypothesis {hypothesis_id, span_ref, variants[] (нормализация/восстановление опечаток), keep_as_is (первоклассный вариант с D-provenance), provenance{pattern_id}, ProvenanceRecord} | SRL (§17.3) [Rev16/H7] | T1/T3,T4 (статус LexDecision) | hypothesis_id, span_ref | InterpretationVersion; в каноническую память — только через закоммиченное лексическое решение |
| BoundaryCandidate {candidate_id, position, kind ∈ {CLAUSE_BOUNDARY, SENTENCE_BOUNDARY, PUNCT_RESTORED}, evidence[], provenance{pattern_id}, ProvenanceRecord} | SRL (§17.3) [Rev16/H7] | T1 п.8 (потребление), T3/T4 (статус BOUNDARY-решения) | candidate_id, position | InterpretationVersion; не факт — альтернатива сегментации |
| ClauseCandidate {candidate_id, segmentation (диапазоны span'ов), alternatives[] (linked до явного discard §2.3/I29), provenance{pattern_id}, ProvenanceRecord} | SRL (§17.3) [Rev16/H7] | T1 п.8, T3/T4 (статус BOUNDARY-решения) | candidate_id | InterpretationVersion; выжившие сегментации — linked alternatives |
| EllipsisCandidate {candidate_id, gap_ref (clause/span), kind ∈ {PREDICATE_GAP, ARGUMENT_GAP, SUBORDINATOR_GAP}, antecedent_ref (структурный), evidence[], provenance{pattern_id}, ProvenanceRecord} | SRL (§17.3) [Rev16/H7] | T2/T3 (подтверждение ELLIPSIS-решением), T4 | candidate_id, gap_ref | InterpretationVersion; до RESOLVED — структурная гипотеза, не факт |
| MissingArgumentCandidate {candidate_id, frame_ref/slot_ref, role, status UNRESOLVED/RESOLVED_BY_ELLIPSIS/UNFILLED, provenance{pattern_id}, ProvenanceRecord} | T2/T3 (valency-проверка §16.9) [Rev16/H3,H7] | T4 (статус), T5 (miss при UNFILLED) | candidate_id, slot_ref | InterpretationVersion; диагностика неполноты, не факт |
| WorldKnowledgeRecord {record_id, version, subject_type/instance, predicate ∈ объявленный WK-набор {IS_A, HAS_PART, PROPERTY, TYPICAL_CONSTRAINT}, object, source (curated\|derived), provenance} | ресурс R-WK (версионный; пополнение — только learning loop §15.10) | — | все | версия wk_resource |
| TemporalExpression {expr_id, span(s), kind ∈ {ABSOLUTE, RELATIVE_ANCHORED, DURATION, ORDER}, value?, trigger_lemma, source} + TemporalAnchor {anchor_id, anchored_ref (frame/event/timepoint), anchor_time (resolved or symbolic)} + TemporalRelation {relation_id, src, dst, operator ∈ TemporalOperators [Rev13] (§15.6), anchor_dependency, evidence[]} | T1 (по объявленным temporal-паттернам) / TD+T3,T4 (anchoring chain §15.6) | — | все | InterpretationVersion; сериализуется в N.meta["time"] |
| QueryFrame {query_id, kind ∈ QueryKind [Rev13] (§15.7), target_vars[] (непривязанные переменные с объявленным сортом; для YESNO — пусто), constraints[] (frame + role bindings, переменные допустимы в ролях), source_span} + QueryCandidate (альтернативные чтения) | T2/T3 (modus=QUERY, V4 §5.1) / QueryCompiler (§15.7) | — | все | InterpretationVersion; компилируется в AssociationGoal |
| EvidencePriorityPolicy {policy_id, version, **domain_rules[] = {domain, source_order[], conflict_rule} [Rev13]**, no_auto_winner_conditions[]} | явный review — вне пайплайна и learning loop (§15.10) | — (immutable) | все | версия policy_resource |
| ResourceProposal {proposal_id, target_resource, proposed_records[], evidence_refs[] (miss-отчёты + span'ы), status PROPOSED/VALIDATED/REJECTED} | learning loop Analysis (§15.10) | Validation (status) | proposal_id, target_resource | версия ресурса N+1 после VALIDATED |
| Diagnostic {diag_id, stage, code, detail, span_refs[], interpretation_version?, unknown_reason? (§15.8)} | этап, создавший диагностику (T0–T6b) | — | все | не версионируется; ссылки из ObservationRecord.diagnostics [D5] |
| MorphVariant {variant_id, span_id, lemma?, pos, cases, number/gender/person/tense/mood (если в tagset), tagset-признаки (напр. Subx), score} | T1 | T1 (расширение падежного набора объявленным правилом общей словоформы) | variant_id, span_id, lemma, pos, score | не версионируется; расширение = новый вариант с тем же stem-key |
| TokenEvidence {span_id, variants[], cases_index (выводится из variants строго), oov_flag} | T1 | T1 | span_id | не версионируется |
| LexDecision {decision_id, span_id, candidates[], status, grounds[]} | T1 | T3/T4 (статус, основания) | decision_id, span_id | запись решения (§2.4) |
| FrameCandidate {frame_id, clause_id, interpretation_version, op ∈ OP1..OP5, kind FLAT/NESTED/COORD, frame_type ∈ {VERB_ANCHORED, COPULAR, EXISTENTIAL, NOMINAL_PREDICATE, INSUFFICIENT_CONTEXT} (§5.3 п.3), polarity POS/NEG [B13], predicate_ref, participants[](=MentionCandidate), scope_ops[], copula_ellipsis} | T2 | — (immutable внутри версии) | все кроме status | InterpretationVersion |
| Slot {slot_id, frame_id, slot_type, candidates[]} | T3 | T3 (добавление кандидатов из разрешённых источников), ConstraintEngine (сужение множеств) | slot_id, frame_id, slot_type | InterpretationVersion |
| Candidate (§2.3) | владелец типа (§2.3) | ConstraintEngine (status REJECTED с D-трассой), T4 (EXPIRED при смене версии) | id, type, value, source, provenance | InterpretationVersion |
| Decision {decision_id, slot_id, state, outcome?, selected[], grounds[], revision_history[], last_prompt?, raw_response?, provenance{resource_versions{}, pattern_ids[]}} [Rev16/H6] | T3 | DecisionEngine (§6) — единственный мутатор state/outcome; T3/T4 добавляют grounds и историю | decision_id, slot_id | запись решения + InterpretationVersion |
| Ground {type ∈ R/C/D/A/M/W, source (LEXICON\|VALENCY\|WORLD_KNOWLEDGE\|RESOURCE\|CONTEXT\|MODEL\|TRACE), text, value (id кандидата или None), provenance} | T1 (R,D для OOV), TD (D из трассы согласования §15.4), T3 (C,M,W §15.2/§15.5), T4 (D из трассы) | — (immutable) | все | не версионируется; ссылка из Decision |
| ConstraintEdge {edge_id, interpretation_version, slots[], forbidden_tuples[], rule_id, D-ground} | декларация схемы/объявленное правило | — (immutable) | все | InterpretationVersion |
| Cluster {cluster_id, interpretation_version, member_slot_ids[]} | ConstraintEngine (§7.1) | ConstraintEngine (пересборка при новом ребре) | cluster_id, interpretation_version | InterpretationVersion |
| InterpretationVersion {observation_id, version, frames[], decisions{}, edges[], clusters[], status} | T5 (нумерация версий) | T6b (status SUPERSEDED/STALE) | observation_id, version | сам является версией |
| ObservationRecord {observation_id, source_id, span (= диапазон SentenceUnit/ClauseUnit формализации, §9.1 [D9]), interpretations[], linked_alternatives[] (совместимые сочетания), status, context_version, resolution_log[], diagnostics[] (ссылки на Diagnostic [D5])} | журнал наблюдений (§9.1) | T4/T5 (status, alternatives), этапы T0–T3 (diagnostics), T6b (retraction) | observation_id, source_id, span | append-only записи по точной паре |
| FormalizationBatch {batch_uid, interpretation_version, elements[], marker} | T5 | — до атомарного коммита | все | канал материализации |
| MutationPlan {plan_id, batch_uid, ops[]} | T6 | — | все | канал материализации |
| CanonicalElement (N/M/S/T/G/L по §2.1 V4) + meta {source_id, span, batch_uid, observation_id} | integrate_plan (T6) | T6b (meta.status), SupportLedger (опоры) | uid | каноническое хранилище |
| SupportRecord {conclusion_ref, ground_type, ground_text, tag=(observation_id, interpretation_version)} | T6 (из grounds решения) | T6b (retraction по тегу) | все | SupportLedger |
| RXRecord {record_id, stage_channel ∈ RX1/RX2/RX3, key, payload, provenance{observation_id, interpretation_version, decision_id}, versions{formalizer_schema_version, framegen_version, semantic_schema_version}, status LIVE/SUPERSEDED/STALE} | T6 (только из закоммиченных решений) | T6b (status) | record_id, key, provenance, versions | кэш-хранилище [B] |
| CandidateIR {ir_id, observation_id, interpretation_version, lexical_units[], clauses[], mention_candidates[], predicate_frames[], dependency_candidates[], operator_trees[] (ScopeTreeCandidate), coreference_candidates[] (ReferenceCandidate), structural_candidates[] (§17.3: TokenHypothesis/Boundary/Clause/Ellipsis/MissingArgument), temporal_candidates[] (§15.6), semantic_candidates[] (§16), ambiguity_sets[] (AMBIGUOUS-решения + linked_alternatives), provenance (ProvenanceRecord на каждую структуру, §2.5)} | T4 (сборка) — единственный выход формализации | Consolidator (§2.7) | все | InterpretationVersion; каноническая память получает только результат после consolidation |
| SemanticExpression / PropositionNode {expr_id, head (predicate\|operator), arguments[] (ArgumentSpec §16.2), modifiers[], status TOP_LEVEL/EMBEDDED, provenance} | T3/T4 (§16.1) | Consolidator | все | InterpretationVersion; вложенная proposition не является фактом |
| ArgumentSpec {slot_ref, arg_type ∈ ArgumentType {ENTITY, EVENT, PROPOSITION, PROPERTY, SET, VALUE, TIME, LOCATION}, value (ref\|variable\|PropositionNode)} | T3/T4 (§16.2) | Consolidator | все | InterpretationVersion; набор замкнут — расширение = декларация схемы |
| EventFrame {frame_id, schema_ref (PredicateSchema §16.9), predicate, participants[] (ArgumentSpec), temporal? (§15.6), location?, state, modifiers[], embedded_propositions[] (PropositionNode), provenance} | T3/T4 (разрешённая форма FrameCandidate §16.3) | Consolidator | все | InterpretationVersion |
| AttributeExpr {attr_id, subject (ArgumentSpec ENTITY), property (PROPERTY/VALUE), value?, provenance} | T3/T4 (§16.4) | Consolidator | все | InterpretationVersion; автоматических phrase-level концептов нет (§16.5) |
| ExistentialRef {var_id, discourse_ref, scope_span(s), bindings[] (местоимения → var), status UNRESOLVED/RESOLVED_BY_CONSOLIDATOR} | T1 (объявленный паттерн §16.6) / T3 (привязка местоимений) | Consolidator (identity resolution) | все | InterpretationVersion; фиктивных сущностей нет |
| SemanticGraphCandidate {graph_id, ir_ref, nodes[] (EventFrame/AttributeExpr/PropositionNode/QueryFrame), edges[] (dependency/scope/reference/temporal/constraint), ambiguity_sets[], provenance} | T4 (§16.7) — единственный вход в Consolidator | Consolidator | все | InterpretationVersion |

Правило единственного создателя: объект создаётся ровно одним этапом; другие этапы только ссылаются.
Внешние мутации FormalizationState запрещены: внешнее изменение входа создаёт новую версию контекста (§4).

### 2.2 Версионные схемы и их роль
Версионная схема (semantic_schema_version) хранит: набор значений слотов; **candidate_generation_rules** — явная таблица
совместимости (тип рамки/слота → множество значений), implicit «все значения схемы» запрещён [D7]; объявленные scope-
паттерны (§5.2 п.10); constraint-декларации, реестр связей «значение → uid канонического шаблона» (§9.3).
CandidateGenerationRules остаётся ВНУТРИ SemanticSchema, а не отдельным версионным объектом [Rev10]: правила осмысленны только
относительно множества значений и типов рамки той же схемы; раздельное версионирование создало бы два часовых механизма,
которые обязаны синхронизироваться, при том что в Фазе 1 (demo v1 заморожен) независимой эволюции правил нет. Схема immutable;
изменение = новая версия схемы. Записи с несовпадающей версией схемы НЕ применяются автоматически: либо не
используются, либо явно мигрируются объявленной процедурой [A-согласно V4 rev6].

### 2.3 Модель кандидата

```
Candidate {
    id            — уникальный внутри InterpretationVersion (формат: {slot_type}:{frame_id}:{seq})
    type          — LEXICAL_FORM | LEX_RECOVERY | FRAME | BINDING | PREDICATE_VALUE | ROLE_VALUE | SCOPE_OP | MODALITY
    value         — значение (id значения схемы / структура привязки / морф-вариант)
    source        — SCHEMA | R1 | RS | RX1 | RX2 | RX3 | LEX_RECOVERY | FRAMEGEN
    provenance    — {origin_stage, origin_record_id, interpretation_version, resource_versions{} [Rev16/H6]}
    dependencies  — id кандидатов/свидетельств, от которых кандидат выведен (пусто для базовых)
    status        — ACTIVE | REJECTED | EXPIRED
    version       — версия InterpretationVersion, в которой создан
}
```

**Создание по типам (единственный создатель):**
- LEXICAL_FORM, LEX_RECOVERY — T1 (§5.2);
- FRAME, BINDING — T2 (§5.3);
- PREDICATE_VALUE, SCOPE_OP, MODALITY — T3 (§5.4): множество кандидатов = **candidate_generation_rules** версионной схемы для
  типа рамки/слота [D7]; R-S (по лемме-якорю); R-X3 (ранжированный набор; исключает только явным решением текущего предложения).
  SCOPE_OP-кандидаты создаёт T1 (MentionCandidateBuilder, ER-QUANTIFIER) по объявленным паттернам (§5.2 п.9d/п.10).
- ROLE_VALUE — только если схема явно declares альтернативные конфигурации ролей для значения: тогда T3 открывает решение с
  замкнутым множеством = объявленные альтернативы; иначе ролевой слот НЕ существует — роли вычисляются проекцией
  (Frame structure + selected value → canonical roles, §5.4 п.1) [D2].

**Существование:** кандидат существует с момента регистрации в `Slot.candidates` с уникальным id. До регистрации он
не существует ни для ConstraintEngine, ни для LLM, ни для T4.

**Удаление — никогда физическое.** Два перехода status:
- ACTIVE → REJECTED: только объявленным constraint (запись D с rule_id в трассе) либо явной операцией discard с причиной;
- ACTIVE → EXPIRED: смена InterpretationVersion (аудит сохраняется в журнале наблюдений).

**Дедупликация:** два источника, дающих одно и то же значение слота (напр. SCHEMA и RX3 для V2), дают ОДИН кандидат
со списком source; provenance хранится per-source. R-X-источник НЕ считается основанием (§6.4): дубликат из R-X не
увеличивает доказательность.

**CandidateStatus [Rev14.1]** — отдельное измерение статуса для всех неоднозначных структур в CandidateIR/SemanticGraphCandidate
(§16): CONFIRMED_CANDIDATE / POSSIBLE_CANDIDATE / AMBIGUOUS_CANDIDATE / REJECTED_CANDIDATE. Не отождествляется с:
(a) жизненным циклом Candidate.status ACTIVE/REJECTED/EXPIRED выше; (b) семантическим outcome решения (§1.4);
(c) истинностью утверждения. **confidence ≠ truth value**: confidence (если присутствует в структуре) показывает качество
кандидата (силу и число оснований), а не истинность утверждения; не участвует в коммите, не хранится как факт,
не изменяет CandidateStatus.

### 2.4 Пять сущностей: различение и запрет скрытых переходов

| Сущность | Определение | Создаётся | Уничтожается/завершается |
|---|---|---|---|
| Кандидат (§2.3) | допустимое значение слота с источником; НЕ выбрано | владелец типа | REJECTED / EXPIRED (аудит) |
| Гипотеза | Decision в state PROVISIONAL: выбор T3, не прошедший совместную проверку | T3 | T4 присуждает outcome; ревизия (§6.5) |
| Интерпретация | InterpretationVersion: связанный набор frames+decisions+edges одного input при одной версии контекста — ЕДИНИЦА ревизии и журналирования | T5 нумерует версию | SUPERSEDED/STALE по T6b (без физического удаления) |
| Решение | Decision: запись слота со state machine (§6.1), основаниями, историей ревизий | T3 | терминальные состояния §6.1 |
| Материализованный факт | канонический элемент (N/M/S/T/G/L) в AH-памяти с meta и опорами SupportLedger | integrate_plan (T6) — ЕДИНСТВЕННЫЙ путь | отзыв T6b (§10); LOST при утере канала |

**Единственная цепочка candidate → fact [A3]:**
```
Candidate ──(P1: выбор T3, §5.4)──> Гипотеза (PROVISIONAL Decision)
Гипотеза ──(P2: совместная проверка T4, §6.4)──> RESOLVED/AMBIGUOUS Decision
Decision  ──(P3: коммит T5 по четырём условиям, §9.2 + атомарный batch)──> FormalizationBatch
Batch     ──(P4: integrate_plan T6, единственная граница записи, §9.3)──> CanonicalElement + SupportRecords
```
Каждая стрелка — процедура с владельцем (этап), предусловием и записью аудита (журнал наблюдений / маркер
материализации). Других путей в канонический слой не существует: integrate_plan — единственный writer [A4];
FunctionRegistry отклоняет неизвестные ID на этой границе. Кандидат, гипотеза и решение существуют только внутри
InterpretationVersion; факт — вне её, с провенансом-ссылкой.

---

### 2.5 Provenance layer [Rev13b]
**ProvenanceRecord** {source_span, source_id, transformation_chain[] (упорядоченные шаги (component, operation) от исходного span до данной структуры), producer_component, version}.
Назначение: хранение происхождения решения; воспроизводимость диагностики; объяснение выбора кандидата; аудит acceptance failures.

P1 (обязательность): все структуры, которые участвуют в выборе, разрешении или отбраковке кандидатов, обязаны сохранять ProvenanceRecord. Минимальный список:
SurfaceOperatorCandidate, OperatorAttachmentCandidate, ScopeConstraintGraph (nodes и edges), ScopeTreeCandidate,
ReferenceCandidate (coreference, §15.4), TemporalAnchor (§15.6), QueryFrame, результат оценки свидетельств (T4/§15.9).

P2 (неучастие): provenance НЕ участвует в семантическом выборе: не является типом основания (R/C/D/M/A/W), не является
dополнительным источником знаний, не изменяет ranking; используется только для диагностики, трассировки и объяснения.
ProvenanceRecord никогда не создаёт и не отбраковывает кандидатов.

### 2.6 CandidateIR — промежуточный контракт [Rev14]
**CandidateIR** (тип §2.1) — единая структура передачи результатов между локальной формализацией и консолидацией.
Правила: (a) Parser/Formalization (T0–T4) создают CandidateIR; (b) **Consolidator** разрешает identity, dedup, linking
по CandidateIR (§2.7); (c) каноническая память получает только результат после consolidation — прямые записи T1–T4 в
каноническое хранилище запрещены.
**Immutability [Rev14.1]**: CandidateIR — immutable intermediate representation: создаётся Formalization Layer; не является
хранилищем памяти (не персистится как источник фактов); не содержит канонических identity (только локальные ссылки и
кандидаты, §2.7); передаётся в Consolidator как snapshot; после передачи не мутируется — любое изменение = новый CandidateIR
с новой interpretation_version.
Consolidator НЕ инстанцирует квантованные propositions [Rev14.2]: instantiation по канонической памяти выполняет InferenceEngine
в момент запроса через AssociationGoal (V4 §5.9); формализатор коммитит только саму квантованную proposition (§16.11 тест 1).

### 2.7 Local Formalization vs Semantic Consolidation [Rev14]
**Formalization отвечает**: что выражено в тексте; какие структуры и отношения присутствуют; какие кандидаты возможны
(локально, внутри наблюдения).
**Consolidation отвечает**: identity resolution; merge; coreference между наблюдениями; linking; dedup; каноническая интеграция.
**Запрет раннего связывания сущностей во время локального разбора**: T1–T4 не создают канонических связей между
сущностями и не пишут в каноническое хранилище (I24). Coreference внутри наблюдения (§15.4) — локальный кандидат с
evidence, а не каноническая связь; решение об identity принимает Consolidator.

## 3. Общая архитектура

### 3.1 Компоненты и их границы

```
входной адаптер → T0 лекс. нормализация/сегментация → SRL структурная реконструкция (§17)
→ T1 лингвистический анализ → TD dependency → T2 frame generation → T3 ⇄ LLM-граница (§8) →
T4 семантическое разрешение → T5/T6 коммит/запись → Consolidator (CandidateIR §2.6) → AH (канонический слой)
                    │    │    │    │      │          │     │     │        ↑
                    └────┴────┴────┴──────┘          │     │     │        │
              FormalizationState (runtime, §4.2)     │     │     │        │
                    │                               │     │     │        │
              журнал наблюдений (канал 1) ←─────────┘     │     │        │
              канал материализации (маркеры) ←────────────┘     └──→ R-X кэш [B5]
```

- **SRL/T0–T2** — детерминированные, LLM не вызывают (LLM-граница только T3, §8). Выход каждого этапа — immutable структуры (§2.1).
- Цепочка единиц [B8/B14/Rev12]: RawInput → SentenceUnit (T0) → структурные кандидаты (SRL §17) → ClauseUnit + HeadCandidate + MentionCandidate (T1, декларативно §5.2 п.9) → DependencyCandidate + ReferenceDecision + ScopeOperatorNode-дерево (TD, §15.1–15.4) → FrameCandidate (T2).
- **T3** — единственный этап, вызывающий LLM (bounded selection, §8); решения персистятся немедленно после создания.
- **T4** — детерминированная совместная проверка; присуждает семантические исходы [A2].
- **T5/T6** — коммит и запись в AH; T6 — единственная граница записи [A4].
- **T6b** — ревизия уже записанных интерпретаций (§10); не новый этап пайплайна, а протокол над состоянием.

### 3.2 Поток версий
Каждый прогон = (input_id, context_version) → InterpretationVersion vN. Новая версия контекста (изменение
задекларированного входа по reads-контракту V4 §1.2) триггерит адресный пересчёт: детерминированные этапы T0–T2
пересчитываются мгновенно; T3/T4 — по правилам повторного выбора и осциллятора (§6.5). Прерывающий тест (V4 §1.2):
изменение задекларированного входа ОБЯЗАТЕЛЬНО запускает пересчёт; смена ответа НЕ требуется.

### 3.3 Каналы персистентности [A5]
1. **Журнал наблюдений** — append-only, write-through + fsync на запись; ключ записи = точная пара
   (observation_id, interpretation_version); все версии сосуществуют; единственный владелец неразрешённых
   альтернатив и истории решений.
2. **Канал материализации** — MutationPlan + атомарный маркер в том же комите канонического хранилища; идемпотентен
   по паре (observation_id, interpretation_version).
Порядок коммита закреплён: сначала запись версии интерпретации в журнал (со ссылкой), затем канонический коммит с этой
ссылкой. Окна «AH обновилась, а план не зафиксирован» нет.

---

## 4. Lifecycle формализации

### 4.1 Таблица этапов

Для каждого этапа: вход / выход (обязательные поля) / creator / mutator / условие завершения / триггеры пересчёта /
персистентное vs runtime.

| Этап | Вход | Выход | Creator/Mutator | Условие завершения | Триггеры пересчёта | Персистентно | Runtime |
|---|---|---|---|---|---|---|---|
| T0 | RawInput {input_id, source_id, text} | TokenSpan[] + SentenceUnit[] (§5.1) | T0 / — | каждый символ текста покрыт ровно одним span или классифицирован как PUNCT/WHITESPACE-остаток; каждый SentenceUnit ограничен TERMINAL-знаком (PUNCT_CLASS §5.1 п.2) или концом входа | новый input (пересчёт всего) | RawInput, TokenSpans, SentenceUnits | — |
| SRL | TokenSpan[] + SentenceUnit[] (T0) + объявленные ресурсы (boundary/ellipsis-паттерны; каналы памяти §17.4) | TokenHypothesis[] + BoundaryCandidate[] + ClauseCandidate[] + EllipsisCandidate[] + MissingArgumentCandidate[] (§17.3); ReferenceCandidate расширяется grounds-категориями (§15.4/§17.4) — все через CandidateIR (§2.6), отдельного пути нет | SRL / T3,T4 (статус структурных решений, DecisionType BOUNDARY/ELLIPSIS [Rev15]) | у каждого span: TokenHypothesis или чистая форма; на каждое отсутствие/неоднозначность boundary-сигнала: BoundaryCandidate либо явная «кандидатов нет»-диагностика; каждый кандидат несёт ProvenanceRecord (§2.5) и сохраняется до resolution (I29); в выходе нет семантических фактов, identity links и записей в каноническое хранилище (I26/I27) | новый input; новая версия контекста; новая версия ресурсов | структурные кандидаты (журнал), TokenHypothesis | — |
| T1 | TokenSpan[] + SentenceUnit[] + ruleset (HeadRules/ExpansionRules) | TokenEvidence[] + ClauseUnit[] + HeadCandidate[] + MentionCandidate[] + SurfaceOperatorCandidate + TemporalExpression + LexDecision для OOV (§5.2) | T1 / T3,T4 (статус LexDecision) | у каждого span есть evidence; каждый SentenceUnit разбит на ClauseUnits (п.8, включая выживших ClauseCandidate SRL); каждое срабатывание HeadRule зафиксировано в HeadCandidate; у каждого HeadCandidate ≥1 MentionCandidate ИЛИ диагностика NO_HEAD_CANDIDATE; каждый quantifier-подобный токен либо matched объявленным scope-паттерном, либо помечен SCOPE_NOT_COVERED; у каждого OOV-токена открыто лексическое решение с кандидатами или диагностикой PROVIDER_UNAVAILABLE | новая версия контекста, затрагивающая span; новая версия ruleset | TokenEvidence, ClauseUnits, HeadCandidates, MentionCandidates, SurfaceOperatorCandidate, TemporalExpression, LexSenseCandidate, LexDecision (журнал) | — |
| TD | MentionCandidate[] + TokenEvidence[] + ruleset (DependencyRules, CoreferencePolicy §15.4) + discourse window [NQ7] | DependencyCandidate[] + ReferenceDecision[] + OperatorAttachment/ScopeConstraintGraph/ScopeTreeCandidate (§15.1, §15.3 п.2) | TD / T3,T4 (статус ReferenceDecision) | каждое срабатывание DependencyRule зафиксировано в DependencyCandidate; у каждой PRO/event-anaphora mention: ≥1 ReferenceCandidate ИЛИ REFERENCE_UNKNOWN + miss; scope-дерево построено по объявленным scoping-правилам ИЛИ SCOPE_NOT_COVERED; семантических отношений в выходе TD нет (I14) | новая версия свидетельств/контекста; новый SentenceUnit (расширение discourse window); новая версия ruleset | DependencyCandidates, ReferenceDecisions, SurfaceOperatorCandidate, ScopeTreeCandidates (журнал) | позиция обхода window |
| T2 | ClauseUnit[] + MentionCandidate[] | FrameCandidate[] {frame_id, clause_id, op, kind, predicate_ref, participants[](=MentionCandidate), scope_ops[], copula_ellipsis} + diagnostics | T2 / — | для каждого ClauseUnit: ≥1 frame ИЛИ диагностика CLAUSE_NOT_COVERED; каждый participant — существующий Mention; каждое connective между двумя покрытыми якорями либо покрыто операцией, либо помечено CONNECTIVE_NOT_COVERED (§5.3 п.4); все диагностики записаны в ObservationRecord.diagnostics [D5] | новая версия контекста/свидетельств | frames в InterpretationVersion (журнал) | — |
| T3 | FrameCandidate[] + версионная схема (candidate_generation_rules, scope/temporal-паттерны) + LexicalResource/R-WK/EvidencePriorityPolicy + R-S/R-X3 | Slot[] с Candidate[] и Decision[] (state PROVISIONAL или ниже), last_prompt/raw_response | T3 / DecisionEngine | у каждого слота: множество кандидатов заполнено ВСЕМИ разрешёнными источниками ИЛИ NO_CANDIDATE+miss; каждое решение персистится немедленно | новый кандидат из любого источника; новая версия контекста | Decision (журнал, немедленно) | позиция обхода источников |
| T4 | Decision[] + ConstraintEdge[] + clusters | outcome каждого решения (RESOLVED/AMBIGUOUS/INSUFFICIENT_CONTEXT/NO_CANDIDATE/UNRESOLVED) + diagnostics; linked_alternatives в ObservationRecord; CandidateIR (§2.6) — единственный выход формализации | T4 / — | у каждого решения присвоен outcome или диагностика; search_complete зафиксирован для каждого кластера | ревизия upstream (транзитивная); новое содержание R/C/D/A; новая версия контекста | outcomes, alternatives (журнал), CandidateIR | осцилляционный детектор, позиция bounded search |
| T5 | RESOLVED/AMBIGUOUS Decision[] + ObservationRecord | FormalizationBatch {batch_uid, elements[], marker} ИЛИ ObservationRecord без коммита | T5 / — | для каждого семантически завершённого фрагмента: четыре условия §9.2 проверены (true → batch; false → остаётся в runtime с указанием несостоявшегося условия) | — (коммит однократен по маркеру) | batch + маркер (канал 2), версия интерпретации (журнал, ПЕРВЫМ) | — |
| T6 | FormalizationBatch | CanonicalElements + SupportRecords в AH; RXRecord [B5] | integrate_plan / T6b (meta.status) | все ops плана применены И маркер зафиксирован в том же атомарном комите; FunctionRegistry принял все ID | — | канонический слой, SupportLedger, R-X | — |
| T6b | InterpretationVersion (новая) + записанный фрагмент | SUPERSEDED/STALE-статусы, отозванные SupportRecords, RXRecord→SUPERSEDED/STALE | T6b / — | атомарная смена видимой версии завершена ИЛИ журналируемые шаги восстановимы; читатели видят либо старую, либо новую версию, никогда промежуточное | адресная ревизия (новый контекст, явное уточнение, пересмотр) | журнал + SupportLedger + R-X статусы | — |

### 4.2 Runtime vs персистентное состояние
**Персистентно навсегда:** RawInput, TokenSpans, SentenceUnits, ClauseUnits, rulesets (Head/Expansion/Dependency Rules), CoreferencePolicy (§15.4), EvidencePriorityPolicy (§15.9), HeadCandidates, MentionCandidates, DependencyCandidates, ReferenceDecisions, SurfaceOperatorCandidate, ScopeTreeCandidates, TemporalExpression/Anchor + TemporalOperator-отношения (§15.6), QueryFrame, Diagnostics, TokenHypothesis/BoundaryCandidate/ClauseCandidate/EllipsisCandidate/MissingArgumentCandidate (§17.3), TokenEvidence, LexDecision, frames/decisions/edges/clusters (в
InterpretationVersion), outcomes и linked_alternatives (журнал наблюдений), FormalizationBatch + маркеры, канонические
элементы + SupportRecords, RXRecord.
**Runtime (пересчитывается после сброса):** state решений в PROVISIONAL/SEARCHING/GENERATING (не восстанавливаются как
факты — пересчёт: детерминированные части мгновенно, bounded selection по правилу §6.5), осцилляционный детектор,
позиция обхода bounded search (восстанавливается из контрольной точки журнала [D5]), FormalizationState целиком.

### 4.3 Порядок восстановления после перезапуска [A-согласно V4 §7.3]
1. Загрузка канонического хранилища включая журнал атомарных маркеров — авторитетно для фактов.
2. Загрузка журнала наблюдений: неразрешённые наблюдения восстанавливаются как есть; сверка каналов по ТОЧНОЙ паре:
   маркер есть, записи журнала нет → восстанавливается только факт материализации (отметка + провенанс из meta N/M),
   альтернативы и история помечаются LOST с диагностикой; маркера нет → повторный коммит легален.
3. Переподписка обработчиков на контекстные источники (подписки из reads).
4. Только после этого — приём нового входа.

---

## 5. Спецификации T0–T6b

Формат каждого модуля: Input / Output / Алгоритм (нумерованные шаги) / Ошибки и диагностики / LLM.

### 5.1 T0 — сегментация
Input: RawInput {input_id, source_id, text}. Output: TokenSpan[].
Алгоритм:
1. Разбить `text` по пробельным символам; для каждого фрагмента зафиксировать (start, end) в исходных координатах.
2. **PUNCT_CLASS вместо списка символов** [D8]: TERMINAL {., !, ?, …} — завершает SentenceUnit; CLAUSE {,, ;, :} — не
   разделяет единицы в Фазе 1 [B]; QUOTE/BRACKET {«», ()}. С любого фрагмента снимаются хвостовые символы из ЛЮБОГО класса
   PUNCT_CLASS (не только терминальные: «дождь,» → surface «дождь» + остаток CLAUSE); снятые символы классифицируются по
   классу; surface хранится БЕЗ них — OOV-ветка T1 получает чистую форму.
3. Пустые фрагменты отбрасываются (WHITESPACE-остаток).
4. Для каждого оставшегося фрагмента создать TokenSpan {span_id = input_id + ":" + seq, start, end, surface}.
5. **Группировка SentenceUnit** [D1]: span'ы группируются в SentenceUnit до первого TERMINAL-символа (включая его как
   terminal_punct) или конца входа; каждый SentenceUnit = {unit_id, input_id, start, end, terminal_punct?}; CLAUSE-знаки
   внутри не разделяют [B].
6. Проверить покрытие: каждый символ текста принадлежит ровно одному span/остатку; каждый SentenceUnit ограничен TERMINAL
   или концом входа; иначе — ошибка.
Ошибки: T0_COVERAGE_VIOLATION (символ не покрыт и не классифицирован) → прогон останавливается, вход отклонён.
LLM: нет.

### 5.2 T1 — морфология и лексические решения
Input: TokenSpan[] + SentenceUnit[] + ruleset (HeadRules/ExpansionRules). Output: TokenEvidence[] + ClauseUnit[] + HeadCandidate[] + MentionCandidate[] + SurfaceOperatorCandidate + TemporalExpression + LexDecision
для OOV-токенов.
Алгоритм (на каждый span, затем по единицам):
1. Вызвать R1 lookup по surface. Получить список парсов ресурса.
2. Для каждого парса создать MorphVariant {lemma?, pos, cases, number/gender/person/tense/mood — только признаки,
   присутствующие в tagset парса, остальные tagset-признаки (напр. Subx), score}. Связанные признаки не разбиваются и не
   рекомбинируются между парсами [A].
3. Применить объявленное правило общей словоформы: если surface оканчивается на -ами/-ями — добавить в падежный набор
   ВАРИАНТА оба значения (дат./твор.); правило расширяет только конкретный вариант; cases_index выводится из variants
   строго как объединение, напрямую не правится [D4].
4. Все возвращённые парсы сохраняются: тихого score-cutoff нет; если ресурс вернул 0 парсов — oov_flag=true.
5. Если лимит парсов ресурса исчерпан (объявленный максимум) → диагностика R1_LIMIT, все полученные парсы сохраняются.
6. OOV-ветка: открыть LexDecision с кандидатами в объявленном порядке: (a) KEEP_AS_IS — первый класс (OOV может быть
   именем/термином; D-основание «форма не в словаре, сохранение зафиксировано решением»); (b) LEX_RECOVERY-кандидаты —
   DAWG-поиск по расстоянию с морфологическим и source-frame фильтром [default: Levenshtein ≤ 2 + фильтр POS; метрика и
   порог — §13]; расстояние ранжирует, не вердикт; (c) R-X1 lookup по форме (морф-кандидаты/класс неизвестной лексемы;
   ролей НЕ возвращает). Семантическое уточнение — bounded selection (§8) по короткому списку.
6b. **Lexical sense** [Rev12/§15.2]: для каждой леммы с несколькими записями в LexicalResource — один LexSenseCandidate на
   запись (односмысленные леммы получают implicit-кандидата без ветвления); разрешение омонимии — §15.2.
7. Провайдер недоступен → LexDecision остаётся OPEN + диагностика PROVIDER_UNAVAILABLE [A: не AMBIGUOUS, не молчаливое «как есть»].
8. **ClauseUnit** [B8/D1]: граница клаузы открывается ТОЛЬКО когда кандидат POS=CONJ (R1) И (объявленный clause-pattern для
   этого connective ИЛИ наличие нового predicative center в следующей группе span'ов). Объявленные clause-patterns demo v1 [C]:
   «если», «то» (подчинительные), «либо» (сопоставительный). Не объявленный CONJ без нового predicative center границы НЕ
   создаёт — токен остаётся внутри текущей клаузы. Connective присоединяется к следующей клаузе как `connective_span`;
   span'ы до первого connective образуют `inherited_spans` (общий контекст, напр. подлежащее при «либо…либо»);
   SentenceUnit без границ И без выживших ClauseCandidate = одна ClauseUnit.
   **Потребление SRL [Rev16/H1]:** BoundaryCandidate/ClauseCandidate (§17.3) потребляются здесь: BOUNDARY-решение
   RESOLVED → сегментация по решению; AMBIGUOUS/UNRESOLVED → все выжившие сегментации существуют как linked alternatives
   (ObservationRecord.linked_alternatives, I29), T2 обрабатывает каждую; SRL-кандидат не отбрасывается молча.
9. **Декларативная генерация mention** [B14/D6/Rev11]: T1 строит упоминания в трёх подстадиях; ядровой алгоритм НЕ содержит
   проверок вида `if POS == NOUN` — всё знание о типах несут объявленные правила и ресурсы:
   Morphological output → HeadCandidateGenerator (9a) → MentionCandidateBuilder (9b) → FrameGenerator (T2).

   9a. **HeadCandidateGenerator**: для каждого span'а (и смежной группы span'ов) клаузы оценить набор HeadRules (§2.1):
   activation — декларативный предикат по признакам R1 (наборы POS, tagset-признаки, лемматические наборы из записей ресурса)
   И объявленной локальной структуре (напр. «в окне нет номинальной головы»). Каждое срабатывание создаёт HeadCandidate
   {candidate_id, clause_id, span(s), head_type, rule_id, evidence, constraints{}, source_links}. Несколько правил могут
   сработать на одном span'е — ВСЕ кандидаты сохраняются; тихого отсечения нет. Ни одно правило не сработало по группе
   span'ов → диагностика NO_HEAD_CANDIDATE (span'ы остаются токенами, видны в журнале [I1]).

   9b. **MentionCandidateBuilder**: вход = HeadCandidate[] + ExpansionRules (§2.1) + декларации mention-типов схемы.
   Для каждого head-кандидата применяются правила расширения: правило описывает последовательность feature-предикатов по
   смежным span'ам (направление, максимальная длина) и производит добавление members ИЛИ constraint на упоминание
   (напр. number_constraint из NUMR). Билдер НЕ выбирает единственный вариант: он создаёт МНОЖЕСТВО MentionCandidate с
   provenance {head_rule_id, expansion_rules_applied[], evidence}; альтернативные анализы сосуществуют до разрешения T3/T4
   или сохранения AMBIGUOUS (несовместимые сочетания — linked_alternatives). Несовпадение версий ruleset со схемой →
   RULE_VERSION_MISMATCH (§11).

   9c. **Типы mention** (объявлены в схеме; новый тип = новая строка таблицы + декларации HeadRule/ExpansionRule, ядро не
   меняется [B14]):
   | Тип | Условия создания | Допустимые аргументы FrameCandidate | Стадии с правом изменения |
   |---|---|---|---|
   | EntityMention {head ENTITY_NOUN\|ENTITY_PROPN\|PRO\|SUBST_ADJ, members[], case_index} | HeadRule с head_type из этого набора сработал | любые роли, объявленные схемой для типа | T1 создаёт; T2 ссылается (immutable); T3/T4 — только через решения по связанным слотам |
   | QuantifiedMention {entity_head, number_constraint?, quantifier_member?} | NUMERAL/QUANTIFIER head-кандидат + ExpansionRule, связывающая его с сущностью («два студента») | роли EntityMention; constraint несётся атрибутом упоминания | то же |
   | EventMention {head EVENT (INFN/нефинит), members[]} | HeadRule head_type=EVENT сработал | аргументы, объявленные схемой (напр. субъект copular-рамки «читать полезно») | то же |
   | ClauseMention {nested_clause_id, connective_span} | CLAUSE head-кандидат (объявленный subordinating-pattern + Subx) | аргумент внешней рамки («То, что он сказал, важно»); вложенная клауза формализуется независимо (§5.3 п.4) | то же |

   9d. **Дефолтный ruleset demo v1** [C] (записи ресурса, не код):
   - HeadRules: HR-NOUN {pos ∈ {NOUN} → ENTITY_NOUN}; HR-PROPN {pos = PROPN → ENTITY_PROPN}; HR-NPRO {pos = NPRO → PRO,
     несёт person/number/gender из R1}; HR-NUMR {pos = NUMR → NUMERAL}; HR-SUBSTADJ {pos = ADJF И в окне клаузы нет
     номинальной головы (NOUN/PROPN) → SUBST_ADJ} — сосуществует с модификаторным чтением, если номинальная голова есть;
     HR-INFN {pos = INFN → EVENT}; HR-CLAUSE {объявленный subordinating-pattern + Subx → CLAUSE}.
   - ExpansionRules: ER-ADJF-NOUN (смежный ADJF→NOUN с совпадающим case index — member); ER-NUMR-NOUN (NUMR+NOUN →
     number_constraint на EntityMention И альтернативный анализ QuantifiedMention); ER-GEN-CHAIN (цепочка смежных GEN-span'ов
     — members); ER-RELATIVE (Subx-connective → вложенная ClauseMention как модификатор номинальной головы);
     ER-DETERMINER (объявленный набор лемм детерминаторов — member, не голова); ER-INFN-OBJ (объявленное управление:
     INFN-якорь + смежный ACC/PLUR span' → member EventMention); ER-QUANTIFIER (паттерны кванторов §5.2 п.10 →
     SurfaceOperatorCandidate + QuantifiedMention).
   - **Coreference** [Rev12]: стадия TD (§15.4) с полным контрактом (ReferenceCandidate, ограничения, основания,
     AMBIGUOUS); demo v1 ships минимальный salience-набор [C]; унификация в AH при коммите через merge_identity (V4 §7.2).

   **Ответственность стадий** [Rev11]: T1 отвечает ТОЛЬКО за морфологию, HeadCandidates, MentionCandidates и поверхностные
   scope-кандидаты. T1 НЕ отвечает за роли, значения отношений (HAVE/HAS_PART/…), владение, часть-целое и любые семантические
   отношения — это исключительная область T3/T4 (§5.4). Activation-условия правил работают по признакам R1 и объявленной
   локальной структуре; семантические предикаты в activation запрещены (двухуровневый инвариант V4 §2: структурные правила —
   при декларировании, лексико-семантические отображения — только через ресурсы или bounded LLM-probe).

   **Декларативный самоаудит** [B14]: архитектура достаточна, если каждый пример описывается срабатываниями правил БЕЗ нового
   if/else в ядре:
   | Пример | Срабатывания (ядро не меняется) |
   |---|---|
   | «Каждый студент сдал экзамен» | HR-NOUN («студент», «экзамен») + ER-QUANTIFIER/паттерн EVERY (§5.2 п.10) → EntityMention + SurfaceOperatorCandidate; OP1-якорь «сдал» (T2) |
   | «Два студента пришли» | HR-NUMR («два») + HR-NOUN («студенты») + ER-NUMR-NOUN → EntityMention(number_constraint=2) И альтернативный QuantifiedMention; T3/T4 разрешает или сохраняет AMBIGUOUS |
   | «Больной выздоровел» | HR-SUBSTADJ срабатывает (ADJF, в окне нет номинальной головы) → EntityMention с SUBST_ADJ-головой; при наличии NOUN сосуществует модификаторное чтение |
   | «Читать книги полезно» | HR-INFN («читать») + ER-INFN-OBJ («книги» ACC/PLUR — member) → EventMention [«читать книги»]; внешняя рамка NOMINAL_PREDICATE {predicate=«полезно», аргумент=EventMention} (T2) |
   | «Человек, который помог мне» | HR-NOUN («человек») + ER-RELATIVE (Subx «который» → вложенная ClauseMention как модификатор) → EntityMention с relative-clause member; внешняя клауза без конечного якоря — кандидаты по §5.3 п.3 |
   | «То, что он сказал, важно» | HR-NPRO («то») + ER-RELATIVE/HR-CLAUSE (объявленный паттерн «что»+Subx → ClauseMention [«он сказал»]) → EntityMention с clause-member; внешняя рамка NOMINAL_PREDICATE {predicate=«важно», аргумент=EntityMention(ClauseMention)} |
   Если новый пример требует изменения ядрового алгоритма (а не декларации правила/ресурса) — это архитектурный дефект, а не
   фича.
10. **ScopeOperator generation** [B9/D3]: объявленные surface-паттерны версионной схемы (demo v1 [C]: EVERY ← ADJF лемма
    «каждый»; AT_LEAST_N ← multi-word n-грамма «хотя бы» + NUMR/ADJF по смежным span'ам; T0 не сливает multi-word, паттерн
    матчится по последовательности span'ов). Совпадение → SurfaceOperatorCandidate (source=SCHEMA, §15.3) на Mention. Несовпавший
    quantifier-подобный токен (объявленный признак R1 tagset или лемма из объявленного списка) → диагностика SCOPE_NOT_COVERED,
    токен остаётся модификатором; **молчаливая потеря запрещена**.
Ошибки/диагностики: R1_LIMIT, OOV_KEEP_AS_IS (информационная), PROVIDER_UNAVAILABLE, SCOPE_NOT_COVERED,
NO_HEAD_CANDIDATE [B14], EXPANSION_AMBIGUOUS (информационная — альтернативные анализы сосуществуют), RULE_VERSION_MISMATCH.
LLM: только bounded selection в OOV-ветке и при неоднозначной морфе с семантическим следствием; иначе нет.

### 5.3 T2 — структурные кандидаты (FrameGen)
Input: ClauseUnit[] + MentionCandidate[]. Output: FrameCandidate[] + diagnostics. LLM: нет.
Грамматика Фазы 1 [B1] — конечный набор операций, всё остальное → STRUCTURE_NOT_COVERED:
- OP1 глагольный якорь (VERB-вариант) + косвенные аргументы по падежному управлению; порядок слов ранжирует, не отсекает.
- OP2 безглагольные конструкции — формальная генерация frame_type (§5.3 п.3): COPULAR / EXISTENTIAL / NOMINAL_PREDICATE /
  INSUFFICIENT_CONTEXT; явная copula (лемма есть/нет + VERB/INFN-парс) — possessor до, объект после; эллипсис copula — ТОЛЬКО
  когда copula отсутствует И дательный управляется предлогом «у» (включая NPRO: «у меня»). Polarity [B13]: NEG при
  copula-лемме «нет» или объявленном отрицателе, иначе POS; персистится в N.meta["polarity"] (§9.3).
- OP3 u+GEN: предлог + GEN-токен = косвенный аргумент; голова = оставшийся NOM-токен.
- OP4 NESTED через связующую словоформу с признаком Subx либо конечный якорь внутри пропуска — объявленная заглушка [B7]:
  нераскрытая структура → диагностика STRUCTURE_NOT_COVERED, рамка не генерируется молчаливо.
- OP5 COORD между двумя конечными якорями — объявленная заглушка [B7], то же поведение.
Алгоритм:
1. Для каждой ClauseUnit собрать предикатных кандидатов (MentionCandidate/span с парсом VERB / copula-леммы / NOM по OP2/OP3)
   и участников = MentionCandidates клаузы; `inherited_spans` доступны всем клаузам SentenceUnit как общий контекст [D1].
2. Перебрать операции в объявленном порядке OP1→OP5; для каждой, применимой к текущим свидетельствам, создать
   FrameCandidate {frame_id, clause_id, op, kind, predicate_ref, participants[](=Mention), scope_ops[] (SurfaceOperatorCandidate
   клаузы), copula_ellipsis}. Кандидаты 1–3 перебираются на каждом уровне рекурсии (вложенность); глубина и бюджет ограничены.
3. **Формальная генерация frame_type** [Rev10]: для ClauseUnit без конечного якоря кандидаты создаются в объявленном
   детерминированном порядке; скрытого выбора реализатора нет:
   (a) COPULAR — явная copula-лемма (есть/нет + VERB/INFN-парс): possessor до, объект после; ИЛИ эллипсис: copula отсутствует
       И дательный управляется «у» → copula_ellipsis=true. Polarity по [B13].
   (b) EXISTENTIAL — запись R-V для copula-леммы объявляет экзистенциальную валентность; участники по записи.
   (c) NOMINAL_PREDICATE — нет явной copula и нет условия эллипсиса: NOM/INSTR пара + эллипсис скопа.
   (d) INSUFFICIENT_CONTEXT — ни (a), ни (b), ни (c) не применимы: FrameCandidate с frame_type=INSUFFICIENT_CONTEXT,
       participants пуст; решение получает outcome INSUFFICIENT_CONTEXT (§5.5).
   Если выжило несколько из (a)–(c) — bounded selection (§8); NEG-рамка при отсутствии отрицательных значений в схеме →
   NONE_FIT (§5.4 п.5), а не молчаливое положительное значение [B13].
4. **Частичное покрытие и составление** [D1]: ClauseUnit без применимой операции → диагностика CLAUSE_NOT_COVERED, клауза
   не формализуется; покрытые клаузы SentenceUnit формализуются независимо (свои рамки, свои решения). Connective между
   двумя покрытыми якорями без покрывающей операции (OP4/OP5 — заглушки [B7]) → sentence-level диагностика
   CONNECTIVE_NOT_COVERED: подклаузы сохраняются как независимые интерпретации, связь между ними НЕ выдумывается. Все
   диагностики пишутся в ObservationRecord.diagnostics (§9.1) и персистятся [D5].
5. Ничто не применилось ни к одной клаузе → диагностика STRUCTURE_NOT_COVERED; решение остаётся OPEN [B1].
6. **Query modus** [Rev12]: если modus единицы = QUERY (V4 §5.1) — T2/T3 строят QueryFrame/QueryCandidate вместо
   факт-кандидатов (§15.7); запрос НЕ коммитится как факт.
Ошибки: STRUCTURE_NOT_COVERED, DEPTH_LIMIT (глубина вложенности исчерпана), BUDGET_EXHAUSTED.

### 5.4 T3 — генерация семантических решений
Input: FrameCandidate[] + версионная схема + R-S/R-X3. Output: Slot[] с Candidate[], Decision[] (немедленно персистятся).
Алгоритм:
1. Для каждого frame создать слоты по версионной схеме: predicate_value и (если детектированы §5.2 п.10) scope-слоты;
   модус — при объявлении в схеме. **Роли НЕ являются независимыми решениями** [D2]: конфигурация ролей вычисляется
   проекцией Frame structure + selected value → canonical roles по объявленной таблице схемы (значение → роли на позициях
   участников); ROLE_VALUE-кандидаты существуют только если схема явно declares альтернативные конфигурации для значения —
   тогда T3 открывает решение с замкнутым множеством = объявленные альтернативы (§2.3).
2. Закрытые слоты: множество кандидатов = **candidate_generation_rules версионной схемы** — явная таблица (тип рамки/слота
   → множество значений) [D7]; implicit «все значения схемы» запрещён. Demo v1 [C]: OP2 copula/possession-рамка →
   {HAVE, HAS_PART}; OP1 transitivnyj якорь → {HAVE, HAS_PART, LOCATIVE, LIKE}; scope-слоты → объявленные операторы
   (§5.2 п.10). Промпт перечисляет только кандидатов ЭТОГО решения; id из схемы, но вне множества решения → ProtocolError
   при валидации.
3. Открытые слоты: lookup R-S по лемме-якорю (множество значений с обоснованием — R); LexSenseCandidate сужает множество
   через semantic_type (§15.2); WorldKnowledgeRecord даёт W-основания и constraint-рёбра (§15.5); затем R-X3 (ранжированный
   набор ранее успешных кандидатов; исключает только явным решением текущего предложения [B5]).
4. NO_CANDIDATE + miss-отчёт выдаётся ТОЛЬКО после проверки ВСЕХ разрешённых источников (схема, R-S, R-X3); пустой R-S
   при совместимом кандидате R-X3 → кандидат рассматривается. R-V здесь не используется: отсутствие валентностной записи ≠
   отсутствие значения.
5. Bounded selection (§8) по замкнутому множеству; результат — Decision в state PROVISIONAL (включая ONE_SELECTED:
   единственность не доказывает правильность/полноту [A]). На решении фиксируются last_prompt и raw_response [D3].
   **NONE_FIT** [D4]: валидатор принял отказ → решение UNRESOLVED + диагностика VALUE_OUT_OF_SET + miss-отчёт; повторный
   расширенный запрос (с другим/расширенным множеством) запрещён — открытое множество значений остаётся отложенным (Q7b);
   решение re-arm'ится только новым содержанием R/C/D/A или новой версией контекста (§6.5).
6. Основания T3: C — объявленные контекстные утверждения, переданные в промпт дословно (видимый провенанс; базовый прогон
   их не получает); M — зафиксированный I/O bounded selection (ONE_SELECTED → M привязывается к выбранному значению;
   MULTIPLE_ADMISSIBLE → slot-level, value=None); W — внешние мировые знания (record_id + версия ресурса в provenance,
   §15.5). Самолегализующихся A нет.
7. Каждое решение персистится в журнал наблюдений немедленно после создания (до T4).
Ошибки: ProtocolError (§8), PROVIDER_UNAVAILABLE, NO_CANDIDATE (+miss-отчёт), SEARCH_INCOMPLETE (бюджет на ранжирование R-X).

### 5.5 T4 — совместная проверка и присуждение исходов
Input: Decision[] + ConstraintEdge[] + clusters (§7). Output: outcome каждого решения; linked_alternatives в ObservationRecord. LLM: нет [A2].
Алгоритм:
1. Для каждого кластера выполнить constraint-распространение и bounded search (§7.3–7.4); зафиксировать search_complete.
2. Присудить outcome по правилам:
   - единственный выживший кандидат И у него (или на слоте) положительное основание, привязанное к значению, И
     search_complete, И кластер валиден → RESOLVED;
   - несколько выживших, и у КАЖДОГО есть своё по-значенческое положительное основание → AMBIGUOUS [A9];
   - ни у одного кандидата нет положительных оснований → UNRESOLVED + диагностика NO_GROUNDED_CANDIDATE (не AMBIGUOUS);
   - требуется новый контекст → INSUFFICIENT_CONTEXT (state WAITING_CONTEXT);
   - пустое множество после всех источников → NO_CANDIDATE (+miss, §5.4 п.4);
   - NONE_FIT от bounded selection (§5.4 п.5) → UNRESOLVED + VALUE_OUT_OF_SET (+miss) [D4].
3. Slot-level основание (value=None) лицензирует слот, но не обосновывает ни одно конкретное значение [D2].
4. Валидность кластера — через объявленные constraint-рёбра: запрещённая пара значений → UNRESOLVED + CLUSTER_CONFLICT [D2].
5. Linked alternatives: выжившие совместимые сочетания (кортежи, согласованные со ВСЕМИ рёбрами) персистятся в
   ObservationRecord.linked_alternatives; ни одно сочетание не удаляется молча.
6. Осцилляционный детектор и повторный выбор — §6.5.
7. **UnknownReason** [Rev12]: каждый не-RESOLVED outcome и диагностика несут UnknownReason (§15.8), установленный
   обнаруживающей стадией; miss-отчёты агрегируются по таксономии.
Ошибки: NO_GROUNDED_CANDIDATE, CLUSTER_CONFLICT, CONSTRAINT_CONFLICT, CANDIDATE_INCOMPLETENESS, SEARCH_INCOMPLETE,
COMPUTATIONAL_FAILURE (заморозка).

### 5.6 T5 — коммит
Input: RESOLVED/AMBIGUOUS Decision[] + ObservationRecord. Output: FormalizationBatch ИЛИ «коммит не состоялся» с указанием условия. LLM: нет.
Алгоритм:
1. Для каждого семантически завершённого фрагмента проверить четыре условия [A11]: (1) генерация завершена на текущих
   версиях входов; (2) нет ожидающих записей; (3) зависимости разрешены либо представлены связанными альтернативами,
   включая constraint-рёбра; (4) целостность пройдена.
2. Все true → собрать FormalizationBatch {batch_uid, interpretation_version, elements[] в staging-формате
   (AssertionCandidate/QueryCandidate + bindings/DiscourseRef/quantifier/temporal), marker}.
3. Записать версию интерпретации в журнал наблюдений ПЕРВЫМ (со ссылкой на будущий batch).
4. Атомарный канонический коммит: элементы + маркер (observation_id, interpretation_version) в одном комите [A5].
5. Не все true → фрагмент остаётся в runtime; несостоявшееся условие записывается в resolution_log (не диагностика ошибки).
6. Незакоммиченные AMBIGUOUS-кластеры → ObservationRecord без коммита (канал 1 существует независимо [A5]).

### 5.7 T6 — запись в AH (integrate_plan)
Input: FormalizationBatch. Output: CanonicalElements + SupportRecords; RXRecord [B5]. LLM: нет. Единственная граница записи [A4].
Алгоритм:
1. Собрать MutationPlan {plan_id, batch_uid, ops[]}: создание S (AbstractSymbol по формам), M (SemanticEntity с meta
   {source_id, span, batch_uid}), резолвинг идентичности сущностей объявленными правилами (naming/identity; merge_identity
   — только объединение двух ссылок на одну сущность, предикаты не объединяет).
2. Для каждого значения предиката: lookup реестра связей «значение → uid шаблона» (§9.3); существующая связь → Ref(T);
   новая связь → bounded-выбор template_selection среди существующих T под S ИЛИ явная операция расширения схемы;
   автоматическая привязка запрещена, в т.ч. при единственном структурном кандидате [A].
3. Создание N (Hypernode): template=Ref(T), actants по роли (Operand = Ref | BoundVar), properties["relation"]=значение,
   meta {source_id, span, batch_uid, observation_id}. Дедупликация повторных упоминаний — find_hypernode_by_signature
   (occurrence_count++); различающиеся значения дают разные сигнатуры и не сливаются.
4. Кванторы/модальность: связанные переменные scope в actants; операторы — G через ensure_function.
5. SupportLedger.add_support(conclusion=Ref(N), SupportRecord{ground_type, ground_text, tag=(observation_id, interpretation_version)})
   по каждому основанию решения [A6].
6. FunctionRegistry: каждый ID плана проверяется на границе; неизвестный → отклонение всего плана с диагностикой REGISTRY_REJECT.
7. Маркер (observation_id, interpretation_version) фиксируется в том же атомарном комите [A5].
8. Создание RXRecord из закоммиченных решений: key по каналу (RX1 — форма; RX2 — StructuralPattern {frame_1, connector(span)+evidence, frame_2}; RX3 — предикат/контекст), provenance {observation_id, interpretation_version, decision_id}, versions {formalizer_schema_version, framegen_version, semantic_schema_version} [B5].
Ошибки: REGISTRY_REJECT, TEMPLATE_LINK_CONFLICT (конфликт связей в скане — не привязывается молча, диагностика), MARKER_EXISTS (повторный коммит той же пары — идемпотентное завершение).

### 5.8 T6b — ревизия записанных интерпретаций
Полный протокол — §10. Кратко: триггеры (адресная ревизия по новому контексту, явное уточнение смысла реплики, пересмотр);
порядок (отзыв уровня наблюдения → при необходимости уровень элемента → атомарная смена видимой версии или журналируемые
шаги с восстановлением → инвалидация R-X LIVE→SUPERSEDED/STALE без физического удаления).

---

## 6. Decision engine

### 6.1 State machine решения

**DecisionType [Rev13]**: замкнутый enum {PREDICATE_VALUE, TEMPLATE_SELECTION, SCOPE, REFERENCE, TEMPORAL, QUERY} (§2.1);
расширение = декларация схемы.

Состояния: OPEN, GENERATING, CANDIDATES_READY, SEARCHING, PROVISIONAL, WAITING_CONTEXT, RESOLVED, AMBIGUOUS, UNRESOLVED,
FROZEN, COMMITTED, STALE, SUPERSEDED, LOST. Семантический outcome (V4 §1.4) присуждается T4 независимо от state [A1]:
state — степень фиксации, outcome — результат разрешения; RESOLVED ≠ COMMITTED.

| State | Условие входа | Выходы (переход → guard) |
|---|---|---|
| OPEN | решение зарегистрировано T3/T1; источников не запрашивалось или запрос отложен | GENERATING (запрошен ≥1 источник); UNRESOLVED (все источники пусты — сразу, NO_CANDIDATE+miss); LOST (§4.3) |
| GENERATING | выполняется проверка разрешённых источников (§5.4 п.2–4) | CANDIDATES_READY (все источники проверены, множество непусто); UNRESOLVED (все проверены, пусто — NO_CANDIDATE+miss) |
| CANDIDATES_READY | множество кандидатов зафиксировано; распространение не начиналось | SEARCHING (кластер введён в обход); PROVISIONAL (слот без constraint-рёбер и единственный кандидат — тривиальный поиск завершён мгновенно, выбор записан); UNRESOLVED (NONE_FIT от bounded selection → VALUE_OUT_OF_SET + miss [D4]) |
| SEARCHING | идёт constraint-распространение / bounded search (§7.3–7.4) | PROVISIONAL (найден ≥1 совместимый кортеж, выбор записан; при search_complete=false — PROVISIONAL до завершения); UNRESOLVED (search_complete ∧ 0 кортежей → CONSTRAINT_CONFLICT/CANDIDATE_INCOMPLETENESS; бюджет исчерпан → SEARCH_INCOMPLETE, без заморозки) |
| PROVISIONAL | выбор T3/T4 записан; совместная проверка не присудила outcome | RESOLVED (три условия §5.5 п.2); AMBIGUOUS (каждый выживший с по-значенческим основанием [A9]); WAITING_CONTEXT (INSUFFICIENT_CONTEXT); UNRESOLVED (NO_GROUNDED_CANDIDATE); FROZEN (повторение состояния, §6.3); PROVISIONAL (повторный выбор, §6.5 — новая запись в revision_history) |
| WAITING_CONTEXT | требуется новая версия контекста | CANDIDATES_READY / SEARCHING (изменилась версия контекста — повторный выбор легален даже при неизменном множестве кандидатов) |
| RESOLVED | T4 присудил RESOLVED (три условия) | COMMITTED (четыре условия T5 + атомарный batch [A11]); UNRESOLVED (адресная ревизия до коммита: транзитивная инвалидация upstream — запись в revision_history); STALE/SUPERSEDED (только после COMMITTED, §6.2) |
| AMBIGUOUS | T4 присудил AMBIGUOUS [A9] | COMMITTED (как RESOLVED; незакоммиченные альтернативы → ObservationRecord); UNRESOLVED (ревизия до коммита); WAITING_CONTEXT (контекст может сузить) |
| UNRESOLVED | присуждён отрицательный/недоказанный исход с диагностикой | GENERATING / CANDIDATES_READY (re-arm: новое содержание R/C/D/A, новый кандидат или новая версия контекста); LOST (§4.3) |
| FROZEN | осцилляционная заморозка (§6.3): повторение состояния без новых оснований R/C/D/A | SEARCHING / PROVISIONAL (re-arm ТОЛЬКО новым содержанием R/C/D/A; повторный M не размораживает [A8]); LOST (§4.3) |
| COMMITTED | атомарный batch применён, маркер зафиксирован [A11] | STALE (новая версия интерпретации того же наблюдения supersedes — §6.2); SUPERSEDED (уровень элемента: отозваны ВСЕ опоры уровня наблюдения и независимого полного доказательства нет [A7]) |
| STALE | superseded более новой версией; аудит сохраняется, читатели фильтруют по умолчанию [A12] | — (терминально для этой записи; новая версия = новые записи) |
| SUPERSEDED | элемент отозван на уровне элемента (§10.3) | — (терминально; без физического удаления) |
| LOST | канал журнала утрачен при сверке после перезапуска (§4.3 п.2); из метаданных восстановить невозможно | — (терминальная диагностика) |

**Запрещённые переходы [A]:** COMMITTED → {OPEN, GENERATING, CANDIDATES_READY, SEARCHING, PROVISIONAL, UNRESOLVED}
(пересчёт закоммиченного решения запрещён: путь — только T6b-ревизия через STALE/SUPERSEDED и новую версию);
LOST → любое; SUPERSEDED/STALE → COMMITTED (возрождение = новая запись новой версии, не переход);
GENERATING → RESOLVED/COMMITTED (пропуск этапов запрещён).

**Почему COMMITTED → OPEN запрещён, а COMMITTED → STALE разрешён.** COMMITTED означает: видимость канонического слоя
уже предоставлена читателям; факт может иметь downstream-выводы. Возврат в OPEN означал бы «пересчитать и молча заменить» —
это нарушает атомарность видимости (читатель мог бы увидеть промежуточное состояние) и разрушает аудит. STALE, напротив,
— это результат ПРОЦЕДУРЫ ревизии (§10): новая версия интерпретации записана в журнал ПЕРВЫМ, затем атомарная смена
видимой версии; старый факт остаётся в хранилище как аудит и как возможная опора независимого доказательства [A7].

### 6.2 Семантический outcome vs state (таблица соответствия)
RESOLVED/AMBIGUOUS — присуждаются T4 из PROVISIONAL; INSUFFICIENT_CONTEXT → WAITING_CONTEXT; NO_CANDIDATE и UNRESOLVED —
из GENERATING/CANDIDATES_READY/SEARCHING. Вычислительные диагностики (COMPUTATIONAL_FAILURE, PROVIDER_UNAVAILABLE,
CANDIDATE_INCOMPLETENESS, CONSTRAINT_CONFLICT, SEARCH_INCOMPLETE) — отдельный канал: решение остаётся в своём state с
диагностикой; AMBIGUOUS по вычислительной причине выдавать запрещено [A-согласно V4 §1.4].

### 6.3 Осцилляционный детектор (алгоритм)
На каждое решение хранится: seen_states[] = список (value, ground_signature), где ground_signature = хеш СОДЕРЖАНИЯ
оснований R/C/D/A (текст + provenance; буквы типов в сигнатуру не входят — два основания с разным содержанием различаются,
с одинаковым — нет) [D5]. M-ответы в сигнатуру НЕ входят и детектор не обнуляют [A8].
1. Перед записью нового выбора вычислить (value, ground_signature).
2. Если пара уже есть в seen_states И state ≠ FROZEN → повторение состояния: state = FROZEN, outcome UNRESOLVED +
   COMPUTATIONAL_FAILURE. Одна смена значения (V1→V2) парой не является — это просто новый элемент seen_states [rev7b].
3. Повторное подтверждение того же значения при неизменной сигнатуре, если решение уже в целевом состоянии (RESOLVED/AMBIGUOUS),
   идемпотентно: не записывается как осцилляция и не меняет state [D5].
4. Re-arm из FROZEN: только новое содержание R/C/D/A (сигнатура изменилась) или новая версия контекста; seen_states
   очищается при re-arm. Повторный M — никогда [A8].

### 6.4 Цепочка доказательности (почему система вправе сказать «X доказано»)

```
Observation (RawInput + TokenEvidence)
  ↓ O1: R (ресурс) + D для OOV keep-as-is; C/M только в OOV-ветке T1 (записанный I/O); A запрещён
Interpretation (frames + PROVISIONAL decisions, InterpretationVersion)
  ↓ O2: R, C (объявленные контекстные утверждения дословно), D (ID правила + свидетельства), M (записанный I/O);
        A — только внешнее объявленное предположение с явным флагом; самолегализующиеся A отклоняются валидатором
Decision RESOLVED/AMBIGUOUS
  ↓ O3: по-значенческое положительное основание выбранного значения из {R,C,D,A,M} [A9]; анти-утечки:
        A не ссылается на собственное решение; модельные догадки не переименовываются в D; повторение M не добавляет
Canonical representation (T5 batch)
  ↓ O4: основания наследуются дословно; коммит НЕ создаёт новых оснований [A]; staging-формат сохраняет ground_type/text/value/provenance
Support graph (SupportLedger, tag = точная пара [A6])
  ↓ O5: факт «доказан» ⇔ ≥1 действующая SupportRecord с допустимым типом основания; после любого отзыва — перепроверка:
        независимое полное доказательство (другая observation_id) сохраняет факт [A7]
AH fact
```

Запрещено на любом переходе: R-X-повторное использование как новое основание (запись наследует исходный провенанс);
slot-level ground как обоснование конкретного значения [D2]; расстояние DAWG как вердикт; автоматическая привязка
значения к шаблону [A].

### 6.5 Повторный выбор и ревизия (до коммита)
Повторный выбор легален при: изменении множества кандидатов ИЛИ версии контекста (§T4 V4). Адресная инвалидация
транзитивна по цепочке downstream; upstream не трогается. Добавление кандидата в закоммиченное решение → ревизия кластера;
если фрагмент уже записан — протокол T6b (§10), а не пересчёт in-place [A].

---

## 7. Constraint engine

### 7.1 Формирование кластеров (алгоритм)
Вход: Slot[] + ConstraintEdge[] одной InterpretationVersion.
1. Построить граф G с вершинами = слоты. Ребро типа F между двумя слотами, если оба принадлежат ОДНОМУ FrameCandidate
   (значение предиката + привязки его участников + scope-операторы этой рамки). Правило: **предикат + аргументные
   привязки + scope одной рамки = ОДИН кластер** — они проверяются совместно, T4 присуждает исходы по кластеру.
2. Ребро типа X между слотами, если объявленное constraint-ребро (ConstraintEdge) их соединяет; X-рёбра между разными
   рамками НЕ сливают кластеры: кластер = связная компонента по F-рёбрам; X-рёбра хранятся как межкластерные связи.
3. Область поиска для согласованности = связный компонент в объединённом графе (F ∪ X) затронутых ограничений; компонент
   может охватывать всё предложение — перечисление не запрещено, оно велико и бюджетировано [V4 §6.2/§6.4 rev7].
4. Пересборка: новое объявленное ребро → пересчитать области поиска; списки членов кластеров сохраняются (слияние =
   новая область, а не уничтожение кластеров). Автоматическое слияние кластеров без X-ребра запрещено; слияние между
   разными InterpretationVersion запрещено.

### 7.2 Constraint: формат и источники
ConstraintEdge {edge_id, interpretation_version, slots[], forbidden_tuples[] (n-арные запрещённые сочетания значений),
rule_id, D-ground}. Источники: декларации версионной схемы; объявленные правила (кореферентная идентичность, вложенность
scope, уникальность связывания референта). Каждое применение constraint'а порождает D-запись с rule_id.

### 7.3 Распространение ограничений (алгоритм)
1. Порядок применения: constraints сортируются по индексу объявления, затем по id слота; обход однопоточный и
   детерминированный [B3] — параллельное применение запрещено до доказательства идентичного порядка перечисления.
2. Итеративно (до фикс-поинта): для каждого constraint'а удалить из множества каждого участника значение, у которого
   НЕТ поддержки целым кортежем в выживших множествах партнёров по n-арному ограничению (обобщённая дуга-согласованность;
   не «каждый сосед отдельно»). Каждое удаление записано (D + rule_id). Монотонно: множества только сжимаются внутри версии.
3. Множество опустело → остановиться; классификация по §5.5/§6.4 V4: CANDIDATE_INCOMPLETENESS (генератор не произвёл
   поддерживающего значения) либо CONSTRAINT_CONFLICT (объявленные ограничения взаимно несовместимы); решение UNRESOLVED,
   трасса фиксирует сработавшие ограничения. Никогда не «выбирается первое выжившее» молча.
4. Фикс-поинт достигнут → переход к bounded search (§7.4).

### 7.4 Bounded search совместимых кортежей (алгоритм)
1. Распространение НЕ доказывает существование общего решения (три двоичные переменные с попарным «не равны» проходят
   локальную проверку, но общего решения нет): перечисляются полные назначения, удовлетворяющие ВСЕМ ограничениям.
2. Детерминированный порядок: слоты по id, значения в порядке регистрации; цикл constraint-рёбер обрабатывается
   конденсацией SCC (цикл сам по себе ≠ UNRESOLVED [V4 §6.4 rev7]).
3. Флаг search_complete + контрольная точка позиции обхода в журнале [D5]: продолжение с сохранённой позиции оплачивает
   только оставшиеся шаги; сумма затрат двух прогонов равна затратам одного полного.
4. Исходы: (а) ≥1 кортеж И search_complete → совместный выбор (§7.5); кортежи найдены, но перечисление прервано бюджетом →
   выбор только среди найденных, PROVISIONAL до завершения; (б) завершено, 0 кортежей → CONSTRAINT_CONFLICT /
   CANDIDATE_INCOMPLETENESS, UNRESOLVED; (в) budget исчерпан до завершения → SEARCH_INCOMPLETE: отсутствие НЕ доказано,
   UNRESOLVED без заморозки; найденные кортежи доступны для PROVISIONAL-выбора. Увеличение бюджета = продолжение того же
   поиска (вычислительная операция; новые смысловые основания не требуются; осцилляционный детектор не считает это
   повторным выбором [V4 §6.3]).

### 7.5 Совместный выбор
Допустим только между найденными совместимыми кортежами: bounded selection (§8) по замкнутому множеству кортежей; при
нескольких — AMBIGUOUS/RESOLVED по основаниям [A9]; не разрешено в бюджете → UNRESOLVED + диагностика. Выжившие наборы
хранятся как согласованные кортежи (не независимые списки по слотам) и персистятся в ObservationRecord.linked_alternatives;
отбрасывание — явная операция с причиной [V4 §6.4 п.5].

---

## 8. Граница LLM (контракт, не подключение)

### 8.1 SelectionRequest (Python → LLM)
```
SelectionRequest {
    request_id          — id попытки (счётчик оплаты)
    decision_id         — решение, для которого вызов
    slot_id / frame_id  — слот и рамка
    context_span        — объявленный пропуск текста (дословно)
    mentions[]          — упоминания с surface + морф-признаками из TokenEvidence
    candidates[]        — ЗАКРЫТОЕ множество ЭТОГО решения: {candidate_id, label} [B4]
    contextual_statements[]  — объявленные контекстные утверждения, дословно (базовый прогон — пустой список)
    schema_version      — версия семантической схемы
    protocol_lang       — "en" [C4]
}
```

### 8.2 SelectionResponse (LLM → Python)
```
SelectionResponse {
    outcome   ∈ ONE_SELECTED | MULTIPLE_ADMISSIBLE | NONE_FIT
    selected[] ⊆ candidate_id из candidates; кардинальность: ONE→ровно 1, MULTIPLE→≥2, NONE→0
    note?     — свободный текст (не является основанием)
}
```

### 8.3 Что LLM никогда не получает [A]
- значения других решений и исходы других кластеров;
- записи R-X как утверждения об истине (только ранжированные candidate_id с меткой источника);
- текст за пределами объявленного context_span;
- инструкции на генерацию новых значений/рамок/решений/оснований.

### 8.4 Что LLM никогда не создаёт [A]
- значение вне замкнутого множества (id из схемы, но вне множества решения = ProtocolError);
- новые рамки, слоты, решения, constraint'ы; структурные объекты (клаузы/границы/эллипсис/scope-деревья) [I30];
- основания: M-основание конструирует T3 ИЗ записанного I/O (last_prompt + raw_response), а не «из головы» LLM.

### 8.5 Валидатор (алгоритм) — выдаёт только верифицированный ПРОТОКОЛЬНЫЙ исход [A2]
1. Ответ не JSON / нарушена схема → ProtocolError.
2. outcome ∉ {ONE_SELECTED, MULTIPLE_ADMISSIBLE, NONE_FIT} → ProtocolError.
3. selected содержит id вне candidates[] → ProtocolError.
4. Нарушение кардинальности (п.8.2) → ProtocolError.
5. Пройдено → верифицированный протокольный исход; семантический исход присуждает ТОЛЬКО T4 [A2].

### 8.6 Стоимость и replay
- Одна оплата за попытку select(), включая неудачные (ProtocolError, PROVIDER_UNAVAILABLE) [D5]; скрытых повторных
  попыток без учёта нет.
- Replay [D3]: на решении хранятся last_prompt и raw_response; повторный прогон raw-ответа через валидатор обязан дать
   тот же выбор; расхождение → диагностика REPLAY_MISMATCH (запись аудита, решение не аннулируется).
- Антиподделка: расширенный сценарий опирается на контекстное утверждение только если оно объявлено в contextual_statements
  промпта; иначе поведение деградирует к базовому.

### 8.7 Отказ провайдера
PROVIDER_UNAVAILABLE — вычислительная диагностика: решение остаётся в текущем state (OPEN/GENERATING/CANDIDATES_READY),
AMBIGUOUS не присуждается; повторный вызов легален при новом бюджете; частичной записи ответа нет (ответ атомарен).

---

## 9. AH integration

### 9.1 ObservationStore (канал наблюдений) [A5]
ObservationRecord {observation_id = hash(source_id + span), source_id, span (= диапазон SentenceUnit/ClauseUnit
формализации — единица наблюдения [D9]), interpretations[] (версионированные), linked_alternatives[], status ∈
{UNRESOLVED, RESOLVED}, context_version, resolution_log[], diagnostics[] (ссылки на структурированные Diagnostic:
stage+code+detail, §2.1 [D5])}. Append-only; write-through +
fsync на запись; ключ записи — точная пара (observation_id, interpretation_version); все версии сосуществуют [D7].
**Дубликат наблюдения** [Rev10]: точный дубликат (тот же хеш текста входа + та же context_version) → идемпотентный no-op:
новая InterpretationVersion НЕ создаётся, bounded selection НЕ повторяется. Другое содержание ИЛИ новая версия контекста →
новая interpretation version на том же observation_id; повторное наблюдение обновляет запись, не создаёт дубля.
Позднее разрешение: новый контекст триггерит адресную ревизию наблюдений, совместимых по source/span/сущностям;
разрешение → коммит (T5/T6) или новая версия; отбрасывание — явная операция с записью причины.
**Нагрузка объекта** [Rev10]: ObservationRecord = идентичность + индекс видимости, а НЕ контейнер фактов: факты живут в
InterpretationVersion и каноническом слое, record хранит только ссылки. `status` = статус ВИДИМОЙ версии (выводится из
InterpretationVersion.status + outcome); вся история — в resolution_log/diagnostics с ключом interpretation_version.
Структура зафиксирована как есть: 9 полей, каждое несёт отдельную функцию (идентичность ×3, видимое состояние ×2,
история ×2, диагностика ×1, контекст ×1).

### 9.2 Четыре условия коммита [A11]
(1) генерация завершена на текущих версиях входов; (2) нет ожидающих записей; (3) зависимости разрешены либо представлены
связанными альтернативами, включая constraint-рёбра; (4) целостность пройдена. Коммит — единственный момент видимости
канонического слоя. Порядок: журнал наблюдений ПЕРВЫМ → атомарный канонический коммит элементов + маркера.

### 9.3 Каноническое отображение (единственный корректный способ записи) [A4]
Единица предикации — N (Hypernode); словариное ядро S/T/G/L общее и бессловесное; провенанс/статус на N.meta/M.meta.
- Ключ канонизации шаблона = (предикат S, конфигурация ролей, объявленное значение). Значение входит в идентичность через
  выбор среди нескольких T под одним лексическим S (легитимный случай существующего резолвера template_resolver.py).
- Реестр связей «значение → uid шаблона» хранится в версионной схеме. Связь существует только как явное решение:
  bounded-выбор template_selection среди существующих T под S либо явная операция расширения схемы (создание T + фиксация
  связи). Автоматическая привязка запрещена, в т.ч. при единственном структурном кандидате [A].
- Восстановление связей после перезапуска: сначала из персистентного реестра; fallback — скан N под кандидатными шаблонами по
  properties["relation"]; конфликтующая связь НЕ привязывается молча (не «первый T») → диагностика TEMPLATE_LINK_CONFLICT, как и
  расхождение реестра со сканом.
- Перефразировки с разными лексическими S («есть» vs «обладает») не сливаются автоматически: общее представление — только
  явный value-level-маппинг на один канонический шаблон либо объявленная эквивалентность значений. merge_identity/
  SupportLedger.rewire_ref объединяет ссылки на сущности, а не предикаты/шаблоны; выбор фиксируется в трассе.
- Кванторы/модальность: actants принимает Operand = Ref | BoundVar (operands.py); операторы — G через ensure_function.
  **Двусмысность снята [Rev10/Rev12]**: **Фаза 1 (заморожено)** — MutationPlan содержит только запись
  N.meta["scope"] = сериализованное ScopeOperatorNode-дерево (§15.3; канонический round-trip); канонические G-элементы НЕ
  создаются; читатели Фазы 1 не обязаны ожидать G для кванторов. **Фаза 2** — G-элемент на узел (NQ5) через ensure_function
  + BoundVar-actants; upgrade-миграция: записи meta["scope"] являются источником истины для backfill G-элементов (явная
  миграция, никогда неявная). Молчаливой потери нет: решение и его основания живут в канале 1.
- Время [Rev12]: N.meta["time"] = {TemporalExpression, anchor_chain} (§15.6); полная timepoint-модель — Фаза 2 (NQ6).
- Запросы [Rev12]: modus QUERY не коммитится как факт; QueryCompiler → AssociationGoal через объявленное отображение
  (V4 §5.9) (§15.7).
- Coreference [Rev12]: ReferenceDecision управляет merge_identity при коммите (T6); неразрешённые ссылки —
  linked_alternatives + REFERENCE_UNKNOWN.
- Три класса контрактных тестов [A12]: (а) различение — два T с одинаковыми полями под одним S дают разные канонические
  элементы; (б) совместимость — перефразировки одного факта при одном выбранном T сливаются find_hypernode_by_signature;
  (в) семантический читатель (Фаза 2) — InferenceEngine-цель по материализованным структурам возвращает ожидаемый результат.

### 9.4 Корректность читателей [A12]
Для каждого читателя (InferenceEngine: каждый Goal-тип; AssociationCoordinator; DSL-interpreter; GUI-проекция):
HYPOTHETICAL/EMBEDDED/ObservationRecord не удовлетворяют fact-целям без явного допуска; SUPERSEDED фильтруется по умолчанию,
STALE-выводы не используются как опора (тесты T6b); CounterfactualGoal — только во временном контексте.

### 9.5 Бюджеты [B8]
Три счётчика в трассе: локальное вычисление (мс), LLM-ожидание (мс/вызовы), итог. Лимиты: вызовы bounded selection на
фрагмент, размер множества кандидатов, wall-clock; числовые значения — после данных [default: llm_limit=8,
search_step_limit=200]. Исчерпание → BUDGET_EXHAUSTED + диагностика; превышение потолка размера множества на слоте →
BUDGET_EXHAUSTED (не молчаливое усечение).

---

## 10. Revision model (T6b)

### 10.1 Триггеры адресной ревизии
(а) новый контекст, совместимый по source/span/сущностям; (б) явное уточнение смысла реплики говорящим (disambiguation act);
(в) пересмотр: новое содержание R/C/D/A, меняющее решение закоммиченного фрагмента. Повторный M-ответ триггером НЕ является [A8].

### 10.2 Идентичность: факт vs наблюдение [A6]
observation_id = hash(source_id + span) — не зависит от интерпретации; пересмотр структуры меняет только interpretations
(новая версия), а не идентичность. Span в хеше — диапазон единицы формализации (SentenceUnit/ClauseUnit, §9.1): ревизия
адресуется по unit-диапазону, и смена clause-сегментации при новой версии свидетельств НЕ меняет идентичность наблюдения
toй же SentenceUnit [D9]. Факт (канонический элемент) и наблюдение (запись журнала) — разные сущности: отзыв всех
непосредственных наблюдений НЕ отменяет факт, если осталось независимое полное доказательство (другая observation_id) [A7].

### 10.3 Два уровня отзыва (алгоритм; не взаимозаменяемы [A7])
1. **Уровень наблюдения** (всегда первый): удалить SupportRecord с тегом = точная пара (observation_id, interpretation_version)
   — на существующих примитивах: clone → фильтр записей по тегу → replace_from; это не трогает опоры других наблюдений и НЕ
   затрагивает downstream-выводы, чьи посылки остаются действующими.
2. **Уровень элемента** (invalidate_by_premise по uid элемента): применяется ТОЛЬКО когда элемент сам становится SUPERSEDED —
   отозваны ВСЕ его опоры уровня наблюдения И независимого полного доказательства нет; вызов над ещё действующим N ошибочно
   инвалидирует зависимые выводы. Зависимые доказательства пересматриваются при потере действительности их посылки: вывод,
   единственная посылка которого — общий N, помечается к ревизии (не удаляется молча).

### 10.4 Атомарность смены версии [A-согласно V4 rev7]
Читатель видит либо старую, либо новую видимую версию, никогда промежуточное состояние: (а) атомарная смена версии в одном
комите канонического хранилища ИЛИ (б) журналируемые шаги с восстановлением (журнал шагов + маркер завершения; при сбросе —
восстановление до последнего завершённого шага).

### 10.5 Инвалидация R-X [B5]
Записи superseded-интерпретации: LIVE → SUPERSEDED/STALE (без физического удаления — аудит); новая интерпретация создаёт
новые записи. «Формализатор не учится на собственных уже признанных ошибках»: запись из отозванной версии не читается ни одним
из каналов RX1/RX2/RX3 до явной миграции.

---

## 11. Failure handling (негативные сценарии)

Для каждого: триггер → ожидаемое состояние системы (state решений, диагностики, каналы персистентности). Ни один сценарий не
приводит к молчаливой подмене фактов и не выдаёт AMBIGUOUS по вычислительной причине [A].

| # | Сценарий | Ожидаемое состояние |
|---|---|---|
| N1 | Два одинаковых значения с разными источниками (SCHEMA + RX3 дают V2) | Один кандидат со списком source; R-X-источник не считается основанием (§6.4 O3); доказательность = только SCHEMA/R/C/D/M; дедупликация по (slot, value), provenance per-source сохраняется в аудите |
| N2 | Один источник с двумя версиями интерпретации (v1 и v2 того же наблюдения) | Обе версии сосуществуют в журнале по точным парам [D7]; факт действителен ⇔ ≥1 действующая опора среди ВСЕХ версий; отзыв v2 не трогает опоры v1; выжившая v1 ни маскирует, ни удовлетворяет утерянную v2 |
| N3 | Удаление знания после коммита (T6b по триггеру 10.1) | Протокол §10: уровень наблюдения первым → при необходимости уровень элемента (§10.3); атомарная смена видимой версии [§10.4]; R-X записи LIVE→SUPERSEDED/STALE; независимое полное доказательство сохраняет факт [A7]; читатели видят либо старую, либо новую версию |
| N4 | Изменение значения предиката в закоммиченном фрагменте (V1→V2) | Адресная ревизия: транзитивная инвалидация по цепочке downstream (§6.5); журналируемые шаги с восстановлением; новая версия интерпретации → новый batch + маркер новой пары; старый факт STALE/SUPERSEDED в аудите; повторный M-ответ триггером не является |
| N5 | Новый кандидат после COMMITTED | Решение НЕ открывается (COMMITTED→OPEN запрещён [A]); кандидат регистрируется в InterpretationVersion как pending; если он противоречит закоммиченному значению через объявленное constraint-ребро → протокол T6b (§10); иначе — запись в resolution_log для следующей версии контекста |
| N6 | Противоречивые ограничения (запрещены все кортежи) | Распространение опустошает множество → остановка; диагностика CONSTRAINT_CONFLICT (объявленные ограничения несовместимы) либо CANDIDATE_INCOMPLETENESS (генератор не произвёл значения); решение UNRESOLVED с трассой сработавших ограничений; «первое выжившее» молча не выбирается |
| N7 | Бесконечный цикл зависимостей | Конденсация SCC (§7.4 п.2); bounded search внутри компонента с бюджетом; cycle сам по себе ≠ UNRESOLVED: исход = результат поиска (завершено+0 → конфликт/неполнота; незавершено → SEARCH_INCOMPLETE) |
| N8 | Бюджет исчерпан посередине поиска | SEARCH_INCOMPLETE: отсутствие решения НЕ доказано; решение UNRESOLVED без заморозки; найденные кортежи доступны для PROVISIONAL-выбора; увеличение бюджета = продолжение с контрольной точки, оплата только оставшихся шагов [D5] |
| N9 | Падение LLM после формирования запроса | Попытка оплачена один раз (§8.6); решение остаётся в предшествующем state (OPEN/GENERATING/CANDIDATES_READY) + PROVIDER_UNAVAILABLE; частичной записи нет (ответ атомарен §8.7); повторный вызов легален при новом бюджете |
| N10 | Изменение формата схемы (semantic_schema_version bump) | Записи со старой версией НЕ применяются автоматически: либо не используются, либо явно мигрируются объявленной процедурой; решения, ссылающиеся на старые значения, действительны в своей замороженной версии; новые прогоны используют новую версию; расхождение версий → диагностика SCHEMA_VERSION_MISMATCH |

Дополнительно: T0_COVERAGE_VIOLATION (вход отклонён), R1_LIMIT, OOV_KEEP_AS_IS, STRUCTURE_NOT_COVERED [B1], CLAUSE_NOT_COVERED,
CONNECTIVE_NOT_COVERED [D1], SCOPE_NOT_COVERED [D3], VALUE_OUT_OF_SET [D4], NO_HEAD_CANDIDATE [B14], EXPANSION_AMBIGUOUS
(информационная), RULE_VERSION_MISMATCH, DEPENDENCY_NOT_COVERED, SENSE_CONFLICT, QUERY_TARGET_UNBOUND, WK_CONTRADICTION,
POLICY_NO_WINNER, TEMPORAL_ANCHOR_UNRESOLVED [Rev12], DEPTH_LIMIT,
REGISTRY_REJECT, TEMPLATE_LINK_CONFLICT, MARKER_EXISTS (идемпотентное завершение), REPLAY_MISMATCH, SCHEMA_VERSION_MISMATCH,
NO_GROUNDED_CANDIDATE, CLUSTER_CONFLICT, COMPUTATIONAL_FAILURE, BUDGET_EXHAUSTED. Вычислительные диагностики — отдельный
канал от семантических исходов [A-согласно V4 §1.4].

---

## 12. Сквозной пример (S1: «У вороны есть лапки», baseline vs augmented)

Структуры на каждом этапе (идентичный механизм, различаются только контекстные утверждения — D3-проверка):

| Этап | Baseline | Augmented (F1: «Лапки — часть тела этой вороны.») |
|---|---|---|
| T0 | 4 span'а: [У][вороны][есть][лапки] + SentenceUnit (весь вход, terminal «.») | то же |
| T1 | «у» PREP; «вороны» {NOUN nom, NOUN gen}; «есть» INFN (copula-лемма); «лапки» NOUN nom/plur; 1 ClauseUnit (нет CONJ); Mentions: [«вороны»], [«лапки»] | то же |
| T2 | OP2: copula-эллипсис НЕ применим (явная copula «есть») → рамка {predicate=«есть», participants=[«вороны»(possessor, gen по управлению), «лапки»(object)]}; альтернатива OP1 отброшена D-трассой | то же |
| T3 | Слот predicate_value: кандидаты {V1 HAVE, V2 HAS_PART} по candidate_generation_rules demo v1: OP2 copula-рамка → {HAVE, HAS_PART} [D7/C]; contextual_statements=[]; bounded selection → MULTIPLE_ADMISSIBLE {V1,V2}; M slot-level (value=None); Decision PROVISIONAL, персистится немедленно | те же кандидаты; contextual_statements=[F1 дословно]; C-основание на V2 (видимый провенанс F1) + M value-bound на V2 → ONE_SELECTED V2; Decision PROVISIONAL |
| T4 | search_complete=true, кластер валиден; ни у одного значения нет по-значенческого положительного основания → UNRESOLVED + NO_GROUNDED_CANDIDATE [A9]; linked_alternatives {V1},{V2} в ObservationRecord (канал 1) | V2: C(F1)+M(value=V2); кластер валиден, search_complete=true → RESOLVED(V2) |
| T5/T6 | Коммит не состоялся (условие: нет RESOLVED); ObservationRecord UNRESOLVED существует независимо [A5] — материал C2 | Четыре условия true → batch + маркер; N с properties["relation"]="HAS_PART", template_selection по реестру, SupportRecords {C(F1), M} с тегом точной пары; RX3-запись создана |
| T6b (при F1′: «У вороны лапки — это перья.») | — | Адресная ревизия: отзыв уровня наблюдения (тег v1) → уровень элемента (все опоры отозваны, независимого доказательства нет) → SUPERSEDED; атомарная смена на v2 (RESOLVED по F1′); R-X записи v1 → SUPERSEDED |

Материал метрик: baseline S1/S2/S4 — UNRESOLVED {V1,V2} (честная неполнота, C2); augmented — RESOLVED; C3 = доля
протокольно валидных ответов селектора на реальных прогонах.

---

## 13. Open questions (остатки выбора с зафиксированными значениями по умолчанию)

| # | Вопрос | Статус | Значение по умолчанию [default] |
|---|---|---|---|
| Q2 | Нужен ли отдельный канал для вопросов vs утверждений в каноническом слое | после данных Фазы 1 | единый канал + модус (V4 §5.1) |
| Q3 | Граница «семантически завершённого фрагмента» для коммита | после данных | рамка + её привязки как минимальная единица |
| Q7a | Выбор/состав R-V (валентностный ресурс) | отложен | T2 работает по объявленным правилам OP1–OP5 без R-V |
| Q7b | Создание R-S (значения предикатов) | отложено до miss-отчётов | T3 — схема + R-X3; открытое множество значений НЕ вводится |
| Q8 | Формат хранилища журнала наблюдений и R-X | после данных | append-only JSONL + fsync (прототипный формат) |
| NQ5 | Полная каноническая материализация scope-операторов (G/BoundVar, §9.3) | Фаза 2, после данных Фазы 1 | meta["scope"] + журнал наблюдений [B11] |
| NQ6 | Полная каноническая timepoint-модель в AH | Фаза 2 [Rev12] | N.meta["time"] = {expr, anchor_chain} (§15.6); контракт anchoring chain зафиксирован — миграция механическая |
| NQ7 | Размер discourse window для coreference | после данных [Rev12] | объявленная константа в ruleset; REFERENCE_UNKNOWN + miss при исчерпании |
| NQ1 | Метрика/порог DAWG-поиска lexical recovery | эксперимент | Levenshtein ≤ 2 + морфологический/source-frame фильтр; расстояние ранжирует, не вердикт |
| NQ2 | Числовые значения бюджетов | после данных Фазы 1 | llm_limit=8, search_step_limit=200 на фрагмент |
| NQ3 | Токенизация слитных форм (прилеченные написания) | вне Фазы 1 [B] | пробельный сплит + объявленный набор пунктуации (§5.1); расщепление слитных форм не выполняется, OOV-ветка обрабатывает форму как есть |
| NQ4 | Параллелизация constraint-распространения | запрещено до доказательства [B3] | однопоточный детерминированный порядок |

---

## 14. Formalizer invariants (обязательные для реализации)

Каждый инвариант — проверяемый контракт; нарушение любого из них = дефект реализации, а не допустимое упрощение.

| # | Инвариант | Где зафиксировано | Как проверяется |
|---|---|---|---|
| I1 | Нет молчаливой потери: каждый span либо формализован, либо имеет персистентную диагностику с его именем (§5.3 п.4, §9.1 diagnostics[]) | §5/§9 | coverage-тесты на S-A…S-E + adversarial-входы |
| I2 | Валидатор никогда не выдаёт семантический исход; protocol outcome ≠ semantic outcome (RESOLVED — только T4) | §8, §5.5 | unit-тесты валидатора (test_formalizer_selection_protocol) |
| I3 | Решения T3 персистятся немедленно; PROVISIONAL до T4; RESOLVED — только по трём условиям T4 | §5.4, §5.5 | pipeline-тесты + инспекция журнала |
| I4 | Нет самоподтверждения: повторное использование R-X не создаёт оснований (не новые R/C/D/A/M); снижение приоритета ≠ снятие неоднозначности | §2.3, V4 §5.10 | тест cache-reuse с пустым контекстом |
| I5 | Нет auto-binding: связь «значение → шаблон» только через объявленную запись реестра; неизвестный g.ID отклоняется на write-границе | V4 §7.2, §9.3 | тест отклонения FunctionRegistry |
| I6 | Честная неполнота персистится и переживает перезапуск (диагностики в канале 1) | §4.3, §9.1 | restart-replay-тест на S-D/S-E |
| I7 | Два канала сверяются по ТОЧНОЙ паре (observation_id, interpretation_version); выживший v1 не скрывает потерянный v2 | V4 §7.1, §9.1 | real-file durability-тест с version reconciliation |
| I8 | Осцилляционный freeze — при повторении состояния без изменения сигнатуры реальных оснований; M никогда не сбрасывает детектор | §6.5 | single-flip-not-oscillation + state-repetition-freezes тесты |
| I9 | Чистота стадий: T1 читает только R-X1, T2 — только R-X2, T3 — только R-X3 (один хранилище, stage-dependent read contract) | V4 §5.10 | reader-contract-тесты |
| I10 | Нет per-example правил между прогонами демо; механизм идентичен для S1–S6 (D3 transfer check) | V4 §11 | diff набора правил до/после каждого предложения |
| I11 | Атомарный коммит: журнал ПЕРВЫМ, канонический слой вторым со ссылкой; маркер идемпотентен | §9.2 | crash-window-тест |
| I12 | Версионная идентичность и mismatch: сверка по точной паре; несовпадение formalizer_schema/framegen/semantic версий → не использовать или явная миграция, никогда неявное применение | V4 §7.1, §2.2 | v1-doesn't-hide-v2 тест + mismatch-rejection тест |
| I13 | Декларативная расширяемость T1 [B14]: новые типы голов / mention-типы / паттерны расширения = новая декларация HeadRule/ExpansionRule или запись ресурса; ядровой алгоритм (оценка правил, сборка кандидатов) не изменяется. Семантические предикаты в activation-условиях запрещены | §5.2 п.9a–9d | декларативный самоаудит (§5.2 п.9): каждый пример описывается срабатываниями правил без изменения ядра; diff ядра до/после добавления правила пуст |
| I14 | Нет семантической утечки в TD [Rev12]: relation_type DependencyCandidate — только из закрытого структурного набора {GOVERNS, MODIFIES, COORD, COREF, TEMPORAL_MOD}; activation-условия DependencyRule работают по признакам R1 и объявленной локальной структуре; TD не создаёт семантические решения/основания C/M/W | §15.1 | валидация ресурса отклоняет правила с семантическими отображениями; аудит выхода TD на демо-корпусе: ни одного семантического отношения |
| I15 | Множество смыслов закрыто LexicalResource [Rev12]: LLM выбирает только среди объявленных sense_id (bounded selection §8); новый смысл = версионная запись через learning loop, никогда не свободная генерация | §15.2 | аудит промпта T3: только объявленные sense_id; валидатор отклоняет неизвестный sense_id |
| I16 | Scope-операторы — дерево с объявленными scoping-правилами [Rev12]: вложенность NOT(EVERY(...)) канонически сериализуется (round-trip); полярность выводится из NEG-узла — единый источник истины | §15.3 | тест вложенности + round-trip сериализации; проверка consistency N.meta["polarity"] с scope-деревом |
| I17 | Каждая reference-связь имеет evidence и может быть AMBIGUOUS [Rev12]: жёсткие фильтры coreference — только объявленные правила согласования; несколько выживших антецедентов → AMBIGUOUS, не тихий выбор | §15.4 | тест с двумя совместимыми антецедентами → AMBIGUOUS; аудит: каждая ReferenceDecision несёт evidence[] |
| I18 | W-основания никогда молча не перекрывают C [Rev12]: каждое противоречие C vs W записывается (miss-отчёт); каждое W-основание несёт record_id + версию ресурса | §15.5, §15.9 | тест C-vs-W противоречия → constraint + запись; аудит provenance W-оснований |
| I19 | Запросы не являются фактами [Rev12]: modus QUERY не создаёт закоммиченных фактов (условие T5); ответ InferenceEngine = новое наблюдение со своим провенансом, никогда не сливается молча с источником запроса | §15.7 | тест условия коммита на query-входе: batch не содержит факт-элементов из запроса |
| I20 | Learning loop изменяет только версионные ресурсы через валидированные предложения [Rev12]: ядро, EvidencePriorityPolicy, множества значений схемы — только явный review; старые версии ресурсов сохраняются для replay; прошлый прогон воспроизвим по точному кортежу версий | §15.10 | тест proposal→version + replay старого кортежа версий; A/B-сравнение на фиксированном корпусе |
| I21 | OperatorCompositionEngine — единый слой для всех типов операторов [Rev13]: вложенность разрешается только объявленными общими правилами (близость триггера к предикату, граница клаузы, surface-порядок); разные surface-структуры области действия дают РАЗНЫЕ канонические сериализации ScopeTreeCandidate; несколько удовлетворяющих деревьев сосуществуют как кандидаты — тихий выбор запрещён | §15.3 п.2 | парный тест «не каждый/каждый не» → NOT(EVERY) vs EVERY(NOT); «Иван не знает, что Пётр пришёл» → NEG в матричной клаузе; round-trip сериализации различим |
| I22 | Приоритеты domain-dependent и версионные [Rev13]: глобального недообъявленного source-приоритета нет; каждое dominance-правило принадлежит объявленной области политики; недообъявленная область = только constraint (без auto-winner). CoreferencePolicy — версионный ресурс с детерминированным lexicographic-ранжирингом; ядро не зашивает критерии | §15.4, §15.9 | аудит: в коде/политике нет глобального C>W вне domain_rules; replay двух прогонов даёт идентичный порядок кандидатов |
| I23 | Provenance Preservation [Rev13b]: для любого resolved semantic structure существует непрерывная provenance chain от исходного surface span до финального решения (transformation_chain без разрывов; каждый шаг несёт producer_component + version); provenance не участвует в выборе, ранжировании и знаниях (§2.5 P2) | §2.5 | тест: для каждой RESOLVED-структуры демо-корпуса реконструировать цепочку TokenSpan → … → Decision и проверить непрерывность; аудит кода: поля ProvenanceRecord не используются в генерации/ранжировании кандидатов |
| I24 | Нет раннего связывания сущностей [Rev14]: T1–T4 не создают канонических связей между сущностями и не пишут в каноническое хранилище; identity/dedup/linking принимает только Consolidator по CandidateIR (§2.6/§2.7); phrase-level identity запрещена по умолчанию (§16.5); existential unknowns представляются как EXISTS + discourse reference, фиктивные сущности запрещены (§16.6) | §2.6–2.7, §16.5–16.6 | аудит выходов T1–T4: ноль канонических ссылок до consolidation; «Кто-то вошёл. Он сел.» → EXISTS x без m_UNKNOWN_PERSON; «красная машина» → entity + attribute без нового m |
| I25 | Никакая стадия до Consolidation не имеет права изменять Canonical Memory [Rev14.1]: запись в каноническое хранилище делает только коммит-стадия (T6 integrate_plan) по результату консолидации; CandidateIR — immutable snapshot (§2.6); T0–T4 и TD не имеют write-доступа к каноническому хранилищу | §2.6, §9 | аудит кодовых путей: ни одного вызова записи в каноническое хранилище до Consolidator/T6; тест: сбой на T3 оставляет каноническое хранилище неизменным |
| I26 | SRL не создаёт семантики [Rev15]: в выходе нет семантических фактов/propositions; нет записей в Canonical Memory (расширяет I25 — SRL до Consolidation); нет выбора единственной интерпретации; нет identity links (§2.7/I24) — только структурные кандидаты с провенансом | §17.2, §17.3 | аудит выхода SRL: ноль семантических/канонических объектов; тест: сбой на SRL оставляет каноническое хранилище неизменным |
| I27 | Все структурные реконструкции имеют provenance [Rev15]: каждый TokenHypothesis/BoundaryCandidate/ClauseCandidate/EllipsisCandidate/MissingArgumentCandidate несёт ProvenanceRecord (§2.5) с pattern_id/rule_id + span входа; кандидат без провенанса не существует | §17.3, §2.5 | реестровая проверка: 100% SRL-кандидатов с ProvenanceRecord; тест: кандидат без pattern_id отклоняется на write-границе |
| I28 | Влияние контекста/памяти до семантического выбора — только через evidence [Rev15]: каналы памяти (§17.4) добавляют Grounds с провенансом, меняют ранжирование объявленной версионной политикой и помогают разрешению; скрытых правил нет, кандидатов без основания не создаётся; R-X — не основание (O3); один вход при разных версиях контекста может дать разные исходы только через записанные свидетельства | §17.4 | аудит: каждое влияние памяти в трассе имеет ссылку на Ground/политику; тест: две версии контекста «Он взлетел» — различие исходов объяснено записанными свидетельствами |
| I29 | Все альтернативы сохраняются до resolution [Rev15]: SRL-кандидаты (и их downstream-подтверждения) не удаляются молча; REJECTED только с D-trace, EXPIRED при смене версии (§2.3); linked_alternatives адресуются в ObservationRecord | §17.3, §2.3 | тест: отклонённый boundary/ellipsis-кандидат остаётся в журнале с причиной; аудит молчаливых удалений — ноль |
| I30 | Структурное закрытие [Rev16]: множество структурных объектов (ClauseUnit/FrameCandidate/EllipsisCandidate/границы/scope-деревья) ЗАКРЫТО после TD+T2; T3/T4 принимают решения только по существующим кандидатам и не генерируют новую структуру (§8.4); отсутствующая нужная структура → NOT_COVERED-диагностика, а не молчаливая генерация | §17.3, §5.3–5.4, §8.4 | тест: «Иван сказал Петя пришёл» — T3/T4 работают только с A/B-сегментациями из SRL; аудит выходов T3/T4: ноль новых структурных объектов |

---

## 15. Семантический слой композиции (Rev12)

Rev12 расширяет архитектуру из структурного формализатора в универсальный формализатор естественного языка. Все механизмы —
declarative и версионные; расширение = новая декларация правила/ресурса/схемы, никогда не изменение ядра [B14]. Стадия TD
(DependencyComposition) вставлена между T1 и T2 (§4.1); семантические слои (смыслы, мировые знания, время, запросы)
участвуют в T3/T4 через объявленные ресурсы и политики.

### 15.1 DependencyComposition layer (TD)
Позиция: T1 → **TD** → T2. Input: MentionCandidate[] + TokenEvidence[] по SentenceUnit (+ cross-unit window для coreference).
Output: DependencyCandidate[] + ReferenceDecision[] + ScopeOperatorNode-деревья. LLM: нет — TD чисто структурный;
неоднозначные зависимости сосуществуют как кандидаты, тихого отсечения нет.
1. **DependencyRule** (§2.1): декларативный предикат по паре (mention/token) + объявленной локальной структуре →
   relation_type из ЗАКРЫТОГО структурного набора {GOVERNS, MODIFIES, COORD, COREF, TEMPORAL_MOD}. Семантические отношения
   (HAVE, агентность, часть-целое…) НЕ являются типами зависимостей — они существуют только как решения T3/T4.
2. **DependencyCandidate** (§2.1): TD создаёт для каждого срабатывания правила; несколько правил могут сработать на одной паре
   — все кандидаты сохраняются (linked_alternatives). Ожидаемое объявленным паттерном совпадение не найдено → диагностика
   DEPENDENCY_NOT_COVERED (честная неполнота, I1).
3. Дефолтные DependencyRules demo v1 [C]: DR-GOVERNMENT (конечный глагол + падежно управляемый mention → GOVERNS);
   DR-MODIFIER (смежная модификатор-голова пара с совпадающим case index → MODIFIES); DR-COORD (connective между
   однотипными конституентами → COORD); DR-TEMPMOD (временное выражение, смежное event-якорю → TEMPORAL_MOD).
4. **Использование FrameGenerator**: T2 потребляет DependencyCandidates как evidence для назначения участников и структуры:
   OP1 связывает аргументы по GOVERNS-кандидатам; OP5 координация — по COORD-кандидатам. Зависимости ранжируют, не
   отсекают (принцип §5.3 «порядок слов ранжирует, не отсекает»).
5. **Почему TD не является семантическим фактом**: relation_type — структурная категория из объявленного набора; activation-
   условия работают по признакам R1 и объявленной локальной структуре (двухуровневый инвариант V4 §2); TD НЕ создаёт
   решения/основания C/M/W для семантики, его выход — только кандидаты-свидетельства. Правило, предлагающее семантическое
   отображение → отклоняется при валидации ресурса (§15.10). Инвариант I14.
Ошибки: DEPENDENCY_NOT_COVERED, RULE_VERSION_MISMATCH.

### 15.2 Lexical Sense layer
Путь: surface → MorphVariant(lemma) → **LexSenseCandidate** → semantic compatibility → Frame/T3.
1. T1 п.6b (после морфологии): для каждой леммы с несколькими записями в версионном **LexicalResource** — один
   LexSenseCandidate на запись; односмысленные леммы получают implicit-кандидата без ветвления. Запись ресурса: {lemma,
   sense_index, semantic_type, syntactic compatibility (POS-паттерны), typical government}.
2. Разрешение омонимии («ключ»: дверной / музыкальный / родник): кандидаты сосуществуют; constraint-распространение от
   контекста рамки (структура T2 + объявленные валентность/совместимость) сужает множество; выжило несколько → bounded
   selection в T3 среди ОБЪЯВЛЕННЫХ смыслов (§8 — LLM допустим только здесь, по замкнутому множеству); ни один не
   совместим → диагностика SENSE_CONFLICT + UnknownReason KNOWLEDGE_ABSENT (§15.8) + miss.
3b. **Multiword-граница [Rev13]**: многословные лексические единицы (фразовые глаголы, идиомы — «поставить на конь») вне
   demo v1; архитектура резервирует версионный ресурс-слот для них (расширение = новая декларация ресурса, I15 действует);
   до объявления таких записей форма → UnknownReason KNOWLEDGE_ABSENT + miss; молчаливой подмены нет.
3. Влияние на FrameCandidate: sense.semantic_type сужает candidate_generation_rules (допустимые значения/роли различаются
   по смыслам); промпт T3 перечисляет смыслы как R-основания с source=LEXICAL_RESOURCE.
4. **Почему смысл не определяет одна LLM**: множество смыслов закрыто ресурсом; LLM выбирает только среди объявленных
   (bounded selection §8); новый смысл = версионная запись через learning loop (§15.10), никогда не свободная генерация.
   Инвариант I15.
Ошибки: SENSE_CONFLICT, RESOURCE_MISSING (UnknownReason).

### 15.3 Unified ScopeOperator architecture
**ScopeOperatorNode** {operator_id, operator_type ∈ объявленный набор (§15.3 п.1), operand (ref: frame|slot|под-узел),
scope_span(s), **локальная привязка [Rev13]: target_slot_ref (слот рамки, к которому оператор привязывается; обязателен для
QUANT/RESTRICT), local_variable_id (идентификатор локальной переменной интерпретации — НЕ канонический BoundVar; граница
Фазы 2 NQ5 сохраняется), restriction_ref (ссылка на выражение-ограничение области квантификации или None)**, binding
(ScopeOperatorBinding), provenance} — единственное представление операторов; SurfaceOperatorCandidate остаётся только как
leaf-форма на выходе T1. ScopeOperatorBinding — поле узла (ссылка материализации).
1. Объявленные OperatorTypes [C]: QUANT {EVERY, SOME, AT_LEAST_N(n)}; NEG {NOT}; MODAL {POSSIBLE, NECESSARY}; COND {IF —
   связывает две рамки: antecedent/consequent через connective-pattern}; RESTRICT {ONLY}. Новый тип = декларация схемы.
2. **OperatorCompositionEngine [Rev13]** (единый слой в TD): SurfaceOperatorCandidate → OperatorAttachmentCandidate
   → ScopeConstraintGraph → ScopeTreeCandidate. Один движок для ВСЕХ типов операторов (QUANT/NEG/MODAL/COND/RESTRICT +
   TemporalOperators §15.6); костыльных per-operator правил нет: каждый тип объявляет в ресурсе только свои *attachment-
   паттерны* (к чему может прикрепляться: рамка/слот/якорь события), а вложенность разрешает ОДНО объявленное общее
   правило: (a) **глубина прикрепления = близость триггера к предикату внутри ClauseUnit [Rev13a]** — оператор с более близким
   триггером крепится глубже (INNER); метрика depth_rank = число токенов от конца триггера до начала предиката;
   равные ранги разрешаются surface-порядком слева направо (детерминированно); (b) граница клаузы ограничивает прикрепление (оператор не пересекает ClauseUnit §5.2 п.8);
   (c) операторы, привязанные к разным слотам одной рамки, образуют множество на рамке в surface-порядке; (d) COND — пара
   клауз через connective-pattern (antecedent/consequent). Движок строит ScopeConstraintGraph (рёбра INNER/OUTER/SAME_FRAME),
   затем ВСЕ удовлетворяющие ScopeTreeCandidate: ровно один → принят; несколько → сосуществуют как кандидаты (bounded selection
   или AMBIGUOUS, §8); ноль → SCOPE_NOT_COVERED + miss. «Не каждый студент пришёл» vs «Каждый студент не пришёл»: в первом
   триггер EVERY ближе к предикату, чем триггер NOT → NOT(EVERY(HAS)); во втором — наоборот → EVERY(NOT(HAS)).
3. **Вложенность — дерево**: node.operand может быть другим ScopeOperatorNode; каноническая форма NOT(EVERY(student→came))
   = 2-узловое дерево (EVERY: target_slot_ref=student, local_variable_id=x1; NOT над ним) с binding-цепью. Сериализация в N.meta["scope"] [B11] — вложенный JSON узлов (канонический, round-trip);
   Фаза 2 → G/BoundVar на узел (NQ5).
4. **Полярность — частный случай** [B13]: polarity = наличие NEG-узла над рамкой; N.meta["polarity"] выводится из scope-дерева
   — единый источник истины.
5. Влияние на T3/T4: scope-слоты — решения по объявленным типам операторов + параметрам (candidate_generation_rules);
   разрешённые узлы становятся R-основаниями и constraint-рёбрами (NEG запрещает только положительные значения → путь
   NONE_FIT §5.4 п.5); неразрешённые → UnknownReason STRUCTURE_UNKNOWN/SEMANTIC_AMBIGUITY. Инвариант I16.
Ошибки: SCOPE_NOT_COVERED, SENSE_CONFLICT (для operator-лемм), POLICY_NO_WINNER (§15.9).

### 15.4 Coreference / ReferenceResolution
**ReferenceCandidate** {mention_id, antecedent_id, constraints{}, evidence[], provenance} + **ReferenceDecision** (тип решения
REFERENCE; машина состояний §6). Алгоритм для каждой PRO/event-anaphora mention:
1. Генерация кандидатов-антецедентов = все mentions в discourse window [NQ7] с совместимыми surface-признаками.
   Окно включает mentions предыдущих наблюдений через журнал; их кандидаты несут evidence с провенансом
   memory-канала (§17.4) [Rev16/H5]; identity-унификация по ним — только Consolidator (I24), раннего связывания нет.
2. Применение объявленного набора ограничений: согласование gender/number/person (признаки R1 — жёсткий фильтр; структурное
   правило, разрешено двухуровневым инвариантом); синтаксическая совместимость (паттерны ролей/позиций из ресурса — мягкое,
   ранжирует); discourse focus — версионная **CoreferencePolicy** {policy_id, version, ranking_criteria[] (лексикографический порядок,
   напр. [subject, recency]), window_size} [Rev13]: детерминированный lexicographic-ранжиринг по объявленному списку
   критериев; ядро не зашивает ни одного критерия (новый критерий = новая версия политики); ранжирует, не отсекает; [Rev14.2: ноль выживших в пределах наблюдения → UNRESOLVED + REFERENCE_UNKNOWN (§15.4 п.3) — нормальный исход, а не ошибка разбора; межнаблюдательное разрешение — Consolidator];
   временная совместимость для event-anaphora (§15.6).
3. Выжившие → ReferenceDecision: единственный с положительным основанием (D-trace feature-совпадений) → RESOLVED;
   несколько выживших, у каждого своё основание → AMBIGUOUS (§1.4); ноль → UNRESOLVED + UnknownReason REFERENCE_UNKNOWN
   + miss-отчёт.
Не эвристика: каждая связь имеет evidence, кандидаты персистятся, AMBIGUOUS first-class; жёсткие фильтры — только объявленные
правила согласования. Заменяет [B12]: coreference теперь стадия TD; унификация в AH при коммите через merge_identity (T6) —
ReferenceDecision определяет, какие refs объединяются. Инвариант I17.
Ошибки: REFERENCE_UNKNOWN (UnknownReason), RULE_VERSION_MISMATCH.

### 15.5 WorldKnowledge layer
**WorldKnowledgeRecord** {record_id, version, subject_type/instance, predicate ∈ объявленный WK-набор {IS_A, HAS_PART,
PROPERTY, TYPICAL_CONSTRAINT}, object, source (curated|derived), provenance} — версионный ресурс R-WK («bird IS_A animal»,
«bird HAS_PART wing»).
1. Участие в T3/T4: предоставляет **W-основания** (новый тип основания W — внешние мировые знания; §2.1) для допустимости
   кандидатов и constraint-рёбер.
2. Отличие от пользовательского утверждения: C = утверждение текущего контекста (авторитетно о дискурсе); W = опровержимое
   фоновое знание. Противоречие C vs W → C ограничивает/перекрывает в этой интерпретации, противоречие ЗАПИСЫВАЕТСЯ (miss-отчёт;
   learning loop может предложить поправку WK §15.10; C-утверждение НИКОГДА не мутирует запись WorldKnowledgeRecord [Rev13a]). W vs W → обе записи сохраняются; constraint-ребро запрещает
   несовместимые кортежи в одной рамке; если нужны оба → CONFLICTING_EVIDENCE (§15.8) + miss.
3. Фиксация источника доказательства: каждое W-основание несёт record_id + версию ресурса — полный audit trail. Инвариант I18.
Ошибки: WK_CONTRADICTION, RESOURCE_MISSING (UnknownReason).

### 15.6 Temporal model
**TemporalExpression** {expr_id, span(s), kind ∈ {ABSOLUTE, RELATIVE_ANCHORED (вчера/завтра/тогда…), DURATION, ORDER
(до/после)}, value?, trigger_lemma, source} — создаётся T1 по объявленным temporal-паттернам/ресурсу (как scope-паттерны
§5.2 п.10). **TemporalAnchor** {anchor_id, anchored_ref (frame/event/timepoint), anchor_time (resolved or symbolic)};
**TemporalRelation** {relation_id, src, dst, **operator ∈ TemporalOperators [Rev13]**, anchor_dependency (объявленные якоря,
   требуемые оператором), evidence[]}. Замкнутый набор TemporalOperators: BEFORE, AFTER, OVERLAP, COMPLETED_BEFORE_REFERENCE
   («уже ушёл» — завершение до референс-события), NOT_YET_COMPLETED («ещё не пришёл»), APPROXIMATE_TIME («скоро» — без якорного
   значения; даёт только constraint). Каждый оператор объявляет свой anchor_dependency (напр. COMPLETED_BEFORE_REFERENCE требует
   якорь референс-события); неразрешимо → REFERENCE_UNKNOWN + miss. Temporal-операторы прикрепляются к event-якорям через
   OperatorCompositionEngine (§15.3 п.2) как тип операторов TEMPORAL. Исключение из правила (b) [Rev13a]: TEMPORAL допускает
   межклаузную привязку к объявленному event-якорю (anchor_dependency), тогда как QUANT/NEG/MODAL/COND/RESTRICT остаются в
   пределах ClauseUnit: «Когда Иван пришёл, Петя уже ушёл» → COMPLETED_BEFORE_REFERENCE(anchor=EVENT(пришёл)).
1. Разрешение: тип решения TEMPORAL в T3/T4. RELATIVE_ANCHORED-выражения разрешаются относительно ближайшего объявленного
   якоря (событие управляющей клаузы). Пример «Вчера Иван сказал, что завтра придёт»: EVENT1(say).time = yesterday (абсолютный
   якорь = время высказывания); EVENT2(come).time = tomorrow(anchor=EVENT1.time) — anchoring chain явная, каждое звено с
   evidence; неразрешимо → UnknownReason REFERENCE_UNKNOWN + miss.
2. Влияние на AH: Фаза 1 N.meta["time"] = {TemporalExpression, anchor_chain (сериализована)}; полная каноническая модель
   timepoint — Фаза 2 (NQ6), но контракт структуры anchoring chain зафиксирован сейчас — миграция механическая.
Ошибки: TEMPORAL_ANCHOR_UNRESOLVED, REFERENCE_UNKNOWN (UnknownReason).

### 15.7 Query formalization
**QueryFrame** {query_id, kind ∈ QueryKind [Rev13], target_vars[] (непривязанные переменные с объявленным сортом; для YESNO —
пусто), constraints[]
(frame + role bindings, переменные допустимы в ролях), source_span} — создаётся T2/T3 при modus=QUERY (V4 §5.1).
**Детализация QueryFrame [Rev14.1]**: target_predicate; known_arguments[] (ArgumentSpec с привязанными значениями);
unknown_arguments[] (переменные с объявленным сортом = target_vars); expected_answer_type (сорт ответа, выводится из kind:
entity|bool|count|explanation); proof_requirements (что должен вернуть InferenceEngine: witness-присваивание | вердикт
satisfiability | кардинальность). Вопрос НЕ является Proposition: «Есть ли у Алексея учебник?» → QueryFrame
{predicate=HAS, known=[subject=ALEKSEY], unknown=[object:X:entity]}, а не утверждение HAS(ALEKSEY, TEXTBOOK) (I19).
**QueryCandidate**: альтернативные чтения запроса сосуществуют (напр. скоп WH над несколькими рамками) → bounded selection
или AMBIGUOUS.
1. Пример «Кто имеет книгу?» → QueryFrame {kind=WH, target_vars=[X:entity], constraints=[HAS(X, book)]}.
   **QueryKind [Rev13]** — декларативный замкнутый набор (расширение = декларация схемы): WH (целевая переменная объявленного
   сорта); YESNO (**satisfiability check**: target_vars=[], рамка полностью привязана; компилятор спрашивает InferenceEngine о
   существовании согласованного присваивания — satisfiable/unsatisfiable, а не поиск значений переменных: «Есть ли у Алексея
   учебник?» → {YESNO, [], HAS(ALEKSEY, TEXTBOOK)}); COUNT (целевая переменная = кардинальность по привязанной рамке:
   «Сколько студентов имеют книги?» → COUNT(X:entity | HAS(X, book))); CAUSAL (целевая переменная = объяснение/событие:
   «Почему Иван ушёл?» → {CAUSAL, target=explanation, constraints=[LEFT(IVAN)]}; до объявления causal-паттернов в ресурсе —
   KNOWLEDGE_ABSENT + miss).
2. Отличие от утверждения: modus QUERY — НЕ коммитится как факт (условие T5: запрос создаёт pending goal, а не элемент
   batch-фактов). **QueryCompiler** компилирует RESOLVED QueryFrame → каноническое представление для InferenceEngine через
   объявленное отображение в AssociationGoal (V4 §5.9): target + constraint graph.
3. Жизненный цикл: OPEN→RESOLVED→COMPILED; ответ InferenceEngine = новое наблюдение со своим провенансом, никогда не
   сливается молча с источником запроса. Непривязанная переменная без объявленного сорта → диагностика QUERY_TARGET_UNBOUND.
   Инвариант I19.
Ошибки: QUERY_TARGET_UNBOUND, STRUCTURE_UNKNOWN (UnknownReason).

### 15.8 UnknownReason taxonomy
Поле у каждого не-RESOLVED outcome и диагностики: **UnknownReason ∈ {KNOWLEDGE_ABSENT** (ресурс существует, но нет записи,
покрывающей случай — включая «ни один смысл несовместим» §15.2 п.2 и multiword-единицы §15.2 п.3b), **STRUCTURE_UNKNOWN**
(структура не покрыта объявленными операциями/паттернами), **REFERENCE_UNKNOWN** (coreference/temporal anaphora
неразрешима), **SEMANTIC_AMBIGUITY** (несколько обоснованных кандидатов выжили, победителя по политике нет §15.9),
**RESOURCE_MISSING** (требуемый версионный ресурс как таковой отсутствует/неверсионирован — отличается от KNOWLEDGE_ABSENT:
нет самого ресурса, а не его записи) [Rev13], **CONFLICTING_EVIDENCE** (основания противоречат,
победителя по политике нет §15.9), **COMPUTATION_LIMIT** (бюджет/глубина исчерпаны)}.
1. Кто устанавливает: обнаруживающая стадия — T0/T1 → RESOURCE_MISSING; TD → REFERENCE_UNKNOWN/STRUCTURE_UNKNOWN;
   T2 → STRUCTURE_UNKNOWN; T3/T4 → KNOWLEDGE_ABSENT/SEMANTIC_AMBIGUITY/CONFLICTING_EVIDENCE; engine → COMPUTATION_LIMIT.
2. Использование: miss-отчёты агрегируются по (UnknownReason, stage, resource) — вход learning loop (§15.10) и C-метрики
   демо.

### 15.9 EvidencePriorityPolicy
**EvidencePriorityPolicy** {policy_id, version, **domain_rules[] = {domain, source_order[], conflict_rule} [Rev13]**,
no_auto_winner_conditions[]} — версионный; изменяется только явным review (learning loop не может менять §15.10).
1. Семантика: приоритет НЕ «победитель забирает всё». Модель по умолчанию = **constraint propagation**: источник с более
   высоким приоритетом СУЖАЕТ множество кандидатов нижестоящих; автоматический выбор победителя — только когда после
   применения ограничений выжил ровно один ground И объявленное dominance-правило покрывает пару; иначе →
   AMBIGUOUS/CONFLICTING_EVIDENCE (тихого выбора нет).
2. **Domain-dependent приоритеты [Rev13]**: глобального «C > W» НЕТ. Политика объявляет domain_rules[] = {domain,
   source_order[], conflict_rule}: разные типы знаний имеют свои правила (напр. DISCOURSE_FACTS — C предшествует W с записью
   противоречия; TYPICAL_PROPERTIES — W и C равны, только constraint). Недообъявленная область → dominance нет:
   constraint-распространение только, несколько выживших → AMBIGUOUS/CONFLICTING_EVIDENCE. Пример: лексикон («банк» = финансовая
   организация) vs контекст («сидеть на банке»): контекст НЕ «побеждает» лексикон — он создаёт ограничение совместимости для
   выбора смысла (§15.2); если под ограничением выжили оба смысла → bounded selection или AMBIGUOUS.
   Пример: C «кит — рыба» vs W «кит IS_A млекопитающее»: область DISCOURSE_FACTS (объявленное правило «C предшествует W») →
   RESOLVED(fish) в этой интерпретации + записанное противоречие (I18); если политика не содержит правила для области — AMBIGUOUS.
Ошибки: POLICY_NO_WINNER, CONFLICTING_EVIDENCE (UnknownReason).

### 15.10 Learning loop architecture
**MissReport** (агрегированные по UnknownReason §15.8) → **Analysis** (группировка + классификация корневой причины:
missing rule / missing record / policy gap / core limitation) → **ResourceProposal** {proposal_id, target_resource,
proposed_records[], evidence_refs[] (miss-отчёты + исходные span'ы), status} → **Validation** (объявленные критерии
приёмки: прохождение corpus regression suite; отсутствие противоречий с существующими записями; проверка двухуровневого
инварианта — семантические отображения отклоняются) → **New Version** (версия ресурса N+1; старые версии сохраняются для
replay).
1. Что может обучаться (авто-предложения): декларации HeadRule/ExpansionRule/DependencyRule, записи LexicalResource,
   валентностные записи, WorldKnowledgeRecord, scope/temporal паттерны.
2. Что НЕ может изменяться автоматически: ядровой алгоритм (§5), EvidencePriorityPolicy, множества значений и набор
   отношений decision schema (только явный review), закоммиченные факты (отзыв только протоколом T6b §10), содержимое
   канонического хранилища.
3. Воспроизводимость: каждая версия ресурса имеет provenance к miss-отчётам; любой прошлый прогон воспроизводим по точному
   кортежу версий (formalizer_schema_version, framegen_version, semantic_schema_version, lexical_resource_version,
   wk_version, policy_version); A/B-сравнение версий на фиксированном корпусе — объявленный шаг валидации. Инвариант I20.

---

### 15.11 Acceptance-сценарии Rev13 (обязательные тесты)
| Сценарий | Ожидаемый результат |
|---|---|
| «Не каждый студент пришёл» / «Каждый студент не пришёл» | Разные канонические ScopeTreeCandidate: NOT(EVERY(HAS)) vs EVERY(NOT(HAS)); поля локальной привязки заполнены; полярность выведена из NEG-узла (I21) |
| «Иван не знает, что Пётр пришёл» | NOT(KNOWS(IVAN, THAT(CAME(PYOTR)))) — NEG прикрепляется к предикату матричной клаузы (граница ClauseUnit); подчинённый предикат не захватывается (I21) |
| «Есть ли у Алексея учебник?» | QueryFrame {YESNO, target_vars=[], HAS(ALEKSEY, TEXTBOOK)}; компилятор формирует satisfiability-запрос к InferenceEngine; в batch фактов нет (I19) |
| «Почему Иван ушёл?» | kind=CAUSAL с target=explanation ИЛИ KNOWLEDGE_ABSENT + miss (пока causal-паттерны не объявлены); запрос не коммитится как факт (I19) |
| Конфликт C/W при разных политиках: C «кит — рыба» vs W «кит IS_A млекопитающее», policy A (DISCOURSE_FACTS: C предшествует W) / policy B (правила для области нет) | Policy A → RESOLVED(fish) в этой интерпретации + записанное противоречие (I18); policy B → AMBIGUOUS {fish, mammal} + CONFLICTING_EVIDENCE miss. Один и тот же вход, разные версионные политики — механизм идентичен (I22) |

## 16. Универсальный semantic core [Rev14]
Цель: новые конструкции формализуются композицией уже существующих объектов; per-example правил, keyword-обработчиков
и частных языковых паттернов нет (I24 действует на весь слой).

### 16.1 PropositionNode / SemanticExpression
**SemanticExpression** — универсальный объект смысла; **PropositionNode** {expr_id, head (predicate|operator), arguments[]
(ArgumentSpec §16.2), modifiers[], status TOP_LEVEL/EMBEDDED, provenance}. Выражение может использоваться как аргумент
другого выражения — композиция без новых типов: SAID(IVAN, PropositionNode(COME(PYOTR))), BELIEVES(ANNA,
PropositionNode(...)), FALSE(PropositionNode(...)).
Правило: вложенная proposition НЕ обязана становиться factual assertion — она существует в скопе attitude-предиката;
коммит (T5) материализует только top-level утверждения; embedded propositions хранятся как аргументы со своим
провенансом и статусом EMBEDDED (контракт читателей V4 §7.4).
**Epistemic layer [Rev14.1]**: PropositionNode разделяет **PropositionContent** (что утверждается — head + arguments;
неизменяемо операциями над proposition) и **EpistemicStatus ∈ {ASSERTED, BELIEVED, POSSIBLE, NECESSARY, FALSE, UNKNOWN}**.
Операция над proposition не меняет её содержание: FALSE(P) — это узел с EpistemicStatus=FALSE НАД P, а не модификация
содержимого P. Embedded proposition НЕ получает ASSERTED автоматически: статус определяется внешним attitude-предикатом по
объявленному в ресурсе отображению (attitude → EpistemicStatus); если отображение не объявлено — UNKNOWN; top-level
утверждение в assertoric-контексте без внешних операторов → ASSERTED.
**Коммит и epistemics [Rev14.2]**: T5 материализует как факт-элементы только узлы с EpistemicStatus=ASSERTED; attitude/
modality-оператор коммитится как собственное asserted-выражение (MAY(P) — утверждение о возможности, а не P); embedded
non-ASSERTED proposition существует в канонической памяти ТОЛЬКО как аргумент внешнего выражения и никогда не становится
отдельным фактом.

### 16.2 ArgumentType
**ArgumentSpec** {slot_ref, arg_type ∈ ArgumentType, value (ref|variable|PropositionNode)}; **ArgumentType** — замкнутый
набор {ENTITY, EVENT, PROPOSITION, PROPERTY, SET, VALUE, TIME, LOCATION} (расширение = декларация схемы).
FrameCandidate и SemanticGraph различают тип аргумента отдельно от роли: OBJECT может ссылаться как на ENTITY, так и на
PROPOSITION — это разные случаи: KNOWS(IVAN, ArgumentSpec{ENTITY, PYOTR}) vs KNOWS(IVAN,
ArgumentSpec{PROPOSITION, PropositionNode(CAME(PYOTR))}).

### 16.3 EventFrame — базовая семантическая модель
**EventFrame** {frame_id, schema_ref (PredicateSchema §16.9), predicate, participants[] (ArgumentSpec), temporal? (§15.6),
location?, state, modifiers[], embedded_propositions[] (PropositionNode), provenance}. Большинство естественных предложений формализуются как
события/состояния, а не как простые бинарные отношения entity-entity. FrameCandidate (§5.3) — локальный кандидат;
EventFrame — его разрешённая форма в CandidateIR.

### 16.4 Attribute model
Разделение: **Relation** = entity ↔ entity; **Attribute** = entity ↔ value/property. **AttributeExpr** {attr_id, subject
(ArgumentSpec ENTITY), property (PROPERTY/VALUE), value?, provenance}. Примеры: «Машина красная» →
ATTRIBUTE(color(machine), red); «Иван высокий» → ATTRIBUTE(height(Ivan), high). Отдельные phrase-level concepts НЕ
создаются автоматически (§16.5).

### 16.5 Запрет Phrase-level identity
По умолчанию композиция именных групп НЕ создаёт новый semantic entity: «красная машина» = machine (entity) +
attribute RED; модификатор остаётся AttributeExpr/modifier на EventFrame. Создание отдельного m допускается только при
доказанной устойчивой identity — это решение Consolidator (§2.7) по межнаблюдательным свидетельствам, а не локального
разбора.

### 16.6 Existential unknowns
Запрет создания фиктивных сущностей (m_UNKNOWN_PERSON). «Кто-то вошёл. Он сел.» → EXISTS x: ENTER(x); SIT(x) —
existential-переменная **ExistentialRef** {var_id, discourse_ref, scope_span(s), bindings[] (местоимения → var)} с
временной переменной/discourse reference до разрешения identity; местоимение «он» связывается с локальной переменной x
(локальная привязка §15.3), а не с канонической сущностью. Identity resolution (если есть) — Consolidator.
Детекция existential-неопределённых местоимений = объявленный surface-паттерн в T1 [Rev14.2] (тот же механизм, что
ER-QUANTIFIER §5.2 п.10; новый триггер = декларация ресурса, I13); producer ExistentialRef: T1 (триггер), T3 (привязка местоимений).

### 16.7 SemanticGraphCandidate
**SemanticGraphCandidate** {graph_id, ir_ref, nodes[] (EventFrame/AttributeExpr/PropositionNode/QueryFrame), edges[]
(dependency candidates, scope trees, reference candidates, temporal relations, constraint edges), ambiguity_sets[],
provenance} — объединяет ВСЕ локальные структуры (ScopeTree, DependencyGraph, ReferenceCandidates, TemporalCandidates,
Frames) в единый граф кандидатов; единственный вход в Consolidator (§2.6).

### 16.8 Acceptance-примеры Rev14
| Пример | Структура | Почему без специальных исключений |
|---|---|---|
| «Анна сказала, что Иван пришёл» | SAID(ANNA, PropositionNode(CAME(IVAN))); embedded — не факт | композиция §16.1+§16.2; attitude-предикат с PROPOSITION-аргументом |
| «Возможно, Иван пришёл» | MODAL(MAY)(PropositionNode(CAME(IVAN))) | scope-оператор над proposition (§15.3); отличие от предыдущего примера = тип внешнего узла (MODAL vs SAID), не исключение |
| «Красная машина стоит у дома» | EventFrame(STANDS, machine + AttributeExpr RED, LOCATION(near house)) | §16.5: нового сущностного концепта для «красная машина» нет |
| «Кто-то вошёл. Он сел.» | EXISTS x: ENTER(x); SIT(x) — ExistentialRef + discourse reference; без m_UNKNOWN_PERSON | §16.6: existential unknown, identity — Consolidator |
| «Иван знает Петра» / «Иван знает, что Пётр пришёл» | KNOWS(IVAN, {ENTITY, PYOTR}) vs KNOWS(IVAN, {PROPOSITION, PropositionNode(CAME(PYOTR))}) | §16.2: одна и та же роль OBJECT, разные ArgumentType — структурное различие объяснено типом аргумента |

### 16.9 PredicateSchema — расширяемый контракт [Rev14.1]
**PredicateSchema** {schema_id, version, predicate_id, allowed_roles[], argument_type_constraints{} (роль → подмножество
ArgumentType §16.2), optional_roles[], cardinality{}} — версионный ресурс; EventFrame ссылается на schema definition по
predicate_id (нет записи в ресурсе → KNOWLEDGE_ABSENT + miss). Полноценная валентность НЕ реализуется: PredicateSchema
фиксирует только расширяемый контракт (роли, типы аргументов, опциональность, кардинальности); семантический выбор значений
и глубокая валентность — вне этого слоя. Расширение = новая версия ресурса через learning loop (§15.10).

### 16.10 Acceptance-проверки Rev14.1 (обязательные тесты)
| Проверка | Вход | Ожидаемый результат |
|---|---|---|
| A | «Иван сказал, что Пётр пришёл» | НЕ создаётся факт COME(PYOTR): embedded proposition имеет EpistemicStatus ≠ ASSERTED (§16.1); batch T5 содержит SAID(IVAN, PropositionNode(CAME(PYOTR))) со статусом EMBEDDED; отдельного элемента COME(PYOTR) в канонической памяти нет |
| B | «Возможно, Иван пришёл» | Создаётся PropositionNode CAME(IVAN) с EpistemicStatus=POSSIBLE (MODAL(MAY), §15.3); не ASSERTED и не коммитится как факт |
| C | «Иван не знает, что Пётр пришёл» | NOT(KNOWS(IVAN, PropositionNode(CAME(PYOTR)))) — отрицание прикрепляется к матричному предикату (§15.3 п.2), а НЕ к COME(PYOTR); негативного факта о приходе PYOTR нет (I21) |
| D | «Есть ли у Алексея учебник?» | Создаётся QueryFrame {predicate=HAS, known=[subject=ALEKSEY], unknown=[object:X:entity]} (§15.7), а не утверждение HAS(ALEKSEY, TEXTBOOK); modus QUERY не коммитится (I19) |
В проверках не вводится ни одного keyword-правила или частного языкового исключения — все результаты следуют из
§16.1/§15.3/§15.7.

### 16.11 Semantic Core Closure Audit [Rev14.2]
Проверка: контракты CandidateIR, PropositionNode, ArgumentType, EventFrame, AttributeExpr, ExistentialRef,
SemanticGraphCandidate, QueryFrame покрывают M1/M2 acceptance БЕЗ новых специальных правил.

| Тест | Formalizer output (T0–T4) | CandidateIR | Ответственность Consolidator | Ожидаемый канонический результат |
|---|---|---|---|---|
| 1a «Каждый студент имеет учебник» | T1: HR-NOUN («студент», «учебник») + ER-QUANTIFIER/EVERY (§5.2 п.10) → SurfaceOperatorCandidate; T2: OP1 FrameCandidate {HAS, participants}; TD §15.3: EVERY прикрепляется к ближайшему предикату (depth_rank), локальная привязка target_slot_ref=SUBJECT, restriction_ref=«студент»; T4 RESOLVED (структурные основания) | semantic_candidates=[EventFrame HAS{x, учебник}]; operator_trees=[EVERY(x\|STUDENT(x))(HAS(x,book)) с локальной привязкой]; ambiguity_sets=[]; provenance на каждую структуру | нет identity-решений — все mentions локальны; передаёт как есть | факт ∀x(STUDENT(x)→HAS(x,book)), EpistemicStatus=ASSERTED (G2); N.meta["scope"] [B11] |
| 1b «Алексей студент» | T2: OP4 NOMINAL_PREDICATE; T3/T4 значение предиката из объявленной схемы → RESOLVED | semantic_candidates=[EventFrame STUDENT{ArgumentSpec{ENTITY, mention(Алексей)}}] — Relation entity↔entity (§16.4), не AttributeExpr | identity «Алексей» ↔ канонический ALEKSEY (merge/linking); dedup против существующего STUDENT(ALEKSEY) | факт STUDENT(ALEKSEY) ASSERTED; при существовании сущности — linking, без нового m |
| 1c «Есть ли у Алексея учебник?» | modus=QUERY → QueryFrame {kind=YESNO, target_predicate=HAS, known=[subject=Aleksey], unknown=[object:X:entity], expected_answer_type=bool, proof_requirements=satisfiability} (§15.7); I19 — не коммитится | semantic_candidates=[QueryFrame]; EventFrame HAS как факт ОТСУТСТВУЕТ | нет (компиляция — QueryCompiler → AssociationGoal) | новых фактов нет; InferenceEngine: satisfiable по цепочке ∀x(STUDENT(x)→HAS(x,book)) + STUDENT(ALEKSEY) → instantiation в момент запроса (G3) → YES |
| 2 «Иван сказал, что Пётр пришёл» | матрица SAID(IVAN), придаточная CAME(PYOTR); TD GOVERNS; PropositionNode(CAME) — аргумент PROPOSITION, status EMBEDDED, EpistemicStatus по объявленному attitude→status (не объявлено → UNKNOWN §16.1) | semantic_candidates=[EventFrame SAID{ArgumentSpec{ENTITY, Иван}, ArgumentSpec{PROPOSITION, P(CAME(PYOTR), EMBEDDED)}}] | identity mentions; факта COME не создаёт | только SAID(IVAN, P); отдельного элемента CAME(PYOTR) НЕТ (проверка A §16.10) |
| 3 «Возможно, Иван пришёл» | MODAL {POSSIBLE} (§15.3 п.1) → SurfaceOperatorCandidate; OperatorCompositionEngine прикрепляет к единственному предикату; PropositionNode CAME(IVAN) EpistemicStatus=POSSIBLE | operator_trees=[MODAL(MAY)]; semantic_candidates=[EventFrame CAME{EpistemicStatus=POSSIBLE}] | нет | MAY(CAME(IVAN)) — asserted-выражение о возможности (G2); содержания CAME как факта НЕТ (проверка B) |
| 4 «Иван не знает, что Пётр пришёл» | NEG прикрепляется к матричному KNOWS (§15.3 п.2, I21): NOT(KNOWS(IVAN, P(CAME(PYOTR), EMBEDDED))); embedded ≠ ASSERTED; негативного факта о CAME нет | operator_trees=[NOT над KNOWS]; semantic_candidates=[EventFrame KNOWS{ArgumentSpec{PROPOSITION, P}}] | identity mentions | NOT(KNOWS(…)) как факт; отрицательного факта о приходе PYOTR НЕТ (проверка C) |
| 5 «Кто-то вошёл. Он сел.» | T1: объявленный паттерн indefinite-местоимения (G1) → ExistentialRef x + ENTER(x); T3: ReferenceCandidate {«он»→x} — согласование (§15.4), единственный выживший → локальная привязка; identity остаётся UNRESOLVED | semantic_candidates=[ENTER{x}, SIT{x}]; coreference_candidates=[ReferenceCandidate(он→x)]; канонических сущностей НЕТ | ЕДИНСТВЕННЫЙ владелец identity resolution (RESOLVED_BY_CONSOLIDATOR при межнаблюдательных свидетельствах; иначе discourse reference сохраняется) | EXISTS x: ENTER(x); SIT(x) с discourse reference; m_UNKNOWN_PERSON нет (I24, §16.6) |
| 6 «Алексей встретил его вчера» | T2: OP1 MET(Алексей, его); T3: ReferenceCandidate для «его» = антецеденты в наблюдении — ноль → UNRESOLVED + REFERENCE_UNKNOWN (§15.4 п.3) + miss; раннего связывания нет (I24); «вчера» → TemporalExpression RELATIVE_ANCHORED, symbolic anchor [NQ6] | semantic_candidates=[EventFrame MET{Алексей, unresolved-ref}]; coreference_candidates=[] + диагностика REFERENCE_UNKNOWN; temporal_candidates=[RELATIVE_ANCHORED(вчера)]; ambiguity_sets=[reference] | разрешает «его» по mentions других наблюдений (window [NQ7], CoreferencePolicy); нет — reference остаётся unresolved в канонической памяти | MET(ALEKSEY, ?) с неразрешённой ссылкой + временным constraint; молчаливой привязки к любой сущности НЕТ |

**Результат аудита**: все 6 тестов выводятся существующими контрактами без per-example правил. Закрыты три пробела:
- **G1** — детекция existential-триггеров: объявленный surface-паттерн в T1 (механизм ER-QUANTIFIER §5.2 п.10; новый
  триггер = декларация ресурса, I13); producer ExistentialRef исправлен (T1/T3).
- **G2** — коммит и epistemics: T5 материализует только ASSERTED-узлы; modality/attitude — как собственные asserted-
  выражения; embedded non-ASSERTED — только аргумент (§16.1).
- **G3** — instantiation квантованных propositions выполняет InferenceEngine в момент запроса (AssociationGoal, V4 §5.9);
  Consolidator не инстанцирует (§2.7).

## 17. Structural Reconstruction Layer (SRL) [Rev15]

### 17.1 Позиция в lifecycle
Отдельная стадия между T0 и T1; цепочка: RawInput → T0 лексическая нормализация/сегментация (§5.1) → **SRL структурная
реконструкция** → T1 лингвистический анализ (§5.2) → TD dependency (§15.1–15.4) → T2 frame generation (§5.3) →
T3/T4 семантическое разрешение (§8, §9.2) → Consolidator (CandidateIR §2.6) → Canonical Memory (T6).
Вход: TokenSpan[]/SentenceUnit[] от T0 + объявленные ресурсы (boundary/ellipsis-паттерны; каналы памяти §17.4).
Выход: только структурные кандидаты — все через CandidateIR (§2.6), отдельного пути в Consolidator или каноническую
память нет. SRL детерминирован, LLM не вызывает (LLM-граница только T3, §8); пересчёт при новом input/версии контекста/
версии ресурсов; выход immutable внутри версии интерпретации (§2.1).

### 17.2 Запреты [I26]
SRL не имеет права: создавать семантические факты или propositions; писать в Canonical Memory (расширяет I25 — SRL до
Consolidation); выбирать единственную интерпретацию (все альтернативы сохраняются до resolution, I29); создавать identity
links (§2.7/I24). Выход = только структурные кандидаты с ProvenanceRecord (I27).

### 17.3 Объекты (реестр §2.1)
- **TokenHypothesis** {hypothesis_id, span_ref, variants[] (варианты нормализации/восстановления опечаток), keep_as_is
  (первоклассный вариант с D-provenance), provenance{pattern_id}} — для OOV/аномальных форм; интегрируется с LEX_RECOVERY
  (§5.2): расстояние — ранжирование, не вердикт; «keep as-is» по умолчанию никогда не отбрасывается.
- **BoundaryCandidate** {candidate_id, position (между span'ами / конец span'а), kind ∈ {CLAUSE_BOUNDARY,
  SENTENCE_BOUNDARY, PUNCT_RESTORED}, evidence[] (структурные сигналы: позиции глагольных форм, объявленные
  boundary-паттерны, отсутствие пунктуации), provenance} — интегрируется с PUNCT_CLASS T0 [D8]: нет TERMINAL/CLAUSE-
  сигнала → кандидат, а не молчаливое решение.
- **ClauseCandidate** {candidate_id, segmentation (диапазоны span'ов), alternatives[] (связанные, адресуются до явного
  discard §2.3/I29), provenance} — альтернативные сегментации; разрешение = объявленный DecisionType BOUNDARY [Rev15].
- **EllipsisCandidate** {candidate_id, gap_ref (clause/span), kind ∈ {PREDICATE_GAP, ARGUMENT_GAP, SUBORDINATOR_GAP},
  antecedent_ref (структурный: предыдущая клауза/рамка), evidence[], provenance} — структурная анафора; T2/T3 подтверждает
  объявленными паттернами; интегрируется с FrameCandidate.copula_ellipsis (§5.3) и OP2-эллипсисом.
- **MissingArgumentCandidate** {candidate_id, frame_ref/slot_ref, role, status UNRESOLVED/RESOLVED_BY_ELLIPSIS/UNFILLED,
  provenance} — создаётся T2/T3 при valency-проверке (кардинальности PredicateSchema §16.9) и может ссылаться на
  EllipsisCandidate SRL как evidence [Rev16/H3]; сам SRL предлагает только структурные gaps (EllipsisCandidate);
  подтверждение/отклонение — существующим механизмом решений (DecisionType ELLIPSIS).
- **ReferenceCandidate** (§15.4) создаётся TD, а не SRL [Rev16/H2]: SRL передаёт только структурные сигналы (позиции,
  окно); grounds-категории {morphology, syntax, discourse, memory} добавляются в evidence[] при генерации TD (§17.4);
  новый тип не создаётся.

### 17.4 Каналы памяти до семантического выбора
Три объявленных канала (все версионные; влияние = только evidence + ранжирование + помощь разрешению):
- **Linguistic memory**: R-X RX1/RX2 (§5.10) + лексические/dependency-ресурсы → свидетельства и ранжирование структурных
  кандидатов; R-X — не основание (§6.4 O3), только приоритет/ранжирование, без self-confirmation (Rev7).
- **World knowledge**: R-WK WorldKnowledgeRecord (§15.5) → W-основания допустимости и constraint-рёбра; конфликт C vs W —
  по §15.5.
- **Episodic/discourse memory**: журнал наблюдений + discourse window [NQ7] + CoreferencePolicy (§15.4) → свидетельства/
  ранжирование ReferenceCandidate, помощь разрешению между наблюдениями (Consolidator).
Контракт [I28]: память не создаёт кандидатов без основания — она добавляет evidence (Grounds с провенансом), меняет
ранжирование объявленной версионной политикой и помогает разрешению; скрытые правила запрещены; один вход при разных
версиях контекста может дать разные исходы только через записанные свидетельства.

### 17.5 Acceptance-тесты [Rev15]
| Вход | Выход SRL | Downstream-разрешение | Ожидаемый результат |
|---|---|---|---|
| «Иван встретил Петра. Он ушёл.» | T0: TERMINAL после «Петра» → SentenceUnit×2; BoundaryCandidate нет (пунктуация есть); ReferenceCandidate «он»: grounds morphology (жёсткий фильтр MASC/SING §15.4), syntax (предпочтение subject — CoreferencePolicy [subject, recency]), discourse (window) | оба Иван и Пётр проходят жёсткий фильтр → несколько выживших с собственными основаниями → AMBIGUOUS {Иван, Пётр} с ранжированием объявленной политикой; молчаливого «первый» нет (§7.5); при наличии эпизодического наблюдения о одном из них — evidence смещает ранжирование (I28), иначе linked alternative сохраняется (I29) |
| «Машина была быстраяя» | TokenHypothesis «быстраяя»: variants {keep-as-is (первоклассный, D-provenance), объявленный typo-паттерн → «быстрая»}; LEX_RECOVERY-кандидат; SRL не решает смысл | T1/T3: разрешение объявленными правилами + bounded selection; вердикт по словарному расстоянию нет (V4 rev3: расстояние = ранжирование) |
| «Иван сказал Петя пришёл» | BoundaryCandidate после «сказал» (структурный сигнал: две глагольные формы в одном SentenceUnit, объявленный boundary-паттерн) vs чтение одной клаузы; EllipsisCandidate SUBORDINATOR_GAP («что»); ClauseCandidate {2 клаузы \| 1 клауза} | T2: NESTED frame (GOVERNS) vs FLAT — неоднозначность сохраняется до resolution (I29); keyword-правила «сказал» нет |
| «Иван в Москве. Пётр тоже.» | EllipsisCandidate PREDICATE_GAP во второй клаузе, antecedent = предикат первой + locative-аргумент (объявленный parallelism-паттерн); MissingArgumentCandidate на незаполненный роль | T2/T3: подтверждение объявленными паттернами → кандидат BE(Пётр, LOC(Moscow)) |
| «Он взлетел» с разным контекстом | ReferenceCandidate «он»: grounds morphology/syntax/discourse/memory; контекст A (предыдущее наблюдение о птице) vs B (о самолёте) vs C (антецедентов нет) | A/B: RESOLVED объявленной политикой + D-trace либо AMBIGUOUS при нескольких выживших с собственными основаниями; C: UNRESOLVED + REFERENCE_UNKNOWN (§15.4 п.3); один вход, разные версии контекста → разные исходы через evidence, не скрытые правила (I28) |

## 18. Стресс-аудит [Rev16]

### 18.1 Направление 1 — граница ответственности SRL
| Объект | Где заканчивается SRL | Где начинается семантика | Может ли стать семантическим фактом? |
|---|---|---|---|
| TokenHypothesis | варианты/keep_as_is (орфографический уровень, без POS и смысла) | T1 LexDecision (POS/lemma/OOV-решение) | Нет: смысла не несёт; в каноническую память — только через закоммиченное лексическое решение |
| BoundaryCandidate | позиция + evidence (структурные сигналы) | BOUNDARY-решение (T3/T4), потребление T1 п.8 [H1] | Нет: альтернатива сегментации, не факт; после RESOLVED влияет на ClauseUnit |
| ClauseCandidate | альтернативные сегментации + linked alternatives | BOUNDARY-решение (T3/T4) | Нет: до resolution — гипотезы; выжившие обрабатываются T2 как linked alternatives (I29) |
| ReferenceCandidate | НЕ объект SRL [H2]: создаётся TD по mentions окна (§15.4); «он» + кандидаты с evidence {morphology/syntax/discourse/memory} | REFERENCE-решение (T3/T4, §15.4 п.3) | «Он = Иван» появляется только как RESOLVED-решение с основаниями; канонический identity link — только T6/Consolidator (§2.7/I24); до resolution — кандидат + evidence, пары нет |
| EllipsisCandidate | gap + structural antecedent_ref | ELLIPSIS-подтверждение (T2/T3) | Нет: до RESOLVED — структурная гипотеза; после — часть frame completion с провенансом |
| MissingArgumentCandidate | НЕ объект SRL [H3]: создаётся T2/T3 valency-проверкой (§16.9), может ссылаться на EllipsisCandidate как evidence | slot resolution / UNRESOLVED+miss (T4) | Нет: диагностика неполноты (UNFILLED), не факт |
| CandidateIR | собирается T4 — единственный выход формализации; Consolidator читает semantic_candidates для фактов, structural_candidates[] — только read-only evidence/контекст [Rev16] | Consolidation (§2.7) | Объекты без RESOLVED-решения не материализуются (I25/I26) |
| PropositionNode / EventFrame | НЕ объекты SRL: создаются T3/T4 (семантика), I26 | T3/T4 → T5/T6 | Да, но только через коммит (T5/T6) — их штатный путь; до коммита — кандидаты |

### 18.2 Направление 2 — traceability
Цепочка Raw token → SRL candidate → CandidateIR → Decision → Canonical Memory покрыта: I23 (непрерывная цепь от span до
решения), I27 (SRL-кандидаты несут ProvenanceRecord pattern_id+span), §2.5 P1/P2, RXRecord provenance+versions, T6 —
единственная write-граница [A4]. Закрытые в Rev16 пробелы: **Decision.provenance{resource_versions{}, pattern_ids[]}** и
**Candidate.provenance.resource_versions{}** [H6] — теперь для каждого типа решения существуют: источник (Grounds.source),
версия ресурса (provenance.resource_versions), evidence (grounds[]), причина выбора (selected+grounds; M-основание через
last_prompt/raw_response §8.4), причина отклонения альтернатив (§2.3 REJECTED с D-trace/discard-причиной; EXPIRED — аудит).

### 18.3 Направление 3 — конфликт SRL и T3/T4
«Иван сказал Петя пришёл»: A/B-сегментации = ClauseCandidate (I29); T1 п.8 потребляет их [H1]; T2 генерирует frames по
каждой выжившей сегментации; T3/T4 принимают решения только по существующим кандидатам. Новый инвариант **I30**:
структурное закрытие после TD+T2; отсутствующая структура → NOT_COVERED-диагностика, а не молчаливая генерация.

### 18.4 Направление 4 — память и SRL
- **Linguistic (RX1/RX2)**: приоритет/ранжирование только, не основание (O3) — не может генерировать структуру или
  кандидатов без базовой записи.
- **World knowledge (R-WK)**: W-основания допустимости/constraints (§15.5); кандидатов и структуры не создаёт; C vs W —
  по §15.5.
- **Episodic/discourse**: единственный канал, расширяющий множество кандидатов — ReferenceCandidate из mentions
  предыдущих наблюдений через журнал/окно [H5]; evidence с провенансом memory-канала; identity-унификация — только
  Consolidator (I24).
Пример: «У нас есть только самолёт.» + «Он взлетел.» → допустимо ReferenceCandidate {самолёт, evidence(memory)};
недопустимо «Он = самолёт» до resolution: пара появляется только как REFERENCE-решение с основаниями (§15.4 п.3),
канонический link — T6. I28 покрывает все три канала.

### 18.5 Направление 5 — неоднозначность (сохранение неопределённости)
| Вход | Кандидаты | Где хранится ambiguity | Когда разрешение допустимо |
|---|---|---|---|
| «Он увидел его» | ReferenceCandidate для обоих PRO (множества антецедентов из окна) | Decision AMBIGUOUS + CandidateIR.ambiguity_sets[] + ObservationRecord.linked_alternatives | новая версия контекста / эпизодические свидетельства / явное уточнение (§10.1); reselection-правило; осцилляционная защита §6.3 |
| «Старый человек с собакой» | DependencyCandidate attachment модификатора (TD, объявленные правила) | несколько удовлетворяющих структур сосуществуют как кандидаты (I21/I29) | T3 bounded selection по существующим кандидатам или UNRESOLVED; новой структуры нет (I30) |
| «Я видел как он работает» | BoundaryCandidate на «видел\|как»; ClauseCandidate NESTED/FLAT; ReferenceCandidate «он» | ambiguity_sets[] + linked_alternatives, как в строке 1 | новая версия контекста / evidence; до того — обе сегментации живы (I29) |
| «Она сказала что придёт» | PropositionNode EMBEDDED non-ASSERTED (§16.1); MissingArgumentCandidate (субъект подчинённой, §16.9) / EllipsisCandidate ARGUMENT_GAP | UNRESOLVED slot + miss; linked_alternatives | объявленные паттерны или UNRESOLVED+miss; embedded proposition не факт до RESOLVED |
| «Пётр тоже» | EllipsisCandidate PREDICATE_GAP + antecedent из предыдущей клаузы (§17.5) | AMBIGUOUS с ранжированными кандидатами при нескольких антецедентах; linked_alternatives | объявленная политика + D-trace; молчаливого «первого» нет (§7.5) |

### 18.6 Направление 6 — LLM-граница
LLM только T3 (§3.1); T4 детерминирован [A2]. LLM не предлагает структуру: §8.4 (новые рамки/слоты/решения/
constraint'ы + структурные объекты I30) [H7→F7]; валидатор §8.5 выдаёт только протокольный исход; provenance:
last_prompt/raw_response в Decision, M-основание конструирует T3 из записанного I/O (§8.4). Прямой путь
LLM → Canonical Memory невозможен: единственная write-граница T6 [A4], I25/I26, CandidateIR — immutable snapshot.

### 18.7 Направление 7 — end-to-end acceptance (Phase 1 validation)
| Сценарий | M0 (память пуста) | M1 (эпизодический контекст) |
|---|---|---|
| A «Иван встретил Петра. Он ушёл.» | SRL: SentenceUnit×2, ReferenceCandidate «он» {Иван, Пётр} с evidence; Resolution: AMBIGUOUS ранжированный; Memory write: коммит MET-факта, reference UNRESOLVED — linked_alternatives в ObservationRecord, канонического identity link НЕТ | M1 (предыдущее наблюдение об Иване): evidence(memory) смещает ранжирование → RESOLVED(Иван)+D-trace; коммит + ReferenceDecision; identity через Consolidator |
| B «Иван сказал Петя пришёл.» | SRL: ClauseCandidate A/B; Resolution: AMBIGUOUS boundary — обе рамки linked alternatives; Memory write: embedded proposition НЕ коммитится (UNRESOLVED), ObservationRecord | явное уточнение (T6b) или новый контекст → RESOLVED + структура SAID/EMBEDDED по §16.1 |
| C «Иван в Москве. Пётр тоже.» | SRL: EllipsisCandidate PREDICATE_GAP, antecedent = предикат первой клаузы (структурно единственен) → RESOLVED объявленным паттерном; Memory write: коммит BE(Пётр, LOC(Moscow)) с провенансом | несколько антецедентов в контексте → AMBIGUOUS с ранжированными кандидатами |
| D «Машина была быстраяя.» | SRL: TokenHypothesis {keep-as-is (первоклассный), typo-паттерн→«быстрая»}; Resolution: LEX-решение по политике + D-trace; Memory write: коммит с LexDecision-provenance; вердикта по словарному расстоянию нет | то же; memory не влияет на орфографический уровень |
| E «Он взлетел.» | ReferenceCandidate: ноль антецедентов → UNRESOLVED + REFERENCE_UNKNOWN, miss; Memory write: факт НЕ коммитится (UNFILLED) | M1-птица: {птица, evidence(memory)} → RESOLVED/AMBIGUOUS по политике; M2-самолёт+птица: AMBIGUOUS с ранжированными кандидатами |

### 18.8 Направление 8 — финальный вердикт
**A. Найденные дыры:** H1 — T1 режет ClauseUnits без потребления SRL-кандидатов (Rev15-противоречие); H2 —
ReferenceCandidate числился объектом SRL при producer=TD; H3 — MissingArgumentCandidate: размытый producer (SRL vs
T2/T3 valency); H4 — не было явного запрета генерации структуры в T3/T4; H5 — межнаблюдательный scope окна для
ReferenceCandidate не был специфицирован; H6 — у Decision/Candidate отсутствовала версия ресурса в provenance;
H7 — в реестре §2.1 не было строк пяти новых SRL-объектов.
**B. Необходимые изменения (применены в Rev16):** F1 — T1 п.8 потребляет BoundaryCandidate/ClauseCandidate (+строка T1
§4.1); F2/F3 — §17.3: ReferenceCandidate и MissingArgumentCandidate не объекты SRL; F4 — I30 структурное закрытие;
F5 — §15.4 п.1: окно включает предыдущие наблюдения, identity только Consolidator; F6 — Decision/Candidate
provenance + resource_versions{}; F7 — §8.4: запрет структурных объектов LLM [I30]; H7 — строки реестра пяти объектов.
**C. Frozen:** после Rev16 документ frozen для Phase 1 validation (rev2–16): lifecycle T0→SRL→T1→TD→T2→T3/T4→
Consolidator→Canonical Memory; контракты §17/§18; инварианты I1–I30.
**D. Передаётся в реализацию:** (1) расширение Phase 1 прототипа SRL-стабом (TokenHypothesis/BoundaryCandidate/
EllipsisCandidate на корпусе A–E, FakeSelector); (2) end-to-end acceptance §18.7 как тестовый набор; (3) подключение
реального LLM-бэкенда через существующий интерфейс (§8).

## Приложение A. Самоаудит достаточности

Критерий: «может ли программист реализовать компонент, читая только V5 + типы AG_Memory, без собственных архитектурных
решений?» Остатки выбора — либо зафиксированы [default] в §13, либо помечены как открытые вопросы с дефолтным поведением.

| Раздел | Реализуем без собственных решений? | Остаток и его фиксация |
|---|---|---|
| 1 Scope / классификация A-B-C | Да | — |
| 2 Модели данных (реестр, кандидаты, цепочка §2.4) | Да | формат id кандидатов зафиксирован (§2.3); хеш observation_id = hash(source_id+span) [Q8: функция хеширования — существующая в AG_Memory] |
| 3 Архитектура (компоненты, поток версий, каналы) | Да | — |
| 4 Lifecycle (таблица этапов, runtime vs персистентное, порядок восстановления) | Да | — |
| 5 T0–T6b (алгоритмы + коды ошибок; rev9: PUNCT_CLASS, SentenceUnit/ClauseUnit/Mention, scope-паттерны, NONE_FIT; rev11: декларативный MentionBuilder — HeadRule/ExpansionRule, типы mention, самоаудит) | Да | PUNCT_CLASS зафиксирован (§5.1 п.2); границы clause — объявленные правила [B8]; дефолтный ruleset demo v1 (HeadRules HR-*, ExpansionRules ER-*) [C] (§5.2 п.9d); scope-лексикон demo v1 [C] (§5.2 п.10); DAWG-метрика [NQ1]; числовые бюджеты [NQ2] |
| 6 Decision engine (state machine, осциллятор, цепочка доказательности) | Да | функция хеша ground_signature — любая детерминированная (содержание R/C/D/A); конкретный хеш не влияет на контракт |
| 7 Constraint engine (кластеры, распространение, bounded search) | Да | порядок сортировки зафиксирован (§7.3 п.1); параллелизация запрещена [NQ4] |
| 8 LLM boundary (запрос/ответ/валидатор/стоимость/replay) | Да | — |
| 9 AH integration (ObservationStore, коммит, каноническое отображение, читатели) | Да | формат журнала [Q8]; числовые бюджеты [NQ2] |
| 10 Revision model (триггеры, два уровня отзыва, атомарность, R-X) | Да | — |
| 11 Failure handling (N1–N10 + диагностики) | Да | — |
| 12 Сквозной пример | Да (пример иллюстрирует §5/§6/§9/§10; не вводит новых правил) | — |
| 13 Open questions | Да (каждый остаток имеет [default]) | Q2/Q3/Q7a/Q7b/Q8/NQ5–NQ7 — отложены до данных, дефолтное поведение зафиксировано |
| 14 Formalizer invariants I1–I30 (Rev9/Rev12/Rev13b/Rev14.1/Rev15/Rev16) | Да (каждый инвариант имеет место фиксации и способ проверки) | — |
| 15 Семантический слой композиции (Rev12): TD/DependencyCandidate, LexSense, ScopeOperatorNode-дерево, coreference, WK, время, запросы, UnknownReason, EvidencePriorityPolicy, learning loop | Да | дефолтные DependencyRules [C] (§15.1); дефолтная CoreferencePolicy/EvidencePriorityPolicy (domain_rules) [C]; OperatorTypes + attachment-паттерны [C] (§15.3); размер discourse window [NQ7]; каноническая timepoint-модель (Фаза 2) [NQ6]; содержимое WK-корпуса — данные; domain_rules политики — явный review |
| 16 Универсальный semantic core (Rev14): CandidateIR, Local vs Consolidation, PropositionNode/SemanticExpression, ArgumentType, EventFrame, Attribute model, запрет phrase-level identity, existential unknowns, SemanticGraphCandidate | Да | множество ArgumentType замкнуто — расширение = декларация схемы; содержимое WK/лексических ресурсов — данные; окно межнаблюдательной coreference [NQ7]; отображение attitude→EpistemicStatus (§16.1) и записи PredicateSchema (§16.9) — версионные ресурсы, явный review; existential-триггерные паттерны — декларация ресурса (I13) |
| 17 Structural Reconstruction Layer (SRL, Rev15): стадия между T0 и T1, структурные кандидаты, каналы памяти до семантического выбора | Да | набор boundary/ellipsis-паттернов — объявленные ресурсы (I13); политики каналов памяти версионные; discourse window [NQ7] |

Вывод: ни один раздел не требует от реализатора самостоятельных архитектурных решений; все остатки выбора
зафиксированы значениями по умолчанию и помечены как снимаемые после данных Фазы 1. Количество тестов прототипа (79/79)
не является основанием считать архитектуру завершённой: они подтверждают корректность текущего прототипного контракта, а не
полноту настоящей спецификации; полнота проверяется критерием выше и валидацией Фазы 1.
