from __future__ import annotations

from ah.agent import InteractionContext
from ah.conflict import ConflictEngine
from ah.config import InferenceSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import (
    FormulaGoal,
    GoalSpec,
    InferenceEngine,
    InferenceQuery,
    InferenceSchema,
    LogicalStatus,
    StopReason,
)
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Property, Ref, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)
from ah.perception.morphology import MorphInfo


class _Morphology:
    def analyze_all(self, word: str):
        normalized = word.casefold()
        if normalized == "он":
            return (
                MorphInfo(
                    "он",
                    "NPRO",
                    case="nomn",
                    number="sing",
                    gender="masc",
                    grammemes=frozenset({"NPRO", "3per"}),
                    score=1.0,
                ),
            )
        return ()

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def _env(*, with_morphology: bool = False):
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}, uid="M_USER"
    )
    context = InteractionContext(
        self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid)
    )
    service = IntegrationService(
        core,
        IntegrationConfig(0.4, 0.3, 0.2),
        discourse_morphology=_Morphology() if with_morphology else None,
    )
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _unary(local_id: str, predicate: str, mention: str, *, entity_ref: str | None = None):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (
            ActantCandidate(
                ActantRole.SUBJECT,
                mention=mention,
                normalized_hint=mention.casefold(),
                entity_ref=entity_ref,
            ),
        ),
    )


def _functional_assertion(
    local_id: str,
    subject: str,
    value: str,
    *,
    location: str | None = None,
):
    roles = [ActantRole.SUBJECT, ActantRole.OBJECT]
    actants = [
        ActantCandidate(ActantRole.SUBJECT, mention=subject),
        ActantCandidate(ActantRole.OBJECT, mention=value),
    ]
    if location is not None:
        roles.append(ActantRole.LOCATION)
        actants.append(ActantCandidate(ActantRole.LOCATION, mention=location))
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            "иметь цвет",
            "иметь цвет",
            template_candidate=TemplateCandidate(tuple(roles)),
        ),
        tuple(actants),
    )


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_unknown_participant_becomes_one_exists_scope_not_fake_entity() -> None:
    core, context, service, engine = _env()
    result = PerceptionResult(
        "Кто-то вошёл. Он сел.",
        assertions=(
            _unary("A1", "войти", "Кто-то", entity_ref="E1"),
            _unary("A2", "сесть", "Он", entity_ref="E1"),
        ),
    )

    commit = service.integrate_external(result, context)
    assert len(commit.existentials) == 1
    existential = commit.existentials[0]
    assert existential.variable_ids == (0,)
    assert len(existential.member_refs) == 2

    # No fictitious semantic identity is allowed for the unknown participant.
    assert core.store.find_entities_by_name("кто-то", Domain.C) == ()
    assert core.store.find_entities_by_name("он", Domain.C) == ()

    for member in existential.member_refs:
        node = core.store.get_hypernode(member.uid)
        assert node.meta["semantic_scope"] == "QUANTIFIED"
        subject = node.actants[ActantRole.SUBJECT]
        assert isinstance(subject, BoundVar)
        assert subject.local_id == 0
        # Pattern N is not an ordinary asserted factual premise by itself.
        outcome = _solve(engine, member)
        assert outcome.status is LogicalStatus.UNKNOWN

    root = core.store.get_element_any_domain(existential.ref.uid)
    assert isinstance(root, FunctionSymbol)
    assert root.function_id == "EXISTS"
    assert _solve(engine, existential.ref).status is LogicalStatus.PROVED

    # H stores the asserted existential proposition as the turn content, not the
    # two scoped pattern N as independent facts.
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert event.actants[ActantRole.OBJECT] == existential.ref


def test_unresolved_pronoun_can_bind_to_existential_anchor_before_atomic_commit() -> None:
    core, context, service, _engine = _env(with_morphology=True)
    result = PerceptionResult(
        "Кто-то вошёл. Он сел.",
        assertions=(
            _unary("A1", "войти", "Кто-то", entity_ref="E1"),
            AssertionCandidate(
                "A2",
                PredicateCandidate(
                    "сел",
                    "сесть",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                ),
                (
                    ActantCandidate(
                        ActantRole.SUBJECT,
                        mention="Он",
                        normalized_hint="он",
                        evidence=EvidenceSpan("Он", 14, 16),
                    ),
                ),
            ),
        ),
    )
    plan = service.prepare_external_plan(result, context)
    assert tuple(item.entity_ref for item in plan.candidate_ir.existential_bindings) == ("E1",)
    assert len(plan.candidate_ir.discourse_refs) == 1
    discourse = plan.candidate_ir.discourse_refs[0]
    assert discourse.candidate_entity_refs == ("E1",)

    rebound = service.bind_discourse_ref(plan, discourse.local_id, "E1", context)
    assert rebound.candidate_ir.discourse_refs == ()
    assert tuple(item.entity_ref for item in rebound.candidate_ir.existential_bindings) == ("E1",)
    commit = service.integrate_plan(rebound, context)
    assert len(commit.existentials) == 1
    assert core.store.find_entities_by_name("кто-то", Domain.C) == ()


def test_two_independent_unknowns_remain_two_existential_scopes() -> None:
    _core, context, service, _engine = _env()
    result = PerceptionResult(
        "Кто-то вошёл. Кто-то вышел.",
        assertions=(
            _unary("A1", "войти", "Кто-то", entity_ref="E1"),
            _unary("A2", "выйти", "Кто-то", entity_ref="E2"),
        ),
    )
    commit = service.integrate_external(result, context)
    assert len(commit.existentials) == 2
    assert {item.variable_ids for item in commit.existentials} == {(0,), (1,)}


def test_two_unknown_roles_in_one_fact_create_nested_exists_without_m_unknown() -> None:
    core, context, service, engine = _env()
    result = PerceptionResult(
        "Кто-то передал что-то.",
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "передать",
                    "передать",
                    template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
                ),
                (
                    ActantCandidate(ActantRole.SUBJECT, mention="Кто-то", entity_ref="E1"),
                    ActantCandidate(ActantRole.OBJECT, mention="что-то", entity_ref="E2"),
                ),
            ),
        ),
    )
    commit = service.integrate_external(result, context)
    assert len(commit.existentials) == 1
    existential = commit.existentials[0]
    assert existential.variable_ids == (0, 1)
    assert _solve(engine, existential.ref).status is LogicalStatus.PROVED
    assert core.store.find_entities_by_name("кто-то", Domain.C) == ()
    assert core.store.find_entities_by_name("что-то", Domain.C) == ()

    outer = core.store.get_element_any_domain(existential.ref.uid)
    assert isinstance(outer, FunctionSymbol) and outer.function_id == "EXISTS"
    assert isinstance(outer.operands[0], BoundVar) and outer.operands[0].local_id == 0
    inner_ref = outer.operands[1]
    assert isinstance(inner_ref, Ref) and inner_ref.kind is RefKind.G
    inner = core.store.get_element_any_domain(inner_ref.uid)
    assert isinstance(inner, FunctionSymbol) and inner.function_id == "EXISTS"
    assert isinstance(inner.operands[0], BoundVar) and inner.operands[0].local_id == 1


def test_explicit_functional_predicate_detects_positive_positive_conflict() -> None:
    core, context, service, engine = _env()
    first = service.integrate_external(
        PerceptionResult(
            "Лампа красная",
            assertions=(_functional_assertion("A1", "лампа", "красный"),),
        ),
        context,
    )
    first_ref = first.assertions[0].ref
    first_node = core.store.get_hypernode(first_ref.uid)
    service.schema_registry.register(
        InferenceSchema(
            first_node.template.uid,
            functional=True,
            functional_role=ActantRole.OBJECT,
        )
    )

    second = service.integrate_external(
        PerceptionResult(
            "Лампа зелёная",
            assertions=(_functional_assertion("A2", "лампа", "зелёный"),),
        ),
        context,
    )
    second_ref = second.assertions[0].ref
    assert len(second.conflicts) == 1
    conflict = second.conflicts[0]
    assert conflict.kind == "FUNCTIONAL"
    assert set(conflict.members) == {first_ref, second_ref}
    group = core.store.get_element_any_domain(conflict.ref.uid)
    assert group.meta["functional_role"] == "OBJECT"
    assert group.meta["functional_template"] == first_node.template.uid

    for ref in (first_ref, second_ref):
        outcome = _solve(engine, ref)
        assert outcome.status is LogicalStatus.UNKNOWN
        assert outcome.stop_reason is StopReason.CONFLICTED


def test_functional_conflict_requires_identical_non_value_context() -> None:
    core, context, service, _engine = _env()
    first = service.integrate_external(
        PerceptionResult(
            "Лампа красная в комнате A",
            assertions=(_functional_assertion("A1", "лампа", "красный", location="комната A"),),
        ),
        context,
    )
    node = core.store.get_hypernode(first.assertions[0].ref.uid)
    service.schema_registry.register(
        InferenceSchema(
            node.template.uid,
            functional=True,
            functional_role=ActantRole.OBJECT,
        )
    )
    second = service.integrate_external(
        PerceptionResult(
            "Лампа зелёная в комнате B",
            assertions=(_functional_assertion("A2", "лампа", "зелёный", location="комната B"),),
        ),
        context,
    )
    assert second.conflicts == ()
    assert not ConflictEngine(core).is_conflicted(first.assertions[0].ref)
    assert not ConflictEngine(core).is_conflicted(second.assertions[0].ref)


def test_third_functional_value_widens_existing_conflict_group() -> None:
    core, context, service, _engine = _env()
    first = service.integrate_external(
        PerceptionResult("1", assertions=(_functional_assertion("A1", "лампа", "красный"),)),
        context,
    )
    node = core.store.get_hypernode(first.assertions[0].ref.uid)
    service.schema_registry.register(
        InferenceSchema(node.template.uid, functional=True, functional_role=ActantRole.OBJECT)
    )
    second = service.integrate_external(
        PerceptionResult("2", assertions=(_functional_assertion("A2", "лампа", "зелёный"),)),
        context,
    )
    third = service.integrate_external(
        PerceptionResult("3", assertions=(_functional_assertion("A3", "лампа", "синий"),)),
        context,
    )
    groups = tuple(
        group for group in core.store.elements(Domain.C)
        if getattr(group, "meta", {}).get("TYPE") == "CONFLICT"
        and getattr(group, "meta", {}).get("conflict_kind") == "FUNCTIONAL"
    )
    assert len(groups) == 1
    assert set(groups[0].members) == {
        first.assertions[0].ref,
        second.assertions[0].ref,
        third.assertions[0].ref,
    }
    assert len(third.conflicts) == 1
    assert third.conflicts[0].ref == core.ref(groups[0].uid)


def test_existential_scope_survives_persistence_roundtrip(tmp_path) -> None:
    core, context, service, _engine = _env()
    commit = service.integrate_external(
        PerceptionResult(
            "Кто-то вошёл. Он сел.",
            assertions=(
                _unary("A1", "войти", "Кто-то", entity_ref="E1"),
                _unary("A2", "сесть", "Он", entity_ref="E1"),
            ),
        ),
        context,
    )
    root_ref = commit.existentials[0].ref
    member_refs = commit.existentials[0].member_refs

    path = tmp_path / "ah.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core

    root = loaded.store.get_element_any_domain(root_ref.uid)
    assert isinstance(root, FunctionSymbol) and root.function_id == "EXISTS"
    for member_ref in member_refs:
        member = loaded.store.get_hypernode(member_ref.uid)
        assert member.meta["semantic_scope"] == "QUANTIFIED"
        assert isinstance(member.actants[ActantRole.SUBJECT], BoundVar)

    engine = InferenceEngine(loaded, InferenceSettings(max_depth=12, max_expanded_states=512))
    assert _solve(engine, loaded.ref(root_ref.uid)).status is LogicalStatus.PROVED


def test_functional_conflict_survives_reload_and_stays_inadmissible(tmp_path) -> None:
    core, context, service, _engine = _env()
    first = service.integrate_external(
        PerceptionResult("1", assertions=(_functional_assertion("A1", "лампа", "красный"),)),
        context,
    )
    first_ref = first.assertions[0].ref
    node = core.store.get_hypernode(first_ref.uid)
    service.schema_registry.register(
        InferenceSchema(node.template.uid, functional=True, functional_role=ActantRole.OBJECT)
    )
    second = service.integrate_external(
        PerceptionResult("2", assertions=(_functional_assertion("A2", "лампа", "зелёный"),)),
        context,
    )
    second_ref = second.assertions[0].ref
    assert second.conflicts

    path = tmp_path / "ah.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    loaded_engine = InferenceEngine(
        loaded, InferenceSettings(max_depth=12, max_expanded_states=512)
    )

    for ref in (first_ref, second_ref):
        outcome = _solve(loaded_engine, loaded.ref(ref.uid))
        assert outcome.status is LogicalStatus.UNKNOWN
        assert outcome.stop_reason is StopReason.CONFLICTED
