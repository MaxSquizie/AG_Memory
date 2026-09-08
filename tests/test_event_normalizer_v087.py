from __future__ import annotations

from pathlib import Path

import pytest

from ah.integration.candidate_validator import CandidateValidator
from ah.integration.errors import CandidateValidationError
from ah.model import ActantRole
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    SituationRelationHintCandidate,
    SituationRelationHintKind,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.event_normalizer import EventNormalizer
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from ah.config import LLMRoleSettings


ROOT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "event-normalizer-v087"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(value) for key, value in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class NoModelBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected model call {role}:\n{prompt}")


def mi(normal_form: str, pos: str, **kwargs) -> MorphInfo:
    grammemes = frozenset(kwargs.pop("grammemes", ()))
    return MorphInfo(normal_form, pos, grammemes=grammemes, score=1.0, **kwargs)


def span(text: str, surface: str) -> EvidenceSpan:
    start = text.index(surface)
    return EvidenceSpan(surface, start, start + len(surface))


def assertion(
    local_id: str,
    text: str,
    surface: str,
    lemma: str,
    actants: tuple[ActantCandidate, ...],
    *,
    status: AssertionStatus = AssertionStatus.ASSERTED,
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        PredicateCandidate(surface, lemma, evidence=span(text, surface)),
        actants,
        evidence=span(text, surface),
        status=status,
    )


def test_detached_perfective_gerund_becomes_independent_event_following_into_matrix_event():
    text = "Ударившись о стену, мяч отскочил."
    morph = StaticMorphology({
        "ударившись": (mi("удариться", "GRND", transitivity="intr", grammemes={"GRND", "past", "perf", "intr"}),),
        "о": (mi("о", "PREP"),),
        "стену": (mi("стена", "NOUN", case="accs", number="sing", gender="femn"),),
        "мяч": (mi("мяч", "NOUN", case="nomn", number="sing", gender="masc"),),
        "отскочил": (mi("отскочить", "VERB", mood="indc", number="sing", gender="masc", transitivity="intr", grammemes={"VERB", "past", "perf", "intr"}),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    ball = ActantCandidate(ActantRole.SUBJECT, mention="мяч", normalized_hint="мяч", entity_ref="E_BALL", evidence=span(text, "мяч"))
    hit = assertion(
        "A1", text, "Ударившись", "удариться",
        (ball, ActantCandidate(ActantRole.OBJECT, mention="стену", normalized_hint="стена", evidence=span(text, "стену"))),
        status=AssertionStatus.EMBEDDED,
    )
    bounce = assertion(
        "A2", text, "отскочил", "отскочить",
        (ball, ActantCandidate(ActantRole.HOW_TO, candidate_ref="A1")),
    )

    outcome = EventNormalizer(graph, morph).normalize((hit, bounce), ())
    by_id = {item.local_id: item for item in outcome.assertions}
    assert by_id["A1"].status is AssertionStatus.ASSERTED
    assert all(item.candidate_ref != "A1" for item in by_id["A2"].actants)
    assert [(item.canonical_relation_id, item.source_ref, item.target_ref) for item in outcome.relations] == [
        ("FOLLOW", "A1", "A2")
    ]
    assert outcome.relation_hints == ()


def test_imperfective_detached_gerund_does_not_invent_sequence_or_cause():
    text = "Улыбаясь, Иван вошёл."
    morph = StaticMorphology({
        "улыбаясь": (mi("улыбаться", "GRND", transitivity="intr", grammemes={"GRND", "pres", "impf", "intr"}),),
        "иван": (mi("иван", "NOUN", case="nomn", number="sing", gender="masc"),),
        "вошёл": (mi("войти", "VERB", mood="indc", number="sing", gender="masc", transitivity="intr", grammemes={"VERB", "past", "perf", "intr"}),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    ivan = ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="иван", entity_ref="E_IVAN", evidence=span(text, "Иван"))
    smile = assertion("A1", text, "Улыбаясь", "улыбаться", (ivan,), status=AssertionStatus.EMBEDDED)
    enter = assertion("A2", text, "вошёл", "войти", (ivan, ActantCandidate(ActantRole.HOW_TO, candidate_ref="A1")))

    outcome = EventNormalizer(graph, morph).normalize((smile, enter), ())
    assert outcome.relations == ()
    assert [(item.kind, item.source_ref, item.target_ref) for item in outcome.relation_hints] == [
        (SituationRelationHintKind.SIMULTANEOUS_CANDIDATE, "A1", "A2")
    ]


def test_coordinated_perfective_events_remain_only_runtime_temporal_candidate():
    text = "Он поднял письмо и спрятал его."
    morph = StaticMorphology({
        "он": (mi("он", "NPRO", case="nomn", number="sing", gender="masc"),),
        "поднял": (mi("поднять", "VERB", mood="indc", number="sing", gender="masc", transitivity="tran", grammemes={"VERB", "past", "perf", "tran"}),),
        "письмо": (mi("письмо", "NOUN", case="accs", number="sing", gender="neut"),),
        "и": (mi("и", "CONJ"),),
        "спрятал": (mi("спрятать", "VERB", mood="indc", number="sing", gender="masc", transitivity="tran", grammemes={"VERB", "past", "perf", "tran"}),),
        "его": (mi("он", "NPRO", case="accs", number="sing", gender="masc"),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    actor = ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", entity_ref="E_PERSON", evidence=span(text, "Он"))
    letter = ActantCandidate(ActantRole.OBJECT, mention="письмо", normalized_hint="письмо", entity_ref="E_LETTER", evidence=span(text, "письмо"))
    lift = assertion("A1", text, "поднял", "поднять", (actor, letter))
    hide = assertion(
        "A2", text, "спрятал", "спрятать",
        (actor, ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="письмо", entity_ref="E_LETTER", evidence=span(text, "его"))),
    )

    outcome = EventNormalizer(graph, morph).normalize((lift, hide), ())
    assert outcome.relations == ()
    assert [(item.kind, item.source_ref, item.target_ref) for item in outcome.relation_hints] == [
        (SituationRelationHintKind.TEMPORAL_CANDIDATE, "A1", "A2")
    ]
    assert all(item.kind is not SituationRelationHintKind.CAUSAL_CANDIDATE for item in outcome.relation_hints)


def test_passive_participle_exposes_result_state_without_inventing_origin_event():
    text = "Сломанная ветка лежала на земле."
    morph = StaticMorphology({
        "сломанная": (mi("сломать", "PRTF", case="nomn", number="sing", gender="femn", grammemes={"PRTF", "past", "perf", "pssv", "nomn", "sing", "femn"}),),
        "ветка": (mi("ветка", "NOUN", case="nomn", number="sing", gender="femn"),),
        "лежала": (mi("лежать", "VERB", mood="indc", number="sing", gender="femn", transitivity="intr", grammemes={"VERB", "past", "impf", "intr"}),),
        "на": (mi("на", "PREP"),),
        "земле": (mi("земля", "NOUN", case="loct", number="sing", gender="femn"),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    source = assertion(
        "A1", text, "лежала", "лежать",
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Сломанная ветка", normalized_hint="ветка", entity_ref="E_BRANCH", evidence=EvidenceSpan("Сломанная ветка", 0, len("Сломанная ветка"))),
            ActantCandidate(ActantRole.LOCATION, mention="земле", normalized_hint="земля", evidence=span(text, "земле")),
        ),
    )

    outcome = EventNormalizer(graph, morph).normalize((source,), ())
    predicates = [item.predicate.lookup_form for item in outcome.assertions]
    assert predicates.count("лежать") == 1
    assert "быть" in predicates
    assert "сломать" not in predicates and "сломаться" not in predicates
    state_assertion = next(item for item in outcome.assertions if item.predicate.lookup_form == "быть")
    role_map = {item.role: item for item in state_assertion.actants}
    assert role_map[ActantRole.SUBJECT].entity_ref == "E_BRANCH"
    assert role_map[ActantRole.STATE].mention == "Сломанная"
    assert role_map[ActantRole.STATE].semantic_hint.startswith("RESULT_STATE_FROM_PARTICIPLE:")


def test_candidate_validator_checks_relation_hint_endpoints_but_never_treats_hint_as_canonical_link():
    base = AssertionCandidate("A1", PredicateCandidate("шум"), ())
    other = AssertionCandidate("A2", PredicateCandidate("уйти"), ())
    valid = PerceptionResult(
        source_text="Шум. Он ушёл.",
        assertions=(base, other),
        relation_hints=(SituationRelationHintCandidate(SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "A2"),),
    )
    CandidateValidator().validate(valid)

    invalid = PerceptionResult(
        source_text="Шум.",
        assertions=(base,),
        relation_hints=(SituationRelationHintCandidate(SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "MISSING"),),
    )
    with pytest.raises(CandidateValidationError):
        CandidateValidator().validate(invalid)


def test_pronoun_runtime_alternatives_stabilize_candidate_source_refs_before_branching():
    """Ambiguous pronoun branching must vary one role, not mutate the base mid-loop."""
    text = "Шум эха его встревожил."
    morph = StaticMorphology({
        "шум": (mi("шум", "NOUN", case="nomn", number="sing", gender="masc"),),
        "эха": (mi("эхо", "NOUN", case="gent", number="sing", gender="neut"),),
        # The oblique third-person paradigm can be compatible with masculine/neuter.
        "его": (mi("он", "NPRO", case="accs", number="sing", gender="masc"),),
        "встревожил": (mi("встревожить", "VERB", mood="indc", number="sing", gender="masc", transitivity="tran", grammemes={"VERB", "past", "perf", "tran"}),),
    })
    parser = AdaptivePerceptionParser(
        NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": AssertionCandidate(
            "A1",
            PredicateCandidate("встревожил", "встревожить", evidence=span(text, "встревожил")),
            (
                ActantCandidate(ActantRole.CAUSE, mention="Шум", normalized_hint="шум", evidence=span(text, "Шум")),
                ActantCandidate(ActantRole.SOURCE, mention="эха", normalized_hint="эхо", evidence=span(text, "эха")),
                ActantCandidate(ActantRole.OBJECT, mention="его", evidence=span(text, "его")),
            ),
        )
    }

    parser._resolve_pronoun_coreferences(by_id)
    current = by_id["A1"]
    assert len(current.alternatives) == 2
    # Both source mentions are stabilized on the common base before branching.
    base_refs = {a.role: a.entity_ref for a in current.actants if a.role in {ActantRole.CAUSE, ActantRole.SOURCE}}
    assert all(base_refs.values())
    for alternative in current.alternatives:
        alt_refs = {a.role: a.entity_ref for a in alternative.actants}
        assert alt_refs[ActantRole.CAUSE] == base_refs[ActantRole.CAUSE]
        assert alt_refs[ActantRole.SOURCE] == base_refs[ActantRole.SOURCE]
        assert alt_refs[ActantRole.OBJECT] in set(base_refs.values())
