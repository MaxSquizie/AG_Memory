# Slice 25.9 — composite ellipsis acceptance frontier

This slice deliberately changes the **acceptance frontier**, not the parser.

The previous `acceptance_ellipsis` corpus contained 22 mostly isolated constructions. That was enough to locate the missing frame-completion layer, but became too narrow after v0.25.7/v0.25.8 started closing individual classes. v0.25.9 expands the same suite to 100 semantic-oracle cases so subsequent fixes are driven by interactions between mechanisms rather than by isolated happy paths.

## Longitudinal compatibility

Cases 1..22 are preserved unchanged. This allows direct comparison with earlier live runs (`0/22`, then `11/22`) while the complete run now exposes a larger capability frontier.

## New interaction classes

The 78 additional cases cover:

- long chains with 3–4 reconstructed propositions;
- nearest-antecedent selection after an explicit predicate changes;
- stopping ellipsis when a genuine nominal predicate begins;
- coordinated subjects and objects, including coordination inside proposition negation;
- positive → negative → confirmation polarity chains;
- role-rich frames with RECIPIENT, TOOL, MATERIAL, LOCATION, TIME and DURATION;
- simultaneous temporal and locative substitutions;
- semicolon and sentence-boundary reconstruction;
- control/embedded scope (`хотеть`, `начать`, `решить`, `попросить`) where recovery must not flatten embedded propositions into factual assertions;
- coreference in the antecedent followed by ellipsis in the next coordinated frame;
- syntax inversion and typo noise combined with ellipsis.

Two deliberately high-value examples are included exactly as requested:

```text
Иван купил журнал, а Мария и Пётр - нет.
```

Expected semantics: one positive BUY assertion and one negated BUY assertion whose SUBJECT is `AND(Мария, Пётр)` and whose OBJECT is inherited `журнал`.

```text
Иван живёт в Москве, Мария - в Казани, Пётр - в Париже, а Слава - бродяга.
```

Expected semantics: three LIVE frames with distinct LOCATION values followed by a genuine nominal predicate `бродяга(Слава)`. The final clause is a boundary condition: it must **stop** ellipsis instead of producing `жить(Слава, ...)`.

## Regression contract

`tests/test_gui_m1_ellipsis_acceptance_v0256.py` now verifies:

- exactly 100 case lines;
- exactly 100 oracle entries;
- production-loader alignment;
- absence of accidental `[CASE_ID]` pseudo-lines;
- presence of the composite frontier examples;
- presence of all new interaction families.

No live LM Studio score is claimed in this slice. The intended next step is to run the unchanged GUI action `M1: ellipsis acceptance` and use family-level failures to choose the next semantic correction.
