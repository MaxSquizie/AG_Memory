# Slice 4 — Workspace projection + symbolic inference

Архитектурная опора: `docs/reference/Архитектура_v3.md`, разделы 16–20 и runtime contracts 24.6–24.7.

## Реализовано

```text
Workspace refs
→ ACTIVE root projection
→ DEPENDENCY semantic dereference
→ AgentContext
```

Projector не выполняет reranking/top-k и не меняет Workspace. `Pr` раскрываются только у ACTIVE владельца; `Mt`, `R_text`, x/w/t/ticks/trace в обычный AgentContext не попадают.

```text
InferenceGoal
→ deterministic InferenceEngine
→ InferenceOutcome
   ├── logical status
   ├── semantic conclusion
   ├── premise refs
   └── exact UID trace
```

Поддерживаются:

- predicate-agnostic role fill / exists;
- transitive `IS-A`;
- transitive `FOLLOW`;
- `CAUSE` MP-like entailment;
- запрет общей транзитивности `CAUSE`;
- depth/budget/visited semantics;
- materialization final conclusion only;
- domain rule `C < P < H` over premises;
- derived `L` dedup through `ensure_link`;
- materialization does not create confirmation seed.

## Важная сверка архитектуры

Исправлено раннее расхождение реализации: `L` больше не получает `RuntimeState`. Канонический `L` находится в `AH.L`, передаёт output через `w`, но собственного `x` не имеет и не может попасть в Workspace. При необходимости `L` проецируется как root результата inference без excitation field.
