from __future__ import annotations

from datetime import datetime, timezone

import pytest

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
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
)
from ah.perception.adaptive_parser import AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo


class _NoLLMBackend:
    def generate(self, *args, **kwargs):  # pragma: no cover - decision is injected
        raise AssertionError("unexpected backend call")


class _Morphology:
    name = "test"
    _MAP = {
        "я": (
            MorphInfo(
                "я",
                "NPRO",
                case="nomn",
                number="sing",
                grammemes=frozenset({"1per"}),
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
        "ильёй": (
            MorphInfo(
                "илья",
                "NOUN",
                case="ablt",
                number="sing",
                gender="masc",
                grammemes=frozenset({"Name"}),
                score=1.0,
            ),
        ),
        "инженер": (
            MorphInfo(
                "инженер",
                "NOUN",
                case="nomn",
                number="sing",
                gender="masc",
                score=1.0,
            ),
        ),
        "инженером": (
            MorphInfo(
                "инженер",
                "NOUN",
                case="ablt",
                number="sing",
                gender="masc",
                score=1.0,
            ),
        ),
        "являюсь": (
            MorphInfo(
                "являться",
                "VERB",
                number="sing",
                mood="indc",
                grammemes=frozenset({"1per", "pres"}),
                score=1.0,
            ),
        ),
        "это": (
            MorphInfo("это", "PRCL", score=1.0),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _DecisionParser(GeneralizedNamingAdaptiveParser):
    def __init__(self, *args, semantic_decision: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.semantic_decision = semantic_decision

    def _verbal_naming_choice(self, source_text, assertion, owner, values):
        return self.semantic_decision


def _parser(text: str, decision: str):
    morphology = _Morphology()
    graph = LinguisticCandidateBuilder(morphology).build(text)
    parser = _DecisionParser(
        _NoLLMBackend(),
        AdaptiveSettings(
            prompt_dir=None,
            generation=LLMRoleSettings(max_new_tokens=24),
            morphology_backend="none",
        ),
        morphology=morphology,
        semantic_decision=decision,
    )
    parser._candidate_graph = graph
    return parser, graph


def _evidence(graph, surface: str) -> EvidenceSpan:
    token = next(
        item for item in graph.tokens if item.text.casefold() == surface.casefold()
    )
    return EvidenceSpan(token.text, token.start, token.end)


def _nominal_assertion(
    graph,
    *,
    predicate_surface: str,
    predicate_normalized: str,
    subject_surface: str,
    subject_normalized: str,
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            predicate_surface,
            normalized_hint=predicate_normalized,
            sense_hint="NOMINAL_PREDICATION",
            evidence=_evidence(graph, predicate_surface),
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention=subject_surface,
                normalized_hint=subject_normalized,
                evidence=_evidence(graph, subject_surface),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("source", "predicate_surface", "subject_surface"),
    (
        ("Я Илья", "Илья", "Я"),
        ("Я — Илья", "Илья", "Я"),
        ("Я - Илья", "Илья", "Я"),
        ("Илья — это я", "я", "Илья"),
        ("Илья — я", "я", "Илья"),
    ),
)
def test_deictic_nominal_name_variants_become_one_naming_semantics(
    source: str,
    predicate_surface: str,
    subject_surface: str,
) -> None:
    parser, graph = _parser(source, "VALUE_1")
    assertion = _nominal_assertion(
        graph,
        predicate_surface=predicate_surface,
        predicate_normalized=("я" if predicate_surface.casefold() == "я" else "илья"),
        subject_surface=subject_surface,
        subject_normalized=("я" if subject_surface.casefold() == "я" else "илья"),
    )

    rewritten, changed = parser._rewrite_naming_assertions(source, (assertion,))

    assert changed is True
    assert len(rewritten) == 1
    naming = rewritten[0]
    assert isinstance(naming, NamingAssertionCandidate)
    assert naming.owner is not None
    assert naming.owner.mention.casefold() == "я"
    assert naming.name_normalized_hint == "илья"
    assert naming.name_value.casefold() == "илья"


@pytest.mark.parametrize(
    ("source", "predicate_surface", "subject_surface"),
    (
        ("Я инженер", "инженер", "Я"),
        ("Я — инженер", "инженер", "Я"),
        ("Я - инженер", "инженер", "Я"),
        ("Инженер — это я", "я", "Инженер"),
        ("Инженер — я", "я", "Инженер"),
    ),
)
def test_same_nominal_shapes_remain_classification_when_semantics_reject_name(
    source: str,
    predicate_surface: str,
    subject_surface: str,
) -> None:
    parser, graph = _parser(source, "OTHER_PREDICATION")
    assertion = _nominal_assertion(
        graph,
        predicate_surface=predicate_surface,
        predicate_normalized=("я" if predicate_surface.casefold() == "я" else "инженер"),
        subject_surface=subject_surface,
        subject_normalized=("я" if subject_surface.casefold() == "я" else "инженер"),
    )

    rewritten, changed = parser._rewrite_naming_assertions(source, (assertion,))

    assert changed is False
    assert rewritten == (assertion,)
    assert not isinstance(rewritten[0], NamingAssertionCandidate)


def test_explicit_state_predication_can_name_user_with_inflected_name() -> None:
    source = "Я являюсь Ильёй"
    parser, graph = _parser(source, "VALUE_1")
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "являюсь",
            normalized_hint="являться",
            evidence=_evidence(graph, "являюсь"),
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Я",
                normalized_hint="я",
                evidence=_evidence(graph, "Я"),
            ),
            ActantCandidate(
                ActantRole.STATE,
                mention="Ильёй",
                normalized_hint="илья",
                evidence=_evidence(graph, "Ильёй"),
            ),
        ),
    )

    rewritten, changed = parser._rewrite_naming_assertions(source, (assertion,))

    assert changed is True
    naming = rewritten[0]
    assert isinstance(naming, NamingAssertionCandidate)
    assert naming.owner is not None and naming.owner.mention == "Я"
    assert naming.name_value == "Ильёй"
    assert naming.name_normalized_hint == "илья"


def test_explicit_state_profession_remains_ordinary_predication() -> None:
    source = "Я являюсь инженером"
    parser, graph = _parser(source, "OTHER_PREDICATION")
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "являюсь",
            normalized_hint="являться",
            evidence=_evidence(graph, "являюсь"),
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Я",
                normalized_hint="я",
                evidence=_evidence(graph, "Я"),
            ),
            ActantCandidate(
                ActantRole.STATE,
                mention="инженером",
                normalized_hint="инженер",
                evidence=_evidence(graph, "инженером"),
            ),
        ),
    )

    rewritten, changed = parser._rewrite_naming_assertions(source, (assertion,))

    assert changed is False
    assert rewritten == (assertion,)


def test_inflected_name_is_indexed_by_normal_form_not_surface_case() -> None:
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
        predicate=PredicateCandidate("являюсь", normalized_hint="являться"),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Я", normalized_hint="я"),
            ActantCandidate(ActantRole.STATE, mention="Ильёй", normalized_hint="илья"),
        ),
        owner=ActantCandidate(ActantRole.SUBJECT, mention="Я", normalized_hint="я"),
        name_value="Ильёй",
        name_normalized_hint="илья",
    )

    commit = integration.integrate_external(
        PerceptionResult(source_text="Я являюсь Ильёй", assertions=(naming,)),
        context,
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc),
    )

    assert commit.assertions == ()
    assert tuple(item.uid for item in core.store.find_entities_by_name("Илья", Domain.P)) == (
        user.uid,
    )
    assert core.store.find_entities_by_name("Ильёй", Domain.P) == ()
