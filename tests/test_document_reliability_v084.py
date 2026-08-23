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
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "v084-static"

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


def make_parser(morphology):
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


def test_grnd_noun_homograph_before_agreeing_finite_head_is_not_a_second_predicate():
    morph = StaticMorphology({
        "полив": (
            MorphInfo("полить", "GRND", number=None, gender=None, transitivity="tran", grammemes=frozenset({"GRND", "past", "perf", "tran"}), score=0.4),
            MorphInfo("полив", "NOUN", case="nomn", number="sing", gender="masc", animacy="inan", score=0.2),
            MorphInfo("полив", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=0.2),
        ),
        "задержался": (
            MorphInfo("задержаться", "VERB", number="sing", gender="masc", mood="indc", transitivity="intr", grammemes=frozenset({"VERB", "past", "sing", "masc", "intr"}), score=1.0),
        ),
    })
    graph = LinguisticCandidateBuilder(morph).build("Полив задержался.")
    assert [(head.token_index, head.lemma_candidates) for head in graph.predicates] == [
        (2, ("задержаться",))
    ]


def test_detached_nonfinite_homograph_survives_when_punctuation_marks_its_own_frame():
    morph = StaticMorphology({
        "полив": (
            MorphInfo("полить", "GRND", transitivity="tran", grammemes=frozenset({"GRND", "past", "perf", "tran"}), score=0.4),
            MorphInfo("полив", "NOUN", case="nomn", number="sing", gender="masc", score=0.2),
        ),
        "цветы": (MorphInfo("цветок", "NOUN", case="accs", number="plur", gender="masc", score=1.0),),
        "рабочий": (MorphInfo("рабочий", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
        "задержался": (
            MorphInfo("задержаться", "VERB", number="sing", gender="masc", mood="indc", transitivity="intr", grammemes=frozenset({"VERB", "past", "sing", "masc", "intr"}), score=1.0),
        ),
    })
    graph = LinguisticCandidateBuilder(morph).build("Полив цветы, рабочий задержался.")
    assert {head.token_index for head in graph.predicates} == {1, 5}


def test_unique_agreeing_nominative_of_active_intransitive_frame_is_structural_subject():
    morph = StaticMorphology({
        "жидкость": (MorphInfo("жидкость", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "вытекла": (
            MorphInfo("вытечь", "VERB", number="sing", gender="femn", mood="indc", transitivity="intr", grammemes=frozenset({"VERB", "past", "sing", "femn", "intr"}), score=1.0),
        ),
    })
    text = "Жидкость вытекла."
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._candidate_graph.tokens
    subject = _Span(1, 1, "Жидкость", EvidenceSpan("Жидкость", 0, 8))
    predicate_span = _Span(2, 2, "вытекла", EvidenceSpan("вытекла", 9, 16))
    roles = parser._deterministic_role_candidates(
        tokens, predicate_span, PredicateCandidate("вытекла", "вытечь"), subject
    )
    assert roles == (ActantRole.SUBJECT,)


def test_semantic_object_can_select_rare_accusative_lexeme_over_top_nominative_homograph():
    morph = StaticMorphology({
        "техника": (
            MorphInfo("техника", "NOUN", case="nomn", number="sing", gender="femn", animacy="inan", score=0.946),
            MorphInfo("техник", "NOUN", case="gent", number="sing", gender="masc", animacy="anim", score=0.027),
            MorphInfo("техник", "NOUN", case="accs", number="sing", gender="masc", animacy="anim", score=0.027),
        ),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build("техника")
    span = _Span(1, 1, "техника", EvidenceSpan("техника", 0, 7))
    object_actant = parser._make_actant(ActantRole.OBJECT, span)
    subject_actant = parser._make_actant(ActantRole.SUBJECT, span)
    assert object_actant.normalized_hint == "техник"
    assert subject_actant.normalized_hint == "техника"


def _runtime(morphology):
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "Агент", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER"
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    service = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
        discourse_morphology=morphology,
    )
    return core, context, service


def _assertion(local_id, predicate, *actants):
    roles = tuple(dict.fromkeys(item.role for item in actants))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate(roles),
        ),
        tuple(actants),
    )


def test_cross_turn_nominative_pronoun_reuses_unique_same_role_discourse_entity():
    morph = StaticMorphology({
        "анна": (MorphInfo("Анна", "NOUN", case="nomn", number="sing", gender="femn", animacy="anim", score=1.0),),
        "теплицу": (MorphInfo("теплица", "NOUN", case="accs", number="sing", gender="femn", animacy="inan", score=1.0),),
        "коммутатор": (MorphInfo("коммутатор", "NOUN", case="nomn", number="sing", gender="masc", animacy="inan", score=1.0),),
        "она": (MorphInfo("она", "NPRO", case="nomn", number="sing", gender="femn", animacy="anim", grammemes=frozenset({"3per"}), score=1.0),),
        "щиток": (MorphInfo("щиток", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
    })
    core, context, service = _runtime(morph)
    first = PerceptionResult(
        source_text="Анна осмотрела теплицу. Коммутатор отключился.",
        assertions=(
            _assertion(
                "A1", "осмотреть",
                ActantCandidate(ActantRole.SUBJECT, mention="Анна", normalized_hint="Анна"),
                ActantCandidate(ActantRole.OBJECT, mention="теплицу", normalized_hint="теплица"),
            ),
            _assertion(
                "A2", "отключиться",
                ActantCandidate(ActantRole.SUBJECT, mention="Коммутатор", normalized_hint="коммутатор"),
            ),
        ),
    )
    first_commit = service.integrate_external(first, context)
    anna_ref = core.store.get_hypernode(first_commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert context.pronoun_refs["она"] == anna_ref

    second = PerceptionResult(
        source_text="Она проверила щиток.",
        assertions=(
            _assertion(
                "A1", "проверить",
                ActantCandidate(ActantRole.SUBJECT, mention="Она", normalized_hint="она"),
                ActantCandidate(ActantRole.OBJECT, mention="щиток", normalized_hint="щиток"),
            ),
        ),
    )
    second_commit = service.integrate_external(second, context)
    second_node = core.store.get_hypernode(second_commit.assertions[0].ref.uid)
    assert second_node.actants[ActantRole.SUBJECT] == anna_ref
    assert core.store.find_entities_by_name("Она", Domain.C) == ()


def test_cross_turn_pronoun_anchor_is_cleared_when_two_same_signature_subjects_are_current():
    morph = StaticMorphology({
        "анна": (MorphInfo("Анна", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "мария": (MorphInfo("Мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
    })
    _core, context, service = _runtime(morph)
    result = PerceptionResult(
        source_text="Анна вошла. Мария осталась.",
        assertions=(
            _assertion("A1", "войти", ActantCandidate(ActantRole.SUBJECT, mention="Анна", normalized_hint="Анна")),
            _assertion("A2", "остаться", ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария")),
        ),
    )
    service.integrate_external(result, context)
    assert "она" not in context.pronoun_refs
