"""Short transport preserves the existing bounded-selection semantic contract."""
from __future__ import annotations

import itertools
import json

import pytest

from ah.formalizer.selection_labels import (
    PROTOCOL_VERSION,
    build_label_selection_prompt,
    selection_label_instructions,
    validate_selection_label_response,
)
from ah.formalizer.selection_protocol import (
    DecisionSchema,
    ProtocolError,
    Relation,
    validate_selection_response,
)


@pytest.fixture
def schema():
    return DecisionSchema("pinned-resource", {
        cid: Relation(cid, name, 2, ("X", "Y"), meaning)
        for cid, name, meaning in (
            ("sense:14", "FIRST", "declared first candidate"),
            ("sense:200", "SECOND", "declared second candidate"),
            ("sense:3", "THIRD", "declared third candidate"),
        )
    })


def test_all_selections_preserve_existing_json_outcome(schema):
    ids = tuple(schema.relations)
    for size in range(1, len(ids) + 1):
        for labels in itertools.permutations(range(1, len(ids) + 1), size):
            wire = ",".join(map(str, labels))
            selected = [ids[index - 1] for index in labels]
            outcome = "ONE_SELECTED" if size == 1 else "MULTIPLE_ADMISSIBLE"
            gold = validate_selection_response(
                json.dumps({"outcome": outcome, "selected": selected}), schema,
                allowed=frozenset(ids),
            )
            assert validate_selection_label_response(wire, schema, ids) == gold


@pytest.mark.parametrize("wire,outcome", [("?", "INSUFFICIENT_CONTEXT"), ("0", "NONE_FIT")])
def test_empty_outcomes_stay_distinct(schema, wire, outcome):
    result = validate_selection_label_response(wire, schema, tuple(schema.relations))
    assert result.outcome == outcome
    assert result.selected == ()
    assert result.note == ""


def test_mapping_uses_explicit_order_not_lexicographic_id_order(schema):
    ids = ("sense:3", "sense:14")
    assert validate_selection_label_response("1", schema, ids).selected == ("sense:3",)
    assert validate_selection_label_response("2", schema, ids).selected == ("sense:14",)


def test_allowed_ids_gate_is_still_enforced(schema):
    with pytest.raises(ProtocolError, match="outside"):
        validate_selection_label_response("2", schema, tuple(schema.relations),
                                          allowed=frozenset({"sense:14"}))


@pytest.mark.parametrize("wire", [
    "", "ONE_SELECTED", "V1", "-1", "+1", "01", "1.0", "1,1", "1,2,1",
    "0,1", "1,0", "?1", "1,?", "4", "1,4", "1,", ",1", "1 2", "1, 2",
    "1\n2", "1\nexplanation", "```\n1\n```", "[1]", "{\"selected\":[\"sense:14\"]}",
    "１", "1e0", "9" * 10_000, None, 1, True,
])
def test_invalid_wire_is_rejected_without_json_or_prose_fallback(schema, wire):
    with pytest.raises(ProtocolError):
        validate_selection_label_response(wire, schema, tuple(schema.relations))


def test_outer_whitespace_does_not_change_selection(schema):
    assert validate_selection_label_response(" \n2\r\n", schema, tuple(schema.relations)).selected == ("sense:200",)


def test_large_closed_set_rejects_overlong_integer_as_protocol_error():
    ids = tuple(f"candidate:{index}" for index in range(1, 1101))
    schema = DecisionSchema("large-closed-set", {
        cid: Relation(cid, cid, 0, (), "declared candidate") for cid in ids
    })
    # This fits the total reply-length envelope for 1100 candidates, but it is
    # neither a valid ordinal nor safe to pass to int's global conversion limit.
    with pytest.raises(ProtocolError, match="outside"):
        validate_selection_label_response("9" * 4301, schema, ids)
    assert validate_selection_label_response("1100", schema, ids).selected == (ids[-1],)


@pytest.mark.parametrize("wire", ["0", "?"])
def test_empty_candidate_set_can_only_abstain(schema, wire):
    assert validate_selection_label_response(wire, schema, ()).selected == ()
    with pytest.raises(ProtocolError):
        validate_selection_label_response("1", schema, ())


@pytest.mark.parametrize("ids", [("sense:14", "sense:14"), ("unknown",), ("",), (1,), "sense:14", {"sense:14"}])
def test_invalid_label_assignment_is_rejected(schema, ids):
    with pytest.raises(ValueError):
        validate_selection_label_response("1", schema, ids)


def test_prompt_preserves_declared_context_and_closed_candidate_mapping(schema):
    prompt = build_label_selection_prompt(
        slot_id="predicate_value", frame_id="F1", context_span="Текст входа",
        mentions={"X": "явное упоминание"}, schema=schema,
        contextual_statements=("declared C statement",), candidates=("sense:3", "sense:14"),
    )
    assert PROTOCOL_VERSION in prompt
    assert "Текст входа" in prompt
    assert "явное упоминание" in prompt
    assert "declared C statement" in prompt
    assert "declared third candidate" in prompt
    assert '1 = "sense:3"' in prompt
    assert '2 = "sense:14"' in prompt
    assert "sense:200" not in prompt
    assert "Insufficient context: ? (INSUFFICIENT_CONTEXT)" in prompt
    assert "No candidate fits: 0 (NONE_FIT)" in prompt
    assert "No JSON" in prompt


def test_empty_mapping_is_explicit():
    assert "(empty candidate set)" in selection_label_instructions(())
