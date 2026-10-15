# Примеры изолированных запросов после прогона 11

Получены через native/GUI путь с предписанными ответами. Это фактические тексты новых запросов, не результаты живой модели.

## Содержание отрицания

Исходное предложение: «Неверно, что Иван пришёл.».

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
Which option describes the displayed text? Choose its outermost relation; inner relations are handled later. The content option requires both the parent predicate and dependent content to be present in this text. Numeric quantification is deferred. More options remain on another page; 0 rejects only this page.

Decision slot: structural_relation
Context span: Иван пришёл
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

## Родитель с вынесенным содержанием

Исходное предложение: «Иван сказал, что Пётр пришёл.».

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
A content slot of this predicate is supplied separately. Classify the displayed words with that slot left open. Which option describes the displayed text? Choose its outermost relation; inner relations are handled later. The content option requires both the parent predicate and dependent content to be present in this text. Numeric quantification is deferred. More options remain on another page; 0 rejects only this page.

Decision slot: structural_relation
Context span: Иван сказал
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

## Выбор роли получателя

Исходное предложение: «Вчера марии Пётр передал книгу.».

```text
Read the source and answer the question about its meaning or grammar. Options are proposals, not facts. Use only the supplied text and context; do not invent identities or events. You are interpreting what is said, not checking whether it happened.
Choose the immediate grammatical attachment of «марии» at 6. GENITIVE means a noun in the genitive case modifying another noun; it does not establish ownership. CASE_DEPENDENCY means a complement of the named noun, not an argument of the verb. Matching case alone is insufficient. Already fixed dependencies: «Пётр» is grammatical subject of the predicate «передал»; «книгу» is direct object or content of the predicate «передал». Choose the attachment supported by this sentence; preserve ambiguity if evidence is insufficient.

Decision slot: nominal_dependency
Context span: Вчера марии Пётр передал книгу.
Options:
1. Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate
2. GENITIVE dependency on «Пётр» at 12; lemma: мария; pos: noun; cases: genitive; number: singular; gender: feminine; features: personal name, animate
3. GENITIVE dependency on «книгу» at 25; lemma: мария; pos: noun; cases: genitive; number: singular; gender: feminine; features: personal name, animate
4. CASE_DEPENDENCY dependency on «Пётр» at 12; lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate
5. CASE_DEPENDENCY dependency on «книгу» at 25; lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate
6. CASE_DEPENDENCY dependency on «Пётр» at 12; lemma: мария; pos: noun; cases: prepositional; number: singular; gender: feminine; features: personal name, animate
7. CASE_DEPENDENCY dependency on «книгу» at 25; lemma: мария; pos: noun; cases: prepositional; number: singular; gender: feminine; features: personal name, animate
Response protocol: SELECT_LABELS_V1
Reply with the number of the supported option. If several options remain possible, list their numbers separated by commas. Insufficient context: ?
No candidate fits: 0
One line, no spaces. No JSON or explanation.
```
