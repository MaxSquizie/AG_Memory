# v0.12.84 — document reliability fixes

Первый ручной document-level прогон: 3 документа, 21 абзац, `15/21` semantic PASS, `0` runtime errors, `0/3` document PASS. Диагностика показала не проблему длины документа, а четыре повторяемых класса perception/integration ошибок.

## Исправления

1. **Predicate homograph suppression.** Weak non-finite head удаляется только если тот же source token имеет material NOMINAL/NOM reading, ближайший следующий strong finite predicate находится в том же punctuation segment, между ними нет coordinator/другого predicate head, а nominal reading согласуется с finite predicate. Это закрывает ложное расщепление `NOUN/GRND`-гомографов без лексических исключений.

2. **Intransitive structural SUBJECT.** Для active finite frame со стабильной lexical transitivity=`intr` и ровно одним согласованным nominative nominal этот nominal детерминированно является SUBJECT. Bare NOM сам по себе по-прежнему не назначает AH-роль.

3. **Cross-turn nominative coreference.** InteractionContext теперь получает `он/она/оно/они` anchor только от уникального canonical M, который был SUBJECT соответствующей number/gender signature в текущем внешнем turn. Два равноправных SUBJECT-кандидата очищают anchor. Canonical AH не изменяется этим механизмом.

4. **Role-conditioned lexical identity.** После semantic role resolution bare SUBJECT/OBJECT может использовать все dictionary readings для выбора единственной NOM/ACC lemma. Это позволяет грамматической структуре пересилить неверный top morphology score при homography, не превращая analyzer probability в truth.

5. **OBJECT/RECIPIENT cue.** Runtime semantic protocol явно различает человека, которого непосредственно вызывают/выбирают/видят, и адресата, с которым связываются речью, телефоном или сообщением. LLM всё ещё делает только один bounded UID-free semantic choice.

## Regression

- `507 passed`
- `22 subtests passed`
- `compileall` должен проходить перед упаковкой.

M2 runtime не изменён. Document oracle и заранее зафиксированные M2 proof paths остаются прежними.
