# Slice 0.14.0 — исполнение кванторов и универсальных правил

## 1. Назначение среза

Версия 0.14.0 доводит до исполняемого состояния кванторную часть логического слоя v4 поверх уже готового `N/g`-контура 0.13.0. Срез не вводит новую модель памяти и не меняет формализм `AH=<S,C,P,H,L>`: атомарная proposition по-прежнему представляется `N`, логическая композиция — зарегистрированным `g`, а переменная квантора — только scoped-дескриптором `BoundVar` без собственного UID.

Закрывается цепочка:

```text
canonical quantified formula
        ↓
BoundVar + scoped N-patterns
        ↓
runtime BindingEnvironment
        ↓
goal-directed unification
        ↓
proof premises
        ↓
forward validation
        ↓
InferenceOutcome + ProofSupport
```

Этот срез касается исполнения уже канонизированных формул. Распознавание кванторов из произвольного естественного языка остаётся задачей слоя формализации и не объявляется закрытым здесь.

## 2. Каноническое представление атома с переменной

Обычный factual `N` хранит конкретные ссылки-актанты. Для атома внутри области действия квантора используется тот же `N`, но как scoped formula-pattern:

```text
FORALL $0:
    HUMAN($0) -> MORTAL($0)
```

представляется как:

```text
g_FORALL(
    BoundVar(0, ENTITY),
    g_IMPLIES(
        N_HUMAN_PATTERN(SUBJECT=$0),
        N_MORTAL_PATTERN(SUBJECT=$0)
    )
)
```

`N_*_PATTERN` имеет `semantic_scope=QUANTIFIED`. Это не новый `q` и не самостоятельный factual occurrence.

Canonical validation запрещает `BoundVar` в обычном factual `N`. Тем самым переменная не может случайно попасть в фактическую память как неизвестная сущность.

## 3. BoundVar

`BoundVar(local_id, sort)` обозначает тождество одного placeholder внутри owning scope.

Поддерживаемые сорта текущего кода:

- `ENTITY`;
- `PROPOSITION`;
- `TIME`;
- `VALUE`;
- `EVENT`;
- `UNKNOWN`.

Инварианты:

- нет глобального UID;
- не является `s/m/N/g/k/T/L`;
- не имеет `x`;
- не попадает в Workspace;
- не является endpoint распространения возбуждения;
- не участвует в Hebbian update;
- конкретное значение не записывается обратно в canonical formula.

Persistence сохраняет только descriptor переменной как operand формулы. Старые `Ref`-актанты сохраняют прежнюю форму сериализации.

## 4. BindingEnvironment и области видимости

Конкретная подстановка существует только во время proof:

```text
$0 -> m_ИВАН
```

`BindingEnvironment` поддерживает parent/child scopes. Объявление переменной в дочернем scope является lexical barrier: внутренний `$0` может затенить внешний `$0`, даже пока ещё не получил значение.

Пример:

```text
EXISTS $0:
    HUMAN($0)
    AND EXISTS $0:
        SIT($0)
```

Два `$0` принадлежат разным областям. Binding внутреннего квантора не переписывает внешний.

Sort проверяется при связывании. Например `ENTITY` связывается только с canonical `m`; proposition/event — с `N/g` в пределах текущего формального контракта.

## 5. EXISTS

Форма:

```text
EXISTS BoundVar, body
```

Исполнение:

1. создаётся дочерняя область `BindingEnvironment`;
2. переменная объявляется в ней;
3. reasoner доказывает `body`;
4. variable-bearing atomic `N` получает кандидатов только из индекса соответствующего `T`;
5. кандидат унифицируется с pattern;
6. остальные conjuncts проверяются с той же подстановкой;
7. первый полный witness завершает existential proof.

Пример:

```text
EXISTS $0:
    ENTER($0) AND SIT($0)
```

`ENTER(Иван)` и `SIT(Мария)` не являются witness. Нужна одна identity, удовлетворяющая обеим частям.

Open-world semantics:

```text
witness найден     -> PROVED
witness не найден  -> UNKNOWN
```

Отсутствие witness не превращается в `FALSE`.

Внутренний binding existential-переменной не выходит за пределы её scope. Premises и trace доказательства при этом сохраняются.

## 6. FORALL

Reasoner не выводит универсальность из конечного содержимого памяти.

Недопустимо:

```text
HUMAN(Иван)
HUMAN(Мария)
нет известных контрпримеров
=> FORALL x HUMAN(x)
```

Такой запрос возвращает `UNKNOWN`.

Универсальное утверждение может выступать premise, если оно само явно утверждено или имеет формальное независимое основание. Это сохраняет open-world semantics и не подменяет универсальный proof перебором текущей базы.

## 7. Универсальное правило

Основной исполняемый случай:

```text
FORALL $0:
    HUMAN($0) -> MORTAL($0)
```

При цели:

```text
MORTAL(Иван)
```

поиск выполняется от цели, а не сканированием всех правил.

### 7.1. Поиск правила

```text
MORTAL(Иван)
    ↓ template T_MORTAL
quantified N-patterns того же T
    ↓ reverse function-parent index
IMPLIES(..., MORTAL($0))
    ↓ reverse function-parent index
FORALL $0
```

Рассматриваются только структуры, которые могут унифицироваться с текущей целью.

### 7.2. Подстановка

Consequent pattern сопоставляется с ground goal:

```text
MORTAL($0)
MORTAL(Иван)
=> $0 = m_ИВАН
```

Подстановка создаётся только в runtime.

### 7.3. Backward decomposition

Из правила строится подцель:

```text
HUMAN(Иван)
```

### 7.4. Forward validation

После доказательства premise правило применяется вперёд:

```text
HUMAN(Иван)
+
FORALL $0: HUMAN($0) -> MORTAL($0)
=>
MORTAL(Иван)
```

Результат получает `ProofSupport(rule_id=FORALL_IMPLIES_MP)`.

Это сохраняет принятый v4 принцип: backward decomposition определяет, что искать, а фактический вывод подтверждается вперёд по допустимому правилу.

## 8. Вложенные кванторы

Кванторы рекурсивны. Поддерживаются, в частности:

```text
FORALL x:
    EXISTS y:
        FRIEND(x,y)
```

и универсальные правила с несколькими переменными:

```text
FORALL x:
    FORALL y:
        FRIEND(x,y) -> KNOWS(x,y)
```

А также дополнительные existential variables в premise:

```text
FORALL x:
    HUMAN(x)
    AND EXISTS y: FRIEND(x,y)
    -> SOCIAL(x)
```

Вложенность не имеет отдельного фиксированного семантического лимита. Реальное выполнение ограничивается общими `max_depth` и `max_expanded_states`, то есть ресурсным бюджетом запроса, а не искусственным правилом «не больше N кванторов».

## 9. AND / OR / NOT внутри quantified body

`AND` выполняет backtracking последовательно: binding, полученный в одной части, передаётся следующей.

`OR` разворачивает независимые ветви с копиями текущего environment.

`NOT` не использует negation-as-failure. Для variable-bearing atom отрицательная ветвь требует явного `NOT(P)` или `FALSE(N)` evidence. `UNKNOWN` не считается отрицанием.

## 10. Индексы и доступ к большой AH

Quantified proof не получает права на unrestricted scan всей памяти.

Используются только перестраиваемые технические индексы:

- `T -> N` для ground witnesses и quantified patterns;
- `operand UID -> parent g` для подъёма от head к `IMPLIES/FORALL`.

Поэтому нерелевантные шаблоны и факты не перебираются только потому, что присутствуют в AH. Регрессия с 500 отдельными шумовыми T/N подтверждает, что число expanded states для целевого HUMAN/MORTAL proof остаётся малым.

Индекс остаётся ускорителем и может быть восстановлен из canonical AH. Он не является второй памятью и не создаёт доказательство сам по себе.

## 11. Proof и Ignition

При подключённом `InferenceAttention` подтверждённые canonical шаги получают focus и проходят через обычный Ignition contour.

Для универсального вывода наблюдаемы, например:

```text
G_FORALL
N_HUMAN_IVAN
N_HUMAN_PATTERN
G_IMPLIES
N_MORTAL_IVAN
```

`BoundVar` отсутствует в этом списке принципиально: у него нет UID и runtime activation slot.

Таким образом:

```text
proof rule validation
!=
activation
```

но фактически используемые элементы proof воздействуют на Workspace через тот же механизм памяти, что и другие активные структуры.

## 12. ProofSupport и materialization

Если conclusion уже имеет canonical UID, materializer больше не теряет proof dependency. `ExistingRefConclusion` получает support records:

```text
conclusion N
    <- premise N
    <- universal g_FORALL
    <- implication g_IMPLIES
```

Один conclusion может иметь несколько независимых supports.

Явное refutation premise:

```text
FALSE(N_PREMISE)
```

инвалидирует только supports, которые зависят от этой premise. Если у conclusion остаётся другой независимый support, он остаётся допустимым. Если supports больше нет и собственного asserted occurrence тоже нет, conclusion перестаёт доказываться; дальнейшее физическое удаление остаётся обязанностью lifecycle/GC.

## 13. Совместимость с M2 и постановкой хакатона

Срез не заменяет и не переопределяет структурный M2.

Сохраняются без изменения:

- `IS-A` — транзитивное зарегистрированное отношение;
- `FOLLOW` — транзитивное зарегистрированное отношение;
- `CAUSE` — обязательное причинное отношение без автоматического transitive closure;
- UID trace;
- Ignition/Workspace;
- существующие relation indexes и acceptance hooks.

Кванторный reasoner расширяет общую символическую подсистему, но не превращает `IS-A/FOLLOW/CAUSE` в обычные текстовые предикаты и не отменяет их обязательную хакатонную семантику.

## 14. Что намеренно не входит в 0.14.0

Версия не объявляет готовыми:

- распознавание всех кванторных конструкций естественного языка;
- forced interpretation неоднозначного scope;
- доказательство `FORALL` перебором известной базы;
- closed-world negation;
- универсальный математический решатель;
- полную модальную логику;
- новый canonical тип переменной;
- глобальный поиск по всей AH.

Следующий слой формализации должен создавать описанные здесь canonical structures детерминированно после синтаксического сужения и bounded semantic probes, а не менять контракт reasoner-а.

## 15. Регрессионный контракт среза

Проверяются:

- existential witness;
- `UNKNOWN` при отсутствии witness;
- одинаковый witness для повторяющейся переменной;
- lexical shadowing;
- universal modus ponens;
- запрет использования unasserted universal rule;
- несколько universal variables;
- запрет FORALL-by-enumeration;
- persistence/reload variable-bearing N;
- запрет BoundVar в factual N;
- persisted ProofSupport и invalidation после refutation;
- nested EXISTS внутри universal antecedent;
- физическое движение proof через Ignition;
- отсутствие activation state у BoundVar;
- устойчивость к большому нерелевантному шуму;
- отсутствие фиксированного лимита в восемь вложенных FORALL;
- безопасная диагностика legacy declaration-only quantifier.

Полный hackathon acceptance этим срезом не подменяется и запускается отдельно после завершения архитектурного цикла.

Результат полной регрессии перед выпуском: `620 passed, 22 subtests passed`; `python -m compileall -q src` — успешно.
