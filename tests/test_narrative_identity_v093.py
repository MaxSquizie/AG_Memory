from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    NominalRelationKind,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class Morphology:
    name = "v093-static"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(values) for key, values in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class ScriptedBackend:
    def __init__(self, answers=None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, dict(override or {})))
        queue = self.answers.get(role)
        if not queue:
            raise AssertionError(f"unexpected model call {role}:\n{prompt}")
        return LLMResponse(queue.pop(0), {})


def parser(morph, backend=None):
    return AdaptivePerceptionParser(
        backend or ScriptedBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )


def ev(text: str, needle: str, start: int = 0) -> EvidenceSpan:
    pos = text.index(needle, start)
    return EvidenceSpan(needle, pos, pos + len(needle))


def assertion(local_id: str, surface: str, lemma: str, *actants: ActantCandidate, evidence=None):
    roles = tuple(dict.fromkeys(item.role for item in actants))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            surface,
            normalized_hint=lemma,
            evidence=evidence,
            template_candidate=TemplateCandidate(roles),
        ),
        tuple(actants),
        evidence=evidence,
    )


def test_fronted_compound_subordinator_never_parents_to_previous_sentence():
    text = "Павел поставил таз. После того как дождь ослаб, вода капала."
    morph = Morphology({
        "павел": (MorphInfo("Павел", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "поставил": (MorphInfo("поставить", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
        "таз": (MorphInfo("таз", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        "после": (MorphInfo("после", "PREP", score=1.0),),
        "того": (MorphInfo("тот", "NPRO", case="gent", number="sing", gender="neut", score=1.0),),
        "как": (MorphInfo("как", "CONJ", score=1.0),),
        "дождь": (MorphInfo("дождь", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "ослаб": (MorphInfo("ослабнуть", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
        "вода": (MorphInfo("вода", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "капала": (MorphInfo("капать", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    child = next(clause for clause in graph.clauses if clause.marker == "после_того_как")
    parent = next(clause for clause in graph.clauses if clause.clause_id == child.parent_clause_id)
    assert child.sentence_id == parent.sentence_id == 2
    assert "вода капала" in parent.span.text.casefold()


def test_causal_connective_anchors_to_clause_predicate_not_synthetic_helper():
    text = "Бумага в письмах намокла, потому что вода просочилась."
    morph = Morphology({
        "бумага": (MorphInfo("бумага", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "в": (MorphInfo("в", "PREP", score=1.0),),
        "письмах": (MorphInfo("письмо", "NOUN", case="loct", number="plur", gender="neut", score=1.0),),
        "намокла": (MorphInfo("намокнуть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
        "потому": (MorphInfo("потому", "ADVB", score=1.0),),
        "что": (MorphInfo("что", "CONJ", score=1.0),),
        "вода": (MorphInfo("вода", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "просочилась": (MorphInfo("просочиться", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    p = parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    p._candidate_graph = graph
    tokens = p._source_tokens(text)
    spans = {
        "Ahelper": p._resolve_span(text, tokens, 2, 2),
        "Awet": p._resolve_span(text, tokens, 4, 4),
        "Aseep": p._resolve_span(text, tokens, 8, 8),
    }
    assertions = [
        assertion("Ahelper", "в", "в"),
        assertion("Awet", "намокла", "намокнуть"),
        assertion("Aseep", "просочилась", "просочиться"),
    ]
    relations = p._derive_situation_relations(assertions, spans)
    cause = next(item for item in relations if item.relation_id == "CAUSE")
    assert cause.source_ref == "Aseep"
    assert cause.target_ref == "Awet"


def test_case_syncretic_genitive_np_uses_bounded_attachment_and_keeps_structure():
    text = "Кусок штукатурки упал."
    morph = Morphology({
        "кусок": (MorphInfo("кусок", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "штукатурки": (
            MorphInfo("штукатурка", "NOUN", case="gent", number="sing", gender="femn", score=0.5),
            MorphInfo("штукатурка", "NOUN", case="nomn", number="plur", gender="femn", score=0.5),
        ),
        "упал": (MorphInfo("упасть", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
    })
    backend = ScriptedBackend({"perception_nominal_genitive_attachment": ["GENITIVE_DEP"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = p._source_tokens(text)
    end = p._nominal_phrase_end(tokens, 1, 3, set())
    assert end == 2
    actant = p._make_actant(ActantRole.SUBJECT, p._resolve_span(text, tokens, 1, 2))
    assert actant.normalized_hint == "Кусок"
    assert [(r.kind, r.dependent_normalized_hint) for r in actant.nominal_relations] == [
        (NominalRelationKind.GENITIVE_DEP, "штукатурка")
    ]
    assert [call[0] for call in backend.calls] == ["perception_nominal_genitive_attachment"]


def test_postnominal_possessive_is_not_swallowed_when_probe_selects_participant():
    text = "Падение штукатурки его испугало."
    morph = Morphology({
        "падение": (MorphInfo("падение", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "штукатурки": (MorphInfo("штукатурка", "NOUN", case="gent", number="sing", gender="femn", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", grammemes=frozenset({"NPRO", "Anph", "3per"}), score=0.7),
            MorphInfo("его", "ADJF", grammemes=frozenset({"ADJF", "Apro", "Anph", "Fixd"}), score=0.3),
        ),
        "испугало": (MorphInfo("испугать", "VERB", number="sing", gender="neut", mood="indc", transitivity="tran", score=1.0),),
    })
    backend = ScriptedBackend({
        "perception_postnominal_possessive_attachment": ["SEPARATE_PARTICIPANT"]
    })
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = p._source_tokens(text)
    assert p._nominal_phrase_end(tokens, 1, 4, set()) == 2
    np = p._make_actant(ActantRole.SUBJECT, p._resolve_span(text, tokens, 1, 2))
    assert all(rel.kind is not NominalRelationKind.POSSESSOR for rel in np.nominal_relations)
    assert backend.calls[0][0] == "perception_postnominal_possessive_attachment"


def test_cross_sentence_personal_pronoun_preserves_all_compatible_antecedents():
    text = "Шум разбудил Павла. Он пришёл."
    morph = Morphology({
        "шум": (MorphInfo("шум", "NOUN", case="nomn", number="sing", gender="masc", animacy="inan", score=1.0),),
        "разбудил": (MorphInfo("разбудить", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", score=1.0),),
        "павла": (MorphInfo("Павел", "NOUN", case="accs", number="sing", gender="masc", animacy="anim", score=1.0),),
        "он": (MorphInfo("он", "NPRO", case="nomn", number="sing", gender="masc", grammemes=frozenset({"NPRO", "3per"}), score=1.0),),
        "пришёл": (MorphInfo("прийти", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
    })
    backend = ScriptedBackend()
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": assertion(
            "A1", "разбудил", "разбудить",
            ActantCandidate(ActantRole.SUBJECT, mention="Шум", normalized_hint="шум", evidence=ev(text, "Шум"), grammatical_number="sing"),
            ActantCandidate(ActantRole.OBJECT, mention="Павла", normalized_hint="Павел", evidence=ev(text, "Павла"), grammatical_number="sing"),
            evidence=ev(text, "разбудил"),
        ),
        "A2": assertion(
            "A2", "пришёл", "прийти",
            ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", evidence=ev(text, "Он"), grammatical_number="sing"),
            evidence=ev(text, "пришёл"),
        ),
    }
    p._resolve_pronoun_coreferences(by_id)
    pavel = next(a for a in by_id["A1"].actants if a.role is ActantRole.OBJECT)
    assert pavel.entity_ref is not None
    alternatives = by_id["A2"].alternatives
    assert len(alternatives) == 2
    possible = {
        next(a for a in item.actants if a.role is ActantRole.SUBJECT).entity_ref
        for item in alternatives
    }
    antecedents = {
        a.entity_ref
        for a in by_id["A1"].actants
        if a.role in {ActantRole.SUBJECT, ActantRole.OBJECT}
    }
    assert possible == antecedents
    assert backend.calls == []


def test_explicit_coordinator_clause_inherits_omitted_subject():
    text = "Вера узнала знак и на мгновение закрыла глаза."
    morph = Morphology({
        "вера": (MorphInfo("Вера", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "узнала": (MorphInfo("узнать", "VERB", number="sing", gender="femn", mood="indc", transitivity="tran", score=1.0),),
        "знак": (MorphInfo("знак", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "на": (MorphInfo("на", "PREP", score=1.0),),
        "мгновение": (MorphInfo("мгновение", "NOUN", case="accs", number="sing", gender="neut", score=1.0),),
        "закрыла": (MorphInfo("закрыть", "VERB", number="sing", gender="femn", mood="indc", transitivity="tran", score=1.0),),
        "глаза": (MorphInfo("глаз", "NOUN", case="accs", number="plur", gender="masc", score=1.0),),
    })
    p = parser(morph)
    builder = LinguisticCandidateBuilder(morph)
    graph = builder.build(text)
    # The production parser may split a coordinator-led predicate into a second
    # clause after structural mode resolution. Build that exact source structure
    # here so this test targets omitted-subject inheritance, not clause segmentation.
    original = graph.clauses[0]
    heads = tuple(original.predicate_heads)
    left = replace(
        original,
        clause_id="CL1",
        span=builder._span(text, graph.tokens, 1, 3),
        predicate_heads=(heads[0],),
        marker="вера",
    )
    right = replace(
        original,
        clause_id="CL2",
        span=builder._span(text, graph.tokens, 4, 8),
        predicate_heads=(heads[-1],),
        marker="и",
    )
    p._candidate_graph = replace(graph, clauses=(left, right))
    clauses = [left, right]
    by_id = {
        "A1": assertion(
            "A1", "узнала", "узнать",
            ActantCandidate(ActantRole.SUBJECT, mention="Вера", normalized_hint="Вера", entity_ref="E1", evidence=ev(text, "Вера"), grammatical_number="sing"),
            evidence=ev(text, "узнала"),
        ),
        "A2": assertion("A2", "закрыла", "закрыть", evidence=ev(text, "закрыла")),
    }
    p._inherit_omitted_clause_subjects(
        by_id, {clauses[0].clause_id: ["A1"], clauses[1].clause_id: ["A2"]}
    )
    inherited = next(a for a in by_id["A2"].actants if a.role is ActantRole.SUBJECT)
    assert inherited.entity_ref == "E1"


def test_quantified_subject_uses_common_noun_lemma_and_plural_group_number():
    text = "Несколько матросов подошли."
    morph = Morphology({
        "несколько": (
            MorphInfo("несколько", "ADVB", score=0.9),
            MorphInfo("несколько", "NUMR", case="nomn", score=0.1),
        ),
        "матросов": (
            MorphInfo("матрос", "NOUN", case="gent", number="plur", gender="masc", animacy="anim", score=0.5),
            MorphInfo("Матросов", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", grammemes=frozenset({"Surn"}), score=0.25),
            MorphInfo("матрос", "NOUN", case="accs", number="plur", gender="masc", animacy="anim", score=0.25),
        ),
        "подошли": (MorphInfo("подойти", "VERB", number="plur", mood="indc", score=1.0),),
    })
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = p._source_tokens(text)
    actant = p._make_actant(ActantRole.SUBJECT, p._resolve_span(text, tokens, 1, 2))
    assert actant.normalized_hint.casefold() == "матрос"
    assert actant.grammatical_number == "plur"


def test_global_memory_does_not_merge_singular_and_plural_same_lemma():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")}, {"identity_role": "USER"})
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")}, {"identity_role": "SELF"})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(self_entity.uid))
    service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))

    def integrate(local_id, surface, lemma, mention, number):
        subject = ActantCandidate(
            ActantRole.SUBJECT,
            mention=mention,
            normalized_hint="матрос",
            grammatical_number=number,
        )
        result = PerceptionResult(
            mention,
            assertions=(assertion(local_id, surface, lemma, subject),),
        )
        return service.integrate_external(result, context).assertions[0]

    plural_fact = integrate("A1", "подошли", "подойти", "матросы", "plur")
    singular_fact = integrate("A2", "подошёл", "подойти", "матрос", "sing")
    plural_again = integrate("A3", "ушли", "уйти", "матросы", "plur")

    plural_ref = core.store.get_hypernode(plural_fact.ref.uid).actants[ActantRole.SUBJECT]
    singular_ref = core.store.get_hypernode(singular_fact.ref.uid).actants[ActantRole.SUBJECT]
    plural_again_ref = core.store.get_hypernode(plural_again.ref.uid).actants[ActantRole.SUBJECT]
    assert plural_ref.uid != singular_ref.uid
    assert plural_again_ref.uid == plural_ref.uid
    entities = core.store.find_entities_by_name("матрос", Domain.C)
    assert {item.meta.get("grammatical_number") for item in entities} == {"sing", "plur"}


def test_preposition_governed_nominal_homograph_is_not_predicate_or_coordination_member():
    text = "Алексей сорвал занавеску с крючков и бросил её."
    morph = Morphology({
        "алексей": (MorphInfo("Алексей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "сорвал": (MorphInfo("сорвать", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", score=1.0),),
        "занавеску": (MorphInfo("занавеска", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        "с": (MorphInfo("с", "PREP", score=1.0),),
        "крючков": (
            MorphInfo("Крючков", "NOUN", case="nomn", number="sing", gender="masc", animacy="anim", score=0.5),
            MorphInfo("крючок", "NOUN", case="gent", number="plur", gender="masc", animacy="inan", score=0.25),
            MorphInfo("крючковый", "ADJS", number="sing", gender="masc", score=0.25),
        ),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "бросил": (MorphInfo("бросить", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", score=1.0),),
        "её": (MorphInfo("она", "NPRO", case="accs", number="sing", gender="femn", score=1.0),),
    })
    graph = LinguisticCandidateBuilder(morph).build(text)
    heads = [(item.token_index, item.lemma_candidates) for item in graph.predicates]
    assert all(index != 5 for index, _ in heads)
    assert any(group.member_token_indices == (2, 7) for group in graph.frame_graph.coordinations)


def test_asserted_infinitive_survives_embedded_status_marking_after_bounded_probe():
    text = "Лодка продолжала идти."
    morph = Morphology({
        "лодка": (MorphInfo("лодка", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "продолжала": (MorphInfo("продолжать", "VERB", number="sing", gender="femn", mood="indc", transitivity="tran", score=1.0),),
        "идти": (MorphInfo("идти", "INFN", transitivity="intr", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_nonfinite_assertion_status": ["ASSERTED_EVENT"]})
    p = parser(morph, backend)
    p._asserted_nonfinite_refs = set()
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = p._source_tokens(text)
    subject = ActantCandidate(ActantRole.SUBJECT, mention="Лодка", normalized_hint="лодка", evidence=ev(text, "Лодка"))
    child_subject = replace(subject, evidence=ev(text, "Лодка"))
    by_id = {
        "A1": assertion(
            "A1", "продолжала", "продолжать",
            subject,
            ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),
            evidence=ev(text, "продолжала"),
        ),
        "A2": assertion("A2", "идти", "идти", child_subject, evidence=ev(text, "идти")),
    }
    spans = {
        "A1": p._resolve_span(text, tokens, 2, 2),
        "A2": p._resolve_span(text, tokens, 3, 3),
    }
    p._classify_nonfinite_assertion_status(by_id, spans)
    marked = p._mark_embedded_statuses(list(by_id.values()))
    child = next(item for item in marked if item.local_id == "A2")
    assert child.status.value == "ASSERTED"
    assert "A2" in p._asserted_nonfinite_refs


def test_nonasserted_infinitive_remains_embedded_after_bounded_probe():
    text = "Он хотел уйти."
    morph = Morphology({
        "он": (MorphInfo("он", "NPRO", case="nomn", number="sing", gender="masc", score=1.0),),
        "хотел": (MorphInfo("хотеть", "VERB", number="sing", gender="masc", mood="indc", transitivity="tran", score=1.0),),
        "уйти": (MorphInfo("уйти", "INFN", transitivity="intr", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_nonfinite_assertion_status": ["NONASSERTED_CONTENT"]})
    p = parser(morph, backend)
    p._asserted_nonfinite_refs = set()
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = p._source_tokens(text)
    subject = ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", evidence=ev(text, "Он"))
    by_id = {
        "A1": assertion(
            "A1", "хотел", "хотеть",
            subject,
            ActantCandidate(ActantRole.OBJECT, candidate_ref="A2"),
            evidence=ev(text, "хотел"),
        ),
        "A2": assertion("A2", "уйти", "уйти", replace(subject, evidence=ev(text, "Он")), evidence=ev(text, "уйти")),
    }
    spans = {
        "A1": p._resolve_span(text, tokens, 2, 2),
        "A2": p._resolve_span(text, tokens, 3, 3),
    }
    p._classify_nonfinite_assertion_status(by_id, spans)
    marked = p._mark_embedded_statuses(list(by_id.values()))
    child = next(item for item in marked if item.local_id == "A2")
    assert child.status.value == "EMBEDDED"
    assert "A2" not in p._asserted_nonfinite_refs
