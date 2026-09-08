from __future__ import annotations

from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole, Domain, FunctionSymbol, Hypernode, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    TemporalMode,
    TransitionOperator,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import Pymorphy3Morphology


ROOT = Path(__file__).resolve().parents[1]


class _TransitionFixture:
    def __init__(self, operator: str) -> None:
        self.operator = operator
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        del system, override
        self.calls.append((role, prompt))
        if role == "perception_role_cue":
            target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            if target == "лев":
                return LLMResponse("ACTOR_OR_EXPERIENCER", {})
            if target == "мотор":
                return LLMResponse("AFFECTED_OR_CONTENT", {})
            if target in {"снова", "больше"}:
                return LLMResponse("TRANSITION_OPERATOR", {})
        if role == "perception_frame_relation":
            return LLMResponse("CONTENT_LINK", {})
        if role == "semantic_nonfinite_assertion_status":
            if "MATRIX PREDICATE:\nхочет" in prompt:
                return LLMResponse("NONASSERTED_CONTENT", {})
            return LLMResponse("SCOPED_EVENT", {})
        if role == "semantic_transition_operator":
            cue = (
                prompt.split("OPERATOR CUE:\n", 1)[1].split("\n", 1)[0].casefold()
                if "OPERATOR CUE:\n" in prompt
                else None
            )
            if cue == "не":
                return LLMResponse("NONE", {})
            return LLMResponse(self.operator, {})
        if role == "perception_act_relation":
            return LLMResponse("NONE", {})
        raise AssertionError(f"unexpected bounded call: {role}\n{prompt[:800]}")


@pytest.fixture(scope="module")
def morphology() -> Pymorphy3Morphology:
    return Pymorphy3Morphology()


def _parser(morphology, backend) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


@pytest.mark.parametrize(
    ("operator", "text"),
    (
        ("START", "Лев начал проверять мотор."),
        ("STOP", "Лев перестал проверять мотор."),
        ("CONTINUE", "Лев продолжил проверять мотор."),
        ("AGAIN", "Лев снова начал проверять мотор."),
        ("NO_LONGER", "Лев больше не проверяет мотор."),
    ),
)
def test_source_text_yields_each_occurrence_level_transition_operator(
    morphology: Pymorphy3Morphology,
    operator: str,
    text: str,
) -> None:
    backend = _TransitionFixture(operator)
    parsed = _parser(morphology, backend).parse(text).perception
    assert len(parsed.assertions) == 1
    occurrence = parsed.assertions[0]
    assert occurrence.predicate.lookup_form == "проверять"
    assert occurrence.temporal_mode is TemporalMode.TRANSITION
    assert occurrence.transition_operator is TransitionOperator(operator)
    assert occurrence.negated is False
    assert {item.lookup_text for item in occurrence.actants} == {"Лев", "мотор"}
    assert any(role == "semantic_transition_operator" for role, _ in backend.calls)


def test_nested_phase_content_is_not_promoted_through_a_nonasserted_matrix(
    morphology: Pymorphy3Morphology,
) -> None:
    backend = _TransitionFixture("START")
    parsed = _parser(morphology, backend).parse(
        "Лев хочет начать проверять мотор."
    ).perception
    assert {item.predicate.lookup_form for item in parsed.assertions} == {
        "хотеть", "начать", "проверять",
    }
    assert all(item.transition_operator is None for item in parsed.assertions)
    assert not any(
        role == "semantic_transition_operator" for role, _ in backend.calls
    )


def _services() -> tuple[AHCore, InteractionContext, IntegrationService]:
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(agent.uid),
    )
    return (
        core,
        context,
        IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02)),
    )


@pytest.mark.parametrize("operator", tuple(TransitionOperator))
def test_transition_without_time_materializes_wrapper_without_inventing_interval(
    operator: TransitionOperator,
) -> None:
    core, context, integration = _services()
    candidate = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "работать",
            "работать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="сервер"),),
        temporal_mode=TemporalMode.TRANSITION,
        transition_operator=operator,
    )
    commit = integration.integrate_external(
        PerceptionResult("Сервер изменил состояние работы.", assertions=(candidate,)),
        context,
    )
    wrapper = core.store.get_element_any_domain(commit.assertions[0].ref.uid)
    assert isinstance(wrapper, FunctionSymbol)
    assert wrapper.function_id == operator.value
    assert len(wrapper.operands) == 1

    operand = core.store.get_hypernode(wrapper.operands[0].uid)
    assert ActantRole.TIME not in operand.actants
    assert operand.meta["semantic_scope"] == "TRANSITION_OPERAND"
    assert not any(
        isinstance(item, Hypernode)
        and item.meta.get("temporal_mode") == TemporalMode.STATE.value
        for item in core.store.all_elements()
    )
