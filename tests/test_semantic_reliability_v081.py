from __future__ import annotations

from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import IntegrationSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import SemanticGoalCompiler
from ah.integration import IntegrationConfig, IntegrationService, TemplateCompletionService
from ah.integration.contracts import IntegratedAssertion, IntegrationCommit
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateSelection,
)
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from ah.perception.goal_semantics import GoalSemanticService
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class Morphology:
    name = "v081-generic"

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


def parser(morphology, backend=None):
    return AdaptivePerceptionParser(
        backend or NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


def runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "Agent", "str")},
        meta={"identity_role": "SELF"},
    )
    user_entity = core.add_entity(
        Domain.P,
        properties={"name": Property("name", "User", "str")},
        meta={"identity_role": "USER"},
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    integration = IntegrationService(
        core, IntegrationConfig.from_settings(IntegrationSettings())
    )
    return core, context, integration


def test_orphan_embedded_assertion_is_not_a_user_inference_goal():
    core, context, _integration = runtime()
    placeholder = core.add_entity(
        Domain.C, properties={"name": Property("name", "placeholder", "str")}
    )
    ref = core.ref(placeholder.uid)
    commit = IntegrationCommit(
        assertions=(IntegratedAssertion("A1", ref, Domain.C, True, semantic_scope="EMBEDDED"),),
        experience_ref=ref,
        activation_seeds=(),
    )
    perception = PerceptionResult(
        source_text="Someone stated embedded content.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate("state"),
                (ActantCandidate(ActantRole.SUBJECT, mention="someone"),),
                status=AssertionStatus.EMBEDDED,
            ),
        ),
    )
    assert SemanticGoalCompiler(core).build(commit, context, perception) == ()
    assert SemanticGoalCompiler(core).build(commit, context) == ()


def test_oblique_personal_pronoun_syncretism_does_not_exclude_neuter_object():
    morph = Morphology({
        "Алексей": (MorphInfo("Алексей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "создал": (MorphInfo("создать", "VERB", number="sing", score=1.0),),
        "сообщение": (MorphInfo("сообщение", "NOUN", case="accs", number="sing", gender="neut", animacy="inan", score=1.0),),
        "отправил": (MorphInfo("отправить", "VERB", number="sing", score=1.0),),
        # A dictionary may expose only the masculine tag even though this
        # third-person oblique paradigm is also compatible with neuter referents.
        "его": (
            MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", animacy="anim", score=1.0),
        ),
        "коллеге": (MorphInfo("коллега", "NOUN", case="datv", number="sing", gender="masc", animacy="anim", score=1.0),),
        "и": (MorphInfo("и", "CONJ", score=1.0),),
    })
    p = parser(morph)
    text = "Алексей создал сообщение и отправил его коллеге."
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": AssertionCandidate(
            "A1", PredicateCandidate("создал", "создать", evidence=EvidenceSpan("создал", 8, 14)),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Алексей", entity_ref="E1", evidence=EvidenceSpan("Алексей", 0, 7)),
                ActantCandidate(ActantRole.OBJECT, mention="сообщение", normalized_hint="сообщение", entity_ref="E2", evidence=EvidenceSpan("сообщение", 15, 24)),
            ),
        ),
        "A2": AssertionCandidate(
            "A2", PredicateCandidate("отправил", "отправить", evidence=EvidenceSpan("отправил", 27, 35)),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Алексей", entity_ref="E1", evidence=EvidenceSpan("Алексей", 0, 7)),
                ActantCandidate(ActantRole.OBJECT, mention="его", evidence=EvidenceSpan("его", 36, 39)),
                ActantCandidate(ActantRole.RECIPIENT, mention="коллеге", evidence=EvidenceSpan("коллеге", 40, 47)),
            ),
        ),
    }
    p._resolve_pronoun_coreferences(by_id)
    obj = next(a for a in by_id["A2"].actants if a.role is ActantRole.OBJECT)
    assert obj.entity_ref == "E2"


def test_instrumental_pp_with_two_structural_owners_requires_clarification_without_model_vote():
    morph = Morphology({
        "Ольга": (MorphInfo("Ольга", "NOUN", case="nomn", score=1.0),),
        "заметила": (MorphInfo("заметить", "VERB", score=1.0),),
        "Андрея": (MorphInfo("Андрей", "NOUN", case="accs", animacy="anim", score=1.0),),
        "с": (MorphInfo("с", "PREP", score=1.0),),
        "фонарём": (MorphInfo("фонарь", "NOUN", case="ablt", score=1.0),),
    })
    p = parser(morph)
    text = "Ольга заметила Андрея с фонарём."
    tokens = p._source_tokens(text)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    pred = p._resolve_span(text, tokens, 2, 2)
    modifier = p._resolve_span(text, tokens, 4, 5)
    with pytest.raises(AdaptiveStructuralClarificationRequired) as caught:
        p._resolve_modifier_attachment(
            text, tokens, pred, PredicateCandidate("заметила", "заметить"), modifier
        )
    assert caught.value.spec.mention == "с фонарём"
    assert len(caught.value.spec.options) == 2


def test_directional_pp_is_not_blanket_promoted_to_structural_ambiguity():
    morph = Morphology({
        "Ольга": (MorphInfo("Ольга", "NOUN", case="nomn", score=1.0),),
        "положила": (MorphInfo("положить", "VERB", score=1.0),),
        "папку": (MorphInfo("папка", "NOUN", case="accs", score=1.0),),
        "на": (MorphInfo("на", "PREP", score=1.0),),
        "полку": (MorphInfo("полка", "NOUN", case="accs", score=1.0),),
    })

    class AttachmentBackend:
        def generate(self, prompt, *, system="", override=None, role="generic"):
            assert role == "perception_modifier_attachment"
            return LLMResponse("EVENT", {})

    p = parser(morph, AttachmentBackend())
    text = "Ольга положила папку на полку."
    tokens = p._source_tokens(text)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    pred = p._resolve_span(text, tokens, 2, 2)
    modifier = p._resolve_span(text, tokens, 4, 5)
    selected = p._resolve_modifier_attachment(
        text, tokens, pred, PredicateCandidate("положила", "положить"), modifier
    )
    assert selected is not None
    assert selected.kind.value == "PREDICATE"


def test_counted_nominal_participant_becomes_object_plus_amount_but_duration_stays_whole():
    morph = Morphology({
        "пять": (MorphInfo("пять", "NUMR", case="accs", score=1.0),),
        "журналов": (MorphInfo("журнал", "NOUN", case="gent", number="plur", score=1.0),),
        "два": (MorphInfo("два", "NUMR", score=1.0),),
        "часа": (MorphInfo("час", "NOUN", case="gent", score=1.0),),
    })
    p = parser(morph)
    text = "пять журналов"
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    split = p._split_quantified_nominal_actants(
        text,
        [ActantCandidate(ActantRole.OBJECT, mention=text, evidence=EvidenceSpan(text, 0, len(text)))],
    )
    by_role = {item.role: item for item in split}
    assert by_role[ActantRole.OBJECT].mention == "журналов"
    assert by_role[ActantRole.OBJECT].normalized_hint == "журнал"
    assert by_role[ActantRole.AMOUNT].mention == "пять"

    text2 = "два часа"
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text2)
    duration = p._split_quantified_nominal_actants(
        text2,
        [ActantCandidate(ActantRole.DURATION, mention=text2, evidence=EvidenceSpan(text2, 0, len(text2)))],
    )
    assert [(item.role, item.mention) for item in duration] == [(ActantRole.DURATION, "два часа")]


def test_query_filler_role_is_reconciled_only_inside_selected_template_roles():
    core, _context, integration = runtime()
    symbol = core.add_abstract_symbol({"compose"})
    template = core.add_template(
        Domain.C,
        core.ref(symbol.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME, ActantRole.TOOL),
    )

    class Reconciler:
        calls = []

        def resolve_actant_role(self, source_text, predicate, target_text, candidate_roles):
            self.calls.append((target_text, candidate_roles))
            assert set(candidate_roles) == {ActantRole.OBJECT, ActantRole.TIME}
            return ActantRole.OBJECT

    perception = Reconciler()
    query = QueryCandidate(
        PredicateCandidate(
            "compose", "compose", template_selection=TemplateSelection(existing_template_uid=template.uid)
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="author"),
            ActantCandidate(ActantRole.MATERIAL, mention="note"),
        ),
        requested_role=ActantRole.TOOL,
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q1",
    )
    result = PerceptionResult(source_text="With what did the author compose the note?", queries=(query,))
    repaired = TemplateCompletionService(integration, perception)._reconcile_selected_query_roles(result)
    roles = {a.role: a.mention for a in repaired.queries[0].actants}
    assert roles == {ActantRole.SUBJECT: "author", ActantRole.OBJECT: "note"}
    assert perception.calls
    assert ActantRole.MATERIAL not in core.store.get_template(template.uid).roles


def test_nominal_predication_complement_is_not_reclassified_as_taxonomic_is_a():
    class Classifier:
        def __init__(self):
            self.calls = 0

        def classify_act_relation(self, source_text, act_ref, predicate, actants):
            self.calls += 1
            raise AssertionError("nominal predication must not be sent to IS-A classifier")

    classifier = Classifier()
    assertion = AssertionCandidate(
        "A1",
        PredicateCandidate("title", "title", sense_hint="NOMINAL_PREDICATION"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="X"),
            ActantCandidate(ActantRole.OBJECT, mention="owner's project"),
        ),
    )
    result = GoalSemanticService(classifier).complete(
        PerceptionResult(source_text="X is the title of the owner's project", assertions=(assertion,))
    )
    assert result.act_relations == ()
    assert classifier.calls == 0
