from __future__ import annotations

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import BatchKind, IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.morphology import MorphInfo


class Morphology:
    def analyze_all(self, word: str):
        key = word.casefold()
        values = {
            "он": (
                MorphInfo(
                    "он", "NPRO", case="nomn", number="sing", gender="masc",
                    grammemes=frozenset({"NPRO", "3per"}), score=1.0,
                ),
            ),
            "иван": (
                MorphInfo("Иван", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),
            ),
        }
        return values.get(key, ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def services():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.02),
        discourse_morphology=Morphology(),
    )
    return core, context, integration


def test_prepare_plan_is_pure_and_integration_consumes_same_validated_ir():
    core, context, integration = services()
    result = PerceptionResult(
        "Иван пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),),
            ),
        ),
    )
    before = set(core.store.all_uids())
    plan = integration.prepare_external_plan(
        result, context, batch_kind=BatchKind.MESSAGE, source_ref="msg:1"
    )
    assert set(core.store.all_uids()) == before
    assert plan.candidate_ir.source_ref == "msg:1"
    assert plan.candidate_ir.ordered_assertion_ids == ("A1",)
    commit = integration.integrate_plan(plan, context)
    assert len(commit.assertions) == 1
    assert len(core.store.find_entities_by_name("Иван", Domain.C)) == 1


def test_scope_normalization_happens_before_plan_and_not_during_write():
    core, context, integration = services()
    # Directly provide already-scoped content to ensure the plan is the canonical
    # pre-write source of truth consumed by Integration.
    candidate = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "работает", "работать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),),
        status=AssertionStatus.EMBEDDED,
    )
    plan = integration.prepare_external_plan(PerceptionResult("работает", (candidate,)), context)
    assert plan.perception.assertions[0].status is AssertionStatus.EMBEDDED
    commit = integration.integrate_plan(plan, context)
    assert commit.assertions[0].semantic_scope == "EMBEDDED"


def test_unresolved_third_person_reference_is_visible_in_candidate_ir_not_hidden_as_uid():
    core, context, integration = services()
    result = PerceptionResult(
        "Он пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти",
                    evidence=EvidenceSpan("пришёл", 3, 9),
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (
                    ActantCandidate(
                        ActantRole.SUBJECT,
                        mention="Он",
                        normalized_hint="он",
                        evidence=EvidenceSpan("Он", 0, 2),
                    ),
                ),
            ),
        ),
    )
    plan = integration.prepare_external_plan(result, context)
    assert len(plan.candidate_ir.discourse_refs) == 1
    ref = plan.candidate_ir.discourse_refs[0]
    assert ref.assertion_id == "A1"
    assert ref.role is ActantRole.SUBJECT
    assert ref.grammatical_number == "sing"
    assert ref.grammatical_gender == "masc"
    assert not hasattr(ref, "uid")


def test_existing_dialogue_anchor_means_no_unresolved_discourse_ref():
    core, context, integration = services()
    ivan = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
    context.pronoun_refs["он"] = core.ref(ivan.uid)
    result = PerceptionResult(
        "Он пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он"),),
            ),
        ),
    )
    plan = integration.prepare_external_plan(result, context)
    assert plan.candidate_ir.discourse_refs == ()
    commit = integration.integrate_plan(plan, context)
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    assert node.actants[ActantRole.SUBJECT] == core.ref(ivan.uid)


def test_document_units_are_namespaced_and_committed_as_one_batch():
    from ah.integration import FormalizationBatch

    core, context, integration = services()
    first = PerceptionResult(
        "Иван пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван", entity_ref="E1"),),
            ),
        ),
    )
    second = PerceptionResult(
        "Мария ушла.",
        assertions=(
            AssertionCandidate(
                "A1",  # deliberate local-id collision between parser windows
                PredicateCandidate(
                    "ушла", "уйти",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария", entity_ref="E1"),),
            ),
        ),
    )
    batch = FormalizationBatch(
        source_text="Иван пришёл. Мария ушла.",
        units=(first, second),
        batch_kind=BatchKind.DOCUMENT,
        source_ref="doc:test",
    )
    plan = integration.prepare_external_batch_plan(batch, context)
    assert plan.candidate_ir.ordered_assertion_ids == ("B0:A1", "B1:A1")
    assert plan.candidate_ir.source_ref == "doc:test"
    assert plan.candidate_ir.batch_kind is BatchKind.DOCUMENT
    commit = integration.integrate_plan(plan, context)
    assert len(commit.assertions) == 2
    assert len(core.store.find_entities_by_name("Иван", Domain.C)) == 1
    assert len(core.store.find_entities_by_name("Мария", Domain.C)) == 1


def test_document_batch_rolls_back_all_units_if_late_unit_fails_canonical_validation():
    from ah.integration import FormalizationBatch
    from ah.integration.errors import IntegrationError

    core, context, integration = services()
    first = PerceptionResult(
        "Иван пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),),
            ),
        ),
    )
    # This is structurally valid at CandidateIR level but its selected T UID does
    # not exist, so failure occurs after the transaction clone has begun.
    from ah.perception import TemplateSelection
    second = PerceptionResult(
        "Мария ушла.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "ушла", "уйти",
                    template_selection=TemplateSelection(existing_template_uid="T_MISSING"),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария"),),
            ),
        ),
    )
    batch = FormalizationBatch(
        source_text="Иван пришёл. Мария ушла.",
        units=(first, second),
        batch_kind=BatchKind.DOCUMENT,
    )
    plan = integration.prepare_external_batch_plan(batch, context)
    before = set(core.store.all_uids())
    try:
        integration.integrate_plan(plan, context)
    except Exception:
        pass
    else:
        raise AssertionError("late canonical failure must abort the document transaction")
    assert set(core.store.all_uids()) == before
    assert core.store.find_entities_by_name("Иван", Domain.C) == ()


def test_explicit_identity_merge_keeps_older_uid_and_deduplicates_dependent_fact():
    core, context, integration = services()
    first = core.add_entity(Domain.C, {"name": Property("name", "Иван", "str")})
    second = core.add_entity(Domain.C, {"name": Property("name", "Иван Петров", "str")})
    thing = core.add_entity(Domain.C, {"name": Property("name", "книга", "str")})
    predicate = core.add_abstract_symbol({"читать"})
    template = core.add_template(Domain.C, core.ref(predicate.uid), (ActantRole.SUBJECT, ActantRole.OBJECT))
    n1, _ = core.add_hypernode(
        Domain.C, core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(first.uid), ActantRole.OBJECT: core.ref(thing.uid)},
        0.4,
    )
    n2, _ = core.add_hypernode(
        Domain.C, core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(second.uid), ActantRole.OBJECT: core.ref(thing.uid)},
        0.4,
    )
    assert n1.uid != n2.uid

    result = integration.merge_identity(core.ref(second.uid), core.ref(first.uid), reason="explicit identity")
    assert result.survivor.uid == first.uid
    assert result.removed.uid == second.uid
    assert result.reason == "explicit identity"
    assert not core.store.has_uid(second.uid)
    survivor = core.store.get_element_any_domain(first.uid)
    assert "identity_merge_reason" not in survivor.meta
    assert "Иван Петров" in tuple(survivor.properties["aliases"].value)
    facts = tuple(
        node for node in core.store.find_hypernodes_by_template(template.uid)
        if core.store.domain_of(node.uid) is Domain.C
    )
    assert len(facts) == 1
    assert facts[0].actants[ActantRole.SUBJECT] == core.ref(first.uid)
    assert int(facts[0].meta.get("occurrence_count", 0)) == 2


def test_identity_merge_property_conflict_rolls_back_atomically():
    core, context, integration = services()
    first = core.add_entity(
        Domain.C,
        {
            "name": Property("name", "Иван", "str"),
            "age": Property("age", 30, "int"),
        },
    )
    second = core.add_entity(
        Domain.C,
        {
            "name": Property("name", "Иван", "str"),
            "age": Property("age", 31, "int"),
        },
    )
    before = set(core.store.all_uids())
    try:
        integration.merge_identity(core.ref(first.uid), core.ref(second.uid), reason="test")
    except Exception as exc:
        assert "property conflict" in str(exc)
    else:
        raise AssertionError("conflicting properties must not be auto-resolved by merge")
    assert set(core.store.all_uids()) == before
    assert core.store.has_uid(first.uid) and core.store.has_uid(second.uid)


def test_document_source_spans_are_rebased_to_whole_batch_coordinates():
    from ah.integration import FormalizationBatch

    core, context, integration = services()
    first_text = "Иван пришёл."
    second_text = "Мария ушла."
    first = PerceptionResult(
        first_text,
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти", evidence=EvidenceSpan("пришёл", 5, 11),
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван", evidence=EvidenceSpan("Иван", 0, 4)),),
                evidence=EvidenceSpan(first_text, 0, len(first_text)),
            ),
        ),
    )
    second = PerceptionResult(
        second_text,
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "ушла", "уйти", evidence=EvidenceSpan("ушла", 6, 10),
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Мария", normalized_hint="Мария", evidence=EvidenceSpan("Мария", 0, 5)),),
                evidence=EvidenceSpan(second_text, 0, len(second_text)),
            ),
        ),
    )
    source = first_text + "\n" + second_text
    plan = integration.prepare_external_batch_plan(
        FormalizationBatch(source, (first, second), BatchKind.DOCUMENT, source_ref="doc:spans"),
        context,
    )
    second_assertion = plan.candidate_ir.assertion("B1:A1")
    offset = len(first_text) + 1
    assert second_assertion.evidence.start == offset
    assert second_assertion.actants[0].evidence.start == offset
    assert second_assertion.predicate.evidence.start == offset + 6


def test_document_batch_requires_explicit_offsets_when_unit_text_cannot_be_located():
    from ah.integration import FormalizationBatch

    core, context, integration = services()
    unit = PerceptionResult(
        "нормализованное окно",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "пришёл", "прийти", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))
                ),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван"),),
            ),
        ),
    )
    batch = FormalizationBatch(
        "исходный документ с другим представлением",
        (unit, unit),
        BatchKind.DOCUMENT,
    )
    try:
        integration.prepare_external_batch_plan(batch, context)
    except ValueError as exc:
        assert "unit_offsets" in str(exc)
    else:
        raise AssertionError("ambiguous window provenance must fail closed")


def test_unresolved_discourse_ref_exposes_grammatically_bounded_batch_candidates_and_can_be_bound_before_commit():
    from ah.integration import FormalizationBatch

    core, context, integration = services()
    pronoun = PerceptionResult(
        "Он пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate("пришёл", "прийти", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))),
                (ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", evidence=EvidenceSpan("Он", 0, 2)),),
            ),
        ),
    )
    later = PerceptionResult(
        "Иван ответил.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate("ответил", "ответить", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))),
                (ActantCandidate(ActantRole.SUBJECT, mention="Иван", normalized_hint="Иван", entity_ref="E1", evidence=EvidenceSpan("Иван", 0, 4)),),
            ),
        ),
    )
    batch = FormalizationBatch(
        "Он пришёл.\nИван ответил.", (pronoun, later), BatchKind.DOCUMENT
    )
    plan = integration.prepare_external_batch_plan(batch, context)
    assert len(plan.candidate_ir.discourse_refs) == 1
    unresolved = plan.candidate_ir.discourse_refs[0]
    assert unresolved.candidate_entity_refs == ("B1:E1",)

    rebound = integration.bind_discourse_ref(
        plan, unresolved.local_id, "B1:E1", context
    )
    assert rebound.candidate_ir.discourse_refs == ()
    commit = integration.integrate_plan(rebound, context)
    first_node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    second_node = core.store.get_hypernode(commit.assertions[1].ref.uid)
    assert first_node.actants[ActantRole.SUBJECT] == second_node.actants[ActantRole.SUBJECT]


def test_unresolved_discourse_ref_never_materializes_fake_pronoun_entity():
    from ah.integration.errors import UnresolvedDiscourseReferenceError

    core, context, integration = services()
    result = PerceptionResult(
        "Он пришёл.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate("пришёл", "прийти", template_candidate=TemplateCandidate((ActantRole.SUBJECT,))),
                (ActantCandidate(ActantRole.SUBJECT, mention="Он", normalized_hint="он", evidence=EvidenceSpan("Он", 0, 2)),),
            ),
        ),
    )
    plan = integration.prepare_external_plan(result, context)
    before = set(core.store.all_uids())
    try:
        integration.integrate_plan(plan, context)
    except UnresolvedDiscourseReferenceError:
        pass
    else:
        raise AssertionError("unresolved discourse reference must block canonical commit")
    assert set(core.store.all_uids()) == before
    assert core.store.find_entities_by_name("он", Domain.C) == ()
