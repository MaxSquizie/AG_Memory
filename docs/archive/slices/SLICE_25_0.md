# Slice v0.25.0 — cross-turn existential discourse и adversarial M1 frontier

## Цель среза

После v0.24.0 acceptance расширяется не дополнительными вариациями уже закрытых M2/GC механизмов, а двумя зонами риска перед хакатоном:

1. продолжение истинно неизвестного участника через границу пользовательских сообщений;
2. отдельный M1 frontier corpus для прямо заявленных постановкой шумовых классов — опечаток, синтаксической инверсии и эллипсиса.

Срез не меняет canonical множество типов `AH=<S,C,P,H,L>` и не добавляет LLM fallback.

## 1. Cross-turn existential discourse anchor

### 1.1. Проблема

v0.24.0 корректно формализует внутри одного batch:

```text
Кто-то вошёл. Он сел.
```

как один existential scope без `m_UNKNOWN`. Но после atomic commit `DiscourseRef` исчезает как staging-state; следующее сообщение до v0.25.0 не имело безопасного runtime handle на ещё не идентифицированного участника.

### 1.2. Runtime representation

Добавлен `ExistentialDiscourseAnchor` в `InteractionContext`:

```text
existential_ref   -> canonical asserted g_EXISTS root
member_refs       -> quantified proposition members этого scope
variable_id       -> local BoundVar внутри scope
```

Anchor — только runtime context. Он не получает canonical UID, activation, Hebbian semantics или самостоятельный факт.

### 1.3. Продолжение scope

Для узкого детерминированного случая одно-переменной existential participant + совместимого номинативного местоимения:

```text
turn 1: Кто-то вошёл.
turn 2: Он сел.
```

получается:

```text
turn 1:
EXISTS $0: ENTER($0)

turn 2:
EXISTS $0:
  AND(
    ENTER($0),
    SIT($0)
  )
```

Старый H-occurrence остаётся связан со старой пережитой proposition, новый H-occurrence указывает на расширенный existential root. Старый canonical смысл не мутируется задним числом.

Третий turn может аналогично продолжить тот же participant:

```text
Он улыбнулся.
```

→ новый scope с тремя member propositions и тем же `$0`.

### 1.4. Fail-closed ограничения

Система не делает произвольный cross-turn bind, если:

- в предыдущем turn появились два одинаково допустимых однотипных неизвестных;
- existential scope содержит несколько переменных и местоимение не определяет, какую выбрать;
- canonical named-pronoun resolution уже даёт более конкретный referent.

При неоднозначности обычный `DiscourseRef` остаётся unresolved и atomic integration блокируется согласно существующему контракту.

Если после неизвестного участника появляется обычный именованный SUBJECT, его pronoun salience заменяет старый existential anchor для будущих turns.

### 1.5. Persistence

`existential_pronoun_anchors` сериализуются вместе с `InteractionContext` как runtime/session state. После reload новый turn может продолжить existential discourse без создания фиктивной сущности.

### 1.6. Не реализовано

Это не automatic late identity grounding. Случай:

```text
Кто-то вошёл.
Это был Иван.
```

пока не materialize/rewire старые quantified predicates на `m_ИВАН`. Полный late identity split также остаётся вне обязательного текущего контура.

## 2. M1 adversarial corpus

### 2.1. Причина

Основной broad200 acceptance хорошо покрывает valency, coordination, coreference, relative clauses, nested content, temporal/causal structures, conditionals, negation, passive/impersonal forms, queries, provenance, ambiguity и morphology pressure. Но отдельного систематического семейства для трёх прямо указанных в хакатонной постановке шумов M1 не было:

- опечатки;
- синтаксическая инверсия;
- эллипсис.

Новый corpus предназначен именно для обнаружения capability gap и не подгоняется под текущий parser.

### 2.2. Файлы

```text
data/acceptance_cases_m1_adversarial.txt
data/acceptance_oracle_m1_adversarial.json
```

Всего 36 `EXACT` cases:

| Family | Cases | Pressure |
|---|---:|---|
| `m1_typo_noise` | 10 | ошибки в predicate/entity/location/object surface |
| `m1_inversion` | 10 | свободный порядок слов и вынесение actants |
| `m1_ellipsis` | 10 | восстановление пропущенного predicate/shared frame |
| `m1_mixed_noise` | 6 | комбинации typo + inversion/ellipsis |

Oracle включает обязательные M1 роли `SUBJECT`, `OBJECT`, `LOCATION` и дополнительное давление на `RECIPIENT`, `TOOL`, `MATERIAL`, `TIME`, `DURATION`, `SOURCE`.

Для ellipsis ожидаются две semantic assertions, например:

```text
Иван прочитал книгу, а Мария — журнал.
```

→ `READ(Иван, книга)` + `READ(Мария, журнал)`.

Нельзя считать вторую клауза «непарсибельной» только потому, что текущий parser не умеет восстанавливать predicate.

### 2.3. Запуск

Из корня проекта:

```bash
PYTHONPATH=src python -m ah.cli semantic-acceptance
```

По умолчанию используются новые adversarial cases/oracle, а bundle пишется в `acceptance_runs_m1_adversarial`.

После реального прогона:

```bash
PYTHONPATH=src python -m ah.cli m1-score <run_dir>
```

`semantic-acceptance` использует обычный configured local-LLM perception pipeline. В CI/container без подключённой модели corpus проверяется только на целостность/alignment; численный M1 результат не выдумывается.

## 3. Acceptance

Новые regression cases:

- cross-turn pronoun продолжает один existential participant;
- three-turn existential accumulation;
- два равноправных unknown не создают arbitrary anchor;
- multi-variable existential не угадывается;
- named subject supersedes stale existential salience;
- runtime anchor переживает persistence/reload;
- anchored variable + новый unknown получают разные `BoundVar`;
- M1 corpus cases/oracle строго выровнены;
- family counts и role coverage фиксированы;
- ellipsis family всегда требует две assertions.

Финальный локальный regression run:

```text
733 passed
38 subtests passed
compileall OK
```

Readiness smoke после среза:

```text
M2 dirty/live-AH: 40 / 40 PASS
M3: 200 / 200 orphan removed; 202 / 202 live preserved
Tick benchmark: 1001 N+L units
  mean 33.91 ms
  p95  41.66 ms
  max  42.03 ms
  <500 ms PASS
```

Эти числа являются внутренним readiness, а не официальными скрытыми M1–M5 результатами оргкомитета.

## 4. Следующий практический шаг

Запустить `semantic-acceptance` на реальной локальной модели и вернуть полученный run bundle. Дальше исправлять не отдельные предложения, а крупнейшие систематические failure families. Наиболее вероятные фронты — typo normalization/morphology и predicate reconstruction при ellipsis. Формализация остаётся эволюционной: никаких sentence-specific keyword fallbacks.
