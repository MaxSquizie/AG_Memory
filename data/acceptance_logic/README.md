# Logical formalization acceptance v1

Dedicated acceptance suite for point 2: propositional logical formalization from natural language.

Coverage (33 EXACT cases):
- AND: additive and adversative conjunction;
- OR: inclusive, n-ary and semantic paraphrase;
- XOR: multiple exactly-one paraphrases, including a form with no OR keyword and n-ary exactly-one;
- local NOT versus whole-formula NOT;
- IMPLIES: fronted/postposed conditions, only-if direction, AND/OR/XOR inside branches;
- mixed AND/OR scope with explicit grouping.

The semantic oracle checks the source-level `proposition_roots` AST and, for ordinary formulae, the canonical integrated `g` shape. Conditional cases additionally check branch orientation and the existing canonical conditional path.

The suite intentionally does not authorize a keyword dictionary to decide semantics. Surface grammar may open a bounded probe, but the probe receives already-fixed proposition operands and returns only one finite label.

Ambiguous-scope fail-closed behavior is covered by `tests/test_logical_formalization_2602.py`: an unresolved relation/scope/whole-negation decision must abort formalization before Integration rather than silently assert formula leaves as independent facts.
