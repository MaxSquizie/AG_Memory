from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
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
    CommandCandidate,
    NominalRelationCandidate,
    NominalRelationKind,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.lexical_recovery import LexicalRecovery, LexicalRecoveryStatus
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo


ROOT = Path(__file__).resolve().parents[1]
NAME = frozenset({"Name"})


class StaticMorphology:
    name = "session-repair-static"

    def __init__(self, mapping, *, known=None, candidate_map=None):
        self.mapping = {key.casefold(): tuple(value) for key, value in mapping.items()}
        self.known = {item.casefold() for item in (known or mapping.keys())}
        self.candidate_map = {
            key.casefold(): tuple(value) for key, value in (candidate_map or {}).items()
        }

    def analyze_all(self, word: str):
        return self.mapping.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None

    def is_known(self, word: str) -> bool:
        return word.casefold() in self.known

    def indexed_candidates(self, word: str, *, max_distance: int, limit: int = 512):
        del max_distance
        return self.candidate_map.get(word.casefold(), ())[:limit]


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


def _possessive_imperative_morph():
    return StaticMorphology({
        "мой": (
            MorphInfo("мой", "ADJF", case="nomn", number="sing", gender="masc", score=0.9),
            MorphInfo("мой", "ADJF", case="accs", number="sing", gender="masc", score=0.8),
            MorphInfo("мыть", "VERB", mood="impr", number="sing", score=0.5),
        ),
        "друг": (
            MorphInfo(
                "друг", "NOUN", case="nomn", number="sing", gender="masc",
                animacy="anim", score=1.0,
            ),
        ),
        "дима": (
            MorphInfo(
                "дима", "NOUN", case="nomn", number="sing", gender="masc",
                animacy="anim", grammemes=NAME, score=1.0,
            ),
        ),
        "любит": (
            MorphInfo("любить", "VERB", number="sing", mood="indc", transitivity="tran", score=1.0),
        ),
        "чай": (
            MorphInfo("чай", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),
        ),
        "кто": (
            MorphInfo(
                "кто", "NPRO", case="nomn", number="sing",
                grammemes=frozenset({"Ques"}), score=1.0,
            ),
        ),
        "машину": (
            MorphInfo(
                "машина", "NOUN", case="accs", number="sing", gender="femn",
                animacy="inan", score=1.0,
            ),
        ),
        "руки": (
            MorphInfo(
                "рука", "NOUN", case="accs", number="plur", gender="femn",
                animacy="inan", score=1.0,
            ),
        ),
        "пол": (
            MorphInfo(
                "пол", "NOUN", case="nomn", number="sing", gender="masc",
                animacy="inan", score=1.0,
            ),
            MorphInfo(
                "пол", "NOUN", case="accs", number="sing", gender="masc",
                animacy="inan", score=1.0,
            ),
        ),
        "я": (MorphInfo("я", "NPRO", case="nomn", number="sing", score=1.0),),
        "люблю": (
            MorphInfo("любить", "VERB", number="sing", mood="indc", transitivity="tran", score=1.0),
        ),
    })


def _predicate_lemmas(graph) -> tuple[str, ...]:
    lemmas: list[str] = []
    for head in graph.predicates:
        lemmas.extend(head.lemma_candidates)
    return tuple(lemmas)


def test_prenominal_possessive_is_not_a_wash_command_when_finite_verb_follows():
    morph = _possessive_imperative_morph()
    graph = LinguisticCandidateBuilder(morph).build("мой друг Дима любит чай")
    assert _predicate_lemmas(graph) == ("любить",)


def test_who_is_my_friend_has_no_imperative_predicate():
    morph = _possessive_imperative_morph()
    graph = LinguisticCandidateBuilder(morph).build("кто мой друг")
    assert "мыть" not in _predicate_lemmas(graph)
    assert graph.predicates == ()
    assert graph.clauses[0].implicit_copula is True


def test_imperative_wash_commands_keep_the_verb_head():
    morph = _possessive_imperative_morph()
    car = LinguisticCandidateBuilder(morph).build("Мой машину")
    hands = LinguisticCandidateBuilder(morph).build("Мой руки")
    floor = LinguisticCandidateBuilder(morph).build("Мой пол")
    assert _predicate_lemmas(car) == ("мыть",)
    assert _predicate_lemmas(hands) == ("мыть",)
    assert _predicate_lemmas(floor) == ("мыть",)


def test_friend_name_np_uses_the_person_as_actant_identity():
    text = "мой друг Дима любит чай"
    morph = _possessive_imperative_morph()
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
    span = parser._resolve_span(text, parser._source_tokens(text), 1, 3)
    actant = parser._make_actant(ActantRole.SUBJECT, span)
    assert actant.mention == "мой друг Дима"
    assert actant.normalized_hint == "Дима"
    assert any(item.kind is NominalRelationKind.POSSESSOR for item in actant.nominal_relations)


def test_association_skips_wh_gap_and_does_not_probe():
    backend = ScriptedBackend({"semantic_association_query": ["ASSOCIATION:E1:E2"]})
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=0
    )
    query = QueryCandidate(
        PredicateCandidate("быть"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="кто", normalized_hint="кто"),
            ActantCandidate(ActantRole.OBJECT, mention="мой друг", normalized_hint="друг"),
        ),
        requested_roles=(ActantRole.SUBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    decision, attempts = classifier.classify("кто мой друг", query)
    assert decision is None
    assert attempts == ()
    assert backend.calls == []

    command = CommandCandidate(
        PredicateCandidate("мой"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="кто", normalized_hint="кто"),
            ActantCandidate(ActantRole.RECIPIENT, mention="друг", normalized_hint="друг"),
        ),
        local_id="C1",
    )
    decision, attempts = classifier.classify("кто мой друг", command)
    assert decision is None
    assert backend.calls == []


def test_copular_fill_role_does_not_probe_possessive_state_fragment():
    backend = ScriptedBackend({"semantic_association_query": ["ASSOCIATION:Ea:Eb"]})
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=0
    )
    query = QueryCandidate(
        PredicateCandidate("быть"),
        (
            ActantCandidate(ActantRole.STATE, mention="мой", normalized_hint="мой"),
            ActantCandidate(ActantRole.RECIPIENT, mention="друг", normalized_hint="друг"),
        ),
        requested_roles=(ActantRole.SUBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    decision, attempts = classifier.classify("кто мой друг", query)
    assert decision is None
    assert attempts == ()
    assert backend.calls == []


def test_association_protocol_echo_stays_ordinary():
    backend = ScriptedBackend({
        "semantic_association_query": ["ASSOCIATION:Ea:Eb", "ASSOCIATION:Ea:Eb"],
    })
    classifier = AssociationSemanticClassifier(
        backend, ROOT / "prompts" / "perception", retry_attempts=1
    )
    query = QueryCandidate(
        PredicateCandidate("connect"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="fire", normalized_hint="fire"),
            ActantCandidate(ActantRole.OBJECT, mention="smoke", normalized_hint="smoke"),
        ),
        local_id="Q1",
    )
    decision, attempts = classifier.classify("What connects fire and smoke?", query)
    assert decision is None
    assert len(attempts) == 2
    assert all(item.error is not None for item in attempts)


def test_who_is_my_friend_keeps_possessive_np_out_of_copular_state():
    text = "кто мой друг"
    morph = _possessive_imperative_morph()
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
    state = parser._deterministic_copular_state_span(
        text,
        tokens,
        None,
        PredicateCandidate("быть", normalized_hint="быть"),
        [],
        (),
    )
    assert state is None
    who = parser._resolve_span(text, tokens, 1, 1)
    phrases = parser._candidate_phrase_spans(
        text, tokens, None, [], requested_spans=(who,)
    )
    assert [item.text for item in phrases] == ["мой друг"]
    actant = parser._make_actant(ActantRole.OBJECT, phrases[0])
    assert actant.mention == "мой друг"
    assert actant.normalized_hint == "друг"
    assert any(item.kind is NominalRelationKind.POSSESSOR for item in actant.nominal_relations)


def test_discourse_probe_accepts_bare_index_for_unique_p_label():
    backend = ScriptedBackend({
        "semantic_discourse_current_event": ["C1"],
        "semantic_discourse_prior_event": ["1"],
        "semantic_discourse_relation": ["FOLLOW"],
    })
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
    )
    decision = parser.classify_discourse_relation(
        "Я люблю ча1. Я люблю чай.",
        ("люблю(SUBJECT=Пользователь, OBJECT=ча1)",),
        ("люблю(SUBJECT=Пользователь, OBJECT=чай)",),
    )
    assert decision is not None
    assert decision.prior_index == 0
    assert decision.current_index == 0
    assert decision.relation_id == "FOLLOW"


def test_possessive_named_friend_materializes_esta_for_relational_recall():
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
    context = InteractionContext(
        user_ref=core.ref(user.uid),
        self_ref=core.ref(self_entity.uid),
    )
    service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="мой друг Дима",
        normalized_hint="Дима",
        nominal_relations=(
            NominalRelationCandidate(
                NominalRelationKind.POSSESSOR,
                head_mention="друг",
                head_normalized_hint="друг",
                dependent_mention="мой",
            ),
        ),
    )
    assertion = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "любит",
            normalized_hint="любить",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            subject,
            ActantCandidate(ActantRole.OBJECT, mention="чай", normalized_hint="чай"),
        ),
    )
    service.integrate_external(
        PerceptionResult("мой друг Дима любит чай", assertions=(assertion,)),
        context,
    )

    dima = next(iter(core.store.find_entities_by_name("Дима")))
    friend = next(iter(core.store.find_entities_by_name("друг")))
    exists = [
        node
        for node in core.store.hypernodes_for_actant(user.uid)
        if node.actants.get(ActantRole.OBJECT) is not None
        and node.actants.get(ActantRole.AUXILLIARY) is not None
    ]
    assert len(exists) == 1
    node = exists[0]
    assert node.actants[ActantRole.SUBJECT].uid == user.uid
    assert node.actants[ActantRole.OBJECT].uid == friend.uid
    assert node.actants[ActantRole.AUXILLIARY].uid == dima.uid

    resolved = EntityResolver(core).resolve(
        ActantCandidate(ActantRole.OBJECT, mention="мой друг", normalized_hint="друг"),
        context,
        first_person_ref=context.user_ref,
        second_person_ref=context.self_ref,
    )
    assert isinstance(resolved, ExistingEntity)
    assert resolved.ref.uid == dima.uid


def test_number_row_digit_recovers_tea_but_codes_stay_unknown():
    morph = StaticMorphology(
        {
            "Я": (MorphInfo("я", "NPRO", case="nomn", number="sing", score=1.0),),
            "люблю": (
                MorphInfo(
                    "любить", "VERB", number="sing", mood="indc",
                    transitivity="tran", score=1.0,
                ),
            ),
            "чай": (
                MorphInfo(
                    "чай", "NOUN", case="accs", number="sing", gender="masc",
                    animacy="inan", score=1.0,
                ),
            ),
            "ча1": (),
            "Модуль": (MorphInfo("модуль", "NOUN", case="nomn", score=1.0),),
            "использует": (MorphInfo("использовать", "VERB", mood="indc", score=1.0),),
            "QX17": (),
        },
        known={"Я", "люблю", "чай", "Модуль", "использует"},
        candidate_map={},
    )
    recovery = LexicalRecovery(morph)
    tea_graph = LinguisticCandidateBuilder(morph, lexical_recovery=recovery).build("Я люблю ча1")
    tea = next(
        token.recovery for token in tea_graph.tokens if token.provenance_text == "ча1"
    )
    assert tea is not None
    assert tea.status is LexicalRecoveryStatus.CORRECTED_HIGH_CONFIDENCE
    assert tea.normalized_text.casefold() == "чай"

    code_graph = LinguisticCandidateBuilder(morph, lexical_recovery=recovery).build(
        "Модуль использует QX17."
    )
    code = next(
        token.recovery for token in code_graph.tokens if token.provenance_text == "QX17"
    )
    assert code is not None
    assert code.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
    assert code.normalized_text == "QX17"
