> Historical note: `failure_policy=empty` described below was removed in slice 12.11. Current perception fails explicitly and does not return an empty successful parse.

# Slice 10 — Adaptive Perception probes + English semantic predicates

Срез заменяет default single-call parser (`JSON/line/span`) на `adaptive_v1`.

## Почему

Реальный Qwen checkpoint стабильно смешивал schema/instruction с ответом даже при коротких line/span форматах. Поэтому LLM больше не обязана сериализовать составную структуру.

## Новый boundary

```text
source text
  ↓
ACT_TYPE probe
  ↓
PREDICATE_SPAN probe
  ↓
PREDICATE_SYMBOL probe (English)
  ↓
NEGATION / QUERY_MODE probes as needed
  ↓
NEXT_ACTANT ↔ ACTANT_ROLE repeated adaptively
  ↓
deterministic PerceptionResult builder
```

Каждый probe:
- stateless;
- имеет отдельный короткий system prompt-файл;
- отвечает одним enum / bit / token span / English symbol;
- валидируется до следующего этапа;
- при retry не получает предыдущий invalid output.

Если первый semantic act не может быть валидно собран и `failure_policy=empty`, semantic C/P mutation не выполняется, но исходная реплика всё равно остаётся experience event в H.

## Language policy

Архитектурный `S=<UID,R>` не меняется.

- Text Sensory создаёт/переиспользует lexical S для реально наблюдаемых русских wordforms.
- `PredicateCandidate.surface/evidence` остаётся на языке источника.
- `PredicateCandidate.normalized_hint` в adaptive_v1 — английский lowercase `snake_case` symbol.
- `TemplateResolver` использует normalized symbol как predicate S для T и не смешивает с ним русскую surface-форму.

Пример:

```text
"Яблоки бывают красные или зелёные"

surface predicate: "бывают"
semantic predicate S: "be"
T: be(SUBJECT, STATE)
```

## GUI

LLM dock теперь редактирует probe-файлы по отдельности через selector и показывает trace каждого решения: INPUT / RAW / ACCEPTED / VALIDATION ERROR.
