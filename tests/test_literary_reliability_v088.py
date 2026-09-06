from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMConfig, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.deixis_resolver import DeixisResolver
from ah.model import ActantRole, Domain, Property, Ref, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "v088-static"

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


def runtime(morphology):
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


def assertion(local_id: str, surface: str, lemma: str, *actants: ActantCandidate):
    roles = tuple(dict.fromkeys(item.role for item in actants))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            surface,
            lemma,
            template_candidate=TemplateCandidate(roles),
        ),
        tuple(actants),
    )


def test_event_count_has_no_configured_semantic_ceiling():
    config = LLMConfig()
    assert not hasattr(config, "perception_max_acts")
    settings = AdaptiveSettings(
        prompt_dir=PROJECT / "prompts/perception",
        generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
        morphology_backend="none",
    )
    assert not hasattr(settings, "max_acts")
    assert config.perception_max_actants_per_act == 8


def test_finite_predicate_agreement_anchors_ambiguous_proper_name_as_masculine():
    morph = StaticMorphology({
        # Deliberately no stable nominal signature for the surname.
        "арден": (),
        "стоял": (
            MorphInfo("стоять", "VERB", number="sing", gender="masc", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "masc"}), score=1.0),
        ),
    })
    _core, context, service = runtime(morph)
    result = PerceptionResult(
        source_text="Арден стоял у окна.",
        assertions=(assertion(
            "A1", "стоял", "стоять",
            ActantCandidate(ActantRole.SUBJECT, mention="Арден", normalized_hint="Арден"),
        ),),
    )
    commit = service.integrate_external(result, context)
    subject = service.core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert context.pronoun_refs["он"] == subject


def test_finite_plural_agreement_overrides_singular_surface_of_quantified_subject():
    morph = StaticMorphology({
        "рабочего": (
            MorphInfo("рабочий", "NOUN", case="gent", number="sing", gender="masc", score=1.0),
        ),
        "вошли": (
            MorphInfo("войти", "VERB", number="plur", mood="indc", grammemes=frozenset({"VERB", "past", "plur"}), score=1.0),
        ),
    })
    _core, context, service = runtime(morph)
    result = PerceptionResult(
        source_text="Трое рабочего вошли.",
        assertions=(assertion(
            "A1", "вошли", "войти",
            ActantCandidate(ActantRole.SUBJECT, mention="трое рабочего", normalized_hint="рабочий"),
        ),),
    )
    commit = service.integrate_external(result, context)
    subject = service.core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert context.pronoun_refs["они"] == subject
    assert "он" not in context.pronoun_refs


def test_oblique_pronoun_resolves_from_unique_nominative_discourse_anchor():
    ref = Ref("M_PREV", RefKind.M)
    context = InteractionContext(pronoun_refs={"он": ref})
    candidate = ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="его")
    assert DeixisResolver().resolve(candidate, context) == ref


def test_syncretic_oblique_pronoun_does_not_choose_between_distinct_anchors():
    context = InteractionContext(
        pronoun_refs={
            "он": Ref("M_MASC", RefKind.M),
            "оно": Ref("M_NEUT", RefKind.M),
        }
    )
    candidate = ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="его")
    assert DeixisResolver().resolve(candidate, context) is None


def test_non_reflexive_object_pronoun_cannot_bind_its_own_clause_subject():
    morph = StaticMorphology({
        "виктор": (MorphInfo("Виктор", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
        "матрос": (MorphInfo("матрос", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=1.0),),
        "его": (MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", animacy="anim", grammemes=frozenset({"3per"}), score=1.0),),
    })
    parser = make_parser(morph)
    by_id = {
        "A1": assertion(
            "A1", "отступал", "отступать",
            ActantCandidate(ActantRole.SUBJECT, mention="Виктор", normalized_hint="Виктор", evidence=EvidenceSpan("Виктор", 0, 6)),
        ),
        "A2": assertion(
            "A2", "схватил", "схватить",
            ActantCandidate(ActantRole.SUBJECT, mention="Матрос", normalized_hint="матрос", evidence=EvidenceSpan("Матрос", 17, 23)),
            ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="его", evidence=EvidenceSpan("его", 32, 35)),
        ),
    }
    parser._resolve_pronoun_coreferences(by_id)
    previous_subject = next(a for a in by_id["A1"].actants if a.role is ActantRole.SUBJECT)
    object_pronoun = next(a for a in by_id["A2"].actants if a.role is ActantRole.OBJECT)
    local_subject = next(a for a in by_id["A2"].actants if a.role is ActantRole.SUBJECT)
    assert object_pronoun.entity_ref == previous_subject.entity_ref
    assert object_pronoun.entity_ref != local_subject.entity_ref


def test_postnominal_possessive_pronoun_stays_inside_subject_np():
    morph = StaticMorphology({
        "решение": (MorphInfo("решение", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="gent", number="sing", gender="masc", grammemes=frozenset({"3per"}), score=0.6),
            MorphInfo("его", "ADJF", grammemes=frozenset({"Anph", "Apro", "Fixd"}), score=0.4),
        ),
        "было": (MorphInfo("быть", "VERB", number="sing", gender="neut", mood="indc", score=1.0),),
        "странным": (MorphInfo("странный", "ADJF", case="ablt", number="sing", gender="neut", score=1.0),),
    })
    parser = make_parser(morph)
    graph = LinguisticCandidateBuilder(morph).build("Решение его было странным.")
    parser._candidate_graph = graph
    assert parser._nominal_phrase_end(graph.tokens, 1, 2, set()) == 2
