# -*- coding: utf-8 -*-
"""Real-backend seam (V7 §14 / WP4.1): prove the live LLM adapter is a drop-in for the same interface.

These legacy-wire fixtures consume ``selector.select(prompt) -> raw JSON``;
they explicitly pin ``JSON_V1`` instead of relying on production defaults.
:class:`RealBackendSelector` wraps ANY product backend
(``backend.generate(prompt, system=..., role=..., override=...) -> obj(.text)``) behind that one-argument contract, logged via the
ProviderAdapter (replay + integrity). These tests use **stub backends** (no live model) to prove the seam end-to-end:

- a NONE_FIT stub drives honest NO_CANDIDATE misses through the full S1–S6 vertical (the C3 measurement surface);
- an outage degrades honestly — decisions stay *un-evaluated* with PROVIDER_UNAVAILABLE, never conflated into AMBIGUOUS/RESOLVED.

When a local Ollama/LMStudio is reachable, ``selector_from_config`` + :func:`run_s1s6` run unchanged; these tests pin that
the code path they exercise is correct without requiring the model to be up.
"""

import json
import unittest


class _Resp:
    def __init__(self, text):
        self.text = text


class _StubBackend:
    """A product-backend stand-in exposing only ``generate(prompt, *, system=..., role=...) -> obj(.text)``."""

    def __init__(self, payload_json: str):
        self._payload = payload_json
        self.calls = 0

    def generate(self, prompt, *, system=None, role=None, override=None):
        self.calls += 1
        return _Resp(self._payload)


class _FailingBackend:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, system=None, role=None, override=None):
        self.calls += 1
        raise RuntimeError("backend down")


_NONE_FIT = json.dumps({"outcome": "NONE_FIT", "selected": [], "note": "stub: no declared relation fits"})


class TestRealBackendSeam(unittest.TestCase):
    def test_none_fit_stub_drives_honest_misses_end_to_end(self):
        from ah.formalizer.real_backend import RealBackendSelector, run_s1s6

        backend = _StubBackend(_NONE_FIT)
        sel = RealBackendSelector(backend, structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        report = run_s1s6(sel, mode="baseline")

        self.assertEqual(len(report), 6)
        self.assertGreater(backend.calls, 0)          # the real adapter path actually executed
        for _text, outcome, selected, _diags in report:
            self.assertIsNotNone(outcome)             # a predicate_value decision exists per sentence
            self.assertEqual(outcome, "NO_CANDIDATE")  # NONE_FIT (search complete) -> honest miss
            self.assertEqual(selected, [])

    def test_outage_degrades_honestly_never_a_verdict(self):
        from ah.formalizer.real_backend import RealBackendSelector, run_s1s6

        sel = RealBackendSelector(_FailingBackend(), structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        report = run_s1s6(sel, mode="baseline")

        self.assertEqual(len(report), 6)
        for _text, outcome, selected, diags in report:
            # A computational failure is NOT a semantic verdict (§0.8/§1.4): the decision stays un-evaluated.
            self.assertIsNone(outcome)
            self.assertNotIn("AMBIGUOUS", [outcome])
            self.assertIn("PROVIDER_UNAVAILABLE", diags)


if __name__ == "__main__":
    unittest.main()
