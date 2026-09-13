# Кванторы: каноника, формализация из NL, исполнение

Документ описывает **как кванторы устроены в коде сейчас**: слой исполнения (срез 0.14) и слой NL → те же канонические формулы. Не changelog и не постановка хакатона.

Нормативная рамка: `docs/ARCHITECTURE_V4_DEV.md` §23 (и совпадающий §23 в `docs/extra/Архитектура_АГ_памяти_для_разработки.docx`). Исполнение формул: срез 0.14. Распознавание из русского — отдельный слой formalization/integration; reasoner при этом не расширялся.

```text
AH = <S, C, P, H, L>     без изменений
атом                   N
логика                 зарегистрированный g
переменная квантора    BoundVar, без UID
```

---

## 1. Два слоя, одна каноника

**Исполнение (0.14, не трогали).** Уже каноническая формула → `BoundVar` + QUANTIFIED pattern-N → runtime `BindingEnvironment` → unification → proof → `InferenceOutcome` / `ProofSupport`.

**Формализация (этот срез).** Русская фраза → те же `g_FORALL` / `g_EXISTS` / `NOT`. Не новый вид узла `q`, не keyword→логика в парсере как отдельный reasoner.

```text
русский текст
    → Perception (актанты как обычно)
    → Formalization: determiner ≠ сущность; runtime binding
    → Integration: QUANTIFIED N + g
    → H.OBJECT = корень формулы
    → GroundFormulaReasoner (правила 0.14)
```

Код:

| Слой | Файлы |
|---|---|
| Каноника | `src/ah/model/operands.py` (`BoundVar`), `src/ah/core/validation.py` |
| Persistence | `src/ah/core/persistence.py` (descriptor, не UID) |
| Proof | `src/ah/inference/formula.py`, `src/ah/inference/bindings.py` |
| NL → IR | `src/ah/integration/formalization.py` |
| Запись в AH | `src/ah/integration/service.py` |
| Ignition | `src/ah/ignition/engine.py` (BoundVar не endpoint) |

---

## 2. Каноническое представление

Обычный факт: `N` с актантами-`Ref`. Атом **внутри** квантора — тот же `N`, но formula-pattern:

```text
semantic_scope = QUANTIFIED
count_occurrence = False     # не ordinary factual occurrence
SUBJECT / … = BoundVar(...)
```

Валидация запрещает `BoundVar` в фактическом N без этого scope.

Пример §23 / 0.14:

```text
FORALL $0: HUMAN($0) → MORTAL($0)
```

в памяти:

```text
g_FORALL(
    BoundVar(0, ENTITY),
    g_IMPLIES(
        N_HUMAN_PATTERN(SUBJECT=$0),
        N_MORTAL_PATTERN(SUBJECT=$0)
    )
)
```

Операторы ядра (общий reasoner, не textual special-case): `FORALL`, `EXISTS`, `NOT`, `AND`, `OR`, `IMPLIES`.

### BoundVar

```text
BoundVar(local_id: int ≥ 0, sort)
sort ∈ {ENTITY, PROPOSITION, TIME, VALUE, EVENT, UNKNOWN}
```

Инварианты:

- нет глобального UID, не `s/m/N/g/k/T/L`;
- нет runtime `x`, не в Workspace, не Hebbian, не endpoint возбуждения;
- значение **не** записывается обратно в каноническую формулу;
- `local_id` осмыслен только внутри owning scope (вложенный `$0` может затенить внешний `$0`).

NL-универсалии и «кто-то»/«никто» сейчас всегда `sort=ENTITY`.

### BindingEnvironment

Только runtime proof:

```text
$0 → m_ИВАН
```

Parent/child scopes: объявление в дочернем — lexical barrier. Sort проверяется при bind (`ENTITY` → `M`, proposition/event → `N`/`g`, TIME/VALUE → `M`).

---

## 3. Семантика исполнения (open-world)

### EXISTS

```text
EXISTS BoundVar, body
```

1. Дочерний `BindingEnvironment`, переменная объявлена.
2. Reasoner доказывает `body`.
3. Кандидаты variable-bearing N — только индекс `T → N` того же шаблона, не скан всей AH.
4. Первый полный witness → `PROVED` (`EXISTS_WITNESS`).
5. Нет witness → `UNKNOWN`, **не** `FALSE`.

Conjunction: одна и та же подстановка на все части. `ENTER(Иван) ∧ SIT(Мария)` не witness для `EXISTS $0: ENTER($0) ∧ SIT($0)`.

Если формула **сама утверждена** ходом (H указывает на `g_EXISTS`) — корень доказывается как `EXISTS_ASSERTED`. Это посылка «кто-то спит», а не вывод свидетелем. Pattern-N без факта остаётся `UNKNOWN`.

### FORALL

Не выводится из конечной базы:

```text
HUMAN(Иван), HUMAN(Мария), нет известных контрпримеров
⇏  FORALL x HUMAN(x)
```

Такой запрос: `UNKNOWN`. Универсальность — только явное asserted правило или независимый формальный proof (`FORALL_ASSERTED`).

### Универсальное правило (главный исполняемый случай)

Цель `MORTAL(Иван)` ищется **от цели**, не сканом всех правил:

```text
MORTAL(Иван)
  → T_MORTAL
  → QUANTIFIED N того же T
  → parent g IMPLIES(..., MORTAL($0))
  → parent g FORALL $0
```

Подстановка только в runtime: `MORTAL($0)` ⋈ `MORTAL(Иван)` ⇒ `$0 = m_ИВАН`. Дальше подцель `HUMAN(Иван)`, затем **forward** validation:

```text
HUMAN(Иван) + FORALL $0: HUMAN($0) → MORTAL($0)
⇒ MORTAL(Иван)
ProofSupport.rule_id = FORALL_IMPLIES_MP
```

Unasserted контейнер `g_FORALL` правило не стреляет.

### NOT / AND / OR в теле

- `AND` — backtracking, binding идёт дальше по конъюнктам.
- `OR` — независимые ветви с копией environment.
- `NOT` — **не** negation-as-failure. Нужен явный `NOT(P)` или `FALSE(N)`. `UNKNOWN` не отрицание.

Индексы: `T → N`, `operand → parent g`. Не unrestricted scan. Шумовые T/N не раздувают proof HUMAL/MORTAL.

`BoundVar` в UID-trace Ignition не появляется: фокус идёт на `G_FORALL`, ground N, pattern N, `G_IMPLIES` — не на переменную.

ProofSupport / materialization / refutation premise — контракт 0.14, NL его не меняет.

---

## 4. Формализация NL

Узкий лексический контур, не общий quantifier parser и не LLM-as-judge для scope.

### 4.1. Словари

В `SemanticConsolidator` (`formalization.py`):

| Класс | Примеры | Binding |
|---|---|---|
| Indefinite | кто-то, кто-нибудь, некто, что-то, … | `ExistentialBinding` |
| Negative existential | никто, ничто, никакой, nobody, … | `ExistentialBinding(negative=True)` |
| Universal determiner | все/весь/вся/каждый/любой (+ en all/every/each) | `UniversalBinding` |

Не используются NUMR/AMOUNT (`_split_quantified_nominal_actants`) — это не FOL.

### 4.2. Runtime-дескрипторы (не AH)

`ExistentialBinding`: parser-local `entity_ref`, `variable_id`, опциональный cross-turn якорь (`anchor_ref` должен быть `G`). `negative=True` нельзя совмещать с якорем.

`UniversalBinding`: `entity_ref`, `variable_id`, `restriction_lemma` (лемма класса), `negate_quantifier` («не все»).

Оба попадают в `CandidateIR`. Canonical UID на этом шаге не выделяется.

### 4.3. Порядок `prepare()`

1. Speech-act scoping.
2. Cross-turn «он» → предыдущий EXISTS-якорь (узко, не общая кореференция).
3. Temporal.
4. **`_rewrite_quantified_actants`** — отделить determiner, выставить handles и `negated`.
5. Validate + dependency order.
6. Собрать bindings: cross-turn EXISTS → fresh «кто-то» → nobody → universals (сквозная нумерация `variable_id`).

### 4.4. Как узнаём «все» / «не все» / «никто»

Сначала **operator tree по `source_text`** (`_source_quantifier_scope`):

- `не все|каждый|…` → kind `not_all`; если дальше ещё `не` → **ошибка** (не угадываем «не все … не …»).
- иначе `все|каждый|…` → kind `all`; `не` в хвосте → body negation («все N не P»).
- иначе квантора в тексте нет.

Затем mention актанта (`_parse_quantifier_mention`):

1. Одно слово из negative existentials, любая роль → `nobody`.
2. Универсалия **только SUBJECT** (чтобы «открыла все окна» не стала ∀ по подлежащему).
3. Mention `не все N` / `все N` / `каждый N`.
4. Fallback: Perception уже снял «все» с mention, остался класс (`сотрудники`), и в тексте determiner **стоит непосредственно перед этой NP**. Местоимение «он» + «все» позже в клаузе — не универсалия подлежащего.

«Все люди» не identity `m_все_люди`. Head лемматизируется (`люди` → `человек` через morphology), кванторное слово не актант. Handle: `UQ:…` или существующий `entity_ref`; у nobody — `NX:…`.

После rewrite mention = голова класса (`люди` / `сотрудники`), не «все люди».

### 4.5. Область отрицания (соседний §24.2)

Минимальный контракт на одном SUBJECT:

| Источник | `assertion.negated` после rewrite | Корень g |
|---|---|---|
| все N P | false (если не body-не) | `FORALL $0: CLASS → P` |
| все N не P | true | `FORALL $0: CLASS → NOT(P)` |
| не все N P | false (ведущее «не» снято) | `NOT(FORALL $0: CLASS → P)` |
| никто не P | false (concord снята) | `NOT(EXISTS $0: P)` |
| не все … не … | — | `CandidateValidationError` |

Нельзя в одном утверждении смешать nobody с ∀, «все» с «не все», несколько ролей у «не все».

Fail-closed: нет угадывания scope, нет LLM-judge.

---

## 5. Integration: запись в AH

`IntegrationService._integrate_plan`:

1. `BoundVar` на каждый existential/universal handle; смесь ∃ и ∀ в одном assertion — ошибка.
2. Quantified assertion → `_integrate_assertion(..., semantic_scope=QUANTIFIED, count_occurrence=False, existential_vars=bound_vars)`. Актант с handle **не** резолвится в M.
3. Если после rewrite `negated` — обернуть pattern в `g_NOT` (это «все не P», не «не все»).
4. Связные компоненты по общим переменным (как у EXISTS 0.24).
5. Несколько member-N → `AND`, затем кванторы снаружи, внутренние переменные ближе к телу.

**EXISTS (в т.ч. никто):**

```text
body = N | AND(N, …) | NOT(N)   # NOT только если body-negation, не для nobody
для каждой var снаружи: EXISTS(var, body)
если все var negative:  NOT(весь EXISTS-стек)
```

«Никто не спит» ≠ negated N и не `m_никто`.

**FORALL:**

```text
для каждой var (снаружи внутрь):
    CLASS = unary QUANTIFIED N(restriction_lemma, SUBJECT=$var)   # _ensure_class_pattern
    body = IMPLIES(CLASS, body)
    body = FORALL(var, body)
если negate_quantifier: NOT(FORALL)
```

Несколько универсальных актантов — вложенные `FORALL`, как nested EXISTS. «не все» только при одной переменной.

6. `ExperienceMapper`: `H` получает semantic_refs = ordinary assertions **без** QUANTIFIED N + conditionals + **корни EXISTS/FORALL**. Pattern-N в H как факты хода не кладутся.
7. ConflictEngine на QUANTIFIED N не смотрит как на ordinary asserted roots.

Cross-turn: nobody не публикуется как pronoun-якорь «он».

---

## 6. Примеры

### Кто-то спит

```text
N_SLEEP(SUBJECT=$0)     QUANTIFIED
g_EXISTS($0, N_SLEEP)
H.OBJECT = g_EXISTS      EXISTS_ASSERTED
нет m_кто-то
```

### Все люди смертны + Иван — человек

```text
N_HUMAN($0), N_MORTAL($0)     QUANTIFIED
g_IMPLIES, g_FORALL
H.OBJECT = g_FORALL

Иван — человек              ordinary N
цель Иван смертен           unasserted N того же T, что pattern
⇒ FORALL_IMPLIES_MP
```

Не список известных людей.

### Никто не спит + Анна спит

```text
NOT( EXISTS $0: SLEEP($0) )
нет m_никто
без свидетеля: внутренний EXISTS = UNKNOWN
Анна спит → EXISTS_WITNESS на внутреннем EXISTS
asserted NOT остаётся явной посылкой, не NAF
```

### Не все сотрудники пришли vs все не пришли

```text
не все … пришли     NOT( FORALL $0: CLASS($0) → CAME($0) )
все … не пришли     FORALL $0: CLASS($0) → NOT(CAME($0))
```

---

## 7. Вложенность и бюджет

Reasoner рекурсивен, отдельного лимита «не больше 8 кванторов» нет. Ограничение — `max_depth` / `max_expanded_states` запроса.

Примеры, которые 0.14 уже исполняет (API, не обязательно из NL):

```text
FORALL x: EXISTS y: FRIEND(x,y)
FORALL x: FORALL y: FRIEND(x,y) → KNOWS(x,y)
FORALL x: (HUMAN(x) ∧ EXISTS y: FRIEND(x,y)) → SOCIAL(x)
```

NL сейчас: ∀ только на SUBJECT с классом; несколько универсальных актантов в одном факте — nested FORALL; два unknown в одном факте — nested EXISTS.

---

## 8. Что намеренно нет

Нет в §23 / нет в 0.14 / не делали в NL-срезе:

- `COUNT` / `MOST` / «ровно трое» / «все кроме» как операторы;
- closed-world «нет контрпримера ⇒ ∀»;
- closed-world negation / NAF;
- новый canonical тип переменной / узел `q`;
- ∀ на объекте («открыла все окна»);
- forced interpretation неоднозначного scope;
- универсальный математический решатель, полная модальная логика;
- глобальный поиск по всей AH вместо индексов.

M2 (`IS-A`, `FOLLOW`, `CAUSE`) кванторы не переопределяют.

---

## 9. Тесты

Исполнение 0.14 — **не ослаблять**:

```text
tests/test_v4_quantified_logic_1400.py
```

witness / UNKNOWN без witness / тот же witness на повторной переменной / shadowing / `FORALL_IMPLIES_MP` / unasserted rule молчит / две ∀-переменные / запрет enumeration / persistence BoundVar / запрет BoundVar в factual N / ProofSupport + refute / nested EXISTS в антецеденте / Ignition без state у BoundVar / шум нерелевантных T / нет semantic cap на 8 FORALL.

NL:

```text
tests/test_v4_quantified_nl_2300.py
```

регрессия «кто-то» (как 0.24) / все люди + Иван → MP / «все» = rule не список / никто без `m_никто` / разные деревья «не все» vs «все не» / fail-closed «не все … не» / BoundVar без UID и runtime.

Регрессия EXISTS из NL 0.24:

```text
tests/test_v4_capability_frontier_2400.py
```

```text
PYTHONPATH=src:. python3 -m pytest \
  tests/test_v4_quantified_logic_1400.py \
  tests/test_v4_quantified_nl_2300.py \
  tests/test_v4_capability_frontier_2400.py
```

---

## 10. Короткая карта соответствия срезам

| Требование | Где выполняется |
|---|---|
| Каноника N/g/BoundVar без `q` | Core + 0.14 reasoner |
| Open-world EXISTS/FORALL | `formula.py` |
| MP от цели по индексам | `FORALL_IMPLIES_MP` |
| NL → те же g | `formalization.py` + `service.py` |
| Не менять контракт reasoner | inference не расширяли перебором домена |
| Неоднозначный scope | валидация, не угадывание |
