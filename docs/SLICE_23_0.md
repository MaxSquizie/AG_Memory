# Срез v0.23.0 — измеримый acceptance-контур M1–M5

## 1. Назначение

После v0.22.0 основные архитектурные механизмы v4 уже существуют в коде. Следующий этап — не добавлять новый когнитивный слой, а сделать требования хакатона измеримыми теми же формулами, по которым решение будет проверяться.

0.23.0 вводит диагностический контур:

```text
real parser / AH / Ignition / Reasoner output
→ metric observations
→ deterministic scorer
→ machine-readable report
```

Scorer не изменяет AH, не влияет на proof, не создаёт H-событий и не считается частью cognition runtime.

## 2. M1 — F1 ролей актантов

`score_m1_role_f1()` принимает multiset элементов:

```text
(case, predicate, role, normalized_value)
```

и считает для каждой роли:

```text
Precision_r
Recall_r
F1_r
```

`SUBJECT` и `OBJECT` получают вес 2, остальные роли — 1.

Для практического использования `score_m1_acceptance_bundle(run_dir)` читает уже существующий диагностический bundle:

```text
oracle_used.json
turn_001.json
turn_002.json
...
```

и извлекает gold/predicted role fillings без участия agent-generation.

### Не скрывать неоднозначность формулы постановки

В постановке напечатано:

```text
F1 = Σ_r w_r · F1_r
```

одновременно с порогом `0.6`. Буквальная сумма не ограничена единицей. Поэтому код не молча «исправляет» источник, а отдаёт два поля:

```text
weighted_sum_as_stated
weighted_mean
```

`weighted_mean` — нормированный weighted average в `[0,1]`, который CLI использует для проверки порога `0.6`. Для официальной сдачи формулу надо сверить с предоставленным оргкомитетом скриптом, если он появится.

CLI:

```text
python -m ah.cli --config config/default.toml m1-score <acceptance_runs/...>
```

В этом срезе новый LLM-run не подменялся синтетическими predictions: scorer готов, но фактическое M1 зависит от выбранной модели и скрытого зашумлённого корпуса.

## 3. M2 — ExplainScore

`score_m2_explainability()` реализует буквально:

```text
ExplainScore = (1/N) Σ [correct_i · (d_i / d_max) · trace_complete_i]
```

Для официальной формы default:

```text
N = 20
d_max = 6
```

Количество вопросов валидируется; для внутренних stress suites можно явно отключить `expected_count`.

Повторный внутренний M2 run текущей версии:

```text
40/40 PASS
AH = 153599 UID
all exact UID traces complete
elapsed ≈ 5.82 s for the complete internal run
internal ExplainScore40 = 0.6375
```

`0.6375` — не официальный M2 score: наши 40 кейсов имеют собственное распределение глубин, тогда как оргкомитет использует скрытые 20 вопросов.

## 4. M3 — committee-shape GC harness

`run_m3_gc_acceptance()` моделирует именно форму проверки из постановки:

1. создаётся `IgnitionEngine`;
2. после его запуска через обычный AH Core создаётся связная live-структура;
3. тем же публичным API создаётся 200 изолированных узлов;
4. выполняется максимум 50 обычных synchronous ticks;
5. считаются orphan before/after и сохранность live UID.

Test-only режим GC не используется.

На `config/default.toml`:

```text
initial_lifetime_ticks = 40
orphan before = 200
orphan after = 0
ticks until all orphan gone = 41
live before = 202
live after = 202
GC_efficiency = 1.0
live_preservation = 1.0
PASS
```

Почему удаление происходит на tick 41 при lifetime 40: birth tick равен 0, а eligibility и structural collection происходят после истечения окна иммунитета на следующем полном GC step. Требование `<=50` соблюдается.

CLI:

```text
python -m ah.cli --config config/default.toml m3-acceptance
```

## 5. Hard requirement: tick <= 500 ms на N=1000

Добавлен `run_tick_benchmark()` / CLI `tick-benchmark`.

Fixture специально не является пустым графом:

- один S;
- один T;
- много N одного T, создающих заметный `T → N` fanout;
- цепь FOLLOW между N;
- `N + L >= 1000`;
- S получает `QUERY_RECALL` seed и вычисление проходит через настоящий Ignition.

Текущий локальный результат:

```text
graph_units_n_plus_l = 1001
canonical_uids = 1504
warmup_ticks = 3
measured_ticks = 20
mean ≈ 30.01 ms
p95 ≈ 35.25 ms
max ≈ 50.18 ms
passes_500ms = true
```

Это локальный readiness benchmark. Нормативное значение на защите всё равно определяется референсным стендом оргкомитета.

CLI:

```text
python -m ah.cli --config config/default.toml tick-benchmark
```

## 6. M4 — сравнение AH и Vanilla RAG

`score_m4_comparison()` реализует:

```text
Δ_explainability = ExplainScore_AH - ExplainScore_RAG
Δ_hallucination = Hallucination_RAG - Hallucination_AH
```

Все входные доли валидируются как `[0,1]`.

0.23.0 намеренно не придумывает RAG baseline и не выдаёт M4 без реального запуска одной и той же Main LLM и одного корпуса в двух архитектурах.

## 7. M5 — устойчивость к классу модели

`score_m5_robustness()` реализует формулу постановки:

```text
RobustnessGain =
F1_AH(SLM) / F1_RAG(SLM)
-
F1_AH(LLM) / F1_RAG(LLM)
```

RAG denominators обязаны быть >0; четыре F1 должны лежать в `[0,1]`.

Сам эксперимент требует двух настоящих parser/model classes — локальной SLM <=8B и коммерческой модели верхнего эшелона — и поэтому не подменяется unit-тестовыми числами.

## 8. Что именно закрыто

К 0.23.0 есть единые исполняемые формулы для M1–M5 и локальные реальные harnesses для M2/M3/tick performance.

Не заявляются готовыми результаты, которые зависят от внешнего эксперимента:

```text
M1 hidden noisy corpus result
M4 Vanilla RAG comparison
M5 SLM vs commercial model
committee-reference tick timing
```

Это принципиально: диагностический код должен измерять систему, а не создавать «зелёные» числа сам.

## 9. Regression

Перед упаковкой:

```text
compileall: OK
pytest: 714 passed, 38 subtests passed
M2 dirty-150k: 40/40 PASS
M3 local committee-shape: PASS
1000 N+L tick benchmark: PASS locally
```
