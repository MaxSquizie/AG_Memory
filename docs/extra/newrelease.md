# Что изменилось после v0.25.13 и как всё прогнать

База — коммит `3b38557` (релиз v0.25.13). Каталог `docs/extra/` сознательно вне git.

Срез: GC (M3), изолированный Vanilla RAG (M4), кванторы §23 из русского текста, и вынос RAG из `src/` в пакет `rag/`.

Команды ниже — из корня репозитория. Не утверждение «весь pytest зелёный».

```text
export PYTHONPATH=src:.
```

---

## Vanilla RAG больше не в `src/`

RAG — отдельный baseline, он не должен жить внутри AH Core.

```text
rag/                 изолированный пакет, не импортирует AH и не пишет память
  vanilla.py         чанки, cosine retrieve, генерация по выдержкам
  embeddings.py      протокол эмбеддера + FakeEmbeddingClient для pytest
  __main__.py        короткая справка: python -m rag

src/ah/diagnostics/m4_acceptance.py   сравнение AH vs RAG и запись бандла
src/ah/llm/embeddings.py               живые эмбеддинги Ollama / LM Studio
tests/test_m4_rag_baseline.py          офлайн-проверки без сети
data/m4_questions.json               14 вопросов корпуса
data/document_acceptance/oracle.json  тексты документов (те же, что M2)
data/m4_runs/                        появляется после живого m4-acceptance
```

Индекс на диск заранее не кладётся: чанки и векторы собираются на прогоне. `builtin_process` для эмбеддингов закрыт.

Проверка, что пакет на месте:

```text
PYTHONPATH=src:. python3 -m rag
PYTHONPATH=src:. python3 -m pytest tests/test_m4_rag_baseline.py
```

---

## Как прогнать все метрики

Нужны: Python ≥ 3.12, `pymorphy3`, из корня репозитория. Для M4/M5 ещё живой LLM-бэкенд.

### M1 — F1 ролей актантов

По готовому бандлу `acceptance_runs` (не запускает новый LLM-диалог):

```text
Precision_r, Recall_r, F1_r по ролям
SUBJECT и OBJECT вес 2, остальные 1
weighted_sum_as_stated   как в постановке, может быть > 1
weighted_mean            нормированное среднее в [0,1]; CLI-порог 0.6
```

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m1-score data/acceptance_runs/<каталог>
```

Бандл должен содержать `oracle_used.json` и `turn_*.json`. Официальный балл — только на скрытом шумном корпусе комиссии.

Офлайн-регрессия парсера/ролей (не балл комиссии):

```text
PYTHONPATH=src:. python3 -m pytest tests/test_m1_adversarial_corpus_2500.py
```

### M2 — ExplainScore (внимание / следы)

```text
ExplainScore = (1/N) Σ correct_i · (d_i / d_max) · trace_complete_i
официально N=20, d_max=6; внутренний harness может быть другим N
```

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m2-acceptance
```

Это внутренний контур на живом/грязном AH (≥150k UID в постановке среза), без LLM и без мутации live-AH. Цифра не заменяет скрытые 20 вопросов оргкомитета.

Документный граф корпуса (не M2-балл, но тот же oracle, что у RAG):

```text
PYTHONPATH=src:. python3 -m pytest tests/test_m2_goal_directed_acceptance_v039.py tests/test_m2_operator_runner_v040.py
```

### M3 — сборщик мусора

Раньше сироты могли жить вечно: пульс пейсмекера и пол затухания считались активностью. Теперь пейсмекер-only и decay-floor **не** продлевают TTL. Отсрочка — Workspace (`x > t`) или настоящее (не пейсмекерное) возбуждение.

Форма комиссии: Ignition → живая структура + 200 изолированных узлов → ≤50 обычных тиков (с ν).

```text
GC_efficiency      доля собранных сирот
live_preservation  сохранность живых UID
orphan before/after, ticks until orphans gone
```

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m3-acceptance
```

Бандл: `data/m3_runs/`. На `config/default.toml` ожидаемый контур: orphan after = 0, live preservation = 1, укладка сирот около tick 41 при lifetime 40.

Офлайн:

```text
PYTHONPATH=src:. python3 -m pytest tests/test_hackathon_metrics_v023.py tests/test_v4_lifecycle_dsl_2200.py
```

### Tick ≤ 500 ms (N+L ≥ 1000)

Не M1–M5, но тот же диагностический контур.

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml tick-benchmark
```

Смотреть `passes_500ms`, mean / p95 / max. Норматив защиты — стенд комиссии, не наш ноутбук.

### M4 — AH vs Vanilla RAG

Одна и та же Main LLM (Ollama или LM Studio), один корпус, две архитектуры. RAG не пишет в AH.

```text
ExplainScore_AH, ExplainScore_RAG     та же формула, что M2, по 14 вопросам
Hallucination_AH / _RAG             ответ не UNKNOWN и не опирается на след/чанки
Δ_explainability = ExplainScore_AH − ExplainScore_RAG
Δ_hallucination  = Hallucination_RAG − Hallucination_AH
```

Подготовка:

1. Поднять Ollama или LM Studio с моделью генерации и эмбеддингов.
2. В `config/ollama.toml` или `config/lmstudio.toml` задать `backend`, модель чата и при необходимости `ollama_embed_model` / `lmstudio_embed_model` (пустое = модель чата).
3. `config/default.toml` с `builtin_process` для M4 **не** подходит: эмбеддинги fail-closed.

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/ollama.toml m4-acceptance
PYTHONPATH=src:. python3 -m ah.cli --config config/lmstudio.toml m4-acceptance
```

Бандл `data/m4_runs/`: `summary.json`, `report.txt`, `ah_cases.jsonl`, `rag_cases.jsonl`, `index_manifest.json` (без векторов).

Это каркас измерения. Цифры из pytest / FakeEmbeddingClient **не** официальный балл оргкомитета.

### M5 — устойчивость к классу модели

Scorer есть, своего двухмодельного прогона в CLI нет.

```text
RobustnessGain = F1_AH(SLM)/F1_RAG(SLM) − F1_AH(LLM)/F1_RAG(LLM)
```

Нужны четыре F1 ∈ [0,1], знаменатели RAG > 0: локальная SLM ≤8B и коммерческая модель верхнего эшелона, один корпус, AH и RAG. После эксперимента:

```python
from ah.diagnostics import score_m5_robustness
score_m5_robustness(ah_slm_f1=..., rag_slm_f1=..., ah_llm_f1=..., rag_llm_f1=...)
```

Не подставлять unit-тестовые числа как результат хакатона.

---

## Сводка CLI

```text
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m1-score data/acceptance_runs/<каталог>
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m2-acceptance
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml m3-acceptance
PYTHONPATH=src:. python3 -m ah.cli --config config/default.toml tick-benchmark
PYTHONPATH=src:. python3 -m ah.cli --config config/ollama.toml m4-acceptance
PYTHONPATH=src:. python3 -m rag
```

---

## Релевантный pytest этого среза

```text
PYTHONPATH=src:. python3 -m pytest \
  tests/test_m4_rag_baseline.py \
  tests/test_hackathon_metrics_v023.py \
  tests/test_v4_lifecycle_dsl_2200.py \
  tests/test_v4_quantified_nl_2300.py \
  tests/test_v4_capability_frontier_2400.py \
  tests/test_v4_quantified_logic_1400.py
```

---

## Кванторы §23

Reasoner уже умел `FORALL` / `EXISTS`, BoundVar без UID, open-world. Из текста теперь:

- «Кто-то спит» → `EXISTS` (как в 0.24), без `m_кто-то`
- «Все люди смертны» → asserted `FORALL $0: CLASS($0) → P($0)`; частный случай через `FORALL_IMPLIES_MP`
- «Никто не спит» → `NOT(EXISTS …)`, без `m_никто`
- «Не все N P» ≠ «Все N не P»; «не все … не …» не угадывается

Нет: COUNT/MOST, «все кроме», ∀ перебором известных объектов, узел `q`.
