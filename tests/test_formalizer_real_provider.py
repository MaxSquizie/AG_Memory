# -*- coding: utf-8 -*-
"""WP4.1 — real local-provider bridge (V7 §14).

Hermetic: no live model is required. A stub backend duck-types the product contract
``generate(prompt, *, system=..., role=..., override=...) -> obj(.text)`` so we can prove the bridge and its
honest-degradation behavior without Ollama/LMStudio running. The same RealBackendSelector is what a
live backend (via ``selector_from_config``) plugs into; authored JSON fixtures
explicitly select the legacy JSON wire rather than relying on production defaults.
"""

import json
import unittest

from ah.formalizer.provider_adapter import ProviderUnavailable
from ah.formalizer.pipeline import run as pipeline_run
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.selection_protocol import load_decision_schema


class _Resp:
    def __init__(self, text):
        self.text = text


class StubBackend:
    """Duck-typed stand-in for Ollama/LMStudio/AndroidNpu backends."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = 0

    def generate(self, prompt, *, system="", role="", override=None):
        self.calls += 1
        return _Resp(self._responder(prompt))


def _json(outcome, selected, note=""):
    return json.dumps({"outcome": outcome, "selected": selected, "note": note}, ensure_ascii=False)


class RealProviderBridgeTest(unittest.TestCase):
    def test_bridge_returns_backend_text_and_replays(self):
        backend = StubBackend(lambda p: _json("ONE_SELECTED", ["V1"], "stub"))
        sel = RealBackendSelector(backend, structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        sel.start_run("recorded-bridge-run")
        first = sel.select("some prompt")
        self.assertEqual(first, _json("ONE_SELECTED", ["V1"], "stub"))
        # Replay starts the same durable run at ordinal 1. A consecutive call in
        # a running execution has a new ordinal and is not a replay cache hit.
        sel.start_run("recorded-bridge-run")
        again = sel.select("some prompt")
        self.assertEqual(again, first)
        self.assertEqual(backend.calls, 1)

    def test_unavailable_backend_raises_provider_unavailable(self):
        def boom(_prompt):
            raise ConnectionError("connection refused (no local model)")

        backend = StubBackend(boom)
        sel = RealBackendSelector(backend, structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        with self.assertRaises(ProviderUnavailable):
            sel.select("some prompt")

    def test_pipeline_honest_miss_on_outage(self):
        # A live-model outage must degrade to an honest PROVIDER_UNAVAILABLE miss — deterministic
        # candidates continue; it is never silently turned into AMBIGUOUS or a fabricated selection.
        def boom(_prompt):
            raise ConnectionError("down")

        sel = RealBackendSelector(StubBackend(boom), structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        schema = load_decision_schema()
        st = pipeline_run("У вороны есть лапки.", schema, sel)
        codes = {d.code for d in st.diagnostics}
        self.assertIn("PROVIDER_UNAVAILABLE", codes)
        pred = [d for d in st.decisions.values() if d.slot_id == "predicate_value"]
        self.assertTrue(pred, "a predicate decision must still exist (honest miss, not a crash)")
        self.assertEqual(list(pred[0].selected), [])  # nothing selected from the model

    def test_real_style_response_flows_through_t3_t4(self):
        # A well-formed real-model response (ONE_SELECTED V1) flows through T3/T4 exactly like the
        # deterministic dry run: the selection is recorded and no provider diagnostic is raised.
        backend = StubBackend(lambda p: _json("ONE_SELECTED", ["V1"], "textual ground"))
        sel = RealBackendSelector(backend, structure_reply_format="JSON_V1", selection_reply_format="JSON_V1")
        schema = load_decision_schema()
        st = pipeline_run("У меня есть книга.", schema, sel)
        codes = {d.code for d in st.diagnostics}
        self.assertNotIn("PROVIDER_UNAVAILABLE", codes)
        pred = [d for d in st.decisions.values() if d.slot_id == "predicate_value"]
        self.assertTrue(pred)
        self.assertIn("V1", list(pred[0].selected))


if __name__ == "__main__":
    unittest.main()
