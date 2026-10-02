# Срез v0.19.0 — GoalSpec-driven cognition и proof-through-Ignition

## Назначение

Версия 0.19.0 закрывает runtime-контур целевого логического поиска из архитектуры v4. До этого `GoalSpec` уже существовал как формальный target/stop-condition, а отдельные proof paths умели использовать `InferenceAttention`. В 0.19.0 эти механизмы объединены в один причинный runtime-цикл:

```text
GoalSpec
→ GoalRuntime
→ текущий focus
→ узкий goal-derived memory query
→ найденный кандидат / rule / subgoal
→ подтверждённый proof step
→ QUERY_RECALL seed
→ обычный Ignition tick
→ изменённый Workspace
→ следующий допустимый шаг
→ termination
```

`GoalRuntime` не является canonical AH. Он не получает UID, не участвует в Hebbian и не сериализуется как знание.

## 1. GoalSpec как активная цель

`GoalSpec` дополнен `GoalMode`:

- `FACTUAL`;
- `PROOF`;
- `ASSOCIATION`;
- `EVIDENCE`.

Текущий `InferenceEngine` реализует factual/proof reasoning; `ASSOCIATION` предназначен для следующего специализированного coordinator-а и не превращает graph intersection в entailment.

По умолчанию `request_all_proofs=False`: после первого допустимого доказательства обычный запрос завершается. Это сохраняет архитектурное правило «не продолжать поиск на всякий случай после доказанной цели».

## 2. GoalRuntime

Для каждого `InferenceEngine.solve()` создаётся отдельный runtime `GoalRuntime`. Он содержит только состояние текущего запроса:

- исходный `GoalSpec`;
- ссылку на `InferenceAttention`, если она подключена;
- актуальный runtime Workspace snapshot;
- последовательность `CognitiveTraceEvent`.

Поддерживаются события:

```text
GOAL_START
FOCUS
MEMORY_QUERY
SUBGOAL
RULE_SELECTED
GOAL_STOP
```

Эти события — диагностика исполнения, не второй канал истины и не proof premises.

## 3. Focus физически проходит через Ignition

`GoalRuntime.focus(ref, depth)` делегирует реальный focus в `InferenceAttention`.

В штатном агенте используется `IgnitionInferenceAttention`:

```text
ref
→ ActivationSeedRequest(reason=QUERY_RECALL)
→ IgnitionEngine.apply_seed_requests(...)
→ IgnitionEngine.tick(include_pacemaker=False)
→ новый Workspace
```

То есть reasoner не меняет `x` напрямую и не рисует post-hoc animation после уже готового BFS. Следующий proof step открывается после того, как предыдущая proposition действительно прошла через обычную динамику памяти.

Если низкоуровневый unit test вызывает `InferenceEngine` без attention, proof semantics остаётся детерминированной, но `GoalRuntime` всё равно фиксирует причинный trace. Production/M2 path использует реальный Ignition attention.

## 4. Узкие внутренние запросы памяти

`CognitiveTraceEvent.MEMORY_QUERY` фиксирует тип, ключ и число кандидатов конкретного индексного чтения.

### 4.1. Factual role queries

`RoleFill`, `MultiRoleFill`, `Exists`:

```text
GoalSpec
→ focus(T)
→ TEMPLATE_FACTS(T + known role bindings)
→ matched N
→ focus(N)
→ FACT_MATCH / EXISTS_WITNESS
→ stop
```

Кандидаты генерируются существующим индексом `T -> N`; полный AH не сканируется.

### 4.2. Relation proof

Для `IS-A/FOLLOW/...`:

```text
focus(source)
→ exact DIRECT_RELATION lookup
→ если relation transitive:
   REVERSE_DISTANCE_HEURISTIC(target)   # pruning/order only
→ OUTGOING_RELATION(current focus)
→ validate registered transitivity
→ focus(next proposition)
→ ...
```

Reverse-distance не считается proof и это явно записывается в runtime trace.

### 4.3. CAUSE

`CAUSE` остаётся нетранзитивным relation schema. Multi-step путь работает как последовательное применение `CAUSE_MP` от явно допустимой premise:

```text
explicit premise A
A --CAUSE--> B
→ derive B in runtime proof state
→ focus(B)
B --CAUSE--> C
→ derive C
```

Incoming CAUSE lookup используется только как reverse candidate retrieval для legacy one-step/effect-oriented query и помечается как `not reverse proof`.

### 4.4. Formula / quantified proof

`GroundFormulaReasoner` теперь отражает в общем cognitive trace:

- reverse `FUNCTION_PARENTS` lookup от текущей цели;
- `RULE_HEAD_TEMPLATE` lookup для quantified implication;
- scoped-to-ordinary `TEMPLATE_FACTS` grounding;
- backward `SUBGOAL` при `IMPLIES`;
- branch subgoals для proof by cases;
- фактически применённые `RULE_SELECTED`.

Иными словами, backward decomposition и forward validation становятся наблюдаемыми в одном runtime trace.

## 5. Нет unrestricted global read

Для relation proof больше не требуется обращаться к broad store enumerators:

```text
all_elements()
all_uids()
elements(domain)
links()
```

Разрешены только goal/focus-derived индексные операции:

- `find_link(relation, source, target)`;
- `outgoing_links(uid, relation)`;
- `incoming_links(uid, relation)`;
- `find_hypernodes_by_template(T)`;
- `function_parents(operand)`;
- другие точечные reverse indexes, уже определённые canonical store.

Добавлен regression guard: broad enumerators monkeypatch-ятся на exception, после чего transitive FOLLOW proof всё равно обязан завершиться успешно.

## 6. Stop semantics

`GOAL_STOP` всегда является последним событием cognitive trace и содержит фактические `LogicalStatus / StopReason`.

Сохраняются состояния:

- `GOAL_SATISFIED`;
- `GOAL_REFUTED`;
- `CONFLICTED`;
- `CLARIFICATION_REQUIRED`;
- `SEARCH_EXHAUSTED`;
- `DEPTH_EXHAUSTED`;
- `BUDGET_EXHAUSTED`;
- `RESOURCE_LIMIT`.

При `GOAL_SATISFIED` поиск прекращается немедленно. Для цепочки `A→B→C→D` и цели `C` reasoner не делает outgoing query из `C` и не возбуждает `D` как proof focus.

## 7. Диагностика

`InferenceOutcome` получил:

```text
cognitive_trace: tuple[CognitiveTraceEvent, ...]
```

`ProofSnapshotBuilder` выводит два независимых слоя:

1. canonical proof trace — фактическая UID-цепочка premise/link/conclusion;
2. cognitive cycle — цель, focus shifts, memory queries, subgoals, rules, termination.

Это важно: лог доказательства не подменяет dynamics памяти, а dynamics не подменяет proof.

## 8. Сохранённые архитектурные инварианты

- `AH=<S,C,P,H,L>` не расширен;
- `GoalRuntime` и cognitive trace не являются canonical memory;
- `Recall != Inference`;
- `activation != truth`;
- Workspace влияет на доступность/приоритет, но не доказывает proposition;
- index — accelerator, не отдельная memory/truth store;
- reverse reachability/distance — только pruning/order heuristic;
- каждый фактически подтверждённый proof step в production/M2 path проходит через Ignition attention;
- `IS-A` и `FOLLOW` используют только явно зарегистрированную transitivity;
- `CAUSE` не стал транзитивным;
- конфликтные premises по-прежнему не становятся безусловными основаниями;
- counterfactual/branch contexts остаются runtime overlays;
- Main LLM не получает новый global-memory read path.

## 9. Что не входит в этот срез

0.19.0 не закрывает:

- association coordinator / `expand(A) ∩ expand(B)`;
- final Context Projector/document-summary path;
- финальную нормативную GC/acceptance integration;
- все M1–M5 benchmark runs;
- автоматическое построение любого произвольного GoalSpec из любых форм ЕЯ сверх уже существующего semantic goal compiler.

Следующий крупный срез — ассоциативный режим.

## 10. Регрессия

Перед выпуском 0.19.0:

```text
python -m compileall -q src
OK

pytest -q
675 passed, 22 subtests passed
```

Добавлен `tests/test_v4_goal_runtime_1900.py`, который проверяет:

- factual goal seed/query/focus/rule cycle;
- stop сразу на достигнутой relation-цели;
- запрет broad full-store read;
- backward IMPLIES subgoal + forward rule validation в cognitive trace.

Полный hackathon acceptance в этом срезе не запускался.
