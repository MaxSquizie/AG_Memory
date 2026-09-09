from __future__ import annotations

import unittest

from ah.gui.perception_timeline import format_parser_decoded_history, format_parser_raw_history
from ah.perception import PerceptionAttemptDiagnostic, PerceptionDiagnostic, PerceptionResult


class PerceptionTimelineFormattingTests(unittest.TestCase):
    def test_parser_raw_history_keeps_all_calls_and_numbers_steps(self) -> None:
        history = (
            PerceptionDiagnostic(
                sequence=1,
                source_text="Что Иван любит?",
                attempts=(
                    PerceptionAttemptDiagnostic(
                        role="act_type",
                        raw_text="QUERY",
                        normalized_answer="QUERY",
                    ),
                    PerceptionAttemptDiagnostic(
                        role="role_cue",
                        raw_text="AFFECTED_OR_CONTENT",
                        normalized_answer="AFFECTED_OR_CONTENT",
                    ),
                ),
                decoded=PerceptionResult(source_text="Что Иван любит?"),
            ),
            PerceptionDiagnostic(
                sequence=2,
                source_text="Что Иван любит?",
                attempts=(
                    PerceptionAttemptDiagnostic(
                        role="template_sense",
                        raw_text="maybe C1",
                        error="template_sense expected exactly one of: C1, NEW, UNCLEAR",
                    ),
                ),
                decoded=None,
                final_error="template_sense expected exactly one of: C1, NEW, UNCLEAR",
            ),
        )

        raw = format_parser_raw_history(history, turn_source_text="Что Иван любит?")
        self.assertIn("PERCEPTION CALL 1/2", raw)
        self.assertIn("PERCEPTION CALL 2/2", raw)
        self.assertIn("adaptive semantic parse", raw)
        self.assertIn("lexical template sense", raw)
        self.assertIn("STEP 1: act_type — OK", raw)
        self.assertIn("STEP 3: template_sense", raw)
        self.assertIn("WHY IT FAILED:", raw)
        self.assertIn("TURN PERCEPTION STATUS: FAILED", raw)

        decoded = format_parser_decoded_history(history)
        self.assertEqual(decoded["status"], "FAILED")
        self.assertEqual(len(decoded["calls"]), 2)
        self.assertEqual(decoded["calls"][0]["status"], "OK")
        self.assertEqual(
            decoded["calls"][1]["phase"],
            "post-parse: lexical template sense (orchestrator)",
        )


if __name__ == "__main__":
    unittest.main()
