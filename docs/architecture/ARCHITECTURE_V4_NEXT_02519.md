# Точка продолжения архитектурного аудита после v0.25.19

## Закрытые границы

- §18.8 `Lexical Recovery` — **CLOSED** для заявленного deterministic/indexed +
  optional-local-rerank контракта. Ambiguity остаётся допустимым safety outcome,
  а не незакрытым дефектом.
- §18.9 ellipsis — **CLOSED** на зафиксированной acceptance-границе 166 cases;
  universal natural-language coverage не заявляется.
- §19.4 Late split — **DEFERRED** самой архитектурой.
- §20.1–20.5 — ранее закрытый temporal/state runtime сохраняется.
- §20.6 `START/STOP/CONTINUE/AGAIN/NO_LONGER` — **CLOSED end-to-end**:
  source classification, occurrence mode, wrapper integration, timed state effects,
  persistence/state tests и scope-negative regression.

## Следующая строка — §20.7

`TemporalMode` уже является occurrence-level полем, Integration не переносит его
на глобальный `T`, а transition source-path выставляет `TRANSITION`. Однако общий
source classifier для различения `STATE / EVENT / PROCESS` по
morphology/aspect/tense ещё не доказан end-to-end. Поэтому §20.7 имеет статус
**PARTIAL**, а не автоматически CLOSED.

Следующий вертикальный срез должен:

1. инвентаризировать места, где mode реально влияет на persistence/reasoning;
2. не классифицировать mode там, где от него нет наблюдаемого эффекта;
3. построить deterministic narrowing из morphology/aspect/tense и bounded probe
   только для остаточной неоднозначности;
4. доказать, что один `T` допускает разные occurrence readings;
5. добавить negative cases и проверить отсутствие новых semantic word lists.

После §20.7 аудит продолжается последовательно по §21. Существующие реализации
Ignition/Workspace/plasticity дают сильные кандидаты на `CLOSED`, но статус каждой
строки должен подтверждаться исполняемым тестом, а не историческим названием
модуля. §37 и явные non-goals §38 остаются вне обязательного backlog; открытые
вопросы §36 требуют отдельного выбора политики.

