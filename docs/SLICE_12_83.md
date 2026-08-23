# v0.12.83 — manual document-level acceptance

## Задача

После достижения broad semantic acceptance `200/200` проверка одиночных фраз перестала быть достаточной. Следующий слой должен проверять, что AH строит связный canonical graph из нескольких абзацев текста и сохраняет причинно-следственную структуру между perception-вызовами.

По прямому требованию проекта генератор синтетических данных не используется. Ценность набора определяется качеством ручного текста и корректностью oracle, а не количеством автоматически созданных примеров.

## Корпус

`data/document_acceptance/texts/` содержит три вручную написанных документа по 7 абзацев:

1. `01_cooling_station.md` — причинная цепь глубины 6 от падения температуры до остановки насоса, с независимыми distractor-фактами.
2. `02_greenhouse_control.md` — причинная цепь глубины 6 от обесточивания коммутатора до снижения урожая; есть cross-paragraph coreference `Она` → `Анна` и независимые факты.
3. `03_archive_leak.md` — причинная цепь глубины 5 от засорения водостока до переноса коробок, затем два FOLLOW-перехода до проверки двери.

Абзацы не являются независимыми acceptance cases. Все абзацы одного документа имеют общий `scenario_id`, поэтому AH/Context/Ignition продолжаются внутри документа. Между документами восстанавливается baseline.

## Два уровня oracle

`data/document_acceptance/oracle.json` содержит:

- paragraph oracle — точные ожидаемые assertions, roles, CAUSE/FOLLOW и отсутствие query outcomes, через уже существующий `semantic_oracle`;
- final graph oracle — ключевые N, canonical actants, требуемые CAUSE/FOLLOW, минимальную глубину causal chain и forbidden causal links;
- `m2_questions` — typed expected proof paths, которые пока только валидируются структурно и не исполняются.

Таким образом, PASS документа требует одновременно:

```text
все абзацы semantic PASS
AND runtime errors == 0
AND все final canonical facts найдены однозначно
AND все требуемые causal/temporal links существуют в правильном направлении
AND запрещённые ложные causal links отсутствуют
AND causal chain достигает заданной глубины
```

## Runtime

`run_document_acceptance()` компилирует ручные документы во временный paragraph bundle и запускает обычный `run_acceptance_suite()`. Это сохраняет один и тот же production pipeline без отдельного «облегчённого» парсера для document tests.

После прогона final graph каждого scenario восстанавливается из `initial_ah.json + turn ah_diff`. Live AH пользователя не используется как oracle и после диагностики возвращается к pre-run state.

Результаты:

```text
data/document_acceptance_runs/<timestamp>/
  turn_*.json
  semantic_report.json
  document_report.json
  document_summary.txt
  document_<id>_matched_facts.json
```

## GUI

В «Диалог» добавлена кнопка `Document acceptance`. Она запускает 3 документа / 21 абзац через уже запущенный LLM backend и показывает отдельно document PASS и paragraph semantic PASS.

## M2 boundary

v0.12.83 сознательно не меняет inference engine и не объявляет document questions доказанными. `m2_questions` фиксируют будущий oracle заранее, до доработки M2, чтобы следующая реализация inference не могла подгонять ожидаемые цепочки постфактум.

Особенно важен `archive_leak`: его ожидаемый путь уже смешанный:

```text
CAUSE × 5 → FOLLOW × 2
```

Это будет естественным bridge-case от document formalization к M2 на реальной AH, построенной из текста.

## Tests

```text
501 passed
22 subtests passed
```
