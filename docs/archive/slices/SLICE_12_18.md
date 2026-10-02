# Slice 12.18 — lexical identity, clause scope and proposition-safe composition

The second 40-case acceptance run raised technical completion from 11/40 to 36/40,
but exposed silent semantic errors behind several `OK` turns. This slice therefore
optimizes for **canonical correctness rather than acceptance pass rate**.

Changes:

- `adaptive_v3` predicate identity is now the deterministic source-language lexical
  normal form. The LLM does not invent English predicate names. `TextSensoryService`
  and `TemplateResolver` reuse the same `S` and extend its `R_text` with observed
  surface forms, so predicate perception no longer creates a parallel symbol system.
- Morphology supplies only an indexing aid, not a new canonical `lemma` property.
  Stable material readings let inflectional variants share one lexical symbol and
  let `EntityResolver` find an existing `m` through a normalized nominal hint.
- Integration chooses one source-grounded anchor for every turn-local `entity_ref`.
  A named mention outranks a pronoun, so dependency ordering cannot cause `она` or
  `его` to create a second canonical entity before the named antecedent is visited.
- Explicit sentence-initial interrogatives create `QueryCandidate` directly.
  `кто/что/кому/...` determine a finite `requested_role`; the interrogative token is
  not an actant and cannot become a world entity.
- Fronted compound subordinators such as `после того как`, `перед тем как` and
  `если ... , ...` are clause operators, never nominal actants. A coordinated
  conditional antecedent remains one antecedent region and cannot leak its main
  clause into ordinary C/P knowledge.
- Relative-clause antecedents keep one `entity_ref` and can bind the following matrix
  predicate subject. A relative child's own subject is not inherited outward.
- Passive short participles deterministically map instrumental agent to `SUBJECT`
  and nominative patient to `OBJECT`.
- Post-verbal nominative subjects are recognized when no pre-verbal nominative is
  available, preventing shared-subject inheritance across an explicit causal clause
  such as `... потому что шёл дождь`.
- Nested non-finite situations get controller candidates from already extracted
  parent participants. One controller is deterministic; several may use one tiny
  finite `control_subject` probe.
- Multiple structurally compatible pronoun antecedents and unresolved
  `с + instrumental` attachment fail explicitly instead of asking the weak model
  to guess. Only genuinely local control selection may use a bounded finite probe.
- Contrastive negation `не X, а Y` expands one surface predicate into two sibling
  proposition candidates: a negated X fact and a positive Y fact. The siblings are
  never mistaken for nested situations.
- A single OR-composed actant is lifted during deterministic integration into
  `g_OR(N1, N2, ...)`, where every operand is a complete predicate realization.
  This implements the architecture's `OR(N_GREEN, N_RED)` semantics instead of
  storing `OR(m_green, m_red)` inside one N role.

No fallback parser, per-sentence exception table, free-form semantic repair, or new
canonical identity field was added. Ignition/Hebbian dynamics remain outside this
slice so parser correctness and activation dynamics are not conflated.
