from __future__ import annotations

from datetime import datetime, timezone

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    GeneralizedNamingAdaptiveParser,
    LLMPerceptionService,
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
)
from ah.perception.adaptive_parser import AdaptiveSettings
from ah.perception.generalized_naming import GeneralizedNamingLLMPerceptionService
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo


class _NoLLMBackend:
    def generate(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("unexpected LLM call")


class _Morphology:
    name = "test"
    _MAP = {
        "меня": (
            MorphInfo(
                "я",
                "NPRO",
                case="accs",
                number="sing",
                grammemes=frozenset({"1per"}),
                score=1.0,
            ),
        ),
        "зовут": (
            MorphInfo(
                "звать",
                "VERB",
                number="plur",
                mood="indc",
                transitivity="tran",
                grammemes=frozenset({"3per", "pres"}),
                score=1.0,
            ),
        ),
        "илья": (
            MorphInfo(
                "илья",
                "NOUN",
                case="nomn",
                number="sing",
                gender="masc",
                grammemes=frozenset({"Name"}),
                score=1.0,
            ),
        ),
        "встретила": (
            MorphInfo(
                "встретить",
                "VERB",
                number="sing",
                gender="femn",
                mood="indc",
                transitivity="tran",
                grammemes=frozenset({"past"}),
                score=1.0,
            ),
        ),
        "мария": (
            MorphInfo(
                "мария",
                "NOUN",
                case="nomn",
                number="sing",
                gender="femn",
                grammemes=frozenset({"Name"}),
                score=1.0,
            ),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _NamingParser(GeneralizedNamingAdaptiveParser):
    def _verbal_naming_choice(self, source_text, assertion, owner, values):
        return "VALUE_1"


class _OrdinaryParser(GeneralizedNamingAdaptiveParser):
    def _verbal_naming_choice(self, source_text, assertion, owner, values):
        return "OTHER_PREDICATION"


def _parser(text: str, cls=_NamingParser):
    morphology = _Morphology()
    graph = LinguisticCandidateBuilder(morphology).build(text)
    parser = cls(
        _NoLLMBackend(),
        AdaptiveSettings(
            prompt_dir=None,
            generation=LLMRoleSettings(max_new_tokens=24),
            morphology_backend="none",
        ),
        morphology=morphology,
    )
    parser._candidate_graph = graph
    return parser, graph


def _evidence(graph, surface: str) -> EvidenceSpan:
    token = next(
        item for item in graph.tokens if item.text.casefold() == surface.casefold()
    )
    return EvidenceSpan(token.text, token.start, token.end)


def test_public_perception_runtime_uses_generalized_naming_service() -> None:
    assert LLMPerceptionService is GeneralizedNamingLLMPerceptionService


def test_verbal_naming_rewrite_is_structural_not_verb_dictionary() -> None:
    parser, graph = _parser("Меня зовут Илья")
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "зовут",
            normalized_hint="звать",
            evidence=_evidence(graph, "зовут"),
        ),
        actants=(
            # Preserve the bad historical role assignment deliberately: naming
            # detection must recover the deictic owner from morphology, not trust
            # that SUBJECT was already semantically correct.
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Меня",
                normalized_hint="я",
                evidence=_evidence(graph, "Меня"),
            ),
            ActantCandidate(
                ActantRole.STATE,
                mention="Илья",
                normalized_hint="илья",
                evidence=_evidence(graph, "Илья"),
            ),
        ),
    )

    rewritten, changed = parser._rewrite_naming_assertions(
        "Меня зовут Илья", (assertion,)
    )

    assert changed is True
    assert len(rewritten) == 1
    naming = rewritten[0]
    assert isinstance(naming, NamingAssertionCandidate)
    assert naming.owner is not None
    assert naming.owner.mention == "Меня"
    assert naming.name_value == "Илья"
    assert naming.name_normalized_hint == "илья"


def test_same_structure_can_remain_ordinary_when_semantics_reject_naming() -> None:
    parser, graph = _parser("Меня встретила Мария", _OrdinaryParser)
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "встретила",
            normalized_hint="встретить",
            evidence=_evidence(graph, "встретила"),
        ),
        actants=(
            ActantCandidate(
                ActantRole.OBJECT,
                mention="Меня",
                normalized_hint="я",
                evidence=_evidence(graph, "Меня"),
            ),
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Мария",
                normalized_hint="мария",
                evidence=_evidence(graph, "Мария"),
            ),
        ),
    )

    rewritten, changed = parser._rewrite_naming_assertions(
        "Меня встретила Мария", (assertion,)
    )

    assert changed is False
    assert rewritten == (assertion,)


def test_verbal_naming_candidate_updates_user_alias_in_live_integration() -> None:
    core = AHCore()
    user = core.add_entity(
        Domain.P,
        {"name": Property("name", "Пользователь", "str")},
        {"identity_role": "USER"},
    )
    agent = core.add_entity(
        Domain.P,
        {"name": Property("name", "Агент", "str")},
        {"identity_role": "SELF"},
    )
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(agent.uid),
    )
    integration = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
    )

    naming = NamingAssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate("зовут", normalized_hint="звать"),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Меня", normalized_hint="я"),
            ActantCandidate(ActantRole.STATE, mention="Илья", normalized_hint="илья"),
        ),
        owner=ActantCandidate(ActantRole.SUBJECT, mention="Меня", normalized_hint="я"),
        name_value="Илья",
        name_normalized_hint="илья",
    )

    commit = integration.integrate_external(
        PerceptionResult("Меня зовут Илья", assertions=(naming,)),
        context,
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
    )

    assert commit.assertions == ()
    matches = core.store.find_entities_by_name("Илья", Domain.P)
    assert tuple(item.uid for item in matches) == (user.uid,)
    experience = core.store.get_hypernode(commit.experience_ref.uid)
    assert tuple(experience.meta.get("speech_act_kinds", ())) == ("ASSERTION",)