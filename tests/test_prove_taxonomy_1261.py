from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService, TemplateCompletionService
from ah.integration.candidate_validator import CandidateValidator
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import TemplateCandidate
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.contracts import AssertionStatus, PropositionOperator
from ah.perception.morphology import MorphInfo
from ah.perception.scoping import apply_speech_act_scoping
from legacy_semantic_fixture import legacy_semantic_answer


PROJECT = Path(__file__).resolve().parents[1]


class TaxonomyMorphology:
    """Live pymorphy tags copular это as PRCL, which ModalScopeBuilder treats as a cue."""

    name = "prove-taxonomy-prcl-eto"

    _MAP = {
        "докажи": (MorphInfo("доказать", "VERB", mood="impr", number="sing", score=1.0),),
        "что": (MorphInfo("что", "CONJ", score=1.0),),
        "кот": (MorphInfo("кот", "NOUN", case="nomn", number="sing", score=1.0),),
        "это": (
            MorphInfo("это", "PRCL", score=1.0),
            MorphInfo("это", "NPRO", case="nomn", number="sing", score=0.6),
        ),
        "млекопитающее": (
            MorphInfo("млекопитающее", "NOUN", case="nomn", number="sing", score=1.0),
        ),
        "живое": (
            MorphInfo("живой", "ADJF", case="nomn", number="sing", gender="neut", score=1.0),
        ),
        "существо": (
            MorphInfo("существо", "NOUN", case="nomn", number="sing", score=1.0),
        ),
        "животное": (
            MorphInfo("животное", "NOUN", case="nomn", number="sing", score=1.0),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class LiveNpuModalBackend:
    """Reproduce the on-device answer: copular это → POSSIBLE."""

    def __init__(self) -> None:
        self.roles: list[str] = []
        self.modal_cues: list[str] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.roles.append(role)
        if role == "semantic_modal_operator":
            cue = ""
            if "CUE:\n" in prompt:
                cue = prompt.split("CUE:\n", 1)[1].split("\n", 1)[0].strip()
            self.modal_cues.append(cue)
            return LLMResponse("POSSIBLE", {})
        if role == "perception_act_type":
            text = prompt.split("TEXT:\n", 1)[-1].split("\n", 1)[0].casefold()
            if "?" in prompt or text.endswith("?"):
                return LLMResponse("QUERY", {})
            if "докажи" in text:
                return LLMResponse("COMMAND", {})
            return LLMResponse("ASSERTION", {})
        if role == "perception_role_cue":
            target = ""
            if "TARGET:\n" in prompt:
                target = prompt.split("TARGET:\n", 1)[1].split("\n", 1)[0].casefold()
            if target in {"кот", "млекопитающее", "существо"}:
                return LLMResponse("ACTOR_OR_EXPERIENCER", {})
            if target in {"живое", "живое существо"}:
                return LLMResponse("PREDICATED_STATE", {})
            return LLMResponse("AFFECTED_OR_CONTENT", {})
        fallback = legacy_semantic_answer(role, prompt)
        if fallback is not None:
            return LLMResponse(str(fallback), {})
        raise AssertionError(f"unexpected probe {role}:\n{prompt}")


def parser(backend: LiveNpuModalBackend | None = None) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        backend or LiveNpuModalBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=TaxonomyMorphology(),
    )


def _has_possible_root(perception) -> bool:
    for root in perception.proposition_roots:
        if root.expression.operator is PropositionOperator.POSSIBLE:
            return True
        if any(
            member.operator is PropositionOperator.POSSIBLE
            for member in root.expression.members
        ):
            return True
    return False


def test_taxonomy_eto_is_not_possible_even_when_npu_would_say_possible():
    backend = LiveNpuModalBackend()
    parsed = parser(backend).parse("кот это млекопитающее")
    perception = parsed.perception
    assert perception.commands == ()
    assert len(perception.assertions) == 1
    assertion = perception.assertions[0]
    assert assertion.status is AssertionStatus.ASSERTED
    assert assertion.predicate.lookup_form.casefold() == "млекопитающее"
    assert {item.role: item.mention for item in assertion.actants}[
        ActantRole.SUBJECT
    ].casefold() == "кот"
    assert not _has_possible_root(perception)
    assert "это" not in backend.modal_cues
    assert "semantic_modal_operator" not in backend.roles


def test_prove_taxonomy_command_validates_after_speech_act_scoping():
    backend = LiveNpuModalBackend()
    parsed = parser(backend).parse("докажи что кот это живое существо")
    perception = parsed.perception
    assert len(perception.commands) == 1
    assert perception.commands[0].predicate.lookup_form == "доказать"
    assert perception.assertions
    assert not _has_possible_root(perception)
    assert "это" not in backend.modal_cues

    scoped = apply_speech_act_scoping(perception)
    CandidateValidator().validate(scoped)
    embedded = [item for item in scoped.assertions if item.status is AssertionStatus.EMBEDDED]
    assert embedded


def test_prove_taxonomy_command_integrates():
    backend = LiveNpuModalBackend()
    parsed = parser(backend).parse("докажи что кот это живое существо")
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "Agent", "str")},
        meta={"identity_role": "SELF"},
    )
    user_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "User", "str")},
        meta={"identity_role": "USER"},
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))

    class ExplicitTemplateCompletion:
        @staticmethod
        def propose_template_candidate(source_text, predicate, filled_roles, role_bindings=()):
            del source_text, predicate, role_bindings
            return TemplateCandidate(tuple(filled_roles))

    completed = TemplateCompletionService(
        integration, ExplicitTemplateCompletion()
    ).complete(parsed.perception)
    integration.integrate_external(completed, context)
