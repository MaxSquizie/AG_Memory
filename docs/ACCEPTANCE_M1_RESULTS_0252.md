# M1 adversarial acceptance review (v0.25.2)

Observed run:

- Cases: 36
- Runtime OK: 36
- Semantic PASS: 9
- Semantic FAIL: 27

Families:

## Typo noise

10/10 failed.

Classification:
CAPABILITY BOUNDARY.

Reason:
Current semantic pipeline expects normalized lexical input.
Future solution: Lexical Recovery layer.

## Inversion

9/10 passed.

Remaining failure:
duration attachment:

Example:
"Два часа книгу читал Иван."

Classification:
local role extraction issue, not inversion.

## Ellipsis

10/10 failed.

Classification:
missing discourse reconstruction capability.

Required next capability:
frame completion / proposition reconstruction before canonical commit.

Examples:

"Иван прочитал книгу, а Мария — журнал."

"Ivan bought a book, Maria did not."

## Mixed noise

Combination failures expected until lexical recovery and ellipsis reconstruction exist.

This document separates implementation bugs from missing capabilities.
