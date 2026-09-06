from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    NominalRelationCandidate,
    NominalRelationKind,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "v090-static"

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


def make_parser(morphology: StaticMorphology) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


def test_postnominal_possessive_np_resolves_main_actant_from_head():
    text = "Торжество его было недолгим."
    morph = StaticMorphology({
        "торжество": (MorphInfo("торжество", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="gent", number="sing", gender="masc", grammemes=frozenset({"3per"}), score=0.6),
            MorphInfo("его", "ADJF", grammemes=frozenset({"Anph", "Apro", "Fixd"}), score=0.4),
        ),
        "было": (MorphInfo("быть", "VERB", number="sing", gender="neut", mood="indc", score=1.0),),
        "недолгим": (MorphInfo("недолгий", "ADJF", case="ablt", number="sing", gender="neut", score=1.0),),
    })
    parser = make_parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser._candidate_graph = graph
    span = parser._resolve_span(text, parser._source_tokens(text), 1, 2)
    actant = parser._make_actant(ActantRole.SUBJECT, span)

    assert actant.mention == "Торжество его"
    assert actant.normalized_hint == "Торжество"
    assert len(actant.nominal_relations) == 1
    relation = actant.nominal_relations[0]
    assert relation.kind is NominalRelationKind.POSSESSOR
    assert relation.head_normalized_hint == "Торжество"
    assert relation.dependent_mention == "его"


def test_genitive_np_preserves_weak_internal_relation_without_claiming_ownership():
    text = "Дверь здания была закрыта."
    morph = StaticMorphology({
        "дверь": (MorphInfo("дверь", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "здания": (MorphInfo("здание", "NOUN", case="gent", number="sing", gender="neut", score=1.0),),
        "была": (MorphInfo("быть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
        "закрыта": (MorphInfo("закрытый", "PRTS", number="sing", gender="femn", score=1.0),),
    })
    parser = make_parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser._candidate_graph = graph
    span = parser._resolve_span(text, parser._source_tokens(text), 1, 2)
    actant = parser._make_actant(ActantRole.SUBJECT, span)

    assert actant.normalized_hint == "Дверь"
    assert [(r.kind, r.head_normalized_hint, r.dependent_normalized_hint) for r in actant.nominal_relations] == [
        (NominalRelationKind.GENITIVE_DEP, "Дверь", "здание")
    ]


def test_nested_genitives_form_a_chain_instead_of_flat_entity_text():
    text = "Дверь дома брата скрипнула."
    morph = StaticMorphology({
        "дверь": (MorphInfo("дверь", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "дома": (MorphInfo("дом", "NOUN", case="gent", number="sing", gender="masc", score=1.0),),
        "брата": (MorphInfo("брат", "NOUN", case="gent", number="sing", gender="masc", score=1.0),),
        "скрипнула": (MorphInfo("скрипнуть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    parser = make_parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser._candidate_graph = graph
    span = parser._resolve_span(text, parser._source_tokens(text), 1, 3)
    actant = parser._make_actant(ActantRole.SUBJECT, span)

    assert actant.normalized_hint == "Дверь"
    assert [(r.head_normalized_hint, r.dependent_normalized_hint) for r in actant.nominal_relations] == [
        ("Дверь", "дом"),
        ("дом", "брат"),
    ]


def _service_and_context():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")}, {"identity_role": "USER"})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "АГент", "str")}, {"identity_role": "SELF"})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    return core, IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings())), context


def _state_assertion(subject: ActantCandidate) -> AssertionCandidate:
    return AssertionCandidate(
        "A1",
        PredicateCandidate(
            "было",
            normalized_hint="быть",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            subject,
            ActantCandidate(ActantRole.STATE, mention="недолгим", normalized_hint="недолгий"),
        ),
    )


def test_integration_materializes_head_plus_possessor_link_not_flat_phrase_entity():
    core, service, context = _service_and_context()
    zurita = core.add_entity(Domain.C, {"name": Property("name", "Зурита", "str")})
    context.pronoun_refs["он"] = core.ref(zurita.uid)

    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="торжество его",
        normalized_hint="торжество",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="торжество",
                head_normalized_hint="торжество",
                dependent_mention="его",
            ),
        ),
    )
    commit = service.integrate_external(PerceptionResult("Торжество его было недолгим.", assertions=(_state_assertion(subject),)), context)

    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    head_ref = node.actants[ActantRole.SUBJECT]
    head = core.store.get_element_any_domain(head_ref.uid)
    assert head.properties["name"].value == "торжество"
    assert not core.store.find_entities_by_name("торжество его", Domain.C)
    link = core.store.find_link("POSSESSOR", head_ref.uid, zurita.uid)
    assert link is not None


def test_integration_materializes_generic_genitive_dependency_as_typed_link():
    core, service, context = _service_and_context()
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="дверь здания",
        normalized_hint="дверь",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.GENITIVE_DEP,
                head_mention="дверь",
                head_normalized_hint="дверь",
                dependent_mention="здания",
                dependent_normalized_hint="здание",
            ),
        ),
    )
    commit = service.integrate_external(PerceptionResult("Дверь здания была недолгой.", assertions=(_state_assertion(subject),)), context)
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    door = node.actants[ActantRole.SUBJECT]
    building = core.store.find_entities_by_name("здание", Domain.C)[0]
    assert core.store.find_link("GENITIVE_DEP", door.uid, building.uid) is not None
    assert core.store.find_link("POSSESSOR", door.uid, building.uid) is None


def test_negated_assertion_does_not_leak_possession_into_world_graph():
    core, service, context = _service_and_context()
    zurita = core.add_entity(Domain.C, {"name": Property("name", "Зурита", "str")})
    context.pronoun_refs["он"] = core.ref(zurita.uid)
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="торжество его",
        normalized_hint="торжество",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="торжество",
                head_normalized_hint="торжество",
                dependent_mention="его",
            ),
        ),
    )
    assertion = _state_assertion(subject)
    assertion = AssertionCandidate(
        assertion.local_id, assertion.predicate, assertion.actants, negated=True
    )
    service.integrate_external(PerceptionResult("Торжество его не было недолгим.", assertions=(assertion,)), context)
    torzh = core.store.find_entities_by_name("торжество", Domain.C)[0]
    assert core.store.find_link("POSSESSOR", torzh.uid, zurita.uid) is None

def test_turn_local_postnominal_possessor_reuses_unique_prior_subject_identity():
    text = "Зурита стоял спокойно. Торжество его было недолгим."
    morph = StaticMorphology({
        "зурита": (MorphInfo("Зурита", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "стоял": (MorphInfo("стоять", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
        "спокойно": (MorphInfo("спокойно", "ADVB", score=1.0),),
        "торжество": (MorphInfo("торжество", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="gent", number="sing", gender="masc", grammemes=frozenset({"3per"}), score=0.7),
            MorphInfo("его", "ADJF", grammemes=frozenset({"Anph", "Apro", "Fixd"}), score=0.3),
        ),
        "было": (MorphInfo("быть", "VERB", number="sing", gender="neut", mood="indc", score=1.0),),
        "недолгим": (MorphInfo("недолгий", "ADJF", case="ablt", number="sing", gender="neut", score=1.0),),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    parser._entity_ref_counter = 0
    by_id = {
        "A1": AssertionCandidate(
            "A1", PredicateCandidate("стоял", "стоять"),
            (ActantCandidate(ActantRole.SUBJECT, mention="Зурита", normalized_hint="Зурита", evidence=EvidenceSpan("Зурита", 0, 6)),),
        ),
        "A2": AssertionCandidate(
            "A2", PredicateCandidate("было", "быть"),
            (
                ActantCandidate(
                    ActantRole.SUBJECT,
                    mention="Торжество его",
                    normalized_hint="Торжество",
                    evidence=EvidenceSpan("Торжество его", 24, 37),
                    nominal_relations=(
                        NominalRelationCandidate(
                            NominalRelationKind.POSSESSOR,
                            head_mention="Торжество",
                            head_normalized_hint="Торжество",
                            dependent_mention="его",
                            evidence=EvidenceSpan("Торжество его", 24, 37),
                        ),
                    ),
                ),
                ActantCandidate(ActantRole.STATE, mention="недолгим", normalized_hint="недолгий", evidence=EvidenceSpan("недолгим", 43, 52)),
            ),
        ),
    }
    parser._resolve_nominal_relation_coreferences(by_id)
    prior = by_id["A1"].actants[0].entity_ref
    possessor = by_id["A2"].actants[0].nominal_relations[0].dependent_entity_ref
    assert prior is not None
    assert possessor == prior


def test_first_person_possessive_materializes_user_as_possessor():
    core, service, context = _service_and_context()
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="мой проект",
        normalized_hint="проект",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="проект",
                head_normalized_hint="проект",
                dependent_mention="мой",
            ),
        ),
    )
    commit = service.integrate_external(PerceptionResult("Мой проект был недолгим.", assertions=(_state_assertion(subject),)), context)
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    project = node.actants[ActantRole.SUBJECT]
    assert context.user_ref is not None
    assert core.store.find_link("POSSESSOR", project.uid, context.user_ref.uid) is not None
