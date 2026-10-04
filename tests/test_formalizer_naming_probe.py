# -*- coding: utf-8 -*-
"""Tests for the V7 naming/identification port (``naming_probe.py``).

Deterministic via a stub selector; covers all three structural realizations, the NAME vs OTHER
distinction (the negative control «Я инженер» must stay an ordinary predication, never an alias), and
the probe's fail-closed validation (an invented value is rejected, not accepted).
"""

import unittest


class _Stub:
    def __init__(self, response: str):
        self._response = response

    def select(self, prompt: str) -> str:
        return self._response


def _morph():
    import pymorphy3 as pm
    return pm.MorphAnalyzer()


class TestRecognizeNaming(unittest.TestCase):
    def setUp(self):
        self.m = _morph()

    def test_verbal_naming_recognized(self):
        from ah.formalizer.naming_probe import recognize_naming
        rs = recognize_naming("Меня зовут Илья.", self.m)
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0].kind, "verbal")
        self.assertIn("Илья", rs[0].values)

    def test_deictic_predication_recognized(self):
        from ah.formalizer.naming_probe import recognize_naming
        rs = recognize_naming("Я — Илья.", self.m)
        self.assertEqual(len(rs), 1)
        self.assertEqual(rs[0].kind, "deictic_predication")
        self.assertIn("Илья", rs[0].values)

    def test_state_deictic_recognized(self):
        from ah.formalizer.naming_probe import recognize_naming
        # «Я являюсь Ильёй» — no naming verb, but a deictic + nominal value.
        rs = recognize_naming("Я являюсь Ильёй.", self.m)
        self.assertEqual(len(rs), 1)

    def test_no_deictic_no_reading(self):
        from ah.formalizer.naming_probe import recognize_naming
        # A proper name with no first-person deictic is NOT a naming construction.
        self.assertEqual(recognize_naming("Илья любит червей.", self.m), [])


class TestNamingProbe(unittest.TestCase):
    def test_name_value(self):
        from ah.formalizer.naming_probe import NamingReading, naming_probe
        r = NamingReading(kind="deictic_predication", referent="я", values=("Илья",))
        out = naming_probe(_Stub('{"decision": "NAME_VALUE", "value": "Илья"}'), r)
        self.assertEqual(out.outcome, "NAME_VALUE")
        self.assertEqual(out.name_value, "Илья")

    def test_other_predication_negative_control(self):
        # «Я инженер»: a class/property value must stay an ordinary predication, never become an alias.
        from ah.formalizer.naming_probe import NamingReading, naming_probe
        r = NamingReading(kind="deictic_predication", referent="я", values=("инженер",))
        out = naming_probe(_Stub('{"decision": "OTHER_PREDICATION"}'), r)
        self.assertEqual(out.outcome, "OTHER_PREDICATION")
        self.assertIsNone(out.name_value)

    def test_unclear(self):
        from ah.formalizer.naming_probe import NamingReading, naming_probe
        r = NamingReading(kind="deictic_predication", referent="я", values=("Илья",))
        out = naming_probe(_Stub('{"decision": "UNCLEAR"}'), r)
        self.assertEqual(out.outcome, "UNCLEAR")

    def test_invented_value_rejected(self):
        from ah.formalizer.naming_probe import NamingReading, naming_probe, NamingProtocolError
        r = NamingReading(kind="deictic_predication", referent="я", values=("Илья",))
        with self.assertRaises(NamingProtocolError):
            naming_probe(_Stub('{"decision": "NAME_VALUE", "value": "Петр"}'), r)

    def test_non_json_rejected(self):
        from ah.formalizer.naming_probe import NamingReading, naming_probe, NamingProtocolError
        r = NamingReading(kind="deictic_predication", referent="я", values=("Илья",))
        with self.assertRaises(NamingProtocolError):
            naming_probe(_Stub("sure, it is Ilya"), r)

    def test_fenced_json_accepted(self):
        # Real small models wrap the payload in a single markdown code fence; that transport
        # convention must be normalized (shared _strip_code_fence), not rejected.
        from ah.formalizer.naming_probe import NamingReading, naming_probe
        r = NamingReading(kind="deictic_predication", referent="я", values=("Илья",))
        out = naming_probe(_Stub('```json\n{"decision": "NAME_VALUE", "value": "Илья"}\n```'), r)
        self.assertEqual(out.outcome, "NAME_VALUE")
        self.assertEqual(out.name_value, "Илья")

    def test_run_naming_end_to_end(self):
        from ah.formalizer.naming_probe import run_naming
        out = run_naming("Меня зовут Илья.", _Stub('{"decision": "NAME_VALUE", "value": "Илья"}'), morph=_morph())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].outcome, "NAME_VALUE")
        self.assertEqual(out[0].name_value, "Илья")


if __name__ == "__main__":
    unittest.main()
