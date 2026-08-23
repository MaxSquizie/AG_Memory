# v0.12.82 — bare-PP ambiguity boundary

Основание: live acceptance на v0.12.81 / `qwen3.8-27b-nvfp4-q5k-no-mtp` дал `Runtime OK 200/200`, `Semantic PASS 198/200`, `FAIL 2`. Оба FAIL относятся к одному классу: целый relational modifier вида `ADVB + PREP + instrumental` ошибочно попадал под hard-ambiguity правило для postnominal instrumental PP.

## Причина

`_resolve_modifier_attachment()` проверял наличие instrumental complement внутри modifier span, но не различал:

- bare PP: `PREP + instrumental`, непосредственно следующий после nominal;
- более крупный modifier, внутри которого PP является зависимой частью и перед `PREP` уже есть lexical governor.

Из-за этого наличие инструментального падежа внутри любого соседнего modifier автоматически порождало `STRUCTURAL_CLARIFICATION_REQUIRED`, хотя структурное правило было задумано только для bare postnominal PP.

## Исправление

Hard clarification теперь требует одновременно:

1. нескольких structural attachment targets;
2. instrumental nominal complement;
3. `first_prep == span.start_index`, то есть modifier span сам является bare PP.

Если до PREP внутри того же span есть lexical material, construction идёт в прежний bounded attachment probe `EVENT / NOMINAL_n / UNCLEAR`. Никаких словарей конкретных предикатов, существительных, наречий или acceptance-фраз не добавлено.

## Регрессия

Добавлен lexical-independent тест на другом предикате и других сущностях: larger adverbially headed modifier with internal `PREP + instrumental` не должен автоматически требовать clarification. Существующий тест на genuine bare instrumental PP продолжает требовать clarification.

Полный suite: **496 passed, 22 subtests passed**.
