"""General regressions for graph-level ellipsis and repeated-frame completion.

The fixtures answer only bounded semantic questions.  Parser, graph recovery,
identity propagation, completion, and Integration all remain production code.
"""
from pathlib import Path

import pytest

from ah.config import LLMRoleSettings
from ah.integration.template_completion import TemplateCompletionService
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception import LLMPerceptionService, LLMPerceptionSettings
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import Pymorphy3Morphology
from legacy_semantic_fixture import legacy_semantic_answer
from test_ellipsis_canonical_02513 import runtime


ROOT = Path(__file__).resolve().parents[1]


class GraphEllipsisFixture:
    """Finite source-only answers for several unrelated lexical realizations."""

    subjects = {"лев", "нина", "глеб"}
    objects = {
        "мотор", "насос", "ключ", "его", "карту", "схему", "макет", "шлюз",
        "отчёт",
    }
    recipients = {"нину", "веру"}
    places = {"в ящик", "на полку"}

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt))
        if role == "perception_role_cue":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            answer = (
                "ACTOR_OR_EXPERIENCER" if target in self.subjects
                else "AFFECTED_OR_CONTENT" if target in self.objects
                else "RECEIVER_OR_ADDRESSEE" if target in self.recipients
                else "PLACE" if target in self.places
                else None
            )
            if answer is not None:
                return LLMResponse(answer, {})
        if role == "perception_frame_relation":
            return LLMResponse("CONTENT_LINK", {})
        if role == "semantic_nonfinite_assertion_status":
            return LLMResponse("NONASSERTED_CONTENT", {})
        if role == "perception_control_subject":
            participants = prompt.split("PARTICIPANTS:\n", 1)[1].split(
                "\nCHOICES:", 1
            )[0]
            for line in participants.splitlines():
                if any(name in line.casefold() for name in ("нина", "вера")):
                    return LLMResponse(line.split("=", 1)[0].strip(), {})
            return LLMResponse("UNCLEAR", {})
        if role == "perception_modifier_attachment":
            return LLMResponse("EVENT", {})
        if role == "perception_coordination_shared_actant":
            return LLMResponse("LOCAL", {})
        if role == "perception_lexeme_comparison":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            wanted = {"полку": "полка"}.get(target)
            for label in ("A", "B"):
                lemma = prompt.split(f"{label} LEMMA:\n", 1)[1].split("\n", 1)[0]
                if lemma.casefold() == wanted:
                    return LLMResponse(label, {})
        if role == "perception_lexeme_identity":
            return LLMResponse("DIFFERENT", {})
        if role == "perception_act_relation":
            return LLMResponse("NONE", {})
        fallback = legacy_semantic_answer(role, prompt)
        if fallback is not None:
            return LLMResponse(str(fallback), {})
        raise AssertionError(f"unspecified bounded fixture: {role}\n{prompt[:900]}")


@pytest.fixture(scope="module")
def morphology():
    return Pymorphy3Morphology()


def parser(morphology, backend=None):
    return AdaptivePerceptionParser(
        backend or GraphEllipsisFixture(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


def roles(assertion):
    return {item.role: item for item in assertion.actants}


def by_predicate(result, predicate):
    return [
        item
        for item in result.perception.assertions
        if item.predicate.lookup_form == predicate
    ]


def test_zero_predicate_tail_clones_complete_matrix_content_subgraph(morphology):
    parsed = parser(morphology).parse(
        "Лев хочет проверить мотор, а Нина — насос."
    )
    matrices = by_predicate(parsed, "хотеть")
    children = by_predicate(parsed, "проверить")
    assert len(matrices) == len(children) == 2
    assert [item.status.value for item in matrices] == ["ASSERTED", "ASSERTED"]
    assert [item.status.value for item in children] == ["EMBEDDED", "EMBEDDED"]
    for matrix, child, subject, obj in zip(
        matrices, children, ("Лев", "Нина"), ("мотор", "насос")
    ):
        matrix_roles = roles(matrix)
        child_roles = roles(child)
        assert matrix_roles[ActantRole.SUBJECT].lookup_text == subject
        assert matrix_roles[ActantRole.OBJECT].candidate_ref == child.local_id
        assert child_roles[ActantRole.OBJECT].lookup_text == obj
        assert child_roles[ActantRole.SUBJECT].entity_ref == (
            matrix_roles[ActantRole.SUBJECT].entity_ref
        )


def test_cloned_control_graph_replaces_controller_and_content_together(morphology):
    parsed = parser(morphology).parse(
        "Лев попросил Нину проверить мотор, а Глеб — Веру насос."
    )
    matrices = by_predicate(parsed, "попросить")
    children = by_predicate(parsed, "проверить")
    assert len(matrices) == len(children) == 2
    for matrix, child, subject, recipient, obj in zip(
        matrices,
        children,
        ("Лев", "Глеб"),
        ("Нина", "Вера"),
        ("мотор", "насос"),
    ):
        matrix_roles = roles(matrix)
        child_roles = roles(child)
        assert matrix_roles[ActantRole.SUBJECT].lookup_text == subject
        assert matrix_roles[ActantRole.RECIPIENT].lookup_text == recipient
        assert matrix_roles[ActantRole.OBJECT].candidate_ref == child.local_id
        assert child_roles[ActantRole.OBJECT].lookup_text == obj
        assert child_roles[ActantRole.SUBJECT].entity_ref == (
            matrix_roles[ActantRole.RECIPIENT].entity_ref
        )


def test_selected_root_keeps_its_descendants_beside_an_independent_frame(morphology):
    parsed = parser(morphology).parse(
        "Лев попросил Нину проверить мотор и записал отчёт, а Глеб — Веру насос."
    )
    matrices = by_predicate(parsed, "попросить")
    children = by_predicate(parsed, "проверить")
    independent = by_predicate(parsed, "записать")
    assert len(matrices) == len(children) == 2
    assert len(independent) == 1
    recovered_matrix = matrices[1]
    recovered_child = children[1]
    assert roles(recovered_matrix)[ActantRole.OBJECT].candidate_ref == (
        recovered_child.local_id
    )
    assert roles(recovered_child)[ActantRole.OBJECT].lookup_text == "насос"
    assert all(
        actant.candidate_ref != children[0].local_id
        for actant in recovered_matrix.actants
    )


def test_root_selection_uses_identity_alias_not_pronoun_surface(morphology):
    parsed = parser(morphology).parse(
        "Лев нашёл ключ и положил его в ящик, а Нина — карту на полку."
    )
    found = by_predicate(parsed, "найти")
    placed = by_predicate(parsed, "положить")
    assert len(found) == 1
    assert len(placed) == 2
    source, recovered = placed
    assert roles(source)[ActantRole.OBJECT].entity_ref == roles(found[0])[
        ActantRole.OBJECT
    ].entity_ref
    assert {
        role: actant.lookup_text
        for role, actant in roles(recovered).items()
    } == {
        ActantRole.SUBJECT: "Нина",
        ActantRole.OBJECT: "карта",
        ActantRole.LOCATION: "полка",
    }


def test_inverted_slots_replace_provisional_nominal_reading(morphology):
    parsed = parser(morphology).parse(
        "Схему нарисовал Лев, а макет — Нина."
    )
    assertions = parsed.perception.assertions
    assert len(assertions) == 2
    assert {item.predicate.lookup_form for item in assertions} == {"нарисовать"}
    assert {
        role: actant.lookup_text
        for role, actant in roles(assertions[1]).items()
    } == {
        ActantRole.SUBJECT: "Нина",
        ActantRole.OBJECT: "макет",
    }


def test_independent_nominal_predication_survives_strong_punctuation(morphology):
    parsed = parser(morphology).parse("Лев починил мотор; Нина — инженер.")
    assert [item.predicate.lookup_form for item in parsed.perception.assertions] == [
        "починить",
        "инженер",
    ]


@pytest.mark.parametrize("separator", [".", ";"])
def test_parallel_frame_can_continue_across_strong_punctuation(morphology, separator):
    parsed = parser(morphology).parse(
        f"Лев починил мотор{separator} Нина — насос."
    )
    assert [item.predicate.lookup_form for item in parsed.perception.assertions] == [
        "починить",
        "починить",
    ]
    assert roles(parsed.perception.assertions[1])[ActantRole.OBJECT].lookup_text == "насос"


def test_repeated_finite_predicate_inherits_missing_contrastive_slots(morphology):
    parsed = parser(morphology).parse(
        "Лев не открыл шлюз, а Нина — открыла."
    )
    source, target = parsed.perception.assertions
    assert source.negated is True
    assert target.negated is False
    assert roles(source)[ActantRole.OBJECT].entity_ref == roles(target)[
        ActantRole.OBJECT
    ].entity_ref
    assert any(trace.stage == "contrastive_repeated_frame" for trace in parsed.traces)


@pytest.mark.parametrize(
    "text",
    [
        "Лев открыл шлюз, а Нина — открыла.",
        "Лев не открыл шлюз, а Нина — закрыла.",
        "Лев не открыл шлюз, а Нина открыла.",
    ],
)
def test_repeated_frame_completion_requires_every_structural_guard(morphology, text):
    parsed = parser(morphology).parse(text)
    target = parsed.perception.assertions[1]
    assert set(roles(target)) == {ActantRole.SUBJECT}
    assert not any(
        trace.stage == "contrastive_repeated_frame" for trace in parsed.traces
    )


def test_recovered_nested_graph_integrates_as_four_canonical_assertions():
    backend = GraphEllipsisFixture()
    service = LLMPerceptionService(
        backend,
        LLMPerceptionSettings(
            protocol="adaptive_v3",
            probe_prompt_dir=ROOT / "prompts" / "perception",
            probe_retry_attempts=0,
            morphology_backend="pymorphy3",
        ),
    )
    core, context, integration = runtime()
    parsed = service.parse("Лев хочет проверить мотор, а Нина — насос.", context)
    completed = TemplateCompletionService(integration, service).complete(parsed)
    commit = integration.integrate_external(completed, context)
    assert len(commit.assertions) == 4
    assert len({item.ref.uid for item in commit.assertions}) == 4
    assert all(core.store.get_hypernode(item.ref.uid) is not None for item in commit.assertions)
