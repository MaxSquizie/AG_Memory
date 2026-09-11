# Architecture audit — v0.25.25 после merge `temp → main`

## Итог

Объединённая линия сохраняет canonical модель `S/M/T/N/L/g/k/H`, atomic write
boundary, open-world semantics и разделение activation/proof. Блокирующих нарушений
архитектуры v4 в реализованных изменениях не найдено. Незавершённая обязательная
работа сведена к двум независимым потокам:

1. semantic composition и формализация сложных scopes;
2. end-to-end обработка и сжатие больших документов.

Сознательно отложенный §37 и явные non-goals §38 в эти потоки не включены.

## Проверка происхождения merge

- merge-коммит `c88cbb5` имеет родителей `a7b9b19` (`main`, semantic quantifiers)
  и `14c9a08` (`temp`, logic/modal/counterfactual/association line);
- `gc` уже является предком `main` через отдельный merge-коммит `7bd6abb`;
- коммиты автора `artnn <acloudycloudy@gmail.com>` сохранены в истории, поэтому
  contributor attribution не потеряна squash/rebase-операцией;
- после merge исправления выполнены поверх `main`, история обеих линий не переписана.

## Матрица соответствия

| Область архитектуры | Статус | Исполняемая граница | Остаток |
| --- | --- | --- | --- |
| §1–17 canonical AH, identity, persistence, domains | CLOSED | AHCore validation, atomic Integration, persistence, supports, conflicts | Только late identity split из §37.1; он DEFERRED |
| §18 lexical/morphology/frame/ellipsis/quantifiers | PARTIAL | Indexed Lexical Recovery; graph-based inversion/ellipsis; semantic QuantifierFormalizer; CandidateIR | NEVER scope, nested/correlated ambiguity и некоторые combined scopes — поток A |
| §19 identity/consolidation | PARTIAL | delayed `DiscourseRef`, explicit merge, dedup, existential anchors | Multi-variable cross-turn existential binding входит в поток A; automatic late split не входит |
| §20 time/state | PARTIAL | temporal values/relations, intervals, пять transition operators, occurrence TemporalMode | `никогда P → NOT(EXISTS t ...)` отсутствует — поток A |
| §21 activation/Workspace/plasticity | CLOSED | synchronous snapshot tick, floating threshold Workspace, same-tick existing-L plasticity | Нет обязательной реализации |
| §22–29 GoalSpec, logic, conflict, counterfactual, meta | PARTIAL | ground/quantified formula reasoner, branch contexts, modal nonfactivity, proof supports | OR/XOR и составные query targets, cross-scope GoalSpec composition — поток A |
| §30 association | CLOSED | separate coordinator, two activation fronts, narrow queries, `ALL/EXCLUDE_H`, `SEMANTIC/EPISODIC` | Универсальный quality reranker не требуется архитектурой |
| §31 projection/Main LLM | PARTIAL | one frozen AgentContext, no secondary recall, AH-only source projection, cursor/slices | multi-slice document summary/aggregation — поток B |
| §32 lifecycle/GC | CLOSED | lifetime state, structural deletion, support cleanup, persistence | Нет обязательной реализации |
| §33 deployment boundary | CLOSED | local bounded probes, server Main LLM isolation, offline memory continuity | Fully local responder — DEFERRED §37.6 |
| §34 diagnostics/GUI | CLOSED для текущих метрик | отдельные M1/M2/M3 tabs; M1 subgraphs и M2 UID traces, history limit 20 | Iterative-document progress UI относится к потоку B |
| §35 acceptance | PARTIAL | semantic corpora/oracles, dirty-AH M2, metric harnesses | настоящий whole-document pipeline acceptance — поток B; новые scope corpora — поток A |
| §36 policy questions | 2 CLOSED / 1 PARTIAL | H policy и отсутствие Main-LLM recall зафиксированы; source cursor реализован | только завершение document continuation — поток B |

## Обнаруженные и уже устранённые merge-regressions

- modal formalization исключает tokens, уже принадлежащие transition/discourse/
  connector structure, и не превращает preposition/conjunction в modal cue;
- старые semantic fixtures отвечают нейтрально на новые bounded probes только в
  test layer; production не получил corpus-specific shortcuts;
- direct `ExistsGoal` теперь использует formula reasoner для scoped candidates и
  доказывает conjunct через `AND_ELIM`, но не принимает zero-occurrence content за
  asserted fact;
- document plan-transform выполняется до одной публичной atomic commit boundary;
- post-association autosave выполняется повторно только после реального изменения;
- probe files снова укладываются в compact-protocol limit и не содержат examples.

## Единственный список незавершённой реализации

Подробные контракты находятся в двух файлах:

- `docs/ROADMAP_A_SEMANTIC_COMPOSITION_02525.md`;
- `docs/ROADMAP_B_DOCUMENT_RUNTIME_02525.md`.

Эти потоки имеют непересекающееся владение production-файлами. Оба должны
ответвляться от одного финального `main`; общие release/docs-файлы внутри рабочих
веток не редактируются и обновляются только после их будущего merge.

## Граница проверки

Полный локальный regression: `1334 passed, 2 skipped, 38 subtests passed`.
Два пропуска относятся только к optional PyTorch scorer-тестам: в текущем
окружении PyTorch не установлен, и эти тесты не эмулируются. `compileall`
и проверка whitespace проходят; active probe files меньше 360 байт и не
содержат demonstrations. Live-прогон подключённой LM Studio модели не
подменяется scripted fixtures и не заявляется в этом аудите как выполненный.
