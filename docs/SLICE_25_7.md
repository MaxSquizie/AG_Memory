# Slice 25.7 — Ellipsis frame completion

## Причина среза

`acceptance_ellipsis` (22 cases) показал 0/22 при полностью исправном runtime. Первый case:

`Иван купил книгу, а Мария журнал.`

до среза создавал один clause и один assertion, в который `Мария` и `журнал` попадали как лишние роли первого BUY-frame. Значит gap находился до Integration: отсутствовало отдельное runtime представление неполной координированной clause.

## Что изменено

### 1. Clause segmentation

Для явно координированного zero-predicate tail parser теперь строит отдельный `ClauseCandidate`:

```text
CL1: Иван купил книгу
CL2: а Мария журнал
```

CL2 получает runtime-only `ellipsis_kind` и `ellipsis_source_clause_id`.

### 2. Marker modes

Поддерживаются:

- `FRAME` — `Иван купил книгу, а Мария журнал`;
- `PROPOSITION_NEGATION` — `Иван купил книгу, а Мария — нет`;
- `PROPOSITION_CONFIRMATION` — `Иван купил книгу, и Мария тоже`.

`нет` может иметь словарный POS=PRED, но после доказанного proposition-ellipsis shell он исключается только из runtime predicate queue. Морфологическая информация токена сохраняется.

### 3. Frame completion

После обычного разбора antecedent assertion target clause разбирается в узком role-space antecedent frame. Target fillers заменяют fillers тех же ролей; отсутствующие роли наследуются.

Пример:

```text
BUY(SUBJECT=Иван, OBJECT=книга)
+
CL2(SUBJECT=Мария, predicate missing)

=>
BUY(SUBJECT=Мария, OBJECT=книга)
```

Для `— нет` второй assertion получает `negated=True`.

### 4. Safety boundary

- reconstruction не создаёт UID и не пишет AH напрямую;
- role whitelist берётся из уже разобранного antecedent frame;
- при отсутствии overt replacement target assertion не создаётся;
- отрицательный antecedent + `— нет` пока fail-closed как scope-неоднозначный случай;
- scope/status/quoted/temporal occurrence metadata наследуются от antecedent, а не сбрасываются в factual по умолчанию.

## Lexical Recovery

Основной архитектурный документ дополнен отдельным контрактом noisy-token recovery:

```text
Levenshtein candidate generation
→ contextual embedding rerank
→ morphology compatibility
→ EXACT | CORRECTED_HIGH_CONFIDENCE | AMBIGUOUS | UNKNOWN_TOKEN
→ ordinary formalization
```

Embedding similarity не является proof lexical identity и не создаёт semantic fact.

## Regression

`746 passed, 38 subtests passed`.

Реальный `acceptance_ellipsis` требует прогона на машине с подключённой LM Studio, потому что target role classification остаётся bounded semantic probe там, где morphology не оставляет единственного варианта.
