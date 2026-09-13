from __future__ import annotations

from ah.config import LLMRoleSettings
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    LLMPerceptionService,
    PerceptionResult,
    PredicateCandidate,
    RuntimeSemanticAdaptiveParser,
)
from ah.perception.adaptive_parser import AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from ah.perception.runtime_invariants import RuntimeSemanticLLMPerceptionService
from ah.temporal import TemporalModeProbeDecision


class _NoLLMBackend:
    def generate(self, *args, **kwargs):  # pragma: no cover - every decision is injected
        raise AssertionError("unexpected LLM call")


class _Morphology:
    name = "test"
    _MAP = {
        "я": (
            MorphInfo(
                "я", "NPRO", case="nomn", number="sing",
                grammemes=frozenset({"1per"}), score=1.0,
            ),
        ),
        "илья": (
            MorphInfo(
                "илья", "NOUN", case="nomn", number="sing", gender="masc",
                grammemes=frozenset({"Name"}), score=1.0,
            ),
        ),
        "что": (
            MorphInfo(
                "что", "NPRO", case="accs", number="sing",
                grammemes=frozenset({"Ques"}), score=1.0,
            ),
        ),
        "ещё": (
            MorphInfo("ещё", "ADVB", score=1.0),
        ),
        "вчера": (
            MorphInfo("вчера", "ADVB", score=1.0),
        ),
        "сделал": (
            MorphInfo(
                "сделать", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past", "perf"}), score=1.0,
            ),
        ),
        "делал": (
            MorphInfo(
                "делать", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past", "impf"}), score=1.0,
            ),
        ),
        "пил": (
            MorphInfo(
                "пить", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past", "impf"}), score=1.0,
            ),
        ),
        "выпил": (
            MorphInfo(
                "выпить", "VERB", number="sing", gender="masc", mood="indc",
                transitivity="tran", grammemes=frozenset({"past", "perf"}), score=1.0,
            ),
        ),
        "запрос": (
            MorphInfo("запрос", "NOUN", case="accs", number="sing", gender="masc", score=1.0),
        ),
        "чай": (
            MorphInfo("чай", "NOUN", case="accs", number="sing", gender="masc", score=1.0),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _Parser(RuntimeSemanticAdaptiveParser):
    def _classify_role(
        self,
        text,
        predicate,
        span,
        used_roles,
        forbidden_role,
        *,
        requested,
        allowed_roles=None,
        allow_none=False,
    ):
        value = self._semantic_span(span).text.casefold()
        if value in {"я", "илья"}:
            return ActantRole.SUBJECT
        if value in {"запрос", "чай"}:
            return ActantRole.OBJECT
        return super()._classify_role(
            text,
            predicate,
            span,
            used_roles,
            forbidden_role,
            requested=requested,
            allowed_roles=allowed_roles,
            allow_none=allow_none,
        )

    def _adverbial_scope_decision(self, text, predicate, span):
        value = self._semantic_span(span).text.casefold()
        if value == "ещё":
            self._runtime_adverbial_scope[self._span_key(span)] = "DISCOURSE_OPERATOR"
            return "DISCOURSE_OPERATOR"
        return super()._adverbial_scope_decision(text, predicate, span)

    def _resolve_temporal_mode_candidate(self, source_context, assertion, profile):
        return TemporalModeProbeDecision.PROCESS


def _parser_for(text: str):
    morphology = _Morphology()
    graph = LinguisticCandidateBuilder(morphology).build(text)
    parser = _Parser(
        _NoLLMBackend(),
        AdaptiveSettings(
            prompt_dir=None,
            generation=LLMRoleSettings(max_new_tokens=24),
            morphology_backend="none",
        ),
        morphology=morphology,
    )
    parser._candidate_graph = graph
    tokens = parser._source_tokens_from_graph(graph)
    return parser, tokens


def _predicate(parser, tokens, token_index: int, lemma: str):
    span = parser._resolve_span_from_source(tokens, token_index, token_index)
    return span, PredicateCandidate(
        span.text,
        normalized_hint=lemma,
        evidence=span.evidence,
    )


def test_public_runtime_uses_source_semantic_parser() -> None:
    assert issubclass(LLMPerceptionService, RuntimeSemanticLLMPerceptionService)


def test_medial_yesterday_is_preconsumed_as_time_before_generic_roles() -> None:
    text = "Я вчера сделал запрос"
    parser, tokens = _parser_for(text)
    predicate_span, predicate = _predicate(parser, tokens, 3, "сделать")

    actants, _ = parser._extract_actants(
        text,
        tokens,
        predicate_span,
        predicate,
        act_type="ASSERTION",
        requested_roles=(),
        requested_spans=(),
    )

    by_role = {item.role: item for item in actants}
    assert by_role[ActantRole.SUBJECT].mention == "Я"
    assert by_role[ActantRole.OBJECT].mention == "запрос"
    assert by_role[ActantRole.TIME].mention.casefold() == "вчера"


def test_fronted_yesterday_is_preconsumed_as_time_before_generic_roles() -> None:
    text = "Вчера я выпил чай"
    parser, tokens = _parser_for(text)
    predicate_span, predicate = _predicate(parser, tokens, 3, "выпить")

    actants, _ = parser._extract_actants(
        text,
        tokens,
        predicate_span,
        predicate,
        act_type="ASSERTION",
        requested_roles=(),
        requested_spans=(),
    )

    by_role = {item.role: item for item in actants}
    assert by_role[ActantRole.SUBJECT].mention == "я"
    assert by_role[ActantRole.OBJECT].mention == "чай"
    assert by_role[ActantRole.TIME].mention.casefold() == "вчера"


def test_final_source_invariant_restores_time_for_imperfective_tea_frame() -> None:
    """Regression for the live failure: Я вчера пил чай lost TIME before Integration."""
    text = "Я вчера пил чай"
    parser, tokens = _parser_for(text)
    _predicate_span, predicate = _predicate(parser, tokens, 3, "пить")
    result = PerceptionResult(
        source_text=text,
        assertions=(
            AssertionCandidate(
                local_id="A1",
                predicate=predicate,
                actants=(
                    ActantCandidate(ActantRole.SUBJECT, mention="Я", normalized_hint="я"),
                    ActantCandidate(ActantRole.OBJECT, mention="чай", normalized_hint="чай"),
                ),
            ),
        ),
    )

    guarded = parser._enforce_final_source_time(result)
    assertion = guarded.assertions[0]
    times = tuple(item for item in assertion.actants if item.role is ActantRole.TIME)

    assert len(times) == 1
    assert times[0].mention.casefold() == "вчера"
    assert assertion.temporal_mode is not None
    assert assertion.temporal_mode.value == "PROCESS"
    assert "source-time-invariant: explicit deterministic TIME preserved" in guarded.diagnostics


def _assert_absolute_date_is_one_time_actant(text: str, expected: str) -> None:
    parser, tokens = _parser_for(text)
    predicate_index = next(token.index for token in tokens if token.text.casefold() == "делал")
    predicate_span, predicate = _predicate(parser, tokens, predicate_index, "делать")
    requested = parser._resolve_span_from_source(tokens, 1, 1)

    actants, spans = parser._extract_actants(
        text,
        tokens,
        predicate_span,
        predicate,
        act_type="QUERY",
        requested_roles=(),
        requested_spans=(requested,),
    )

    times = [item for item in actants if item.role is ActantRole.TIME]
    assert len(times) == 1
    assert times[0].mention == expected
    assert any(span.text == expected for span in spans)
    # Numeric fragments of the same literal must never escape into ordinary roles.
    assert all(
        item.mention not in {"2026", "09", "12"}
        for item in actants
        if item.role is not ActantRole.TIME
    )


def test_dotted_absolute_date_is_consumed_as_one_time_span() -> None:
    _assert_absolute_date_is_one_time_actant(
        "Что я делал 12.09.2026?",
        "12.09.2026",
    )


def test_iso_absolute_date_is_consumed_as_one_time_span() -> None:
    _assert_absolute_date_is_one_time_actant(
        "Что я делал 2026-09-12?",
        "2026-09-12",
    )


def test_query_additivity_is_consumed_as_discourse_not_transition_actant() -> None:
    text = "Что ещё сделал Илья?"
    parser, tokens = _parser_for(text)
    predicate_span, predicate = _predicate(parser, tokens, 3, "сделать")
    requested = parser._resolve_span_from_source(tokens, 1, 1)

    actants, spans = parser._extract_actants(
        text,
        tokens,
        predicate_span,
        predicate,
        act_type="QUERY",
        requested_roles=(ActantRole.OBJECT,),
        requested_spans=(requested,),
    )

    assert [(item.role, item.mention) for item in actants] == [
        (ActantRole.SUBJECT, "Илья"),
    ]
    assert all(span.text.casefold() != "ещё" for span in spans)
    assert parser._transition_cue_token_indices == set()
    assert [item.text.casefold() for item in parser._runtime_discourse_operator_spans] == [
        "ещё"
    ]
