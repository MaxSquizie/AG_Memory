# Association GoalCompiler acceptance v1

Dedicated acceptance/oracle for point 6: natural-language associative requests must
produce and execute a typed `AssociationGoal` instead of requiring a programmatic
`AssociationCoordinator.solve(...)` call.

The acceptance boundary is deliberately split into three independently observable
stages:

1. **Perception intent** — ordinary parser structure is already available. A bounded,
   non-thinking semantic micro-probe may return only `ORDINARY`, `UNKNOWN`, or one
   enumerated pair `ASSOCIATION:Ea:Eb`. It sees local endpoint labels, never AH UIDs.
2. **GoalCompiler** — parser-local endpoint selectors are resolved read-only to
   existing canonical origins. Allowed source-grounded origins are existing semantic
   `m`, already integrated proposition/formula `N/g`, or an already indexed lexical
   `S` when no semantic entity exists. The compiler never creates an endpoint and
   never scans AH for a merely plausible `T/N/g/k`.
3. **Runtime** — `AssociationCoordinator` performs two-front excitation search. Its
   result is projected in `ASSOCIATION RESULTS`, never as logical proof and never as
   a newly asserted canonical relation.

Important invariants:

- Semantic paraphrases are accepted; no connective/association marker dictionary is
  an authorization mechanism.
- A composition such as `A и B` may remain one actant role while its two members are
  independently addressable by `(role, member_index)` selectors.
- `candidate_ref` / proposition endpoints resolve to already canonical `N/g`; they are
  not flattened to entity names.
- Entity ambiguity fails closed. An unknown semantic entity may fall back only to a
  unique existing lexical `S`; no new `m` is created by asking a question.
- Generic `ActRelationCandidate("ASSOCIATION", ...)` is invalid. The runtime marker
  must use the typed `AssociationActRelationCandidate` contract.
- One act cannot simultaneously carry `ASSOCIATION` and a canonical world-relation
  goal such as `IS-A`; Perception must resolve the requested operation first, so
  GoalCompiler behavior never depends on relation ordering.
- Quoted association requests, quantified association queries, and negated association
  commands do not execute under the current binary AssociationGoal contract.
- Parser endpoint selectors must be distinct. They may nevertheless resolve to the
  same canonical ref; `AssociationCoordinator` then owns the valid depth-zero
  convergence `expand(A) ∩ expand(A)`.
- `AssociationGoal` and `AssociationOutcome` are not sent through `InferenceEngine`.
- `AgentContext.association_blocks` and `ProjectionMode.ASSOCIATION` remain distinct
  from `inference_blocks` / `ProjectionMode.INFERENCE`.
- The coordinator may converge on any excitable AH representation (`S/m/T/N/g/k/...`)
  according to architecture v4; this is a search property, not permission for the
  text resolver to globally guess an origin of any kind.

`cases.txt` is the natural-language stress corpus. `oracle.json` also contains typed
synthetic cases for endpoint resolution/runtime invariants that cannot be expressed
reliably by one isolated sentence without preloaded memory.

The suite is added now but is intentionally **not executed yet**; project testing is
scheduled after the remaining formalization points are closed.
