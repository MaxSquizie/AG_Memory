# v0.12.65 — semantic evidence dispatch

## Why

Inference must never be enabled by lexical intent markers such as `докажи` / `prove`.
Those words describe dialogue pragmatics, not truth conditions. A marker list makes the
reasoner dependent on phrasing and reintroduces a hidden LLM/heuristic decision before
the symbolic proof layer.

## Contract

`TurnGoalBuilder` derives evidence work only from the formalized turn:

- every canonical `QueryCandidate` is normalized through `QueryGoalBuilder`;
- every proposition that deterministic speech-act scoping marks `EMBEDDED` beneath a
  live QUERY/COMMAND root is compiled into a read-only `ExistsGoal`;
- the wording of the root command is irrelevant;
- an ordinary top-level assertion is not automatically reinterpreted as a question;
- the just-mentioned scoped proposition cannot prove itself because ordinary inference
  ignores hypernodes carrying `semantic_scope`;
- the result is still `PROVED`, `DISPROVED` or `UNKNOWN` with exact proof provenance.

The response model only verbalizes the resulting semantic evidence. It does not decide
whether memory reasoning should happen.

## Remaining generalization

The dispatch is now semantic, but natural-language goal compilation still needs to be
extended from `EXISTS`/role-fill targets to the already implemented typed goal families
(`RelationGoal`, `CauseEntailmentGoal`, connected `AllOfGoal`). That extension must be
based on formal semantic candidates / validated relation semantics, never on surface-word
heuristics.
