from __future__ import annotations

from pathlib import Path

from ah.config import LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PredicateCandidate,
    SituationRelationHintCandidate,
    SituationRelationHintKind,
    TemplateCandidate,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

ROOT = Path(__file__).resolve().parents[1]


class Morphology:
    name = "v095-static"

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


def parser(morph, backend):
    return AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )


def test_unique_compatible_n_is_enriched_in_place_instead_of_duplicated():
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.add_abstract_symbol({"усилиться"})
    template = core.add_template(
        Domain.C,
        core.ref(pred.uid),
        (ActantRole.SUBJECT, ActantRole.LOCATION),
    )
    wind = core.add_entity(Domain.C, {"name": Property("name", "ветер", "str")})
    bay = core.add_entity(Domain.C, {"name": Property("name", "бухта", "str")})

    first, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(wind.uid)},
        0.4,
    )
    assert created
    second, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {
            ActantRole.SUBJECT: core.ref(wind.uid),
            ActantRole.LOCATION: core.ref(bay.uid),
        },
        0.4,
    )
    assert not created
    assert second.uid == first.uid
    assert second.actants[ActantRole.LOCATION].uid == bay.uid
    assert second.meta["occurrence_count"] == 2
    assert len(core.store.find_hypernodes_by_template(template.uid)) == 1


def test_enrichment_refuses_to_choose_between_two_compatible_specific_events():
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.add_abstract_symbol({"войти"})
    template = core.add_template(
        Domain.C,
        core.ref(pred.uid),
        (ActantRole.SUBJECT, ActantRole.LOCATION),
    )
    ivan = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
    house = core.add_entity(Domain.C, {"name": Property("name", "дом", "str")})
    office = core.add_entity(Domain.C, {"name": Property("name", "офис", "str")})
    for place in (house, office):
        core.add_hypernode(
            Domain.C,
            core.ref(template.uid),
            {
                ActantRole.SUBJECT: core.ref(ivan.uid),
                ActantRole.LOCATION: core.ref(place.uid),
            },
            0.4,
        )
    generic, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(ivan.uid)},
        0.4,
    )
    assert created
    assert ActantRole.LOCATION not in generic.actants
    assert len(core.store.find_hypernodes_by_template(template.uid)) == 3


def test_incomparable_optional_roles_never_leak_between_repeated_events():
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.add_abstract_symbol({"обработать"})
    template = core.add_template(
        Domain.C,
        core.ref(pred.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TOOL, ActantRole.TIME),
    )
    actor = core.add_entity(Domain.C, {"name": Property("name", "исполнитель", "str")})
    obj = core.add_entity(Domain.C, {"name": Property("name", "деталь", "str")})
    tool = core.add_entity(Domain.C, {"name": Property("name", "инструмент", "str")})
    moment = core.add_entity(Domain.C, {"name": Property("name", "момент", "str")})

    first, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {
            ActantRole.SUBJECT: core.ref(actor.uid),
            ActantRole.OBJECT: core.ref(obj.uid),
            ActantRole.TOOL: core.ref(tool.uid),
        },
        0.4,
    )
    assert created
    second, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {
            ActantRole.SUBJECT: core.ref(actor.uid),
            ActantRole.OBJECT: core.ref(obj.uid),
            ActantRole.TIME: core.ref(moment.uid),
        },
        0.4,
    )
    assert created
    assert second.uid != first.uid
    assert set(first.actants) == {ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TOOL}
    assert set(second.actants) == {ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME}


def test_less_specific_repeat_does_not_inherit_unstated_optional_roles():
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.add_abstract_symbol({"переместить"})
    template = core.add_template(
        Domain.C,
        core.ref(pred.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION),
    )
    actor = core.add_entity(Domain.C, {"name": Property("name", "оператор", "str")})
    obj = core.add_entity(Domain.C, {"name": Property("name", "контейнер", "str")})
    place = core.add_entity(Domain.C, {"name": Property("name", "площадка", "str")})
    detailed, _ = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {
            ActantRole.SUBJECT: core.ref(actor.uid),
            ActantRole.OBJECT: core.ref(obj.uid),
            ActantRole.LOCATION: core.ref(place.uid),
        },
        0.4,
    )
    generic, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {
            ActantRole.SUBJECT: core.ref(actor.uid),
            ActantRole.OBJECT: core.ref(obj.uid),
        },
        0.4,
    )
    assert created
    assert generic.uid != detailed.uid
    assert ActantRole.LOCATION not in generic.actants


def test_narrative_causal_hint_is_promoted_only_for_structural_patient_to_subject_reaction():
    text = "Зурита ударил матроса, и матрос упал."
    morph = Morphology({
        "зурита": (MorphInfo("Зурита", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "ударил": (MorphInfo("ударить", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "матроса": (MorphInfo("матрос", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "матрос": (MorphInfo("матрос", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "упал": (MorphInfo("упасть", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_narrative_causality": ["CAUSAL_RESPONSE"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    hit = AssertionCandidate(
        "A1",
        PredicateCandidate("ударил", "ударить", evidence=EvidenceSpan("ударил", 7, 13)),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Зурита", normalized_hint="Зурита"),
            ActantCandidate(ActantRole.OBJECT, mention="матроса", normalized_hint="матрос"),
        ),
        evidence=EvidenceSpan("Зурита ударил матроса", 0, 21),
    )
    target_start = text.index("матрос упал")
    fall = AssertionCandidate(
        "A2",
        PredicateCandidate("упал", "упасть", evidence=EvidenceSpan("упал", target_start + 7, target_start + 11)),
        (ActantCandidate(ActantRole.SUBJECT, mention="матрос", normalized_hint="матрос"),),
        evidence=EvidenceSpan("матрос упал", target_start, target_start + 11),
    )
    hint = SituationRelationHintCandidate(
        SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "A2"
    )
    relations, hints, diagnostics = p._resolve_narrative_causal_candidates(
        [hit, fall], (), (hint,)
    )
    assert [(r.canonical_relation_id, r.source_ref, r.target_ref) for r in relations] == [
        ("CAUSE", "A1", "A2")
    ]
    assert hints == ()
    assert diagnostics
    assert backend.calls[0][2].get("enable_thinking") is False


def test_narrative_causal_probe_keeps_uncertain_structural_reaction_noncanonical():
    text = "Иван встретил Петра, и Пётр улыбнулся."
    morph = Morphology({
        "иван": (MorphInfo("Иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "встретил": (MorphInfo("встретить", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "петра": (MorphInfo("Пётр", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "пётр": (MorphInfo("Пётр", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "улыбнулся": (MorphInfo("улыбнуться", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_narrative_causality": ["UNCLEAR"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    meet_end = text.index(",")
    smile_start = text.index("Пётр улыбнулся")
    a1 = AssertionCandidate(
        "A1",
        PredicateCandidate("встретил", "встретить", evidence=EvidenceSpan("встретил", 5, 13)),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),
            ActantCandidate(ActantRole.OBJECT, mention="Петра", normalized_hint="Пётр"),
        ),
        evidence=EvidenceSpan(text[:meet_end], 0, meet_end),
    )
    a2 = AssertionCandidate(
        "A2",
        PredicateCandidate("улыбнулся", "улыбнуться", evidence=EvidenceSpan("улыбнулся", smile_start + 5, smile_start + 14)),
        (ActantCandidate(ActantRole.SUBJECT, mention="Пётр", normalized_hint="Пётр"),),
        evidence=EvidenceSpan("Пётр улыбнулся", smile_start, smile_start + 14),
    )
    hint = SituationRelationHintCandidate(SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "A2")
    relations, hints, _ = p._resolve_narrative_causal_candidates([a1, a2], (), (hint,))
    assert relations == ()
    assert hints == (hint,)


def test_generic_cross_sentence_causal_hint_does_not_trigger_semantic_second_pass():
    text = "Раздался звонок. Иван посмотрел в окно."
    p = parser(Morphology({}), ScriptedBackend())
    p._candidate_graph = LinguisticCandidateBuilder(p.morphology).build(text)
    a1 = AssertionCandidate("A1", PredicateCandidate("звонок"), (), evidence=EvidenceSpan("звонок", 9, 15))
    a2 = AssertionCandidate("A2", PredicateCandidate("посмотрел"), (), evidence=EvidenceSpan("посмотрел", 22, 31))
    hint = SituationRelationHintCandidate(SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "A2")
    relations, hints, _ = p._resolve_narrative_causal_candidates([a1, a2], (), (hint,))
    assert relations == ()
    assert hints == (hint,)

def test_reused_unresolved_personal_pronoun_waits_for_real_antecedent_binding():
    text = "Алексей пришёл. Он открыл дверь и вошёл."
    alexei_start = text.index("Алексей")
    pronoun_start = text.index("Он")
    morph = Morphology({
        "алексей": (MorphInfo("Алексей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "пришёл": (MorphInfo("прийти", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "он": (MorphInfo("он", "NPRO", case="nomn", number="sing", gender="masc", grammemes=frozenset({"NPRO", "3per"}), score=1.0),),
        "открыл": (MorphInfo("открыть", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "дверь": (MorphInfo("дверь", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
        "вошёл": (MorphInfo("войти", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
    })
    p = parser(morph, ScriptedBackend())
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    alexei = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Алексей",
        normalized_hint="Алексей",
        evidence=EvidenceSpan("Алексей", alexei_start, alexei_start + 7),
    )
    on1 = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Он",
        normalized_hint="он",
        evidence=EvidenceSpan("Он", pronoun_start, pronoun_start + 2),
    )
    on2 = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Он",
        normalized_hint="он",
        evidence=EvidenceSpan("Он", pronoun_start, pronoun_start + 2),
    )
    by_id = {
        "A1": AssertionCandidate("A1", PredicateCandidate("пришёл", "прийти", evidence=EvidenceSpan("пришёл", 8, 14)), (alexei,)),
        "A2": AssertionCandidate("A2", PredicateCandidate("открыл", "открыть", evidence=EvidenceSpan("открыл", pronoun_start + 3, pronoun_start + 9)), (on1,)),
        "A3": AssertionCandidate("A3", PredicateCandidate("вошёл", "войти", evidence=EvidenceSpan("вошёл", text.rindex("вошёл"), len(text)-1)), (on2,)),
    }
    p._bind_reused_source_mentions(by_id)
    assert all(a.entity_ref is None for aid in ("A2", "A3") for a in by_id[aid].actants)
    p._resolve_pronoun_coreferences(by_id)
    p._resolve_pronoun_coreferences(by_id)
    p._bind_reused_source_mentions(by_id)
    refs = [by_id[aid].actants[0].entity_ref for aid in ("A1", "A2", "A3")]
    assert refs[0] is not None
    assert refs[0] == refs[1] == refs[2]


def test_orphan_subordinate_event_can_be_projected_as_matrix_proposition_content():
    text = "Иван увидел, что к дому, улыбаясь, подошла Мария."
    morph = Morphology({
        "иван": (MorphInfo("Иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "увидел": (MorphInfo("увидеть", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "что": (MorphInfo("что", "CONJ", score=1.0),),
        "к": (MorphInfo("к", "PREP", score=1.0),),
        "дому": (MorphInfo("дом", "NOUN", case="datv", number="sing", gender="masc", score=1.0),),
        "улыбаясь": (MorphInfo("улыбаться", "GRND", score=1.0),),
        "подошла": (MorphInfo("подойти", "VERB", mood="indc", number="sing", gender="femn", score=1.0),),
        "мария": (MorphInfo("Мария", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_subordinate_content": ["EVENT_CONTENT"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    parent = AssertionCandidate(
        "A1",
        PredicateCandidate("увидел", "увидеть", evidence=EvidenceSpan("увидел", 5, 11)),
        (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),),
        evidence=EvidenceSpan("Иван увидел", 0, 11),
    )
    child = AssertionCandidate(
        "A2",
        PredicateCandidate("подошла", "подойти", evidence=EvidenceSpan("подошла", 35, 42)),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="Мария",
                normalized_hint="Мария",
                evidence=EvidenceSpan("Мария", 43, 48),
            ),
        ),
        evidence=EvidenceSpan("подошла Мария", 35, 48),
    )
    projected, diagnostics = p._project_orphan_subordinate_participants([parent, child])
    parent_out = next(item for item in projected if item.local_id == "A1")
    objects = [a for a in parent_out.actants if a.role is ActantRole.OBJECT]
    assert len(objects) == 1
    assert objects[0].candidate_ref == "A2"
    assert objects[0].normalized_hint is None
    assert diagnostics
    assert backend.calls[0][0] == "semantic_subordinate_content"
    assert backend.calls[0][2].get("enable_thinking") is False



def test_enrichment_preserves_existing_uid_and_links_when_template_valency_grows():
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.add_abstract_symbol({"усилиться"})
    cause_pred = core.add_abstract_symbol({"начаться"})
    template = core.add_template(Domain.C, core.ref(pred.uid), (ActantRole.SUBJECT,))
    cause_template = core.add_template(Domain.C, core.ref(cause_pred.uid), (ActantRole.SUBJECT,))
    wind = core.add_entity(Domain.C, {"name": Property("name", "ветер", "str")})
    storm = core.add_entity(Domain.C, {"name": Property("name", "шторм", "str")})
    bay = core.add_entity(Domain.C, {"name": Property("name", "бухта", "str")})
    event, _ = core.add_hypernode(
        Domain.C, core.ref(template.uid), {ActantRole.SUBJECT: core.ref(wind.uid)}, 0.4
    )
    cause, _ = core.add_hypernode(
        Domain.C, core.ref(cause_template.uid), {ActantRole.SUBJECT: core.ref(storm.uid)}, 0.4
    )
    link, _ = core.ensure_link("CAUSE", core.ref(cause.uid), core.ref(event.uid), 0.2)

    core.expand_template_roles(template.uid, (ActantRole.LOCATION,))
    enriched, created = core.add_or_enrich_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(wind.uid), ActantRole.LOCATION: core.ref(bay.uid)},
        0.4,
    )
    assert not created
    assert enriched.uid == event.uid
    assert enriched.actants[ActantRole.LOCATION].uid == bay.uid
    stored_link = core.store.get_link(link.uid)
    assert stored_link.target.uid == event.uid == enriched.uid


def test_same_sentence_causal_candidate_is_reviewed_even_before_entity_identity_converges():
    text = "Матрос ухватил его, но Зурита ударил матроса."
    morph = Morphology({
        "матрос": (MorphInfo("матрос", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "ухватил": (MorphInfo("ухватить", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "его": (MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", score=1.0),),
        "но": (MorphInfo("но", "CONJ", score=1.0),),
        "зурита": (MorphInfo("Зурита", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "ударил": (MorphInfo("ударить", "VERB", mood="indc", number="sing", gender="masc", score=1.0),),
        "матроса": (MorphInfo("матрос", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
    })
    backend = ScriptedBackend({"semantic_narrative_causality": ["CAUSAL_RESPONSE"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    a1 = AssertionCandidate(
        "A1", PredicateCandidate("ухватил", "ухватить", evidence=EvidenceSpan("ухватил", 7, 14)),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Матрос", normalized_hint="матрос", entity_ref="E1"),
            ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="он"),
        ),
        evidence=EvidenceSpan("Матрос ухватил его", 0, 17),
    )
    hit_start = text.index("ударил")
    a2 = AssertionCandidate(
        "A2", PredicateCandidate("ударил", "ударить", evidence=EvidenceSpan("ударил", hit_start, hit_start + 6)),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Зурита", normalized_hint="Зурита"),
            ActantCandidate(ActantRole.OBJECT, mention="матроса", normalized_hint="матрос", entity_ref="E1"),
        ),
        evidence=EvidenceSpan("Зурита ударил матроса", text.index("Зурита"), text.index("матроса") + 7),
    )
    hint = SituationRelationHintCandidate(
        SituationRelationHintKind.CAUSAL_CANDIDATE, "A1", "A2"
    )
    relations, hints, _ = p._resolve_narrative_causal_candidates([a1, a2], (), (hint,))
    assert [(r.canonical_relation_id, r.source_ref, r.target_ref) for r in relations] == [
        ("CAUSE", "A1", "A2")
    ]
    assert hints == ()


def test_factive_proposition_content_is_promoted_back_to_asserted():
    text = "Иван увидел, что лодка приближалась."
    morph = Morphology({})
    backend = ScriptedBackend({"semantic_factivity": ["FACTIVE"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    child = AssertionCandidate(
        "A2",
        PredicateCandidate("приближалась", "приближаться"),
        (ActantCandidate(ActantRole.SUBJECT, mention="лодка", normalized_hint="лодка"),),
        status=AssertionStatus.EMBEDDED,
    )
    parent = AssertionCandidate(
        "A1",
        PredicateCandidate("увидел", "увидеть"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),
            ActantCandidate(
                ActantRole.OBJECT,
                candidate_ref="A2",
                semantic_hint="SUBORDINATE_PROPOSITION_CONTENT",
            ),
        ),
    )
    promoted, diagnostics = p._promote_factive_embedded_content([parent, child])
    child_out = next(item for item in promoted if item.local_id == "A2")
    assert child_out.status is AssertionStatus.ASSERTED
    assert diagnostics == ("factivity: A2 promoted to ASSERTED content of A1",)
    assert backend.calls[0][0] == "semantic_factivity"
    assert backend.calls[0][2].get("enable_thinking") is False


def test_nonfactive_proposition_content_remains_embedded():
    text = "Иван думал, что лодка приближалась."
    morph = Morphology({})
    backend = ScriptedBackend({"semantic_factivity": ["NONFACTIVE"]})
    p = parser(morph, backend)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    child = AssertionCandidate(
        "A2",
        PredicateCandidate("приближалась", "приближаться"),
        (ActantCandidate(ActantRole.SUBJECT, mention="лодка", normalized_hint="лодка"),),
        status=AssertionStatus.EMBEDDED,
    )
    parent = AssertionCandidate(
        "A1",
        PredicateCandidate("думал", "думать"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),
            ActantCandidate(
                ActantRole.OBJECT,
                candidate_ref="A2",
                semantic_hint="SUBORDINATE_PROPOSITION_CONTENT",
            ),
        ),
    )
    marked, diagnostics = p._promote_factive_embedded_content([parent, child])
    child_out = next(item for item in marked if item.local_id == "A2")
    assert child_out.status is AssertionStatus.EMBEDDED
    assert diagnostics == ()
