from __future__ import annotations

from ah.config import LLMRoleSettings
from ah.diagnostics.m1_presentation import build_m1_formalization_view
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EntityIdentityQueryCandidate,
    EvidenceSpan,
    NamingAssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
)
from ah.perception.adaptive_parser import AdaptiveParseResult, AdaptiveSettings
from ah.perception.identity_query import IdentityQueryAdaptiveParser
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from ah.perception.runtime_invariants import RuntimeSemanticAdaptiveParser


class _NoLLMBackend:
    def generate(self, *args, **kwargs):  # pragma: no cover - decisions are injected
        raise AssertionError("unexpected LLM call")


class _Morphology:
    name = "identity-surface-test"

    def analyze_all(self, word: str):
        value = word.casefold()
        if value == "я":
            return (
                MorphInfo(
                    "я",
                    "NPRO",
                    case="nomn",
                    number="sing",
                    grammemes=frozenset({"1per"}),
                    score=1.0,
                ),
            )
        if value == "кто":
            return (
                MorphInfo(
                    "кто",
                    "NPRO",
                    case="nomn",
                    number="sing",
                    grammemes=frozenset({"Ques"}),
                    score=1.0,
                ),
            )
        if value == "такой":
            return (
                MorphInfo(
                    "такой",
                    "ADJF",
                    case="nomn",
                    number="sing",
                    grammemes=frozenset({"Apro"}),
                    score=1.0,
                ),
            )
        if value == "илья":
            return (
                MorphInfo(
                    "илья",
                    "NOUN",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    grammemes=frozenset({"Name"}),
                    score=1.0,
                ),
            )
        if value == "пользователь":
            return (
                MorphInfo(
                    "пользователь",
                    "NOUN",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    score=1.0,
                ),
            )
        return ()

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _InjectedDecisionParser(IdentityQueryAdaptiveParser):
    identity_target_text: str | None = None

    def _verbal_naming_choice(self, source_text, assertion, owner, values):
        assert [(item.mention or item.lookup_text) for item in values] == ["Илья"]
        return "VALUE_1"

    def _identity_query_decision(self, source_text, query, candidates, interrogative):
        assert self.identity_target_text is not None
        texts = [self._candidate_text(item) for item in candidates]
        index = texts.index(self.identity_target_text)
        return f"TARGET_{index + 1}"


def _parser(text: str) -> _InjectedDecisionParser:
    morphology = _Morphology()
    parser = _InjectedDecisionParser(
        _NoLLMBackend(),
        AdaptiveSettings(
            prompt_dir=None,
            generation=LLMRoleSettings(max_new_tokens=24),
            morphology_backend="none",
        ),
        morphology=morphology,
    )
    parser._candidate_graph = LinguisticCandidateBuilder(morphology).build(text)
    return parser


def _evidence(source: str, token: str) -> EvidenceSpan:
    start = source.index(token)
    return EvidenceSpan(token, start, start + len(token))


def test_bare_i_am_name_is_naming_not_be_fact() -> None:
    source = "Я Илья"
    parser = _parser(source)
    assertion = AssertionCandidate(
        local_id="A1",
        predicate=PredicateCandidate(
            "быть",
            normalized_hint="быть",
            sense_hint="IMPLICIT",
            evidence=None,
        ),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Я",
                normalized_hint="я",
                evidence=_evidence(source, "Я"),
                grammatical_number="sing",
            ),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="Илья",
                normalized_hint="Илья",
                evidence=_evidence(source, "Илья"),
                grammatical_number="sing",
            ),
        ),
    )

    rewritten, changed = parser._rewrite_naming_assertions(source, (assertion,))
    assert changed is True
    assert len(rewritten) == 1
    naming = rewritten[0]
    assert isinstance(naming, NamingAssertionCandidate)
    assert naming.owner.mention == "Я"
    assert naming.name_value == "Илья"

    view = build_m1_formalization_view(
        PerceptionResult(source, assertions=(naming,))
    )
    assert view.prompt_type == "ФАКТ · ИМЕНОВАНИЕ"
    assert view.frames[0].predicate == "NAME_OF"
    assert [(role.role, role.value) for role in view.frames[0].roles] == [
        ("ENTITY", "Я"),
        ("NAME", "Илья"),
    ]


def test_who_is_shell_selects_entity_and_consumes_shell(monkeypatch) -> None:
    for target_text in ("Илья", "пользователь"):
        source = f"Кто такой {target_text}?"
        parser = _parser(source)
        parser.identity_target_text = target_text
        query = QueryCandidate(
            predicate=PredicateCandidate(
                "быть",
                normalized_hint="быть",
                sense_hint="IMPLICIT",
            ),
            actants=(
                ActantCandidate(
                    ActantRole.SUBJECT,
                    mention="Кто",
                    normalized_hint="кто",
                    evidence=_evidence(source, "Кто"),
                    grammatical_number="sing",
                ),
                ActantCandidate(
                    ActantRole.STATE,
                    mention="такой",
                    normalized_hint="такой",
                    evidence=_evidence(source, "такой"),
                    grammatical_number="sing",
                ),
                ActantCandidate(
                    ActantRole.OBJECT,
                    mention=target_text,
                    normalized_hint=target_text,
                    evidence=_evidence(source, target_text),
                    grammatical_number="sing",
                ),
            ),
            query_mode=QueryMode.EXISTS,
            local_id="Q1",
        )
        perception = PerceptionResult(source, queries=(query,))

        monkeypatch.setattr(
            RuntimeSemanticAdaptiveParser,
            "parse",
            lambda self, text, structural_resolution=None, p=perception: AdaptiveParseResult(p, ()),
        )
        parsed = parser.parse(source)
        assert len(parsed.perception.queries) == 1
        identity = parsed.perception.queries[0]
        assert isinstance(identity, EntityIdentityQueryCandidate)
        assert identity.target.mention == target_text
        assert tuple(item.mention for item in identity.actants) == (target_text,)
        assert {item.text for item in identity.query_operator_evidence} == {"Кто", "такой"}

        view = build_m1_formalization_view(parsed.perception)
        assert view.prompt_detail == "Найти имя / идентичность сущности"
        assert view.frames[0].kind == "ЗАПРОС ИДЕНТИЧНОСТИ"
        assert view.frames[0].predicate == "IDENTITY_OF"
        words = {word.text: (word.label, word.detail) for word in view.words}
        assert words["Кто"] == ("Оператор запроса", "IDENTITY")
        assert words["такой"] == ("Оператор запроса", "IDENTITY")
        assert words[target_text] == ("ENTITY", "идентифицируемая сущность")
