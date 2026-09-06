# AG Memory v0.25.12

Actual code slice for chained ellipsis reconstruction.

## Code changes

- `src/ah/perception/linguistic_candidates.py`
  - detects comma-separated zero-predicate peer frames such as `A, B — X, C — Y`;
  - links each recovered peer clause to the immediately preceding frame, including an already-elliptic frame;
  - preserves plain coordinated NP lists instead of promoting them to propositions;
  - adds a conservative dash boundary guard: nominative-only `X — Y` stays available for nominal predication, while PP and NOM/ACC replacements remain ellipsis candidates.
- `src/ah/perception/adaptive_parser.py`
  - fixes the `frame_completion` trace bug (`PredicateCandidate.lemma` -> `PredicateCandidate.lookup_form`) that caused runtime `AttributeError` in ellipsis recovery tests.
- `tests/test_ellipsis_recovery_0257.py`
  - adds chained comma ellipsis regression;
  - adds nominal-boundary regression for `... Пётр — в Париже, а Слава — бродяга`.

## Verification

- `pytest -q`: 753 passed, 38 subtests passed.
- `python -m compileall -q src tests`: OK.
