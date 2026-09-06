# Ellipsis Acceptance v2 — 100-case composite corpus

`data/acceptance_ellipsis/` is now a 100-case semantic acceptance suite.

The design rule is **interaction before repetition**: new examples should combine ellipsis with another semantic or structural mechanism whenever possible.

## Coverage families

| Family | Cases |
|---|---:|
| predicate_frame | 6 |
| role_frame | 5 |
| proposition_negation | 4 |
| proposition_confirmation | 2 |
| temporal_ellipsis | 3 |
| locative_ellipsis | 2 |
| complex_chain | 12 |
| coordination_ellipsis | 12 |
| polarity_chain | 10 |
| role_rich_chain | 10 |
| temporal_locative_combo | 10 |
| antecedent_reset | 10 |
| punctuation_ellipsis | 6 |
| scope_ellipsis | 4 |
| coreference_ellipsis | 2 |
| mixed_adversarial_ellipsis | 2 |
| **Total** | **100** |

The first 22 entries are the original v1 corpus and are retained unchanged.

## Important composite dimensions

The suite now checks not only whether a missing predicate can be copied, but also whether recovery preserves:

- proposition polarity;
- coordinated entity groups;
- role identity across richer frames;
- nearest valid antecedent instead of the first sentence predicate;
- explicit predicate reset;
- nominal-predicate boundaries;
- TIME/LOCATION/DURATION substitutions;
- embedded scope;
- coreference identity;
- punctuation boundaries;
- lexical-noise interaction.

The oracle remains implementation-independent: expected semantic structures are written from the intended reading, not copied from parser output.
