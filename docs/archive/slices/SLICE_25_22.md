# Slice 25.22 — document-to-AH и наблюдаемое evidence метрик

## Архитектурная граница

Срез не вводит document ontology, retrieval store или новый canonical node kind.
Он соединяет существующие границы:

```text
file
→ exact operational chunks
→ Perception + TemplateCompletion
→ one DOCUMENT CandidateIR/MutationPlan
→ one canonical AH transaction
→ source index
→ Ignition + complete source projection
→ frozen AgentContext
→ Main LLM summary
```

Raw text доступен только ingestion/provenance стороне. В model-visible memory он
не возвращается.

## Complete source projection

Обычный `ContextProjector.project()` сохраняет Workspace-driven contract и
fail-closed budget. Новый `project_compact_source()` — отдельная capability:

1. получает уже разрешённый `SourceScope`;
2. работает со всеми его semantic roots;
3. читает только outgoing adjacency этих roots;
4. сохраняет causal, episodic, taxonomic и temporal relations;
5. сначала пытается передать всё;
6. при overflow использует стабильный relation-aware порядок;
7. явно сообщает о compaction и никогда не подставляет raw chunks.

Таким образом, одноразовый bounded summary работает и для документа, который
шире текущего Workspace. Итеративный cursor/protocol не выдуман и остаётся
открытой архитектурной политикой.

## Diagnostic evidence

`FormalizationTraceBuilder` начинает bounded traversal только от refs текущего
`IntegrationCommit`. Он включает T/S, actants, g/k operands/members и L текущего
подграфа, но не перечисляет всю AH. `ProofChainSnapshot` уже содержал exact UID
trace; GUI теперь хранит его в отдельной M2 history.

Обе истории:

- имеют hard limit 20;
- состоят из immutable snapshots;
- не влияют на excitation, truth, inference или persistence AH;
- одинаково принимают live и acceptance diagnostics.

## Generality M1

Изменения noise recovery основаны только на edit channel, Pymorphy analyses,
case compatibility, clause topology и существующем predicate/frame context.
Frequency остаётся слабым prior, embeddings — optional reranker близкого
shortlist. Имена, термины, аббревиатуры, коды и неоднозначные варианты не
исправляются принудительно. Inversion и semantic role routing не зависят от
порядка слов и не были заменены.
