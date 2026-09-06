# Slice 25.8 — live ellipsis acceptance hardening

## Input evidence

Live run `20260906_190852_+0300` on v0.25.7:

- 22 cases;
- runtime OK 21, runtime error 1;
- semantic PASS 11, FAIL 11.

Family results:

- predicate_frame 5/6;
- role_frame 2/5;
- proposition_negation 0/4;
- proposition_confirmation 2/2;
- temporal_ellipsis 2/3;
- locative_ellipsis 0/2.

Inspection showed three distinct causes.

## 1. Dash ellipsis vs nominal-predicate contamination

ClauseBuilder already marked tails such as `а Мария — журнал` and `а журнал — на полке` as `EllipsisKind.FRAME`, but nominal predicate candidates for `журнал/полке/Казани` remained in the global predicate work queue. Adaptive parsing therefore consumed a spurious nominal assertion before ellipsis completion.

Fix: once a clause has a licensed ellipsis owner, all predicate candidates inside that tail are removed from the ordinary predicate queue. Morphology remains available as evidence; only the competing lexical predicate interpretation is suppressed.

## 2. Object-level NOT was graded as meta-level FALSE

Live proposition-negation cases (`Иван купил книгу, а Мария — нет`) were already reconstructed correctly in perception and Integration:

- recovered predicate and inherited object;
- `negated=true`;
- canonical root `g_NOT` over the new N.

The semantic oracle incorrectly unwrapped/looked for `FALSE`, which is reserved by architecture for refuting a particular proposition.

Fix: canonical assertion matching unwraps both wrappers where traversal is required, but expected `negated=true` specifically means `g_NOT`. `FALSE(N)` remains meta-refutation.

## 3. Parallel role-slot alignment

A live bounded probe swapped `Ольга` and `Петру` in `Анна отправила письмо Сергею, а Ольга сообщение Петру`. Instead of adding a global case-to-role shortcut, ellipsis recovery now compares overt target fillers with the grammatical realization signatures of the already resolved antecedent slots. A role is transferred only when the signature uniquely identifies one antecedent slot.

This is structural parallelism, not lexical semantic guessing.

## Remaining separate gaps

- `Мастер сделал стол из дерева...`: parser requests clarification for modifier attachment. The deeper fix is to collapse syntactic attachment alternatives when they yield the same canonical MATERIAL semantics, rather than hard-code `из -> MATERIAL`.
- `Вчера ... а сегодня ...`: ellipsis itself is reconstructed correctly; Integration fails because acceptance context has no legal temporal anchor. This belongs to experience/source time anchoring, not ellipsis.
- Typo cases remain under the separately specified Lexical Recovery layer (Levenshtein candidate generation + embedding rerank + morphology validation).
