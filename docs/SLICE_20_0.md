# Срез v0.20.0 — ассоциативный режим как пересечение активированных представлений

## Назначение

Версия 0.20.0 закрывает специализированный ассоциативный контур архитектуры v4:

```text
expand(A) ∩ expand(B) != ∅
```

Ассоциация реализована отдельно от `InferenceEngine`. Она не является логическим следствием, не создаёт `ProofSupport`, не materialize новый факт и не трактует найденный путь как `A -> B`.

Целевой runtime-цикл:

```text
AssociationGoal(A, B)
→ GoalSpec(mode=ASSOCIATION)
→ сильный QUERY_RECALL seed A и B
→ обычный synchronous Ignition
→ два runtime-фронта активации
→ narrow incidence queries только из текущих активированных focus
→ обычные QUERY_RECALL seeds найденных соседних структур
→ следующие Ignition ticks
→ AssociationSearchState фиксирует ancestry двух фронтов
→ первое подтверждённое пересечение front_A ∩ front_B
→ AssociationOutcome
```

`AssociationSearchState` является runtime-only контейнером. Он не получает UID, не сохраняется в AH и не участвует в Hebbian как отдельный объект.

## 1. Явная цель ассоциации

Добавлен `AssociationGoal`:

```text
AssociationGoal {
    left: Ref
    right: Ref
}
```

Он является допустимым target для `GoalSpec`, но намеренно **не входит в `InferenceGoal`**. Исполнение выполняет `AssociationCoordinator`, а не `InferenceEngine`.

Нормативный вызов:

```text
GoalSpec(
    target=AssociationGoal(A, B),
    mode=GoalMode.ASSOCIATION,
)
```

Это сохраняет архитектурное разделение:

```text
association != entailment
Recall/activation != proof
```

## 2. Два фронта и runtime ancestry

Для одного запроса создаётся `AssociationSearchState` с двумя независимыми provenance-фронтами:

```text
LEFT  from A
RIGHT from B
```

Для каждого фронта временно хранятся:

- активированные UID, реально получившие свежую активацию от данного фронта;
- глубина относительно origin;
- parent UID;
- тип перехода;
- canonical UID связи/гиперструктуры, через которую произошёл переход, если он существует;
- tick первого подтверждённого попадания во front;
- pending ancestry для импульсов, которые будут потреблены только следующим synchronous tick.

Warm Workspace не копируется в ancestry автоматически. Поэтому заранее возбуждённый посторонний узел не считается ассоциацией только потому, что уже присутствовал в Workspace до запроса.

## 3. Физическое прохождение через Ignition

Оба исходных понятия получают:

```text
ActivationSeedRequest(..., SeedReason.QUERY_RECALL)
```

После этого `AssociationCoordinator` использует обычный:

```text
IgnitionEngine.tick(include_pacemaker=False)
```

То есть:

- `x` не изменяется coordinator-ом вручную;
- пакет не перескакивает через несколько propagation edges за один tick;
- normal outgoing `L`, `S -> T`, `T -> N`, `N -> actants` продолжают работать существующим Ignition;
- pacemaker не создаёт ложную ancestry текущего ассоциативного запроса;
- сама ассоциация не получает отдельную «симуляцию возбуждения» в обход основного движка.

## 4. Goal-generated narrow incidence queries

Текущий Ignition имеет направленный packet flow. Но ассоциативное разворачивание представления по v4 не совпадает с логическим направлением relation. Поэтому из **только что активированного текущего focus** разрешены узкие reverse/incidence queries по существующим rebuildable indexes.

Поддержаны:

```text
actant       -> N          через hypernodes_for_actant(uid)
operand      -> g          через function_parents(uid)
member       -> k          через groups_containing(uid)
target(L)    -> source(L)  через incoming_links(uid)
N            -> T          canonical template ref
T            -> S          canonical predicate ref
g            -> operands   canonical operands
k            -> members    canonical members
```

Кандидат, найденный таким query, **не считается сразу частью фронта**. Он получает обычный `QUERY_RECALL` seed и должен реально активироваться на следующем Ignition tick. Только после `activation_event` его ancestry считается подтверждённым.

Таким образом, index остаётся accelerator/query boundary, а не отдельной памятью.

## 5. Обратное возбуждение не меняет логическую семантику

Для directed `L` разрешён ассоциативный обратный переход:

```text
A --CAUSE--> B

association activation:
B -> A
```

В trace такой шаг имеет явную диагностическую метку:

```text
L_BACKWARD:CAUSE
```

При этом canonical AH по-прежнему содержит только:

```text
CAUSE(A, B)
```

и **не создаёт**:

```text
CAUSE(B, A)
```

Следовательно, направление активации и направление логического relation остаются различными.

## 6. Допустимый common node

`AssociationCoordinator` не вводит hub-filter. Пересечением может быть любой возбуждаемый canonical AH element:

```text
S
m
T
N
g
k
...
```

`L` не является common node, потому что в текущем формализме у `L` нет собственного `x` и его нельзя seed/focus как элемент возбуждения.

Регрессия покрывает:

- общий semantic `m`;
- общий lexical `S`;
- общий generic `T`;
- общий `g`;
- общий `k`.

В частности, общий `T_HAVE` остаётся валидной ассоциацией. Это может быть менее информативно для verbalized ответа, но **качество объяснения не смешивается с критерием существования ассоциации**.

## 7. Выбор первого результата

Coordinator останавливается после первой фактически достигнутой convergence, если режим не требует дальнейшего exploration.

Если на одном tick появилось несколько common nodes, выбор первого результата детерминирован только техническим порядком:

```text
ранний convergence tick
→ меньшая суммарная глубина двух фронтов
→ меньшая максимальная глубина
→ UID tie-break
```

Это **не semantic ranking** и не hub filtering. Все common nodes, уже обнаруженные на момент остановки, возвращаются в `common_candidates`.

## 8. Runtime H-domain policy

Архитектура v4 оставляет роль H в association mode открытой. Поэтому 0.20.0 не зашивает один вариант в canonical model.

Добавлена runtime-политика:

```text
AssociationDomainPolicy.ALL
AssociationDomainPolicy.EXCLUDE_H
```

`ALL` разрешает эпизодическим H-узлам участвовать в пересечении наравне с C/P.

`EXCLUDE_H` не допускает H в ancestry текущего association search.

Это только параметр конкретного запроса; AH и persistence не меняются.

## 9. Ограничение поиска

`AssociationBudget` задаёт:

```text
max_depth
max_expanded_states
max_ticks
```

Termination:

```text
FOUND
NOT_FOUND
DEPTH_EXHAUSTED
BUDGET_EXHAUSTED
RESOURCE_LIMIT
```

Статусы намеренно не используют `LogicalStatus.PROVED/DISPROVED`: отсутствие найденной ассоциации не является логическим отрицанием какого-либо факта.

## 10. Нет unrestricted global read

Ассоциативный поиск не использует broad enumerators:

```text
all_elements()
all_uids()
elements(domain)
links()
```

Все расширения выводятся из текущего активированного UID через локальные indexes/adjacency.

Регрессия monkeypatch-ит broad reads на exception; association всё равно находит пересечение.

## 11. Каноническая память не расширяется поисковым состоянием

Во время `AssociationCoordinator.solve()`:

- не создаётся новый canonical `q`;
- не создаётся canonical «association node»;
- runtime ancestry не materialize;
- не создаётся `ProofSupport`;
- найденное пересечение не создаёт новый `L`;
- `AssociationOutcome` и trace не сериализуются как знания.

Обычная Ignition dynamics при включённой plasticity может, как и при любой когнитивной активации, обновлять веса **существующих** `L` по общему Hebbian contract. Это не является созданием topology ассоциативным coordinator-ом.

## 12. Диагностика

Добавлен отдельный association trace:

```text
GOAL_START
SEED
ACTIVATION
MEMORY_QUERY
CONVERGENCE
GOAL_STOP
```

`AssociationPath` хранит для каждой стороны:

```text
origin
common
refs[]
hops[]
```

Каждый `AssociationHop` различает:

```text
PROPAGATION
MEMORY_QUERY
```

и сохраняет `relation`, `tick`, `via_uid`.

Trace объясняет **как сошлись активированные представления**, но не называется proof trace.

## 13. Метрика minimum facts

0.20.0 намеренно не вычисляет «число фактов» по количеству внутренних `N/T/L/...` на association path.

Архитектура v4 требует считать **входные factual assertions**, потому что одна человеческая фраза может породить несколько внутренних элементов AH. Поэтому этот показатель должен считаться acceptance/benchmark harness по исходным assertions/provenance, а не внутри `AssociationCoordinator`.

## 14. Сохранённые архитектурные инварианты

- `AH=<S,C,P,H,L>` не расширен;
- association не является proof;
- `activation != truth`;
- `w != confidence`;
- обычный Ignition остаётся единственным механизмом изменения `x`;
- runtime ancestry не становится памятью;
- reverse activation не создаёт reverse semantic relation;
- hub-filter не является условием существования association;
- общий `S` допустим;
- H policy остаётся runtime option;
- query строится только из текущего активного focus;
- unrestricted global AH scan отсутствует;
- `IS-A / FOLLOW / CAUSE` inference semantics не изменены;
- `CAUSE` не стал транзитивным.

## 15. Что не входит в этот срез

0.20.0 не закрывает:

- verbalized ranking/качество объяснения нескольких найденных common nodes;
- окончательное архитектурное решение, считать ли H полноценной semantic association;
- Context Projector/document-summary path;
- финальную lifecycle/GC + DSL + hackathon acceptance integration;
- M1–M5 benchmark runs.

Следующий крупный срез — `0.21.0`: Context Projector, server boundary и документный semantic projection.

## 16. Регрессия

Добавлен `tests/test_v4_association_2000.py`, который проверяет:

- `GoalSpec(mode=ASSOCIATION)`;
- `ворона / стол -> ножки` через два representation fronts;
- допустимость общего `S`;
- отсутствие mandatory hub-filter для общего `T`;
- common `g` и `k`;
- отсутствие false convergence от warm Workspace;
- runtime H policy;
- обратную activation по `CAUSE` без создания `CAUSE(effect,cause)`;
- отсутствие canonical node/link/support materialization;
- resource budget;
- отсутствие broad global reads;
- immediate convergence одинаковых origins.

Перед выпуском 0.20.0:

```text
python -m compileall -q src
OK

pytest -q
688 passed, 22 subtests passed
```

Полный hackathon acceptance в этом срезе не запускался.
