from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class RolePropertyArchitectureGuardTests(unittest.TestCase):
    """Architectural guard: no hardcoded preposition -> SOURCE lexical rule.

    The per-property YES/NO + local-contrast pipeline and the old
    ``_normalize_quantified_measure_actants`` entry point were replaced by the
    single bounded role-cue probe (see test_role_cue_1257) and the split/fuse
    quantified actant methods (see test_semantic_boundaries_1258). This guard
    remains: origin prepositions must never be turned into a direct SOURCE
    assignment by a private lexical rule.
    """

    def test_origin_prepositions_are_not_direct_source_assignments(self):
        source = (PROJECT / "src/ah/perception/adaptive_parser.py").read_text(encoding="utf-8")
        self.assertNotIn('words[0] in {"из", "от"}', source)
        self.assertNotIn('words[0] in {"от", "из"}', source)


if __name__ == "__main__":
    unittest.main()
