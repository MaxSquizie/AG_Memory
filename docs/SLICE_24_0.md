# Slice 24.0 — capability-frontier acceptance: true unknowns and functional conflicts

## Цель среза

После появления измерительного контура M1–M5 следующий шаг намеренно направлен не на добавление ещё одного scorer-а, а на расширение acceptance в местах, где архитектура уже задавала требование, но реализация ранее явно оставляла capability gap.

В v0.24.0 закрыты два таких разрыва:

1. истинно неизвестный участник discourse больше не обязан материализоваться как фиктивная semantic identity;
2. Conflict Engine умеет детерминированно фиксировать конфликт двух положительных propositions для явно зарегистрированного функционального predicate/slot.

Оба изменения сохраняют основную границу v4: runtime staging не становится новым canonical node kind, а специальные semantics включаются только при наличии явного машинного контракта.

## 1. Истинно неизвестный участник → EXISTS

### Проблема

До этого `DiscourseRef` позволял не угадывать antecedent местоимения, однако случай вида:

`Кто-то вошёл. Он сел.`

не имел полноценного canonical lifting в existential formula. Создание `m_КТО-ТО`, `m_ОН` или общего `m_UNKNOWN_PERSON` нарушало бы v4 identity semantics: неизвестный участник не является доказанной устойчивой identity.

### Runtime contract

`CandidateIR` получил `existential_bindings`, составленный из runtime `ExistentialBinding`:

- `entity_ref` — batch-local handle;
- `variable_id` — локальный номер переменной;
- `sort` — `ENTITY`.

`ExistentialBinding` не является AH-узлом, не имеет canonical UID и исчезает после integration.

Текущий deterministic recognizer намеренно узкий: он поднимает только явно indefinite-pronoun anchors (`кто-то`, `кто-нибудь`, `кто-либо`, `некто`, `что-то`, `что-нибудь`, `что-либо`, `нечто` и английские прямые аналоги), если perception уже дал им batch-local `entity_ref`. Более общая семантика generalized quantifiers здесь не заявляется.

### Canonical integration

Assertion, содержащий existential `entity_ref`, материализуется как scoped pattern `N`:

- `semantic_scope = QUANTIFIED`;
- соответствующий actant = `BoundVar`, а не `Ref(M)`;
- pattern N не считается ordinary factual premise сам по себе.

Assertions, соединённые общим неизвестным участником, объединяются в один existential body. При необходимости body строится через `AND`, затем оборачивается в `EXISTS`.

Пример:

```text
Кто-то вошёл. Он сел.

EXISTS $0:
  AND(
    ENTER($0),
    SIT($0)
  )
```

Два независимых неизвестных, не связанных общим assertion, остаются двумя независимыми existential scopes. Два неизвестных actant в одном assertion дают вложенные `EXISTS`.

H occurrence сообщения указывает на asserted existential root, а не на каждый quantified pattern как отдельный factual statement.

### Delayed discourse

Существующий `DiscourseRef` может до atomic commit связать последующее местоимение с batch-local existential anchor. Это позволяет сохранить один и тот же `BoundVar` для `Кто-то ... Он ...`, не создавая промежуточный semantic M.

Cross-turn pronoun salience cache игнорирует `BoundVar`: локальная quantified variable не должна становиться устойчивым cross-turn entity anchor.

## 2. Positive-positive FUNCTIONAL conflict

### Проблема

Polarity conflict `P / NOT(P)` существовал с v0.15.0. Но два положительных утверждения могут быть несовместимы только при дополнительной schema semantics. Например, если `COLOR(subject, value)` явно объявлен функциональным по роли `OBJECT`, то одновременно asserted:

```text
COLOR(lamp, red)
COLOR(lamp, green)
```

при одинаковом контексте образуют conflict. Для обычного произвольного predicate такого вывода делать нельзя.

### Explicit schema contract

`InferenceSchema` расширен полем:

```text
functional: bool
functional_role: ActantRole | None
```

`functional=True` без `functional_role` недостаточен для positive-positive conflict: движок не угадывает, какой slot является единственным значением.

### Conflict conditions

Два N конфликтуют как `FUNCTIONAL`, только если одновременно:

- оба asserted;
- один canonical T;
- один domain;
- schema явно `functional=True`;
- задан `functional_role`;
- значения всех остальных ролей совпадают;
- значение functional role различается.

Поэтому:

```text
COLOR(lamp, red, LOCATION=A)
COLOR(lamp, green, LOCATION=B)
```

не конфликтуют: контекст различается.

Третье конкурирующее значение расширяет уже существующий `k_CONFLICT`, а не создаёт набор pairwise conflict groups.

Как и polarity conflict, FUNCTIONAL conflict не выбирает winner по recency, occurrence count, x или w. Пока минимум два участника остаются asserted/admissible, их нельзя использовать как безусловные premises обычного proof.

`InferenceSchemaRegistry` в bootstrap теперь один и тот же для IntegrationService и InferenceEngine, чтобы schema semantics была согласована между integration и reasoning.

## 3. Acceptance

Добавлен `tests/test_v4_capability_frontier_2400.py` с проверками:

1. `Кто-то вошёл. Он сел.` → один `EXISTS`, один `BoundVar`, без fake M;
2. unresolved pronoun связывается с existential anchor до atomic commit;
3. два независимых неизвестных → два scopes;
4. два unknown roles в одном fact → nested EXISTS;
5. explicit functional predicate → positive-positive conflict;
6. различный non-value context не даёт ложный conflict;
7. третье значение расширяет одну conflict group;
8. existential form переживает JSON persistence/reload;
9. functional conflict переживает reload и остаётся inadmissible для proof.

Полная regression v0.24.0:

```text
723 passed, 38 subtests passed
compileall OK
```

## 4. Что намеренно не заявлено

Срез не утверждает, что закрыты:

- generalized quantifiers (`все кроме`, `ровно трое`, `большинство` и т.п.);
- произвольные indefinite NP вроде `некий инженер` без соответствующего semantic analysis;
- автоматическое распознавание функциональности predicate из естественного языка;
- schema-level mutual exclusion произвольных positive values без явного contract;
- late identity split.

Это остаётся пространством следующих capability-frontier acceptance cases.
