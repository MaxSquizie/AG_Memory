# -*- coding: utf-8 -*-
"""Protocol tests for the bounded-selection micro-shot (docs §8.2, frozen v1)."""

from __future__ import annotations

import json
import unittest

from ah.formalizer.selection_protocol import (
    OUTCOMES,
    ProtocolError,
    build_selection_prompt,
    candidates_for_slot,
    load_decision_schema,
    validate_selection_response,
)


class SelectionProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_decision_schema()

    # -- schema -------------------------------------------------------------

    def test_schema_v1_has_four_relations(self):
        self.assertEqual(self.schema.version, "v1")
        self.assertEqual(set(self.schema.relations), {"V1", "V2", "V3", "V4"})
        self.assertEqual(
            {r.name for r in self.schema.relations.values()},
            {"HAVE", "HAS_PART", "LOCATIVE", "LIKE"},
        )

    # -- prompt builder -----------------------------------------------------

    def test_prompt_follows_english_template(self):
        prompt = build_selection_prompt(
            slot_id="predicate_value",
            frame_id="F1",
            context_span="У вороны есть лапки.",
            mentions={"X": "ворона (GEN after 'у')", "Y": "лапки (NOM pl)"},
            schema=self.schema,
        )
        self.assertIn("Decision slot: predicate_value — predicate value of frame F1", prompt)
        self.assertIn("Context span: У вороны есть лапки.", prompt)
        self.assertIn("Mentions and preliminary structural links:", prompt)
        self.assertIn(f"Candidates (schema {self.schema.version}, closed set):", prompt)
        for rel in ("V1. HAVE", "V2. HAS_PART", "V3. LOCATIVE", "V4. LIKE"):
            self.assertIn(rel, prompt)
        # No final roles are asserted: participants stay preliminary links.
        self.assertNotIn("roles from the committed frame", prompt)

    def test_prompt_states_cardinality_rules(self):
        prompt = build_selection_prompt(
            slot_id="s", frame_id="f", context_span="c", mentions={"X": "x"}, schema=self.schema
        )
        self.assertIn("exactly one selected id", prompt)
        self.assertIn("at least two distinct ids", prompt)

    # -- validator: happy paths ---------------------------------------------

    def _ok(self, outcome, selected):
        return json.dumps({"outcome": outcome, "selected": selected})

    def test_one_selected_single_id(self):
        r = validate_selection_response(self._ok("ONE_SELECTED", ["V2"]), self.schema)
        self.assertEqual(r.selected, ("V2",))
        self.assertEqual(r.outcome, "ONE_SELECTED")  # protocol outcome only

    def test_multiple_admissible_two_ids(self):
        r = validate_selection_response(self._ok("MULTIPLE_ADMISSIBLE", ["V1", "V2"]), self.schema)
        self.assertEqual(set(r.selected), {"V1", "V2"})
        self.assertEqual(r.outcome, "MULTIPLE_ADMISSIBLE")

    def test_insufficient_context_empty_keeps_own_status(self):
        r = validate_selection_response(self._ok("INSUFFICIENT_CONTEXT", []), self.schema)
        self.assertEqual(r.selected, ())
        self.assertEqual(r.outcome, "INSUFFICIENT_CONTEXT")

    def test_none_fit_is_a_protocol_outcome_not_a_semantic_one(self):
        # rev7b: the validator NEVER grants a semantic outcome. NONE_FIT is a protocol
        # refusal; T4 (joint validation) maps it to NO_CANDIDATE + miss report.
        r = validate_selection_response(self._ok("NONE_FIT", []), self.schema)
        self.assertEqual(r.outcome, "NONE_FIT")
        self.assertNotIn("NO_CANDIDATE", type(r).__dataclass_fields__)

    def test_validator_never_grants_semantic_outcomes(self):
        # rev7b regression: no field of the verified response may carry a semantic
        # outcome (RESOLVED/UNRESOLVED/...) — that grant belongs to T4 only.
        for raw in (self._ok("ONE_SELECTED", ["V2"]), self._ok("NONE_FIT", [])):
            r = validate_selection_response(raw, self.schema)
            fields = {f.name: getattr(r, f.name) for f in r.__dataclass_fields__.values()}
            for value in fields.values():
                self.assertNotIn("RESOLVED", str(value))
            self.assertNotIn("contract_outcome", vars(type(r)))

    # -- validator: protocol errors (rejected call, not mechanism violation) -

    def _expect_protocol_error(self, raw):
        with self.assertRaises(ProtocolError):
            validate_selection_response(raw, self.schema)

    def test_malformed_json_rejected(self):
        self._expect_protocol_error('{"outcome": "ONE_SELECTED",')

    def test_non_object_rejected(self):
        self._expect_protocol_error('["V1"]')

    def test_unknown_outcome_rejected(self):
        self._expect_protocol_error(json.dumps({"outcome": "MAYBE", "selected": []}))

    def test_unknown_id_rejected(self):
        self._expect_protocol_error(self._ok("ONE_SELECTED", ["V9"]))

    def test_selected_must_be_list_of_strings(self):
        self._expect_protocol_error(json.dumps({"outcome": "NONE_FIT", "selected": "V1"}))

    def test_one_selected_cardinality_violation(self):
        self._expect_protocol_error(self._ok("ONE_SELECTED", ["V1", "V2"]))

    def test_multiple_admissible_requires_two_distinct(self):
        self._expect_protocol_error(self._ok("MULTIPLE_ADMISSIBLE", ["V1"]))
        # duplicates do not count as distinct candidates
        self._expect_protocol_error(self._ok("MULTIPLE_ADMISSIBLE", ["V1", "V1"]))

    def test_none_fit_with_selection_rejected(self):
        self._expect_protocol_error(self._ok("NONE_FIT", ["V3"]))

    def test_outcomes_enum_is_closed(self):
        self.assertEqual(set(OUTCOMES), {"ONE_SELECTED", "MULTIPLE_ADMISSIBLE",
                                         "INSUFFICIENT_CONTEXT", "NONE_FIT"})

    # -- rev8: per-decision closed set ---------------------------------------

    def test_candidates_for_slot_follows_declared_rule(self):
        # All four demo relations are binary -> all four are candidates for a binary slot.
        self.assertEqual(candidates_for_slot(self.schema, 2), ("V1", "V2", "V3", "V4"))
        # A provably incompatible arity is excluded by the rule itself:
        self.assertEqual(candidates_for_slot(self.schema, 3), ())

    def test_id_in_schema_but_outside_decision_candidates_rejected(self):
        # rev8 (D1): V3 exists in the schema but not in THIS decision's closed set ->
        # selecting it is a protocol error even though the id itself is known.
        with self.assertRaises(ProtocolError):
            validate_selection_response(
                self._ok("ONE_SELECTED", ["V3"]), self.schema, allowed=frozenset({"V1", "V2"}))

    def test_prompt_lists_only_the_decision_candidates(self):
        prompt = build_selection_prompt(
            slot_id="s", frame_id="f", context_span="c", mentions={"X": "x"},
            schema=self.schema, candidates=("V1", "V2"),
        )
        self.assertIn("V1. HAVE", prompt)
        self.assertIn("V2. HAS_PART", prompt)
        self.assertNotIn("V3.", prompt)  # outside this decision's closed set
        self.assertNotIn("V4.", prompt)


if __name__ == "__main__":
    unittest.main()
