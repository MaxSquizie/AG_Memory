# Примеры изолированных запросов после правки

Это точный текст запросов, построенных обычным native/GUI путём. Ответы для прохода по цепочке были заданы скриптом; живую модель не вызывали. Служебная карта вариантов хранится отдельно. Эти фразы не добавлялись в runtime как шаблоны или few-shot примеры.

## structural_relation

Иван вошёл.

Длина: 3632 → 1896 символов.

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
Which option describes the WHOLE target area? Choose the outermost relation; inner relations are handled later. A verb with a dependent clause or quotation uses the content option, not the single-predication option. Numeric quantification is deferred. More options remain on another page; 0 rejects only this page.

Decision slot: structural_relation
Context span: Иван вошёл.
Options:
1. One lexical predication or nominal description; no dependent proposition, quotation, logical operator or quantifier
2. Negation of a proposition (not lexical opposition)
3. Possibility or ability; does not assert occurrence
4. Necessity or obligation; preserve its scope
5. Both propositions hold
6. At least one proposition holds; inclusive alternative
7. Exactly one alternative holds
8. Conditional: antecedent implies consequent; direction must be selected
9. Counterfactual condition and its consequence; not material implication
10. First event/proposition occurs before the second
11. First event/proposition occurs after the second
12. First event/proposition occurs during the second
13. A predicate has another clause as its content: reported speech, thought, quoted speech or a controlled infinitive
14. Universal nonnumeric quantification over a restricted variable
15. Existential nonnumeric quantification; no particular witness identity
16. A question about content; no assertion of the content
Response protocol: SELECT_LABELS_V1
Reply with the number of the supported option. If several options remain possible, list their numbers separated by commas. Insufficient context: ?
No candidate fits: 0
One line, no spaces. No JSON or explanation.
```

## structural_introducer_end

Неверно, что иван вошёл.

Длина: 2756 → 1359 символов.

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
NOT (Negation of a proposition (not lexical opposition)): select only the complete words expressing this outer relation. Include the full linking expression and any conjunction introducing its content. Exclude the content proposition, its subject and predicate. Separating commas may be included; do not end early just because the first word already signals the relation. The start is «Неверно» @0. Select the LAST token.

Decision slot: structural_introducer_end
Context span: Неверно, что иван вошёл.
Options:
1. End after «Неверно» @7; selected words «Неверно»
2. End after «,» @8; selected words «Неверно ,»
3. End after «что» @12; selected words «Неверно , что»
4. End after «иван» @17; selected words «Неверно , что иван»
5. End after «вошёл» @23; selected words «Неверно , что иван вошёл»
6. End after «.» @24; selected words «Неверно , что иван вошёл .»
Response protocol: SELECT_LABELS_V1
Reply with the number of the supported option. If several options remain possible, list their numbers separated by commas. Insufficient context: ?
No candidate fits: 0
One line, no spaces. No JSON or explanation.
```

## structural_governor

Возможно, иван вошёл.

Длина: 2408 → 964 символов.

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
Modal words: «Возможно , .». Content: «иван вошёл». Does a modal word supply person, number or gender agreement for a dependent infinitive? If the content already has its own conjugated predicate, choose no governor. A dictionary reading alone does not establish this connection.

Decision slot: structural_governor
Context span: Возможно, иван вошёл.
Options:
1. No agreement governor: the child has independent predication
2. Agreement/controller anchor «Возможно»
Response protocol: SELECT_LABELS_V1
Reply with the number of the supported option. If several options remain possible, list their numbers separated by commas. Insufficient context: ?
No candidate fits: 0
One line, no spaces. No JSON or explanation.
```

## structural_content_start

Мария сказала: «Иван вошёл».

Длина: 2808 → 1102 символов.

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
Select the complete dependent proposition: what is said, thought, intended or otherwise taken as content. Exclude the parent predicate and its participants, the introducing conjunction, colon, and enclosing quotation marks. Start at the first word INSIDE quoted content; retain any operators inside that content. Select the FIRST token.

Decision slot: structural_content_start
Context span: Мария сказала: «Иван вошёл».
Options:
1. Start at «Мария» @0
2. Start at «сказала» @6
3. Start at «:» @13
4. Start at ««» @15
5. Start at «Иван» @16
6. Start at «вошёл» @21
7. Start at «»» @26
8. Start at «.» @27
Response protocol: SELECT_LABELS_V1
Reply with the number of the supported option. If several options remain possible, list their numbers separated by commas. Insufficient context: ?
No candidate fits: 0
One line, no spaces. No JSON or explanation.
```
