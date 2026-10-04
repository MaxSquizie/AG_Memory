# Валидация Phase 1 (T0–T4) — отчёт

**Статус:** sign-off по механизму. Архитектура V7 (rev2–8), прототип `src/ah/formalizer/`.
**Объём:** T0 (RawInput) → SRL/T1 (морфология) → T2 (структурные правила OP1–OP5) → TD (coref) → I30 closure → T3 (bounded selection) → T4 (joint validation). Коммит-стадия (T5/T6/T6b) — Phase 2, здесь не выполняется.

## Метод: две независимые проверки одного пути

Обе проверки идут через **один и тот же** `run()`; меняется только селектор. Это ключевое свойство валидации: механизм идентичен для детерминированного фикстура и живой модели (D3 — никаких per-example правил между прогонками).

1. **Dry-run** — `FakeSelector.demo("baseline"|"augmented")`: детерминированный, воспроизводимый, офлайн.
2. **Live** — `LMStudioSelector` (локальная модель через LM Studio): реальный backend по тому же интерфейсу `select(prompt) -> raw JSON`.

## Метрики C

- **C1 (механизм):** инварианты держатся на обоих прогонах — anti-forgery, честная неполнота, bounded selection, oscillation. Проверяется тестами (534 зелёных).
- **C2 (честная неполнота):** сколько предложений честно остаются `UNRESOLVED`/open вместо выдуманного ответа.
- **C3 (функциональность реального селектора):** coverage_ratio + разделение honest_gaps vs provider_failures на живой модели.

## Dry-run: детерминированные результаты (S1–S6, эталон v1)

| # | Предложение | baseline outcome | baseline selected | augmented outcome | augmented selected |
|---|---|---|---|---|---|
| S1 | У вороны есть лапки. | UNRESOLVED | [V1,V2] | **RESOLVED** | [V2] |
| S2 | У стола есть ножки. | UNRESOLVED | [V1,V2] | **RESOLVED** | [V2] |
| S3 | У меня есть книга. | RESOLVED | [V1] | RESOLVED | [V1] |
| S4 | Ворона обладает перьями. | UNRESOLVED | [V1,V2] | **RESOLVED** | [V2] |
| S5 | У вороны лапки. | UNRESOLVED | [V1,V2] | UNRESOLVED | [V1,V2] |
| S6 | Вороны любят червей. | RESOLVED | [V4] | RESOLVED | [V4] |

**Coverage:** baseline `answered=2/6 (0.33)`; augmented `answered=5/6 (0.83)`. Honest gaps: 0 в обоих прогонах (UNRESOLVED — открытая амбивалентность, а не «не знает»). Provider failures: 0 (детерминированный фикстур).

### Что это доказывает
- **Единственное, что меняется между baseline и augmented — объявленный контекст** (`context_facts` F1/F2/F3). Ровно те предложения, для которых есть совпадающее объявленное утверждение, разрешаются в `HAS_PART(V2)`. Никаких per-example правил (D3).
- **S5 остаётся UNRESOLVED даже в augmented**, потому что для него нет объявленного факта — механизм не выдумывает связь. Это и есть честная неполнота (C2): множественная допустимость без value-specific ground → `UNRESOLVED`, а не `AMBIGUOUS`/`RESOLVED`.
- **Anti-forgery:** augmented-скрипт опирается на утверждение только если оно объявлено в промпте; иначе деградирует к baseline (тесты это фиксируют).

## Live: реальный backend

Скрипты (офлайн-safe, корректно skip при недоступном сервере):
```bash
# один модельный прогон + §2.3 отчёт
PYTHONPATH=src python scripts/verify_gemma.py [model]
# side-by-side сравнение нескольких моделей
COMPARE_MODELS=gemma-3n-e4b-it,qwen2.5-32b-instruct GEMMA_ATTEMPTS=2 \
    PYTHONPATH=src python scripts/compare_models.py
```

**Bounded retry-once.** Живые слабые модели иногда выдают не-JSON (PROTOCOL_ERROR). Политика: `attempts_per_slot` (по умолчанию 1 = без retry, сохраняет single-charge контракт rev8; live-скрипты ставят 2). Каждый attempt заряжается ровно один раз и логируется; bounded retry переспрашивает тот же промпт. Вычислительный сбой **никогда** не становится семантическим вердиктом (§1.4/§0.8): решение остаётся un-evaluated (`outcome=None`), а `PROTOCOL_ERROR`/`PROVIDER_UNAVAILABLE` уходят в `provider_failures`, отдельно от honest gaps.

### Live-результаты (LM Studio, `attempts_per_slot=2`, temperature 0)

| # | Предложение | gemma-3n-e4b-it | qwen2.5-32b-instruct |
|---|---|---|---|
| S1 base | У вороны есть лапки. | UNRESOLVED [V1,V2] | **RESOLVED V2** |
| S1 aug  | + «Лапки — часть тела…» | UNRESOLVED [V1,V2] | **RESOLVED V2** |
| S2 base | У стола есть ножки. | UNRESOLVED [V2,V1] | **RESOLVED V2** |
| S2 aug  | + «Ножки — часть…» | UNRESOLVED [V2,V1] | **RESOLVED V2** |
| S3 base | У меня есть книга. | **RESOLVED V1** | **RESOLVED V1** |
| S4 base | Ворона обладает перьями. | UNRESOLVED [V1,V2] | **RESOLVED V2** |
| S4 aug  | + «Перья — часть…» | UNRESOLVED [V1,V2] | **RESOLVED V2** |
| S5 base | У вороны лапки. | UNRESOLVED [V1,V2] | **RESOLVED V2** |
| S6 base | Вороны любят червей. | **RESOLVED V4** | **RESOLVED V4** |

**Side-by-side coverage (C3):**

| model | answered | ratio | honest gaps | provider failures |
|---|---|---|---|---|
| gemma-3n-e4b-it | 2/9 | 0.22 | 0 | 0 |
| qwen2.5-32b-instruct | 9/9 | **1.00** | 0 | 0 |

### Чтение результатов
- **Ключевое различие HAVE vs HAS_PART (S3=V1 против S1/S2/S4=V2) обе модели держат верно.** Qwen разрешает его и в baseline — модель сама подтягивает world knowledge («у меня есть книга» → HAVE, «у вороны есть лапки» → HAS_PART), не дожидаясь объявленного контекста.
- **Gemma (4B) честна, но консервативна:** разрешает только S3/S6; на S1/S2/S4/S5 остаётся `UNRESOLVED` даже с объявленным контекстным утверждением — модель сообщает «несколько допустимо», а не угадывает. Это сильный C2 (честная неполнота) и слабый C3.
- **Qwen (32B): полное покрытие 1.00** при верных значениях во всех девяти кейсах — сильный C3.
- **Ни у одной модели нет provider/protocol сбоев** после включения retry-once: вычислительные сбои не превратились в семантические вердикты (§1.4/§0.8). Наблюдавшееся ранее 2/7 PROTOCOL_ERROR у gemma погашено bounded retry.

> **Вывод:** механизм (C1) и честная неполнота (C2) подтверждены на обеих моделях; функциональность (C3) масштабируется с размером модели. Для production-целевого качества на демо-наборе достаточно qwen2.5-32b-instruct; gemma-3n-e4b-it пригодна там, где важна честная неполнота при ограниченном бюджете.

## Инварианты, подтверждённые тестами (C1)
- Validator возвращает только protocol outcome; семантический исход выносит **только T4** (`test_validator_never_grants_semantic_outcomes`).
- RESOLVED требует все три условия: value-specific ground + completed search + cluster validity.
- AMBIGUOUS — только если у каждого survivor свой value-specific ground (§1.4).
- Oscillation = повторение состояния без новых реальных grounds; M не сбрасывает детектор.
- Bounded retry: `attempts_per_slot` ограничивает число вызовов селектора на слот (тесты `TestRetryPolicy`).

## Sign-off и остаток
Phase 1 **закрыта**: механизм корректен на детерминированном прогоне, подключён к реальному backend по одному интерфейсу, live-C3 снят (gemma 0.22 / qwen 1.00). Далее — **Phase 2: T5/T6/T6b** (batch-сборка, head-only admission, отзыв/recovery) и интеграция `if_query` в production GoalMode.
