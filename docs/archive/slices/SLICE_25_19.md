# Slice 25.19 — lexical recovery before commitment

## Архитектурная граница

Lexical noise обрабатывается до того, как morphology/semantic parser получают
право формировать canonical identity. При этом слой остаётся частью perception
staging, а не альтернативным parser или способом записи знания.

| Этап | Выход | Что не разрешено |
| --- | --- | --- |
| OOV classification | exact/protected/repairable token | считать каждый OOV опечаткой |
| Indexed generation | близкие dictionary surfaces | полный перебор словаря |
| Orthographic rank | weighted edit score | semantic commitment |
| Morphology/frame constraints | grammatical shortlist | роль из позиции слова |
| Optional embeddings | score малого close shortlist | generative correction |
| Decision | exact/corrected/ambiguous/unknown | forced guess |

`SourceToken.text` после решения — runtime semantic surface;
`SourceToken.provenance_text`, offsets и `EvidenceSpan.text` остаются исходными.
Поэтому исправленная форма может стать обычной лексической identity через
существующий Formalization/Integration, но ошибочная raw-форма не регистрируется
как её нормальная словоформа.

## Multi-error context

Pymorphy умеет продуктивно анализировать OOV. Такой анализ сохраняется как
гипотеза текущего token, но не считается надёжным finite head для ограничения
соседней опечатки. Finite correction дополнительно проверяет agreement с явно
выраженным dictionary-known nominative participant. Это локальное правило
устраняет cascading error при нескольких опечатках и не зависит от конкретного
глагола или порядка актантов.

## Transition continuation

Тот же срез завершает начатую в v0.25.18 границу `SCOPED_EVENT`:

```text
source frame topology
→ scoped matrix/operand or explicit operator cue
→ bounded transition label
→ occurrence-level TRANSITION
→ g_OP(P)
→ StateTracker only with TIME
```

Protocol labels — машинный интерфейс, а не новые canonical predicates. Они нужны,
чтобы Python валидировал конечную семантику и применял различающиеся state rules,
не извлекая свободный текст модели.

## Проверяемые safety-инварианты

- Lexical Recovery не вызывает `backend.generate` и не пишет AH/H.
- `AMBIGUOUS` останавливает parser до semantic probes.
- Names/terms/acronyms/codes не исправляются только по близости.
- Frequency имеет меньший вес, чем grammar/structure.
- Embedding failure сохраняет ambiguity.
- Inversion не меняет role map.
- Nested nonasserted phase content не становится factual transition.
- Переход без TIME не создаёт time entity/state interval.
- Обычное наречие не порождает отдельный transition-probe: сначала оно должно
  быть явно классифицировано как не-актантный transition cue.

