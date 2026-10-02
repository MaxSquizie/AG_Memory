# Аудит общности v0.25.18

## Граница сравнения

Сравнение выполнено с полным архивом v0.25.17. Изменены два production/prompt-
файла: `adaptive_parser.py` и bounded-инструкция
`nonfinite_assertion_status.txt`. Проверены 114 добавленных строк.

331 уникальный текст broad, regression, adversarial и ellipsis acceptance
сопоставлен с добавленными строками: точных вхождений — **0**. Новых ветвей typo,
fuzzy matching, embeddings или Levenshtein — **0**.

## Основания решений

| Механизм | Используемые данные | Запрещённое основание |
| --- | --- | --- |
| Sequencing relation | proposition references, clause spans, ellipsis source families, число независимых roots | первый/последний event как догадка, case ID, имя или predicate |
| Очистка staging TIME | тип роли, зарегистрированный closed-class discourse marker, source evidence order, наличие prior assertion | удаление всех TIME или всех одинаковых слов |
| Nonfinite scope | уже ориентированная matrix/child пара и один bounded semantic choice | список фазовых глаголов, corpus answer table |

AST-инвентарь литералов условий находится в
`verification/02518/control_literals.json`. Новые ветви сравнивают topology,
cardinality, source offsets и protocol labels. Предметной лексики в условиях нет.

## Контрпримеры

- один root с каждой стороны сохраняет canonical `FOLLOW`;
- несколько parallel roots не получают произвольную пару;
- TIME после predicate остаётся обычным semantic actant;
- scoped nonfinite child остаётся embedded и в source, и в клонированном
  ellipsis-subgraph.

Тексты тестов не импортируются production-кодом и используют другую лексику.
