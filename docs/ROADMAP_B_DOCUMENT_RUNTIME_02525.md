# Поток B — большие документы и iterative AH-only context

Рекомендуемая ветка: `agent/document-runtime` от финального `main`.

## Исключительное владение

Поток может изменять:

```text
src/ah/documents/**
src/ah/projection/source_scope.py
src/ah/projection/contracts.py
src/ah/diagnostics/document_acceptance.py
document-specific GUI/CLI adapters
data/document_acceptance/**
tests/test_document_*.py
tests/test_v4_source_projection_*.py
```

Он использует публичные Perception/Integration interfaces как зависимости и не
изменяет semantic parser, GoalCompiler, reasoner или Integration core. Общие
README/version/audit files обновляются только после merge в `main`.

## Что сделать

### B1. Structure-safe operational chunking

Не разрывать обычное предложение произвольным последним пробелом при достижении
`max_chunk_chars`. Выбирать source-grounded paragraph/sentence/clause boundary,
сохранять точные offsets и однократное покрытие raw source. Для одного чрезмерно
длинного semantic unit нужен явный bounded/fail-closed режим, а не тихая потеря
predicate/frame связи.

### B2. Whole-document semantic consolidation

Довести pre-commit batch transform до общего cross-unit контура:

- uniquely resolvable backward coreference связывается по глобальным offsets;
- несколько совместимых antecedents остаются `DiscourseRef` и блокируют commit;
- future mention не становится antecedent;
- causal/temporal/discourse relation на границе operational chunks сохраняет
  source direction и scope;
- любая поздняя ошибка откатывает весь DOCUMENT, включая identity/link changes.

Использовать существующий `integrate_external_batch(..., plan_transform=...)`;
второй canonical commit или document ontology не вводить.

### B3. Настоящий document acceptance runner

Текущий document diagnostic прогоняет подготовленные turns отдельно. Заменить/
дополнить его запуском одного `DocumentProcessor.ingest_text()` на документ и
оценкой заранее заданного oracle по итоговому canonical graph. Cases должны
покрывать cross-chunk identity, causal/temporal continuity, distractors,
ambiguity, future-reference negative и atomic rollback.

### B4. End-to-end iterative source projection

Подключить готовые `SourceProjectionCursor`/`SourceScopeSlice` к
`DocumentProcessor`:

```text
cursor
→ bounded AH-only slice
→ frozen AgentContext
→ controlled partial result
→ deterministic cursor advance
→ final aggregation and stop
```

Задать фиксированные budgets, максимальное число slices, повтор только
causal/temporal overlap из уже просмотренного контекста и точный `done` condition.
Main LLM не получает raw chunks, arbitrary AH access или право запросить память;
pipeline сам формирует каждый независимый frozen context.

### B5. Operator surface для continuation

Добавить CLI/GUI запуск и диагностику: номер slice, primary/overlap refs, cursor,
budget/stop reason, итоговый source coverage. Эти данные остаются runtime-only и
не входят в AgentContext rendered text или canonical H как execution log.

## Обязательный acceptance/oracle contract

- oracle задаётся до прогона и проверяет canonical refs/relations/source spans;
- один документ проходит один atomic semantic commit;
- summary input проверяется на отсутствие raw source/chunks;
- каждый semantic root становится primary ровно один раз;
- overlap не открывает future roots;
- deterministic rerun даёт тот же cursor sequence и projection ordering;
- overflow/failure не переходит в hidden RAG fallback.

Definition of done потока: `DocumentProcessor.summarize()` использует законченный
multi-slice protocol при overflow, а document acceptance больше не подменяет
whole-document pipeline набором независимых turns.

