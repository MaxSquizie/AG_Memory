# Поток A — semantic composition и сложные scopes

Рекомендуемая ветка: `agent/semantic-composition` от финального `main`.

## Исключительное владение

Поток может изменять:

```text
src/ah/perception/**
src/ah/inference/**
src/ah/integration/candidate_validator*.py
src/ah/integration/formalization.py
src/ah/integration/service.py
data/acceptance_semantic_composition/**
tests/test_*semantic_composition*.py
```

Он не изменяет `src/ah/documents/**`, `src/ah/projection/**` и document acceptance.
Общие README/version/audit files обновляются только после merge в `main`.

## Что сделать

### A1. Temporal NEVER

Реализовать отдельный source-semantic путь:

```text
никогда P
→ NOT(EXISTS t in relevant_past: P@t)
```

Обычный `NOT(P)` не использовать как эквивалент. Relevant-past anchor и scope
должны быть явными runtime/canonical formula components; отсутствие прошлых
occurrence остаётся `UNKNOWN`. Recognition строится через структурное сужение и
bounded semantic probe, без словаря выражений. Добавить acceptance/oracle на
словоформы и парафразы, inversion, ellipsis, scoped/modal/quoted negatives и
open-world inference.

### A2. Полные proposition query goals

Заменить fail-closed заглушки `semantic:OR_goal_not_supported` и
`semantic:XOR_goal_not_supported` на read-only typed goals. Query не должен
materialize запрошенную формулу или её branches. Реализовать open-world semantics:
OR допускает introduction/elimination по admissible supports, XOR означает ровно
одну истинную branch, а `UNKNOWN` не считается FALSE.

Тем же typed expression goal поддержать compound proposition content в matrix
queries вместо ограничения на один `REF`.

### A3. Композиция ортогональных scopes

Добавить единый рекурсивный GoalSpec compiler для комбинаций, которые сейчас
теряют оператор либо завершаются `*_not_supported`:

- quantified + modal;
- counterfactual + modal;
- counterfactual + quantified;
- counterfactual + typed relation;
- quantified + association endpoint/goal.

Композиция должна следовать уже построенному AST и runtime contexts, не распознавать
её повторно по словам. Нельзя понижать modal/counterfactual/quantified content до
ordinary factual `ExistsGoal`.

### A4. Полная модель сохраняемой неоднозначности

Канонизировать correlated alternatives, в которых одновременно меняются несколько
ролей, и nested scoped alternatives. Сохранять корреляцию вариантов: нельзя строить
декартово произведение независимых SUBJECT/OBJECT candidates. Расширить общий
clarification target за пределы entity-only ambiguity и повторно запускать
validation/atomic commit после ответа.

### A5. Quantified discourse и NP-internal relations

Расширить cross-turn existential continuation на несколько явно различимых
переменных без salience guess. Для actant с `BoundVar` сохранить source-grounded
NP-internal relation как formula-level structure вместо текущего пропуска. Не
создавать `m_UNKNOWN`, phrase-level `S` или обычный asserted `L` из scoped content.

## Обязательный acceptance/oracle contract

Каждый подпункт получает независимые cases и oracle до изменения production:

- positive, negative и `AMBIGUOUS/UNKNOWN`;
- разные словоформы/парафразы без их копирования в алгоритм;
- inversion и ellipsis interaction;
- scope pollution guards;
- canonical snapshot и persistence/reload, когда меняется сохранённая formula;
- inference result, exact rule/support и отсутствие query-side writes.

Definition of done потока: в production не остаются перечисленные выше
`*_not_supported` diagnostics, кроме явно design-limited §37, а corpus-specific
строки отсутствуют в algorithms/prompts.

