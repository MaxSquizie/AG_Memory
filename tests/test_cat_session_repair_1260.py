from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ah.agent import InteractionContext
from ah.android_bridge import _query_snapshot
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.entity_resolver import ExistingEntity, EntityResolver
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssociationSemanticClassifier,
    NominalRelationCandidate,
    NominalRelationKind,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from ah.perception.quantifier_formalization import QuantifierFormalizer


ROOT = Path(__file__).resolve().parents[1]
APRO = frozenset({"Apro"})
QUES = frozenset({"Ques"})


class StaticMorphology:
    name = "cat-session-static"

    def __init__(self, mapping, *, known=None):
        self.mapping = {key.casefold(): tuple(value) for key, value in mapping.items()}
        self.known = {item.casefold() for item in (known or mapping.keys())}

    def analyze_all(self, word: str):
        return self.mapping.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None

    def is_known(self, word: str) -> bool:
        return word.casefold() in self.known


class NoProbeBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected semantic probe {role}: {prompt[:300]}")


class ScriptedBackend:
    def __init__(self, answers):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt))
        queue = self.answers.get(role)
        if not queue:
            raise AssertionError(f"unexpected model call {role}:\n{prompt}")
        return LLMResponse(queue.pop(0), {})


def _cat_morph():
    return StaticMorphology({
        "мой": (
            MorphInfo("мой", "ADJF", case="nomn", number="sing", gender="masc", grammemes=APRO, score=1.0),
        ),
        "моим": (
            MorphInfo("мой", "ADJF", case="ablt", number="sing", gender="masc", grammemes=APRO, score=1.0),
        ),
        "кот": (
            MorphInfo("кот", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),
        ),
        "котом": (
            MorphInfo("кот", "NOUN", case="ablt", number="sing", gender="masc", animacy="anim", score=1.0),
        ),
        "умер": (
            MorphInfo("умереть", "VERB", number="sing", mood="indc", transitivity="intr", score=1.0),
        ),
        "что": (
            MorphInfo("что", "CONJ", score=0.9),
            MorphInfo("что", "NPRO", case="nomn", grammemes=QUES, score=0.4),
        ),
        "с": (MorphInfo("с", "PREP", score=1.0),),
        "какой": (
            MorphInfo("какой", "ADJF", case="nomn", number="sing", gender="masc", grammemes=QUES, score=1.0),
        ),
    })


def test_association_found_snapshot_is_not_unresolved():
    found = SimpleNamespace(
        outcome=None,
        association_outcome=SimpleNamespace(status="FOUND"),
        diagnostics=("semantic:association_goal", "semantic:association_status:FOUND"),
    )
    inference_miss = SimpleNamespace(
        outcome=None,
        association_outcome=None,
        diagnostics=("semantic:association_goal",),
    )
    snap = _query_snapshot(SimpleNamespace(queries=(found, inference_miss)))
    assert snap["unresolved_queries"] == [
        {"has_outcome": False, "diagnostics": ["semantic:association_goal"]},
    ]
    assert snap["queries"][0]["has_outcome"] is True


def test_polar_isa_state_is_not_an_association_endpoint():
    backend = ScriptedBackend({"semantic_association_query": ["ASSOCIATION:E1:E2"]})
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=0
    )
    query = QueryCandidate(
        PredicateCandidate("существо"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="кот", normalized_hint="кот"),
            ActantCandidate(ActantRole.STATE, mention="живое", normalized_hint="живое"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    decision, attempts = classifier.classify("кот это живое существо?", query)
    assert decision is None
    assert attempts == ()
    assert backend.calls == []


def test_aboutness_pp_is_not_an_association_endpoint():
    backend = ScriptedBackend({"semantic_association_query": ["ASSOCIATION:E1:E2"]})
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=0
    )
    query = QueryCandidate(
        PredicateCandidate("знаешь"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="ты", normalized_hint="ты"),
            ActantCandidate(ActantRole.RECIPIENT, mention="о моем коте", normalized_hint="кот"),
        ),
        requested_roles=(ActantRole.OBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    decision, attempts = classifier.classify("что ты знаешь о моем коте", query)
    assert decision is None
    assert attempts == ()
    assert backend.calls == []


def test_direct_association_question_still_probes():
    backend = ScriptedBackend({"semantic_association_query": ["ASSOCIATION:E1:E2"]})
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=0
    )
    query = QueryCandidate(
        PredicateCandidate("связывает"),
        (
            ActantCandidate(ActantRole.OBJECT, mention="огонь", normalized_hint="огонь"),
            ActantCandidate(ActantRole.AUXILLIARY, mention="дым", normalized_hint="дым"),
        ),
        requested_roles=(ActantRole.SUBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    decision, attempts = classifier.classify("Что связывает огонь и дым?", query)
    assert decision is not None
    assert backend.calls


def test_possessive_common_noun_is_not_quantifier_eligible():
    morph = _cat_morph()
    owned = ActantCandidate(
        ActantRole.SUBJECT,
        mention="мой кот",
        normalized_hint="кот",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="кот",
                head_normalized_hint="кот",
                dependent_mention="мой",
            ),
        ),
    )
    assert QuantifierFormalizer(morph)._eligible(owned) is False

    which = ActantCandidate(
        ActantRole.SUBJECT,
        mention="какой кот",
        normalized_hint="кот",
    )
    assert QuantifierFormalizer(morph)._eligible(which) is True


def test_unnamed_possessive_cat_is_individual_not_class():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(
        Domain.P,
        {"name": Property("name", "Пользователь", "str")},
        {"identity_role": "USER"},
    )
    self_entity = core.add_entity(
        Domain.P,
        {"name": Property("name", "АГент", "str")},
        {"identity_role": "SELF"},
    )
    core.add_entity(
        Domain.C,
        {"name": Property("name", "кот", "str")},
        {"grammatical_number": "sing"},
    )
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(self_entity.uid),
    )
    service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="мой кот",
        normalized_hint="кот",
        grammatical_number="sing",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="кот",
                head_normalized_hint="кот",
                dependent_mention="мой",
            ),
        ),
    )
    assertion = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "умер",
            normalized_hint="умереть",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (subject,),
    )
    service.integrate_external(
        PerceptionResult("мой кот умер", assertions=(assertion,)),
        context,
    )

    klass = next(iter(core.store.find_entities_by_name("кот")))
    pet = next(iter(core.store.find_entities_by_name("мой кот")))
    assert pet.uid != klass.uid
    exists = [
        node
        for node in core.store.hypernodes_for_actant(user.uid)
        if node.actants.get(ActantRole.OBJECT) is not None
        and node.actants.get(ActantRole.AUXILLIARY) is not None
    ]
    assert len(exists) == 1
    node = exists[0]
    assert node.actants[ActantRole.SUBJECT].uid == user.uid
    assert node.actants[ActantRole.OBJECT].uid == klass.uid
    assert node.actants[ActantRole.AUXILLIARY].uid == pet.uid

    death = [
        item
        for item in core.store.hypernodes_for_actant(pet.uid)
        if item.uid != node.uid
    ]
    assert death
    assert all(item.actants[ActantRole.SUBJECT].uid == pet.uid for item in death)

    resolved = EntityResolver(core).resolve(
        ActantCandidate(
            ActantRole.SUBJECT,
            mention="мой кот",
            normalized_hint="кот",
            grammatical_number="sing",
        ),
        context,
        first_person_ref=context.user_ref,
        second_person_ref=context.self_ref,
    )
    assert isinstance(resolved, ExistingEntity)
    assert resolved.ref.uid == pet.uid


def test_what_about_my_cat_does_not_take_wh_as_predicate():
    text = "что с моим котом"
    morph = _cat_morph()
    parser = AdaptivePerceptionParser(
        NoProbeBackend(),
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser._candidate_graph = graph
    tokens = parser._source_tokens(text)
    assert parser._predicate_morph_candidates(tokens, []) == ()
    assert parser._wh_licenses_implicit_predicate(tokens, []) is True
    lemmas = [
        lemma
        for head in graph.predicates
        for lemma in head.lemma_candidates
    ]
    assert "что" not in lemmas
