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
    name = "v092-static"

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


def ev(text: str, needle: str, start: int = 0) -> EvidenceSpan:
    pos = text.index(needle, start)
    return EvidenceSpan(needle, pos, pos + len(needle))


def assertion(local_id: str, surface: str, lemma: str, *actants: ActantCandidate, evidence=None):
    roles = tuple(dict.fromkeys(a.role for a in actants))
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


def runtime(morphology: StaticMorphology):
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")}, {"identity_role": "SELF"}
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}, {"identity_role": "USER"}
    )
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    service = IntegrationService(
        core,
        IntegrationConfig.from_settings(IntegrationSettings()),
        discourse_morphology=morphology,
    )
    return core, context, service


def test_current_pymorphy_style_postnominal_possessive_stays_inside_np():
    """Regression for the exact Apro+Anph+Fixd signature seen in the live run."""
    text = "Торжество его было недолгим."
    morph = StaticMorphology({
        "торжество": (MorphInfo("торжество", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", grammemes=frozenset({"NPRO", "Anph", "3per"}), score=0.24),
            MorphInfo("его", "ADJF", case="gent", number="sing", gender="neut", grammemes=frozenset({"ADJF", "Apro", "Anph", "Fixd"}), score=0.04),
        ),
        "было": (MorphInfo("быть", "VERB", number="sing", gender="neut", mood="indc", score=1.0),),
        "недолгим": (MorphInfo("недолгий", "ADJF", case="ablt", number="sing", gender="neut", score=1.0),),
    })
    parser = make_parser(morph)
    graph = LinguisticCandidateBuilder(morph).build(text)
    parser._candidate_graph = graph
    tokens = parser._source_tokens(text)

    predicate = parser._resolve_span(text, tokens, 3, 3)
    state = parser._resolve_span(text, tokens, 4, 4)
    holder = parser._deterministic_copular_holder_span(tokens, predicate, state)
    assert holder is not None
    assert holder.text == "Торжество его"

    subject = parser._make_actant(ActantRole.SUBJECT, holder)
    assert subject.normalized_hint == "Торжество"
    assert [(r.kind, r.dependent_mention) for r in subject.nominal_relations] == [
        (NominalRelationKind.POSSESSOR, "его")
    ]


def test_attributive_modifier_uses_nominal_head_as_canonical_identity():
    text = "Сухая ветка сломалась."
    morph = StaticMorphology({
        "сухая": (MorphInfo("сухой", "ADJF", case="nomn", number="sing", gender="femn", score=1.0),),
        "ветка": (MorphInfo("ветка", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "сломалась": (MorphInfo("сломаться", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    span = parser._resolve_span(text, parser._source_tokens(text), 1, 2)
    actant = parser._make_actant(ActantRole.SUBJECT, span)

    assert actant.mention == "Сухая ветка"
    assert actant.normalized_hint == "ветка"
    assert [(r.kind, r.head_normalized_hint, r.dependent_normalized_hint) for r in actant.nominal_relations] == [
        (NominalRelationKind.NOMINAL_MODIFIER, "ветка", "сухой")
    ]


def test_nested_genitive_keeps_modifiers_on_their_own_heads():
    text = "Положили в нижний ящик письменного стола."
    morph = StaticMorphology({
        "положили": (MorphInfo("положить", "VERB", number="plur", mood="indc", score=1.0),),
        "в": (MorphInfo("в", "PREP", score=1.0),),
        "нижний": (MorphInfo("нижний", "ADJF", case="accs", number="sing", gender="masc", score=1.0),),
        "ящик": (MorphInfo("ящик", "NOUN", case="accs", number="sing", gender="masc", score=1.0),),
        "письменного": (MorphInfo("письменный", "ADJF", case="gent", number="sing", gender="masc", score=1.0),),
        "стола": (MorphInfo("стол", "NOUN", case="gent", number="sing", gender="masc", score=1.0),),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    span = parser._resolve_span(text, parser._source_tokens(text), 2, 6)
    actant = parser._make_actant(ActantRole.LOCATION, span)

    assert actant.normalized_hint == "ящик"
    assert [(r.kind, r.head_normalized_hint, r.dependent_normalized_hint) for r in actant.nominal_relations] == [
        (NominalRelationKind.NOMINAL_MODIFIER, "ящик", "нижний"),
        (NominalRelationKind.GENITIVE_DEP, "ящик", "стол"),
        (NominalRelationKind.NOMINAL_MODIFIER, "стол", "письменный"),
    ]


def test_modifier_relation_is_materialized_without_flat_phrase_entity():
    morph = StaticMorphology({
        "ветка": (MorphInfo("ветка", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "сломалась": (MorphInfo("сломаться", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    core, context, service = runtime(morph)
    subject = ActantCandidate(
        ActantRole.SUBJECT,
        mention="Сухая ветка",
        normalized_hint="ветка",
        nominal_relations=(
            # Integration only needs the already source-grounded structural relation.
            NominalRelationCandidate(
                NominalRelationKind.NOMINAL_MODIFIER,
                head_mention="ветка",
                head_normalized_hint="ветка",
                dependent_mention="Сухая",
                dependent_normalized_hint="сухой",
            ),
        ),
    )
    result = PerceptionResult(
        "Сухая ветка сломалась.",
        assertions=(assertion("A1", "сломалась", "сломаться", subject),),
    )
    commit = service.integrate_external(result, context)
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    branch = node.actants[ActantRole.SUBJECT]
    branch_entity = core.store.get_element_any_domain(branch.uid)
    assert branch_entity.properties["name"].value == "ветка"
    assert core.store.find_entities_by_name("Сухая ветка", Domain.C) == ()
    dry = core.store.find_entities_by_name("сухой", Domain.C)[0]
    assert core.store.find_link("NOMINAL_MODIFIER", branch.uid, dry.uid) is not None


def test_coreference_uses_plural_surface_form_not_singular_lookup_lemma():
    text = "Ольга собрала документы и унесла их."
    morph = StaticMorphology({
        "ольга": (MorphInfo("Ольга", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "документы": (MorphInfo("документ", "NOUN", case="accs", number="plur", score=1.0),),
        # This entry deliberately models the normalized lookup lemma as singular.
        "документ": (MorphInfo("документ", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "их": (MorphInfo("они", "NPRO", case="accs", number="plur", grammemes=frozenset({"NPRO", "Anph", "3per"}), score=1.0),),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": assertion(
            "A1", "собрала", "собрать",
            ActantCandidate(ActantRole.SUBJECT, mention="Ольга", normalized_hint="Ольга", evidence=ev(text, "Ольга")),
            ActantCandidate(ActantRole.OBJECT, mention="документы", normalized_hint="документ", evidence=ev(text, "документы")),
        ),
        "A2": assertion(
            "A2", "унесла", "унести",
            ActantCandidate(ActantRole.OBJECT, mention="их", normalized_hint="они", evidence=ev(text, "их")),
        ),
    }
    parser._resolve_pronoun_coreferences(by_id)
    docs = next(a for a in by_id["A1"].actants if a.role is ActantRole.OBJECT)
    pronoun = next(a for a in by_id["A2"].actants if a.role is ActantRole.OBJECT)
    assert docs.entity_ref is not None
    assert pronoun.entity_ref == docs.entity_ref


def test_gerund_inherits_matrix_subject_but_infinitive_does_not():
    text = "Отперев калитку, Алексей вошёл."
    morph = StaticMorphology({
        "отперев": (MorphInfo("отпереть", "GRND", grammemes=frozenset({"GRND", "perf"}), score=1.0),),
        "калитку": (MorphInfo("калитка", "NOUN", case="accs", number="sing", gender="femn", score=1.0),),
        "алексей": (MorphInfo("Алексей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "вошёл": (MorphInfo("войти", "VERB", number="sing", gender="masc", mood="indc", score=1.0),),
    })
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": assertion(
            "A1", "Отперев", "отпереть",
            ActantCandidate(ActantRole.OBJECT, mention="калитку", normalized_hint="калитка", evidence=ev(text, "калитку")),
            evidence=ev(text, "Отперев"),
        ),
        "A2": assertion(
            "A2", "вошёл", "войти",
            ActantCandidate(ActantRole.SUBJECT, mention="Алексей", normalized_hint="Алексей", evidence=ev(text, "Алексей")),
            evidence=ev(text, "вошёл"),
        ),
    }
    parser._inherit_nonfinite_subjects(by_id)
    child_subjects = [a for a in by_id["A1"].actants if a.role is ActantRole.SUBJECT]
    assert len(child_subjects) == 1
    assert child_subjects[0].lookup_text == "Алексей"


def test_cross_turn_anchor_prefers_latest_source_subject_of_same_signature():
    text = "Лампа погасла. Точка появилась."
    morph = StaticMorphology({
        "лампа": (MorphInfo("лампа", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "погасла": (MorphInfo("погаснуть", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
        "точка": (MorphInfo("точка", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "появилась": (MorphInfo("появиться", "VERB", number="sing", gender="femn", mood="indc", score=1.0),),
    })
    core, context, service = runtime(morph)
    result = PerceptionResult(
        text,
        assertions=(
            assertion(
                "A1", "погасла", "погаснуть",
                ActantCandidate(ActantRole.SUBJECT, mention="Лампа", normalized_hint="лампа", evidence=ev(text, "Лампа")),
                evidence=ev(text, "погасла"),
            ),
            assertion(
                "A2", "появилась", "появиться",
                ActantCandidate(ActantRole.SUBJECT, mention="Точка", normalized_hint="точка", evidence=ev(text, "Точка")),
                evidence=ev(text, "появилась"),
            ),
        ),
    )
    commit = service.integrate_external(result, context)
    point_ref = core.store.get_hypernode(commit.assertions[1].ref.uid).actants[ActantRole.SUBJECT]
    lamp_ref = core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert context.pronoun_refs["она"] == point_ref
    assert context.pronoun_refs["она"] != lamp_ref


def test_document_oracle_can_require_structured_nominal_relation():
    from ah.diagnostics.document_acceptance import _match_target

    snapshot = {
        "M1": {"uid": "M1", "kind": "M", "domain": "C", "properties": {"name": {"value": "стекло"}}},
        "M2": {"uid": "M2", "kind": "M", "domain": "C", "properties": {"name": {"value": "лампа"}}},
        "L1": {
            "uid": "L1", "kind": "L", "domain": None, "relation_id": "GENITIVE_DEP",
            "source": {"uid": "M1", "kind": "M"},
            "target": {"uid": "M2", "kind": "M"},
        },
    }
    expected = {
        "canonical_name": "стекло",
        "relations": [{"relation": "GENITIVE_DEP", "target": "лампа"}],
    }
    assert _match_target(snapshot, {"uid": "M1", "kind": "M"}, expected, {})
    assert not _match_target(
        snapshot,
        {"uid": "M1", "kind": "M"},
        {"canonical_name": "стекло", "relations": [{"relation": "GENITIVE_DEP", "target": "окно"}]},
        {},
    )
