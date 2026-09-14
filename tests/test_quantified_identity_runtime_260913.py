from __future__ import annotations

from ah.agent import InteractionContext
from ah.config import ContextSettings, InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    DerivedAtomConclusion,
    EntityIdentityGoal,
    ExistsGoal,
    GoalSpec,
    InferenceEngine,
    InferenceMaterializer,
    InferenceQuery,
    LogicalStatus,
)
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, BoundVar, Domain, Property, Ref, VariableSort
from ah.perception import (
    ActantCandidate,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    QueryQuantifierOperator,
)
from ah.perception.semantic_predicates import SemanticPredicateAdaptiveParser
from ah.projection.event_context import EventAwareContextProjector


def _entity(core: AHCore, uid: str, name: str) -> Ref:
    value = core.add_entity(Domain.C, {"name": Property("name", name, "str")}, uid=uid)
    return core.ref(value.uid)


def _template(core: AHCore, uid: str, predicate: str, roles) -> Ref:
    symbol = core.add_abstract_symbol({predicate}, uid=f"S_{uid}")
    template = core.add_template(Domain.C, core.ref(symbol.uid), tuple(roles), uid=f"T_{uid}")
    return core.ref(template.uid)


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")},
        meta={"identity_role": "SELF"}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")},
        meta={"identity_role": "USER"}, uid="M_USER"
    )
    context = InteractionContext(core.ref(self_entity.uid), core.ref(user_entity.uid))
    engine = InferenceEngine(core, InferenceSettings(max_depth=12, max_expanded_states=512))
    return core, context, engine


def _assert_formula(core: AHCore, context: InteractionContext, root: Ref) -> None:
    ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="Каждый студент имеет учебник",
        speaker_ref=context.user_ref,
        semantic_refs=(root,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )


def test_precise_exists_is_derived_from_asserted_forall_implication_without_query_n() -> None:
    core, context, engine = _runtime()
    t_student = _template(core, "STUDENT", "студент", (ActantRole.SUBJECT,))
    t_have = _template(core, "HAVE", "иметь", (ActantRole.SUBJECT, ActantRole.OBJECT))
    alexey = _entity(core, "M_ALEXEY", "Алексей")
    textbook = _entity(core, "M_TEXTBOOK", "учебник")
    book = _entity(core, "M_BOOK", "книга")
    is_a = core.add_link("IS-A", textbook, book, 0.2)
    student_fact, _ = core.add_hypernode(
        Domain.C, t_student, {ActantRole.SUBJECT: alexey}, 0.4, uid="N_STUDENT_ALEXEY"
    )

    x = BoundVar(0, VariableSort.ENTITY)
    student_pattern, _ = core.add_hypernode(
        Domain.C,
        t_student,
        {ActantRole.SUBJECT: x},
        0.4,
        uid="N_STUDENT_X",
        meta={"semantic_scope": "QUANTIFIED"},
        count_occurrence=False,
    )
    have_pattern, _ = core.add_hypernode(
        Domain.C,
        t_have,
        {ActantRole.SUBJECT: x, ActantRole.OBJECT: textbook},
        0.4,
        uid="N_HAVE_X_BOOK",
        meta={"semantic_scope": "QUANTIFIED"},
        count_occurrence=False,
    )
    implication = core.add_function(
        Domain.C,
        "IMPLIES",
        (core.ref(student_pattern.uid), core.ref(have_pattern.uid)),
        uid="G_RULE",
    )
    forall = core.add_function(
        Domain.C, "FORALL", (x, core.ref(implication.uid)), uid="G_FORALL"
    )
    _assert_formula(core, context, core.ref(forall.uid))

    outcome = engine.solve(
        InferenceQuery(
            GoalSpec(
                ExistsGoal(
                    t_have,
                    {ActantRole.SUBJECT: alexey, ActantRole.OBJECT: textbook},
                )
            )
        )
    )
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, DerivedAtomConclusion)
    assert outcome.conclusion.role_map() == {
        ActantRole.SUBJECT: alexey,
        ActantRole.OBJECT: textbook,
    }
    assert outcome.proof_support[-1].rule_id == "FORALL_IMPLIES_MP"
    assert {ref.uid for ref in outcome.premise_refs} >= {
        student_fact.uid,
        "G_FORALL",
        "G_RULE",
    }

    generalized = engine.solve(
        InferenceQuery(
            GoalSpec(
                ExistsGoal(
                    t_have,
                    {ActantRole.SUBJECT: alexey, ActantRole.OBJECT: book},
                )
            )
        )
    )
    assert generalized.status is LogicalStatus.PROVED
    assert isinstance(generalized.conclusion, DerivedAtomConclusion)
    assert generalized.conclusion.role_map()[ActantRole.OBJECT] == book
    assert core.ref(is_a.uid) in generalized.premise_refs
    # The question itself did not create a canonical ground N during search.
    assert not any(
        node.meta.get("semantic_scope") is None
        and node.actants == {
            ActantRole.SUBJECT: alexey,
            ActantRole.OBJECT: textbook,
        }
        for node in core.store.find_hypernodes_by_template(t_have.uid)
    )

    materialized = InferenceMaterializer(core, IntegrationSettings()).materialize(outcome)
    assert materialized.ref is not None
    node = core.store.get_hypernode(materialized.ref.uid)
    assert int(node.meta.get("occurrence_count", 0)) == 0
    assert core.resolve_supports(materialized.ref)


def test_entity_identity_uses_asserted_unary_classification_as_description() -> None:
    core, _context, engine = _runtime()
    t_student = _template(core, "STUDENT", "студент", (ActantRole.SUBJECT,))
    alexey = _entity(core, "M_ALEXEY", "Алексей")
    student_fact, _ = core.add_hypernode(
        Domain.C, t_student, {ActantRole.SUBJECT: alexey}, 0.4, uid="N_STUDENT_ALEXEY"
    )

    outcome = engine.solve(InferenceQuery(GoalSpec(EntityIdentityGoal(alexey))))
    assert outcome.status is LogicalStatus.PROVED
    assert core.ref(student_fact.uid) in outcome.premise_refs

    projected = EventAwareContextProjector(core, ContextSettings()).project(
        "Кто такой Алексей?",
        (),
        (outcome,),
    )
    assert "Алексей" in projected.rendered
    assert "студент" in projected.rendered.casefold()


def test_possession_semantic_rewrite_unifies_existential_wording_with_have() -> None:
    class Stub(SemanticPredicateAdaptiveParser):
        def __init__(self):
            self._traces = []

        def _possession_kind(self, source_text, item):
            return "POSSESSION"

        def _generic_subject_kind(self, source_text, query, subject):
            return "SPECIFIC_ENTITY"

    parser = Stub()
    query = QueryCandidate(
        PredicateCandidate("есть", normalized_hint="есть"),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="Алексея", normalized_hint="Алексей"),
            ActantCandidate(ActantRole.OBJECT, mention="учебник", normalized_hint="учебник"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    rewritten, changed = parser._normalize_predicate_semantics(
        "Есть ли у Алексея учебник?", query
    )
    assert changed
    assert rewritten.predicate.lookup_form == "иметь"
    assert rewritten.predicate.sense_hint == "POSSESSION"


def test_generic_possession_query_becomes_forall_class_goal() -> None:
    class Stub(SemanticPredicateAdaptiveParser):
        def __init__(self):
            self._traces = []

        def _generic_subject_kind(self, source_text, query, subject):
            return "GENERIC_CLASS"

    parser = Stub()
    query = QueryCandidate(
        PredicateCandidate("есть", normalized_hint="иметь", sense_hint="POSSESSION"),
        actants=(
            ActantCandidate(ActantRole.SUBJECT, mention="студента", normalized_hint="студент"),
            ActantCandidate(ActantRole.OBJECT, mention="учебник", normalized_hint="учебник"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    rewritten, changed = parser._formalize_generic_possession_query(
        "У студента есть учебник?", query
    )
    assert changed
    assert rewritten.quantified is not None
    binding = rewritten.quantified.bindings[0]
    assert binding.operator is QueryQuantifierOperator.FORALL
    assert binding.restriction_lemma == "студент"
    subject = next(item for item in rewritten.actants if item.role is ActantRole.SUBJECT)
    assert subject.entity_ref == binding.entity_ref
