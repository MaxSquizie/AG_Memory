# Semantic acceptance corpus

## broad200-v2

`data/acceptance_cases.txt` and `data/acceptance_oracle.json` define the default
semantic acceptance suite from v0.12.47 onward.

The suite contains **200 user turns grouped into isolated semantic scenarios**. Cases 1–40 are the frozen
regression corpus that first reached a real `40 PASS / 0 FAIL / 0 GAP` on
v0.12.45/v0.12.46 diagnostics.  Their original files remain available as:

- `data/acceptance_cases_regression40.txt`
- `data/acceptance_oracle_regression40.json`

Cases 41–200 are deliberately new pressure, not paraphrases chosen to fit the
current parser.  Every case is `EXACT`; a failure is diagnostic evidence and is
not converted to `ARCHITECTURE_GAP` merely because the mechanism is currently
weak or absent.


### Scenario isolation (v0.12.50)

A 200-turn corpus cannot treat every example as both independent and part of one
discourse. The first broad200 run accumulated unrelated entities across families;
repeated labels such as `книга`, `Мария` and `Анна` then produced real canonical
reference ambiguities that belonged to the test harness history rather than to the
current example.

Each oracle case therefore has a `scenario` id. State continuity exists **only**
inside one scenario. On a scenario transition the runner restores canonical AH,
InteractionContext and Ignition to the acceptance run baseline. The first frozen 40
remain one scenario because their previously confirmed 40/40 result is sequential.
The new corpus uses shared scenarios only where memory is the mechanism under test:

- cases 71–74: `открыть` T evolution;
- cases 75–76: `положить` T evolution;
- cases 77–80: `написать` T evolution + TOOL query;
- cases 161–162, 163–164, 165–166, 167–168, 169–170: assertion/query pairs.

All other new examples are isolated scenarios. The runner also restores the user's
pre-run live state when diagnostics finish, so broad acceptance is non-destructive.

### New 160-case stress families

| Range | Family | Main pressure |
|---|---|---|
| 41–50 | `lexical_basic_frames` | new lexical predicates; SUBJECT/OBJECT/LOCATION/STATE |
| 51–60 | `recipient_transfer` | explicit RECIPIENT across ten transfer/speech predicates |
| 61–70 | `adjunct_roles` | TOOL, SOURCE, MATERIAL, DURATION, TIME, AMOUNT, PURPOSE |
| 71–80 | `template_evolution_stress` | monotonic T growth across later explicit roles and TOOL query |
| 81–90 | `coordination_stress` | subject/object/predicate coordination and shared actants |
| 91–100 | `coreference_stress` | pronouns, lexical identity, `тот`, ambiguous reference |
| 101–110 | `relative_clause_stress` | subject/object/location relative binding |
| 111–120 | `nested_content_stress` | finite complements, control, request/speech, depth 3 |
| 121–130 | `temporal_causal_stress` | preposed/postposed temporal clauses and causal links |
| 131–140 | `conditional_stress` | IF shapes, conjunctions, coreference and negated branches |
| 141–150 | `negation_stress` | simple, coordinated and contrastive negation |
| 151–160 | `passive_impersonal_stress` | passive agent recovery and subjectless recipient frames |
| 161–170 | `query_role_stress` | TOOL/RECIPIENT/SOURCE/TIME/LOCATION FILL_ROLE queries |
| 171–180 | `personal_provenance_stress` | USER deixis, P-domain propagation, nested/persistent identity |
| 181–190 | `ambiguity_stress` | H-only structural clarification and reference alternatives |
| 191–200 | `morphology_case_pressure` | animate accusative/genitive syncretism across new lexemes |

The expanded corpus intentionally includes mechanisms that may fail on the first
real run.  The goal is to expose architectural or generalization weaknesses, not
to preserve a high percentage by selecting only already-solved examples.

## Family metadata

Each oracle case may contain:

```json
{
  "family": "query_role_stress",
  "tags": ["query", "source"]
}
```

The semantic evaluator and live acceptance runner preserve this metadata and
produce per-family PASS/FAIL/GAP counts.  This is the primary diagnostic unit once
the corpus grows beyond a few dozen cases: one failing family is more actionable
than an undifferentiated global percentage.

## Scaling policy

The 200-case suite is still small.  It is a hand-curated architecture probe, not a
claim of language coverage.  Future growth should add new independent semantic
families and lexical/morphological variation inside each family while preserving
three rules:

1. keep old passing cases frozen as regressions;
2. write the oracle from intended semantics, not from parser output;
3. never turn a current implementation failure into an expected GAP merely to
   improve the score.
