# Срез v0.21.0 — Context Projector, source scope и AH-only документы

## Назначение

Версия 0.21.0 закрывает следующий крупный runtime-контур архитектуры v4:

```text
source/document provenance
→ source-scoped semantic roots
→ QUERY_RECALL seeds
→ ordinary synchronous Ignition
→ Workspace
→ deterministic source-bounded semantic projection
→ AgentContext
→ Main LLM
```

Основная граница среза:

```text
Main LLM получает semantic projection AH,
а не raw document/history и не произвольный global retrieval dump.
```

Срез не вводит новую document ontology и не делает source scope каноническим типом AH. Все новые структуры — runtime/rebuildable indexing поверх уже существующих `AH=<S,C,P,H,L>` и H provenance.

## 1. SourceScope — runtime provenance boundary

Добавлен runtime-контракт:

```text
SourceScope {
    source_ref
    experience_refs
    semantic_roots
}
```

`source_ref` — технический handle источника, уже сохраняемый на H occurrence при batch integration. `SourceScope` не получает UID, не имеет `x`, не участвует в Hebbian и не сериализуется как новый canonical element.

`SourceScopeResolver` выполняет:

```text
source_ref
→ rebuildable source_experiences index
→ H occurrence(s)
→ OBJECT content
→ flatten only UTTERANCE_CONTENT grouping
→ ordered canonical semantic roots
```

Это bounded retrieval. Resolver не использует:

```text
all_elements()
all_uids()
elements(Domain.H)
links()
```

Regression guard намеренно запрещает эти broad enumerators во время source-scope resolution/projection.

## 2. Rebuildable source provenance index

В `AHStore` добавлен derived index:

```text
source_ref -> H experience UID[]
```

Он строится только из canonical H hypernodes с:

```text
event_instance = True
meta.source_ref = ...
```

Индекс:

- не является второй памятью;
- не сохраняется отдельным truth-store;
- полностью перестраивается `rebuild_indexes()`;
- восстанавливается после JSON persistence reload;
- используется только как bounded provenance lookup.

Это соответствует общей v4-дисциплине: индекс ускоряет доступ, но canonical truth остаётся в AH.

## 3. Raw DOCUMENT text больше не является ordinary H retrieval memory

До 0.21 `ExperienceMapper` всегда записывал полный `source_text` в:

```text
H event Pr.text
```

Для MESSAGE это нормально: конкретная реплика является пережитым коммуникационным событием H.

Для DOCUMENT такая запись опасна, потому что полный исходный документ превращался бы в обычный model-visible H content и фактически давал бы hidden raw-history/RAG fallback.

Теперь правило разделено:

```text
MESSAGE:
    H event keeps text utterance

DOCUMENT:
    H event keeps source_ref + semantic OBJECT roots
    raw source text is NOT stored in H.text
```

Raw document при необходимости может существовать во внешнем локальном provenance/source store, но текущий canonical H не используется как chunk storage.

Для backward compatibility `ContextProjector` также проверяет legacy H events: если `batch_kind=DOCUMENT`, их `text` не попадает в AgentContext даже если старый persistence-файл его содержит и event оказался активен.

## 4. SourceScopeActivator — документ вспоминается через обычный Ignition

`SourceScopeActivator` не выставляет `x` вручную и не создаёт отдельную activation simulation.

Для каждого source semantic root выполняется:

```text
ActivationSeedRequest(root, QUERY_RECALL)
```

после чего запускаются обычные:

```text
IgnitionEngine.tick(include_pacemaker=False)
```

Следовательно:

- источник вспоминается тем же механизмом, что и прочая память;
- один новый propagation packet проходит не более одного ребра за tick;
- Workspace определяется обычным `x > threshold`;
- source scope не является отдельной памятью;
- pacemaker не подмешивается в искусственное «время пересказа».

Seed получают semantic roots, а не H source-event и не raw text.

## 5. Source-bounded ContextProjector

`ContextProjector.project()` получил runtime параметры:

```text
source_scope: SourceScope | None
budget_tokens: int | None
```

В обычном режиме поведение остаётся Workspace-driven.

При `source_scope` projector сначала ограничивает model-visible ACTIVE roots пересечением:

```text
Workspace ∩ source_scope.semantic_roots
```

Это важно при тёплой AH. Если до запроса уже был активен посторонний факт, shared entity или прошлый диалог, он не должен автоматически попасть в article/source summary.

Source scope не изменяет сам Workspace. Он ограничивает только projection boundary конкретного source-bounded запроса.

## 6. Causal/episodic structure не теряется при projection

Canonical `L` не имеет собственного `x`, поэтому `CAUSE/FOLLOW/IS-A` link не может сам появиться в Workspace как excitable root.

Однако архитектура v4 требует не превращать документ в unordered bag of facts. Поэтому source projection детерминированно добавляет прямые structural relations, если:

```text
source endpoint ∈ visible source roots
AND target endpoint ∈ visible source roots
AND relation ∈ {CAUSE, FOLLOW, IS-A}
```

Lookup выполняется только через:

```text
outgoing_links(current_visible_root)
```

то есть не через global `links()` scan.

Таким образом AgentContext может содержать, например:

```text
ДАТЧИК_ОБНАРУЖИЛ_ТРЕВОГУ
ПЕРСОНАЛ_ЭВАКУИРОВАЛСЯ
ДАТЧИК_ОБНАРУЖИЛ_ТРЕВОГУ --CAUSE--> ПЕРСОНАЛ_ЭВАКУИРОВАЛСЯ
```

без передачи исходного абзаца.

`CAUSE` при этом остаётся направленным и нетранзитивным по умолчанию; projection ничего не доказывает и не материализует.

## 7. Human-readable semantics, а не внутренний DSL

Agent-facing projector продолжает использовать `include_structural_uids=False` независимо от operator/debug projector.

Main LLM получает:

```text
# CURRENT INPUT
...

# ACTIVE MEMORY
- human-readable semantic fact
- human-readable source relation

# INFERENCE RESULTS
- deterministic conclusion/status
```

Не передаются:

- `x`, `w`, decay state;
- proof runtime internals;
- arbitrary canonical UIDs;
- полный AH;
- raw document;
- broad retrieval dump.

Exact source Workspace refs и `source_scope_ref` остаются runtime diagnostics only.

## 8. Deterministic projection budget

`ContextSettings.max_tokens` до этого фактически передавался backend-у, но projector сам не гарантировал fail-closed overflow semantics.

В 0.21 добавлен deterministic estimate:

```text
word/punctuation units in final rendered AgentContext
```

и исключение:

```text
ProjectionBudgetExceeded
```

Если projection превышает:

```text
min(context.max_tokens, explicit budget_tokens)
```

контекст не обрезается и не заменяется raw chunks.

Это намеренно консервативное поведение, потому что exact iterative oversized-source protocol в v4 имеет статус ОТКРЫТО.

До принятия такого protocol допустимо:

```text
overflow -> explicit error/resource boundary
```

но недопустимо:

```text
overflow -> silent top-k facts
overflow -> raw document chunks
overflow -> arbitrary Main-LLM memory request
overflow -> hidden vector RAG
```

Оценка token count является runtime diagnostic, а не семантическим свойством AH.

## 9. Provenance wording также больше не требует H scan

Существующая функция восстановления wording пользовательского assertion раньше читала все `H` events.

Теперь reverse lookup идёт через rebuildable indexes:

```text
semantic root
→ groups_containing(root)
→ hypernodes_for_actant(container)
→ matching USER H event
```

Это сохраняет старое удобство для обычного dialogue projection, но убирает unrestricted H enumeration из ContextProjector.

`DOCUMENT` events из этого механизма исключены: document raw wording никогда не подставляется вместо semantic projection.

## 10. SourceScopedContextService

Добавлена runtime convenience boundary:

```text
SourceScopedContextService.build(
    current_input,
    source_ref,
    settle_ticks,
    inference_results,
    budget_tokens,
)
```

Внутри:

```text
resolve source
→ activate semantic roots
→ ordinary Ignition ticks
→ get Workspace
→ source-bounded ContextProjector
→ AgentContext
```

Это не новый canonical service/domain и не document ontology. Он лишь собирает уже нормативные runtime стадии в один воспроизводимый путь для summary/evidence tasks.

## 11. Persistence

Новая source index не сериализуется.

После reload:

```text
canonical H event meta.source_ref
+ canonical OBJECT refs
→ rebuild_indexes()
→ same SourceScope
```

Отдельный regression test проверяет точное восстановление source semantic roots после JSON persistence round-trip.

## 12. Исправление structural replace consistency

В ходе среза обнаружен старый технический дефект: внутренний `_replace_hypernode()` мог менять actants/properties/index-sensitive meta без перестройки reverse indexes.

Теперь replacement разделяет:

```text
weight/lifecycle-only update
→ no index rebuild

structural/provenance update
→ rebuild derived indexes
```

Index-sensitive изменения включают:

- template;
- actants;
- properties;
- `semantic_scope`;
- `dedup_exempt`;
- `event_instance`;
- `source_ref`;
- `batch_kind`.

Это сохраняет hot-path Ignition/lifecycle без лишнего rebuild, но гарантирует корректность reverse/source indexes после реальной структурной правки N.

## 13. Регрессия 0.21

Добавлен `tests/test_v4_source_projection_2100.py`.

Проверяется:

1. DOCUMENT occurrence сохраняет source handle, но не raw text.
2. SourceScope разрешается через rebuildable index без broad domain scan.
3. Source semantic roots реально проходят через Ignition.
4. Тёплый unrelated Workspace не протекает в source summary.
5. Raw document не присутствует в AgentContext.
6. CAUSE relation между source facts сохраняется в model-visible semantics.
7. Legacy DOCUMENT `text` также не протекает.
8. Projection budget fail-closed и ничего не truncates.
9. Source provenance index восстанавливается после persistence reload.
10. SourceScopedContextService собирает полный source→activation→projection path.

Перед выпуском:

```text
python -m compileall -q src
pytest -q

695 passed
22 subtests passed
```

Полный hackathon acceptance намеренно не запускался.

## 14. Что 0.21.0 не заявляет готовым

Архитектурно открытые пункты остаются открытыми:

- iterative projection protocol, если compact source semantics всё ещё превышает context window;
- Main-LLM initiated extra memory request;
- hidden/raw RAG fallback — по-прежнему запрещён;
- автоматическое качество художественного summary — задача Main LLM поверх корректного AgentContext, не отдельный memory reasoner.

Следующий крупный срез: lifecycle/GC + обязательный DSL/operations/hackathon integration closure.
