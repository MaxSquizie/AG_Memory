"""General regressions for the final ellipsis acceptance boundary."""

import pytest

from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception.morphology import Pymorphy3Morphology
from test_general_formalization_02517 import (
    GraphEllipsisFixture,
    by_predicate,
    parser,
    roles,
)


class SequenceFixture(GraphEllipsisFixture):
    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_role_cue":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            if target in {"потом", "затем"}:
                self.calls.append((role, prompt))
                return LLMResponse("TIME_POINT", {})
        if role == "semantic_transition_operator":
            self.calls.append((role, prompt))
            return LLMResponse("NONE", {})
        return super().generate(prompt, system=system, override=override, role=role)


class ScopedEventFixture(GraphEllipsisFixture):
    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "semantic_nonfinite_assertion_status":
            self.calls.append((role, prompt))
            return LLMResponse("SCOPED_EVENT", {})
        if role == "semantic_transition_operator":
            self.calls.append((role, prompt))
            return LLMResponse("CONTINUE", {})
        return super().generate(prompt, system=system, override=override, role=role)


@pytest.fixture(scope="module")
def morphology():
    return Pymorphy3Morphology()


def test_sequence_marker_does_not_choose_one_pair_between_parallel_blocks(morphology):
    parsed = parser(morphology, SequenceFixture()).parse(
        "Лев починил мотор, Нина — насос; потом Глеб проверил схему, а Лев — макет."
    )
    assert parsed.perception.relations == ()
    assert len(parsed.perception.assertions) == 4
    assert all(
        ActantRole.TIME not in roles(assertion)
        for assertion in parsed.perception.assertions
    )


def test_sequence_marker_keeps_follow_for_one_unambiguous_pair(morphology):
    parsed = parser(morphology, SequenceFixture()).parse(
        "Лев починил мотор; потом Глеб проверил насос."
    )
    assert [
        (item.relation_id, item.source_ref, item.target_ref)
        for item in parsed.perception.relations
    ] == [("FOLLOW", "A1", "A2")]
    assert all(
        ActantRole.TIME not in roles(assertion)
        for assertion in parsed.perception.assertions
    )


def test_post_predicate_marker_remains_an_entity_valued_time(morphology):
    parsed = parser(morphology, SequenceFixture()).parse(
        "Лев проверил насос потом."
    )
    time = roles(parsed.perception.assertions[0])[ActantRole.TIME]
    assert time.lookup_text == "потом"


def test_scoped_nonfinite_event_becomes_transition_and_is_cloned(morphology):
    backend = ScopedEventFixture()
    parsed = parser(morphology, backend).parse(
        "Лев продолжил проверять мотор, а Нина — насос."
    )
    matrices = by_predicate(parsed, "продолжить")
    children = by_predicate(parsed, "проверять")
    assert matrices == []
    assert len(children) == 2
    assert [item.status.value for item in children] == ["ASSERTED", "ASSERTED"]
    assert [item.temporal_mode.value for item in children] == ["TRANSITION", "TRANSITION"]
    assert [item.transition_operator.value for item in children] == ["CONTINUE", "CONTINUE"]
    assert any(
        role == "semantic_nonfinite_assertion_status"
        and "SCOPED_EVENT" in prompt
        for role, prompt in backend.calls
    )
    assert sum(role == "semantic_transition_operator" for role, _ in backend.calls) == 1
