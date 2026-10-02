# Срез v0.18.0 — ветвящееся, контрфактуальное и мета-рассуждение

## Назначение

Версия 0.18.0 закрывает runtime-контур сложных областей рассуждения из архитектуры v4 без расширения канонического кортежа `AH=<S,C,P,H,L>`. Временные допущения, ветви доказательства и контрфактуальные миры остаются состоянием reasoner-а; каноническими объектами по-прежнему являются существующие `N/g/k/...`.

Закрыты четыре связанные границы:

```text
asserted OR
→ BranchContext на каждую ветвь
→ доказательство цели во всех ветвях
→ общий вывод без записи ветвевых допущений

явные допущения
→ CounterfactualContext overlay
→ локальное подавление несовместимых supports/facts
→ обычный rule proof
→ результат только runtime, без factual commit

reported / hypothetical / modal content
→ scoped proposition N/g
→ допускается как содержимое matrix proposition
→ не становится ordinary factual premise

FALSE / CONTRADICTS / CORRECTS
→ зарегистрированная машинная meta-semantics
→ адресуемое исправление/противоречие
→ без выбора истины по x/w/новизне
```

## 1. Runtime ProofContext

`ProofContext` остаётся неканоническим контейнером. Он хранит только состояние конкретного доказательства:

- `bindings`;
- локальные `assumptions`;
- `local_derived`;
- фильтры допустимости;
- ссылку на родительскую область.

Добавлены два специализированных runtime-контекста.

### BranchContext

Используется только для proof by cases. Ветвевое допущение допустимо внутри одной ветви и не получает статус отдельного факта.

### CounterfactualContext

Хранит:

- исходные явные допущения;
- локально подавленные premise UID;
- нормализованное множество положительных допущений;
- соответствие отрицательных допущений тем каноническим propositions, которые они локально перекрывают.

Ни `BranchContext`, ни `CounterfactualContext` не сериализуются как AH-узлы и не получают activation/Hebbian state.

## 2. Proof by cases

Реализована дизъюнктивная элиминация:

```text
OR(A, B)
A -> C
B -> C
────────
C
```

Поиск остаётся целевым:

1. reasoner начинает с текущей цели `C`;
2. через reverse function index получает только `IMPLIES(..., C)`;
3. по antecedent этих правил ищет связанный asserted `OR`;
4. для каждой ветви создаёт отдельный `BranchContext`;
5. в ветви временно допускает соответствующий operand `OR`;
6. цель должна быть доказана в каждой ветви;
7. итоговый `ProofSupport` содержит asserted `OR` и правила ветвей, но не выдаёт branch assumptions за independent factual premises.

Ветвевые промежуточные выводы не materialize в AH. Итоговый вывод может materialize только после успешного доказательства во всех ветвях.

## 3. Контрфактуальный overlay

Добавлен `CounterfactualGoal(assumptions, target)`.

Контрфакт не копирует AH. Он создаёт overlay над тем же read-only canonical state.

### 3.1. Явные допущения

Поддерживается произвольное количество одновременных допущений в пределах обычного proof budget. Встроенного лимита «одна/две переменные» нет.

Если набор допущений содержит одновременно `P` и `NOT(P)`, запрос завершается `CONFLICTED` до запуска доказательства.

### 3.2. Семантически эквивалентные scoped propositions

Допущение из пользовательского гипотетического запроса может иметь собственный scoped UID. Поэтому для ground `N` overlay сопоставляет его с канонически эквивалентными propositions по существующему индексу `T -> N` и равенству актантов.

Пример:

```text
canonical:          N_WORK(server)
hypothetical scope: N_WORK_hyp(server)
assumption:          NOT(N_WORK_hyp)
```

В counterfactual world это корректно подавляет ordinary `N_WORK(server)`, не меняя ни один UID в canonical AH.

### 3.3. Local override

- `NOT(P)` временно подавляет положительный `P`;
- положительное допущение `P` временно подавляет несовместимые `NOT(P)` и `FALSE(P)`;
- unresolved canonical conflict может быть локально перекрыт явным допущением только внутри counterfactual scope;
- после завершения proof исходная AH остаётся неизменной.

### 3.4. Dependency-aware support filtering

Materialized derived fact считается допустимым в overlay только если у него остаётся хотя бы один support, все premise которого допустимы в этом мире.

Проверка рекурсивна:

```text
P -> support(Q)
Q -> support(R)
assume NOT(P)

Q  invalid in overlay
R  invalid in overlay
```

Если у `Q` или `R` есть независимый support, не зависящий от `P`, он сохраняется.

Persisted `SupportLedger` при этом не редактируется.

## 4. Запрет materialization контрфактуального результата

`InferenceMaterializer` проверяет `ProofContext`. Если результат получен внутри `CounterfactualContext`, factual commit запрещён независимо от статуса `PROVED`.

Это защищает AH от конструкции:

```text
предположим P
P -> Q
следовательно Q
```

где `Q` допустимо только внутри изменённого мира.

## 5. Reported, hypothetical и modal scope

`AssertionStatus` расширен runtime-режимами:

- `EMBEDDED`;
- `HYPOTHETICAL`;
- `MODAL`.

Такие propositions канонизируются как адресуемое содержание с `occurrence_count=0` и соответствующим `semantic_scope`, чтобы другой `N` мог ссылаться на них как на proposition-actant.

При этом они не становятся ordinary factual premises.

Пример:

```text
Анна считает, что сервер работает.

N_BELIEVE
SUBJECT -> m_АННА
OBJECT  -> N_WORK[scope=EMBEDDED]
```

Доказуем факт `BELIEVE(Анна, P)`, но сам вложенный `P` не становится доказанным фактом мира.

Полная модальная логика (`K/T/S4/S5`, вероятностный вывод, `POSSIBLE(P) -> P`) не вводится.

## 6. Meta-propositions

`FunctionRegistry` теперь явно регистрирует operational meta-functions:

- `FALSE(N)`;
- `CONTRADICTS(P,Q)`;
- `CORRECTS(target,replacement)`.

### FALSE

Сохраняет существующую семантику явного опровержения конкретного `N` и инвалидирует только downstream supports, зависящие от него.

### CONTRADICTS

`SemanticCorrectionService.mark_contradiction()` создаёт адресуемое meta-утверждение о противоречии. Оно не выбирает победителя и не превращает один operand в истинный, другой — в ложный.

### CORRECTS

`SemanticCorrectionService.correct(target,replacement)`:

1. создаёт/переиспользует `FALSE(target)`;
2. создаёт `CORRECTS(target,replacement)`;
3. инвалидирует только supports, зависящие от `target`;
4. не создаёт `replacement` из текста в обход normal Integration;
5. не удаляет исторический `target`.

`CONTRADICTS` и `CORRECTS` доказуемы как explicit meta-propositions, но их operands не получают truth автоматически.

## 7. Self-reference

Если canonical/persisted formula непосредственно ссылается на саму себя, ordinary reasoner завершает её как `UNKNOWN` с диагностикой self-reference. Отдельный truth-paradox solver не вводится.

Это fail-closed граница, а не попытка решить `N = FALSE(N)`.

## 8. Диагностика

`ProofSnapshotBuilder` умеет явно показывать:

- `OR_CASES` для proof by cases;
- counterfactual goal с перечнем допущений;
- факт работы внутри `CounterfactualContext`;
- отсутствие factual materialization для sandbox proof.

Диагностические snapshots не являются AH/H и не влияют на доказательство.

## 9. Сохранённые инварианты v4

- canonical `AH=<S,C,P,H,L>` не расширен;
- runtime context не становится новым `q`;
- `OR`-ветви не materialize как facts;
- `UNKNOWN != FALSE`;
- конфликт не выбирает победителя по `x`, `w`, повтору или новизне;
- counterfactual assumptions действуют только внутри local proof scope;
- canonical AH не копируется для counterfactual reasoning;
- independent supports переживают локальное подавление другого support;
- reported/modal/hypothetical content не загрязняет factual memory;
- `FALSE(N)` остаётся отличным от object-level `NOT(P)`;
- `IS-A`, `FOLLOW`, `CAUSE` не изменены;
- `CAUSE` не стал транзитивным;
- Main LLM не получила новый канал записи/поиска памяти.

## 10. Что не входит в этот срез

Не реализуются:

- Structural Causal Model;
- автоматическое угадывание скрытых interventions;
- генерация всех возможных альтернативных миров;
- полная модальная логика;
- truth-paradox solver;
- автоматический выбор стороны конфликта;
- универсальный ЕЯ-компилятор контрфактуальных вопросов — это часть последующего GoalSpec/goal-compilation контура.

## 11. Регрессия

Перед выпуском 0.18.0:

```text
python -m compileall -q src   OK
pytest -q                    671 passed, 22 subtests passed
```

Полный hackathon acceptance в этом промежуточном архитектурном срезе не запускался.
