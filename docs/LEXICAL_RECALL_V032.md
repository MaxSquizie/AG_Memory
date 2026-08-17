# Lexical recall / readable H events — v0.32

## Что показал live-тест

В `ah_memory(20260817-165502).json` canonical `S_ПРОИЗОЙТИ` после пользовательского
`Что произошло в 1956 году?` получил сильное возбуждение (`x≈0.948`), но связанный
`T_ПРОИЗОЙТИ` оставался `x=0`. Это означало, что двухступенчатый lexical seed уже
работал, но возбуждение не входило дальше в семантическую память.

Также H event-instance в Workspace/«Все узлы» начинался с общего predicate
`высказать`, поэтому разные реплики визуально выглядели одинаково.

## v0.32

Добавлен односторонний structural lexical recall path:

```text
S -> T -> N -> actants
```

Canonical reference direction не менялся:

```text
T -> S
N -> T
```

Activation rules:

```text
S -> T amount = S.output
T -> N amount = T.output * N.w
N -> actant amount = N.output * N.w
```

Это feed-forward path без `N -> T -> S`, поэтому новый structural cycle не создаётся.

`EMBEDDED / CONDITIONAL / QUOTED` N не поднимаются напрямую как самостоятельные
lexical recall roots. Если N имеет `FALSE(N)`, lexical recall поднимает FALSE wrapper,
а не исторический positive N.

## Output при насыщении

`output` теперь представляет новый входной пакет до storage clamp:

```text
input_gain = max(0, x_raw - x_before)
output = min(x_max, input_gain)
```

Это сохраняет важный инвариант floating floor:

```text
z = 0 -> output = 0
```

но повторное сильное внешнее упоминание уже горячего S не теряет почти весь сигнал
только из-за малого headroom до `x_max`.

## H event projection

ACTIVE projection H `event_instance` теперь начинается с реального текста:

```text
реплика пользователя: Что произошло в 1956 году?
реплика агента: ...
```

Generic `высказать(...)` остаётся canonical structural template, но больше не скрывает
смысл реплики в Workspace/All Nodes/AgentContext. Полный semantic text доступен в
tooltip колонки «Смысл».

## Проверка на live memory

На сохранённом `S_ПРИВЕТ`:

```text
resolved S seed = 0.95
S -> T = 0.95
T -> N = 0.95 * 0.4 = 0.38
```

Через три causal ticks связанный `N_ПРИВЕТ` пересёк `Workspace threshold=0.35`.

## Tests

```text
366 passed
4 subtests passed
0 failed
```
