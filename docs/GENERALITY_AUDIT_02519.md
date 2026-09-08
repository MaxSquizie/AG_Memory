# Аудит общности v0.25.19

## Метод

Production diff сопоставлен с полным архивом v0.25.18. Отдельно извлечены 44
уникальные ошибочные/ambiguous raw-формы из нового typo oracle и проверены как
целые кириллические tokens во всех `src/ah/perception/*.py`.

Результат: **0 точных вхождений**. Production не импортирует generator или data
corpus; это закреплено regression test.

## Основания алгоритмов

| Механизм | Общие признаки | Чего нет |
| --- | --- | --- |
| Candidate generation | DAWG states, DP edit row, distance bound | case IDs, corpus lookup, полный dictionary scan |
| Orthographic rank | четыре edit operations, keyboard topology, `ё/е` | таблица правильных ответов |
| OOV safety | casing, quoting, character class, dictionary membership | список имён/терминов |
| Morphology | POS/case/number/gender/person, agreement, clause/frame edges | verb/object word lists |
| Semantic rerank | только close shortlist и source clause context | chat LLM, rerank каждого token |
| Transition | oriented frames или semantic `TRANSITION_OPERATOR` span | список фазовых глаголов/наречий |

Russian keyboard adjacency — topology устройства ввода, а не предметная лексика.
Closed-class syntax tables, существовавшие до среза, не расширялись private
acceptance-фразами.

## Контрпримеры

- Title-cased unknown name и quoted/literal technical term остаются unchanged.
- Rare dictionary word остаётся `EXACT`.
- Context-free близкие варианты дают `AMBIGUOUS` и не коммитятся.
- Один и тот же recoverable object проходит в normal и inverted frames.
- При нескольких OOV ложный продуктивный predicate parse не подавляет настоящий
  finite correction.
- TIME/MANNER adverb не становится transition, пока role-probe не выделил его как
  non-actant operator cue.
- Modal parent блокирует повышение вложенного phase operand в world fact.

## Граница доказательства

Offline тесты проверяют index, ranking, constraints, provenance, fail-closed
policy, все 81 lexical oracle и полный старый suite. Фактическое качество
конкретной local embedding/perception модели требует отдельного живого acceptance
и не подменяется oracle-aware unit fixture.

