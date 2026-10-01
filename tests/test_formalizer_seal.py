# -*- coding: utf-8 -*-
"""Seal-stage tests (V7 §4.3 / WP1.1) — closure validation + deterministic structural hash."""

import unittest

from ah.formalizer.seal import SealError, structural_hash, structural_seal, validate_closure
from ah.formalizer.state import FrameCandidate, FormalizationState, TokenEvidence


def _state_with_frames(frames):
    st = FormalizationState.new("тест")
    st.evidence = [TokenEvidence(span="вороны"), TokenEvidence(span="лапки")]
    st.frames = list(frames)
    return st


class TestSealClosure(unittest.TestCase):
    def test_wellformed_set_seals_clean(self):
        st = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                               participants=("вороны", "лапки"))])
        self.assertEqual(validate_closure(st), ())
        res = structural_seal(st)
        self.assertTrue(res.closed)
        self.assertEqual(res.object_counts["frame"], 1)
        self.assertIsNotNone(st.structural_hash)

    def test_dangling_participant_is_integrity_error(self):
        st = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                               participants=("вороны", "призрак"))])  # 'призрак' not observed
        with self.assertRaises(SealError):
            structural_seal(st)  # strict (default)
        self.assertTrue(st.has_diag("INTEGRITY_ERROR"))

    def test_nonstrict_records_but_returns(self):
        st = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                               participants=("призрак",))])
        res = structural_seal(st, strict=False)  # records the diagnostic, does not raise
        self.assertTrue(st.has_diag("INTEGRITY_ERROR"))
        self.assertIsNotNone(res.structural_hash)

    def test_dangling_missing_arg_frame_ref(self):
        st = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                               participants=("вороны",))])
        from ah.formalizer.state import MissingArgumentCandidate
        st.missing_argument_candidates.append(
            MissingArgumentCandidate(candidate_id="MA1", frame_ref="NOPE"))  # unknown frame
        self.assertTrue(any("frame_ref" in d for d in validate_closure(st)))


class TestSealHash(unittest.TestCase):
    def test_hash_is_deterministic_and_identity_stable(self):
        a = structural_seal(_state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT",
                                                               anchor_span="вороны", participants=("вороны",))]))
        b = structural_seal(_state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT",
                                                               anchor_span="вороны", participants=("вороны",))]))
        self.assertEqual(a.structural_hash, b.structural_hash)

    def test_structure_change_changes_hash(self):
        base = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                                 participants=("вороны", "лапки"))])
        other = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                                  participants=("вороны",))])  # one fewer participant
        self.assertNotEqual(structural_hash(base), structural_hash(other))

    def test_seal_freezes_structures(self):
        st = _state_with_frames([FrameCandidate(frame_id="F1", kind="FLAT", anchor_span="вороны",
                                               participants=("вороны",))])
        structural_seal(st)
        self.assertTrue(st.structural_closed)
        with self.assertRaises(RuntimeError):  # I30: no new structure after the seal
            st.require_structures_open("T3")


if __name__ == "__main__":
    unittest.main()
