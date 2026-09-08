from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings, _Span
from ah.perception.event_normalizer import EventNormalizer
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

ROOT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "v096-static"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(values) for key, values in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class NoModelBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected model call {role}:\n{prompt}")


def parser(morph: StaticMorphology) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )


def ev(text: str, needle: str, *, start: int = 0) -> EvidenceSpan:
    pos = text.index(needle, start)
    return EvidenceSpan(needle, pos, pos + len(needle))


def mi(normal: str, pos: str, **kwargs) -> MorphInfo:
    grammemes = frozenset(kwargs.pop("grammemes", ()))
    return MorphInfo(normal, pos, grammemes=grammemes, score=kwargs.pop("score", 1.0), **kwargs)


def test_provisional_pronoun_only_entity_ref_is_reopened_for_local_antecedent_binding():
    text = "Алексей пришёл. Он открыл дверь и вошёл."
    morph = StaticMorphology({
        "алексей": (mi("Алексей", "NOUN", case="nomn", number="sing", gender="masc", grammemes={"Name"}),),
        "пришёл": (mi("прийти", "VERB", mood="indc", number="sing", gender="masc", grammemes={"perf"}),),
        "он": (mi("он", "NPRO", case="nomn", number="sing", gender="masc", grammemes={"3per"}),),
        "открыл": (mi("открыть", "VERB", mood="indc", number="sing", gender="masc", grammemes={"perf"}),),
        "дверь": (mi("дверь", "NOUN", case="accs", number="sing", gender="femn"),),
        "и": (mi("и", "CONJ"),),
        "вошёл": (mi("войти", "VERB", mood="indc", number="sing", gender="masc", grammemes={"perf"}),),
    })
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    alexei = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Алексей",
        normalized_hint="Алексей",
        evidence=ev(text, "Алексей"),
    )
    pronoun_pos = text.index("Он")
    pronoun_evidence = EvidenceSpan("Он", pronoun_pos, pronoun_pos + 2)
    by_id = {
        "A1": AssertionCandidate(
            "A1",
            PredicateCandidate("пришёл", "прийти", evidence=ev(text, "пришёл")),
            (alexei,),
        ),
        # Mimic structural subject-control/coordination: both copies were given a
        # temporary ref before real antecedent resolution.
        "A2": AssertionCandidate(
            "A2",
            PredicateCandidate("открыл", "открыть", evidence=ev(text, "открыл")),
            (ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", entity_ref="E_TMP", evidence=pronoun_evidence),),
        ),
        "A3": AssertionCandidate(
            "A3",
            PredicateCandidate("вошёл", "войти", evidence=ev(text, "вошёл")),
            (ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", entity_ref="E_TMP", evidence=pronoun_evidence),),
        ),
    }

    p._resolve_pronoun_coreferences(by_id)
    p._bind_reused_source_mentions(by_id)
    refs = [by_id[key].actants[0].entity_ref for key in ("A1", "A2", "A3")]
    assert refs[0] is not None
    assert refs[0] == refs[1] == refs[2]
    assert refs[0] != "E_TMP"


def test_postnominal_demonstrative_substantive_without_fixd_is_not_possessive_np_material():
    morph = StaticMorphology({
        "то": (
            mi("то", "CONJ", score=0.8),
            mi("тот", "ADJF", case="nomn", number="sing", gender="neut", grammemes={"Anph", "Apro", "Subx"}, score=0.2),
        )
    })
    p = parser(morph)
    tokens = p._source_tokens("рама в дальней комнате то дрожала")
    token = next(item for item in tokens if item.text.casefold() == "то")
    assert not p._is_postnominal_possessive_anaphor(token)


def test_clause_cause_anchors_to_source_predicate_not_structural_helper_sharing_span():
    text = "Бумага в письмах намокла, потому что вода просочилась."
    morph = StaticMorphology({
        "бумага": (mi("бумага", "NOUN", case="nomn", number="sing", gender="femn"),),
        "в": (mi("в", "PREP"),),
        "письмах": (mi("письмо", "NOUN", case="loct", number="plur", gender="neut"),),
        "намокла": (mi("намокнуть", "VERB", mood="indc", number="sing", gender="femn", grammemes={"perf"}),),
        "потому": (mi("потому", "ADVB"),),
        "что": (mi("что", "CONJ"),),
        "вода": (mi("вода", "NOUN", case="nomn", number="sing", gender="femn"),),
        "просочилась": (mi("просочиться", "VERB", mood="indc", number="sing", gender="femn", grammemes={"perf"}),),
    })
    p = parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    p._candidate_graph = graph
    token = {item.text.casefold(): item for item in graph.tokens}

    wet = AssertionCandidate(
        "A_WET",
        PredicateCandidate("намокла", "намокнуть", evidence=ev(text, "намокла")),
        (ActantCandidate(ActantRole.SUBJECT, mention="Бумага", normalized_hint="бумага"),),
    )
    helper = AssertionCandidate(
        "A_HELP",
        PredicateCandidate("в", "в", sense_hint="STRUCTURAL_NOMINAL_ATTACHMENT", evidence=ev(text, "в")),
        (),
    )
    seep = AssertionCandidate(
        "A_SEEP",
        PredicateCandidate("просочилась", "просочиться", evidence=ev(text, "просочилась")),
        (ActantCandidate(ActantRole.SUBJECT, mention="вода", normalized_hint="вода"),),
    )
    # Reproduce the live failure mode: the helper inherited the host predicate span,
    # so span.start alone points at the same source predicate head as A_WET.
    wet_index = token["намокла"].index
    seep_index = token["просочилась"].index
    spans = {
        "A_HELP": _Span(wet_index, wet_index, "намокла", ev(text, "намокла")),
        "A_WET": _Span(wet_index, wet_index, "намокла", ev(text, "намокла")),
        "A_SEEP": _Span(seep_index, seep_index, "просочилась", ev(text, "просочилась")),
    }
    relations = p._derive_situation_relations([helper, wet, seep], spans)
    assert [(r.canonical_relation_id, r.source_ref, r.target_ref) for r in relations] == [
        ("CAUSE", "A_SEEP", "A_WET")
    ]


def _event(text: str, local_id: str, surface: str, lemma: str, subject: ActantCandidate) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        PredicateCandidate(surface, lemma, evidence=ev(text, surface)),
        (subject,),
        evidence=ev(text, surface),
    )


def test_serial_perfective_comma_chain_is_only_a_temporal_candidate():
    text = "Холодный воздух прошёл по комнате, качнул пламя."
    morph = StaticMorphology({
        "холодный": (mi("холодный", "ADJF", case="nomn", number="sing", gender="masc"),),
        "воздух": (mi("воздух", "NOUN", case="nomn", number="sing", gender="masc"),),
        "прошёл": (mi("пройти", "VERB", mood="indc", number="sing", gender="masc", grammemes={"perf"}),),
        "по": (mi("по", "PREP"),),
        "комнате": (mi("комната", "NOUN", case="datv", number="sing", gender="femn"),),
        "качнул": (mi("качнуть", "VERB", mood="indc", number="sing", gender="masc", grammemes={"perf"}),),
        "пламя": (mi("пламя", "NOUN", case="accs", number="sing", gender="neut"),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    subject1 = ActantCandidate(ActantRole.SUBJECT, mention="воздух", normalized_hint="воздух", entity_ref="E_AIR")
    subject2 = ActantCandidate(ActantRole.SUBJECT, mention="воздух", normalized_hint="воздух", entity_ref="E_AIR")
    outcome = EventNormalizer(graph, morph).normalize(
        (_event(text, "A1", "прошёл", "пройти", subject1), _event(text, "A2", "качнул", "качнуть", subject2)),
        (),
    )
    assert outcome.relations == ()
    assert ("TEMPORAL_CANDIDATE", "A1", "A2") in {
        (r.kind.value, r.source_ref, r.target_ref) for r in outcome.relation_hints
    }


def test_serial_perfective_additive_coordination_is_not_canonical_order():
    text = "Занавеска коснулась стекла, и появилась точка."
    morph = StaticMorphology({
        "занавеска": (mi("занавеска", "NOUN", case="nomn", number="sing", gender="femn"),),
        "коснулась": (mi("коснуться", "VERB", mood="indc", number="sing", gender="femn", grammemes={"perf"}),),
        "стекла": (mi("стекло", "NOUN", case="gent", number="sing", gender="neut"),),
        "и": (mi("и", "CONJ"),),
        "появилась": (mi("появиться", "VERB", mood="indc", number="sing", gender="femn", grammemes={"perf"}),),
        "точка": (mi("точка", "NOUN", case="nomn", number="sing", gender="femn"),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    a = ActantCandidate(ActantRole.SUBJECT, mention="Занавеска", normalized_hint="занавеска", entity_ref="E_CURTAIN")
    b = ActantCandidate(ActantRole.SUBJECT, mention="точка", normalized_hint="точка", entity_ref="E_POINT")
    outcome = EventNormalizer(graph, morph).normalize(
        (_event(text, "A1", "коснулась", "коснуться", a), _event(text, "A2", "появилась", "появиться", b)),
        (),
    )
    assert outcome.relations == ()
    assert ("TEMPORAL_CANDIDATE", "A1", "A2") in {
        (r.kind.value, r.source_ref, r.target_ref) for r in outcome.relation_hints
    }


def test_cross_turn_salience_keeps_unique_named_subject_over_later_common_subjects():
    text = "Марина положила письма. Бумага коробилась, печь грела."
    morph = StaticMorphology({
        "марина": (mi("Марина", "NOUN", case="nomn", number="sing", gender="femn", animacy="anim", grammemes={"Name"}),),
        "положила": (mi("положить", "VERB", mood="indc", number="sing", gender="femn", grammemes={"perf"}),),
        "письма": (mi("письмо", "NOUN", case="accs", number="plur", gender="neut"),),
        "бумага": (mi("бумага", "NOUN", case="nomn", number="sing", gender="femn", animacy="inan"),),
        "коробилась": (mi("коробиться", "VERB", mood="indc", number="sing", gender="femn", grammemes={"impf"}),),
        "печь": (mi("печь", "NOUN", case="nomn", number="sing", gender="femn", animacy="inan"),),
        "грела": (mi("греть", "VERB", mood="indc", number="sing", gender="femn", grammemes={"impf"}),),
    })
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")}, {"identity_role": "SELF"})
    user_entity = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")}, {"identity_role": "USER"})
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    service = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
        discourse_morphology=morph,
    )
    marina = ActantCandidate(ActantRole.SUBJECT, mention="Марина", normalized_hint="Марина", evidence=ev(text, "Марина"), grammatical_number="sing")
    paper = ActantCandidate(ActantRole.SUBJECT, mention="Бумага", normalized_hint="бумага", evidence=ev(text, "Бумага"), grammatical_number="sing")
    stove = ActantCandidate(ActantRole.SUBJECT, mention="печь", normalized_hint="печь", evidence=ev(text, "печь"), grammatical_number="sing")
    result = PerceptionResult(
        text,
        assertions=(
            AssertionCandidate("A1", PredicateCandidate("положила", "положить", evidence=ev(text, "положила"), template_candidate=TemplateCandidate((ActantRole.SUBJECT,))), (marina,), evidence=ev(text, "положила")),
            AssertionCandidate("A2", PredicateCandidate("коробилась", "коробиться", evidence=ev(text, "коробилась"), template_candidate=TemplateCandidate((ActantRole.SUBJECT,))), (paper,), evidence=ev(text, "коробилась")),
            AssertionCandidate("A3", PredicateCandidate("грела", "греть", evidence=ev(text, "грела"), template_candidate=TemplateCandidate((ActantRole.SUBJECT,))), (stove,), evidence=ev(text, "грела")),
        ),
    )
    commit = service.integrate_external(result, context)
    marina_ref = core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert context.pronoun_refs["она"] == marina_ref
