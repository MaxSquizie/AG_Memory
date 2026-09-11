# Slice 25.25 — §21, объединение semantic branches и архитектурный аудит

## Activation и Workspace

Исполняемый контракт §21 закреплён отдельными regression-инвариантами:

- tick вычисляется из immutable snapshot и коммитится синхронно;
- propagation, созданный на текущем tick, потребляется только следующим tick;
- Workspace — полный строгий набор `x > threshold`, без top-N relevance policy;
- `resolved_symbol` и `query_recall` равны по умолчанию, но конфигурируются отдельно;
- Hebbian update посещает только существующие `L` и использует только same-tick
  activation/reactivation events;
- односторонняя activation слабо уменьшает `L.w`, inactivity ничего не меняет;
- depression имеет ненулевой floor и не удаляет relation/topology;
- `x` и `L.w` не являются truth/confidence.

Одновременно устранён cold-import cycle `ah.ignition ↔ ah.inference`: type-only
ссылка на inference engine больше не запускает обратный runtime import.

## Merge и совместимость

Semantic quantifier line и ветка `temp` объединены реальным двухродительским
merge-коммитом `c88cbb5`. История ветки, авторы и merge ранее подключённой `gc`
сохранены. После объединения локально исправлены только обнаруженные regressions:

- modal cue pass больше не рассматривает уже потреблённые connectors/prepositions
  как самостоятельные modal candidates;
- DOCUMENT batch использует публичную atomic Integration boundary с детерминированным
  staging transform;
- неуспешный Main LLM call без последующих изменений не запускает второй autosave;
- обычный `ExistsGoal` может получить witness через доказанный formula-scoped atom,
  не превращая zero-occurrence leaf в факт по одному наличию в AH;
- все active probe instructions снова компактны и не содержат demonstrations.

## Зафиксированные policy decisions

- association оставляет участие `H` runtime-параметром `ALL/EXCLUDE_H`, а outcome
  отдельно сообщает `SEMANTIC/EPISODIC`;
- Main LLM получает один окончательный frozen `AgentContext` и не имеет secondary
  memory-request capability;
- source cursor/slices являются runtime-only primitive; полный iterative document
  summary остаётся отдельной реализационной задачей.

Полная матрица и два независимых остаточных потока находятся в
`docs/ARCHITECTURE_AUDIT_02525.md`.
