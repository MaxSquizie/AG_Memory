# Slice 25.24 — occurrence-level TemporalMode

## Граница изменения

`TemporalModeFormalizer` добавлен после построения predicate/frame structure и до
окончательной Integration. Он классифицирует конкретное occurrence, а не
лексический `S` или глобальный `T`:

```text
PerceptionResult
→ observable TIME/DURATION occurrence
→ morphology + frame narrowing
→ bounded semantic choice when required
→ STATE | EVENT | PROCESS | AMBIGUOUS
→ ordinary validated Integration
```

Уже построенный переход сохраняет `TRANSITION` и один из
`START/STOP/CONTINUE/AGAIN/NO_LONGER` без повторной классификации.

## Детерминированная часть

- nominal predication, result state и implicit state дают `STATE`;
- однозначный perfective profile даёт `EVENT`;
- assertion без наблюдаемого TIME/DURATION не получает декоративную метку;
- embedded, quoted и formula-scoped content не превращается в temporal evidence;
- несколько runtime alternatives обязаны согласиться по mode.

Остаточная смысловая развилка получает один UID-free fixed-choice probe. Ответ
ограничен `STATE/EVENT/PROCESS/AMBIGUOUS`; отсутствие решения завершает staging
fail-closed. Никакого marker dictionary или canonical write внутри формализатора
нет.

## Canonical contract

Режим входит в signature конкретного `N` и его indexed metadata. Поэтому два
occurrence одного `T` могут иметь разные temporal readings и не дедуплицируются как
одна ситуация. Synthetic result-state nodes получают `STATE`; переходы сохраняют
`TRANSITION`. Persistence использует существующий metadata path, новая разновидность
AH-узла не вводится.

## Acceptance

`data/acceptance_temporal_modes` содержит 46 заранее заданных cases/oracle:
устойчивые и неоднозначные STATE/EVENT/PROCESS, переходы, TIME/DURATION, inversion,
ellipsis, отрицательные и scoped случаи. Corpus подключён к CLI, GUI и semantic
oracle. Production-код не импортирует его тексты или ответы.

