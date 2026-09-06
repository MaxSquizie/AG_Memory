# Срез v0.16.0 — граница формализации, пакетная консолидация и атомарная интеграция

## Назначение

Версия 0.16.0 закрывает архитектурную границу между восприятием текста и канонической АГ-памятью. До этого `PerceptionResult` мог почти сразу переходить в Integration; теперь весь вход сначала существует как проверенный runtime-пакет, а каноническая запись начинается только после завершения консолидации.

Целевой путь:

```text
PerceptionResult / несколько окон документа
→ FormalizationBatch
→ нормализация локальных идентификаторов и source spans
→ SemanticConsolidator
→ CandidateIR
→ MutationPlan
→ полная проверка
→ AHCore.transaction()
→ единый canonical commit
```

Новые структуры не являются типами АГ-памяти и не расширяют `q`. Каноническая модель остаётся `AH=<S,C,P,H,L>`.

## 1. FormalizationBatch

`FormalizationBatch` задаёт границу одной семантической операции записи:

- `MESSAGE` содержит один результат восприятия сообщения;
- `DOCUMENT` может содержать несколько ограниченных окон восприятия, но они являются только техническими частями одного документа;
- `source_ref` связывает результат с источником для provenance;
- `unit_offsets` при необходимости явно задаёт положение каждого окна в исходном документе.

Для документа parser-local идентификаторы `A1`, `E1` и другие получают namespace `B0:`, `B1:` и т. д. Поэтому перезапуск локальных счётчиков в каждом окне не создаёт ложной идентичности.

Evidence spans каждого окна переводятся в координаты полного `source_text`. Если окно невозможно однозначно найти в исходном документе и explicit `unit_offsets` не заданы, подготовка плана завершается ошибкой до записи AH. Локальные span-координаты разных окон не смешиваются молча.

## 2. CandidateIR

`CandidateIR` — временный, уже структурно проверенный граф кандидатов. Он содержит:

- исходный текст batch;
- scoped `PerceptionResult`;
- детерминированный порядок assertions по зависимостям;
- runtime `DiscourseRef` для неразрешённых ссылок;
- тип batch и `source_ref`.

Перед созданием `CandidateIR` выполняются:

1. `apply_speech_act_scoping`;
2. полная `CandidateValidator.validate`;
3. вычисление dependency order;
4. выделение неразрешённых дискурсивных ссылок.

`CandidateIR` не назначает UID и не пишет persistence.

## 3. MutationPlan и единственная граница записи

`MutationPlan` содержит только проверенное намерение канонической мутации:

- `CandidateIR`;
- выбранный domain policy;
- speaker reference;
- optional existing H occurrence для delayed semantic resolution.

UID и canonical objects создаются только внутри существующей транзакции `AHCore`. Если ошибка возникает даже на позднем этапе materialization, транзакция откатывается целиком: предыдущие окна документа не остаются частично записанными.

Публичные пути `integrate_external`, `integrate_to_h` и document integration теперь проходят через подготовку `MutationPlan`; прямое прежнее поведение сохранено как совместимый API, но семантически использует ту же границу.

## 4. Delayed coreference и DiscourseRef

Неразрешённое третьеличное местоимение больше не может незаметно превратиться в новый `m_ОН`/`m_ОНА` только потому, что actant требует filler.

Для него создаётся runtime descriptor:

```text
DiscourseRef
├── local_id
├── assertion_id / role
├── mention
├── grammatical number / gender
├── source span
└── candidate_entity_refs[]
```

`DiscourseRef`:

- не имеет AH UID;
- не возбуждается;
- не участвует в Hebbian plasticity;
- не является фактом;
- не сериализуется как canonical element.

На полном batch консолидатор собирает только грамматически совместимые локальные `entity_ref` как ограниченный набор кандидатов. Сам факт наличия одного совместимого кандидата **не доказывает coreference** и не вызывает автоматическую привязку.

После внешнего детерминированного решения или bounded semantic probe выбранный локальный кандидат применяется через `bind_discourse_ref(...)`. Метод только переписывает staging graph и заново запускает scoping/validation; AH остаётся неизменной до `integrate_plan`.

Если `DiscourseRef` остаётся неразрешённым, `integrate_plan` завершается `UnresolvedDiscourseReferenceError` **до первой canonical mutation**. Это намеренно сохраняет неоднозначность вместо forced guess.

Cross-turn pronoun anchors, которые уже однозначно определены `InteractionContext`, продолжают использовать существующий `DeixisResolver` и не объявляются новым unresolved reference.

## 5. Явный canonical identity merge

Добавлен публичный `IntegrationService.merge_identity(left, right, reason)` для случая, когда identity уже установлена внешним детерминированным механизмом/консолидацией. Сам метод не делает semantic identity inference.

Правила:

1. оба объекта обязаны быть canonical `M`;
2. выживший UID выбирается детерминированно: более ранний canonical UID по `creation_sequence`, затем UID как tie-break;
3. все ссылки на удаляемый `M` перепривязываются в одной транзакции;
4. aliases объединяются;
5. эквивалентные зависимые `N` дедуплицируются существующим canonical механизмом, а `occurrence_count` складывается семантикой повторного факта;
6. proof supports rewired существующим `SupportLedger`;
7. удаляемый UID физически исчезает только после успешной перепривязки;
8. событие merge и его причина идут во внешний `session_log`, а не в `H` и не в semantic properties сущности.

Если два обычных свойства имеют несовместимые значения, merge не выбирает победителя по новизне, частоте или `w`: операция откатывается. Маршрутизация положительных property-conflicts в общий Conflict Engine остаётся отдельным расширением и не имитируется в этом срезе.

## 6. Provenance batch

`ExperienceMapper.record_turn` принимает `source_ref` и `batch_kind`, поэтому H occurrence сохраняет техническую привязку к источнику входа. Это provenance события, а не новый semantic TIME и не raw-RAG memory.

## 7. Что сознательно не делается в 0.16.0

Этот срез закрывает **границу и атомарность формализации**, но не объявляет завершёнными все виды естественно-языковой семантики.

Не заявляются готовыми:

- автоматическое превращение истинно неизвестного участника `кто-то` в `EXISTS $0 ...` из произвольного ЕЯ-текста; quantified canonical/reasoning слой уже существует с 0.14.0, но NLP-lifting требует отдельной формализации;
- автоматическое решение произвольной forward-coreference только по грамматической совместимости; кандидат сужается, но identity не угадывается;
- late identity split;
- property-level positive-positive conflict resolution.

Эти ограничения не приводят к ложной canonical записи: нерешённый случай остаётся staging/clarification state.

## 8. Сохранённые инварианты

- `S/M/T/N/L/g/k/H` не расширены новым canonical типом.
- `IS-A`, `FOLLOW`, `CAUSE` и M2 не изменены.
- `CAUSE` не становится автоматически транзитивным.
- Phrase-level `s` не создаётся.
- Одинаковое имя не является identity key.
- БЯМ не назначает UID и не пишет AH.
- Atomic commit выполняет только AH Core.
- Runtime state не становится долговременной памятью.
- Неоднозначность не разрешается произвольным выбором.

## 9. Регрессия

Перед выпуском 0.16.0:

```text
python -m compileall -q src   OK
pytest -q                    642 passed, 22 subtests passed
```

Полный hackathon acceptance намеренно не запускался; он остаётся финальным этапом после завершения архитектурных срезов.
