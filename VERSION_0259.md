# AG Memory v0.25.9

Acceptance expansion only: no parser/runtime semantic logic changed.

`M1: ellipsis acceptance` has been expanded from 22 to 100 EXACT cases. The original 22 cases remain at indices 1..22 unchanged so live result deltas remain comparable.

The 78 new cases intentionally combine ellipsis with other mechanisms instead of adding near-duplicate simple examples:

- multi-clause ellipsis chains and nearest-antecedent continuation;
- explicit predicate reset and nominal-predication boundaries;
- coordinated SUBJECT/OBJECT groups under positive and negative propositions;
- mixed confirmation/negation (`тоже`, `нет`, explicit `не`);
- RECIPIENT / TOOL / MATERIAL / LOCATION / TIME / DURATION frame reconstruction;
- temporal + locative inheritance in the same utterance;
- semicolon and cross-sentence ellipsis;
- scope-preserving control/embedded predicates;
- coreference followed by ellipsis;
- inversion and typo + ellipsis composite adversarial cases.

User-requested frontier cases are included verbatim:

- `Иван купил журнал, а Мария и Пётр - нет.`
- `Иван живёт в Москве, Мария - в Казани, Пётр - в Париже, а Слава - бродяга.`

Corpus/oracle alignment is regression-tested at exactly 100 cases.
