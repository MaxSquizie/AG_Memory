# -*- coding: utf-8 -*-
"""Acceptance tests for clause detection (V7 §6.2/§15): paired boundaries for IF + embedded propositions."""

import unittest

from ah.formalizer.clause_detection import (
    Token, detect_clauses, paired_boundaries, IF, COMPLEMENT, RELATIVE, MATRIX,
)


def toks(*items):
    """Build tokens from bare strings or (text, pos) tuples."""
    out = []
    for it in items:
        if isinstance(it, tuple):
            text = it[0]
            pos = it[1] if len(it) > 1 else None
        else:
            text, pos = it, None
        out.append(Token(text, pos))
    return out


class TestClauseDetection(unittest.TestCase):
    def test_single_clause_is_honest(self):
        s = detect_clauses(toks("Ворона", "сидит", "."))
        self.assertTrue(s.is_single)
        self.assertEqual(len(s.clauses), 1)
        self.assertEqual(paired_boundaries(s), [])

    def test_sub_first_conditional_pairs_antecedent_consequent(self):
        # «Если идёт дождь, зонт нужен.» -> IF antecedent + main consequent.
        s = detect_clauses(toks("Если", "идёт", "дождь", ",", "зонт", "нужен", "."))
        self.assertFalse(s.is_single)
        kinds = [c.opener for c in s.clauses]
        self.assertIn(IF, kinds)
        pairs = paired_boundaries(s)
        self.assertEqual(len(pairs), 1)
        ant, cons = pairs[0]
        self.assertEqual(s.clauses[ant].opener, IF)          # antecedent is the conditional
        self.assertEqual(s.clauses[cons].opener, MATRIX)     # consequent is the main clause

    def test_main_first_conditional(self):
        # «Зонт нужен, если идёт дождь.» -> main then trailing IF.
        s = detect_clauses(toks("Зонт", "нужен", ",", "если", "идёт", "дождь", "."))
        pairs = paired_boundaries(s)
        self.assertEqual(len(pairs), 1)
        ant, cons = pairs[0]
        self.assertEqual(s.clauses[ant].opener, IF)
        self.assertEqual(s.clauses[cons].opener, MATRIX)

    def test_relative_clause_no_false_if(self):
        s = detect_clauses(toks("Книга", "которую", "я", "читал", "интересная"))
        kinds = [c.opener for c in s.clauses]
        self.assertIn(RELATIVE, kinds)
        self.assertEqual(paired_boundaries(s), [])   # relative is not a conditional pair

    def test_tagged_complementizer_chto(self):
        # Tagged «что» (CONJ_SUB) opens a complement clause; untagged it would not.
        s = detect_clauses(toks(("Он", "NN"), ("сказал", "VB"), ("что", "CONJ_SUB"), ("ушёл", "VB")))
        kinds = [c.opener for c in s.clauses]
        self.assertIn(COMPLEMENT, kinds)

    def test_untagged_chto_is_not_an_opener(self):
        # Ambiguous «что» without a tag is NOT treated as a subordinator (honest).
        s = detect_clauses(toks("Я", "вижу", "что"))
        self.assertTrue(s.is_single)

    def test_empty_input(self):
        s = detect_clauses([])
        self.assertEqual(len(s.clauses), 0)


class TestClauseDetectionWiring(unittest.TestCase):
    """detect_clauses feeds the interrogative compiler: IF compiles only with real paired boundaries."""

    def test_if_compiles_with_detected_pair(self):
        from ah.formalizer.interrogatives import compile, CLAUSE_DETECTION_REQUIRED
        s = detect_clauses(toks("Если", "идёт", "дождь", ",", "зонт", "нужен"))
        q = compile("IF", clause_detector=s)
        self.assertEqual(q.status, "COMPILED")   # a real IF pair exists

    def test_if_stays_unbound_for_single_clause(self):
        from ah.formalizer.interrogatives import compile, CLAUSE_DETECTION_REQUIRED
        s = detect_clauses(toks("Ворона", "сидит"))
        q = compile("IF", clause_detector=s)
        self.assertEqual((q.status, q.reason), ("QUERY_TARGET_UNBOUND", CLAUSE_DETECTION_REQUIRED))


if __name__ == "__main__":
    unittest.main()
