from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from ah.agent import InteractionContext
from ah.config import ContextSettings, InferenceSettings, PersistenceSettings
from ah.conflict import ConflictEngine
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus, StopReason
from ah.integration import IntegrationConfig, IntegrationService, SeedReason, SemanticCorrectionService
from ah.model import ActantRole, Domain, FunctionSymbol, Group, Property, Ref
from ah.perception import ActantCandidate, AssertionCandidate, PerceptionResult, PredicateCandidate, TemplateCandidate
from ah.projection.semantic_projection import SemanticProjector


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Агент", "str")}, uid="M_SELF"
    )
    user_entity = core.add_entity(
        Domain.P, {"name": Property("name", "Пользователь", "str")}, uid="M_USER"
    )
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    service = IntegrationService(
        core,
        IntegrationConfig(
            initial_hypernode_weight=0.4,
            experience_hypernode_weight=0.3,
            follow_link_weight=0.2,
            cause_link_weight=0.18,
        ),
    )
    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    return core, context, service, engine


def _assertion(local_id: str, predicate: str, subject: str, *, negated: bool = False):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        negated=negated,
    )


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def _conflict_groups(core: AHCore) -> tuple[Group, ...]:
    return tuple(
        element
        for domain in (Domain.C, Domain.P, Domain.H)
        for element in core.store.elements(domain)
        if isinstance(element, Group)
        and str(element.meta.get("TYPE") or element.meta.get("type") or "").upper() == "CONFLICT"
    )


def test_integration_materializes_one_addressable_polarity_conflict_and_seeds_it() -> None:
    core, context, service, _engine = _env()
    positive = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    p_ref = positive.assertions[0].ref

    negative = service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )
    not_ref = negative.assertions[0].ref

    assert len(negative.conflicts) == 1
    conflict = negative.conflicts[0]
    assert conflict.created is True
    assert set(conflict.members) == {p_ref, not_ref}
    assert any(seed.reason is SeedReason.CONFLICT and seed.ref == conflict.ref for seed in negative.activation_seeds)

    groups = _conflict_groups(core)
    assert len(groups) == 1
    assert set(groups[0].members) == {p_ref, not_ref}
    assert groups[0].meta["TYPE"] == "CONFLICT"
    assert groups[0].meta["conflict_kind"] == "POLARITY"
    assert ConflictEngine(core).is_conflicted(p_ref)
    assert ConflictEngine(core).is_conflicted(not_ref)


def test_repeat_does_not_duplicate_conflict_or_choose_winner() -> None:
    core, context, service, engine = _env()
    first = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P1", "спать", "кошка"),)),
        context,
    )
    p_ref = first.assertions[0].ref
    service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N1", "спать", "кошка", negated=True),)),
        context,
    )
    repeat = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P2", "спать", "кошка"),)),
        context,
    )

    assert repeat.assertions[0].ref == p_ref
    assert len(_conflict_groups(core)) == 1
    assert len(repeat.conflicts) == 1
    assert repeat.conflicts[0].created is False

    outcome = _solve(engine, p_ref)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.CONFLICTED
    assert "unresolved canonical conflict" in outcome.diagnostics[0]


def test_conflicted_not_root_is_not_accepted_as_unconditional_proof() -> None:
    core, context, service, engine = _env()
    service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    negative = service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )
    not_ref = negative.assertions[0].ref
    assert isinstance(core.store.get_element_any_domain(not_ref.uid), FunctionSymbol)

    outcome = _solve(engine, not_ref)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.CONFLICTED


def test_explicit_false_resolves_current_admissibility_without_deleting_conflict_history() -> None:
    core, context, service, engine = _env()
    positive = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    p_ref = positive.assertions[0].ref
    service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )
    groups_before = _conflict_groups(core)
    assert len(groups_before) == 1
    assert ConflictEngine(core).is_unresolved_group(groups_before[0])

    SemanticCorrectionService(core).refute(p_ref)

    groups_after = _conflict_groups(core)
    assert len(groups_after) == 1  # addressable history is retained
    assert not ConflictEngine(core).is_unresolved_group(groups_after[0])
    assert not ConflictEngine(core).is_conflicted(p_ref)

    outcome = _solve(engine, p_ref)
    assert outcome.status is LogicalStatus.DISPROVED
    assert outcome.stop_reason is StopReason.GOAL_REFUTED
    assert outcome.proof_support[0].rule_id == "EXPLICIT_REFUTATION"


def test_conflict_is_local_and_does_not_block_unrelated_proof() -> None:
    core, context, service, engine = _env()
    service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )
    unrelated = service.integrate_external(
        PerceptionResult("Собака бежит", assertions=(_assertion("Q", "бежать", "собака"),)),
        context,
    )

    outcome = _solve(engine, unrelated.assertions[0].ref)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED


def test_conflict_group_persists_and_rebuilds_runtime_admissibility() -> None:
    core, context, service, _engine = _env()
    positive = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    p_ref = positive.assertions[0].ref
    service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "ah.json"
        persistence = JsonPersistence(
            path,
            PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
        )
        persistence.save(core, context=context)
        loaded = persistence.load(uid_generator=SequentialUidGenerator()).core

    groups = _conflict_groups(loaded)
    assert len(groups) == 1
    assert ConflictEngine(loaded).is_conflicted(loaded.ref(p_ref.uid))


def test_semantic_projection_makes_conflict_explicit() -> None:
    core, context, service, _engine = _env()
    service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    negative = service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )
    conflict_ref = negative.conflicts[0].ref

    text = SemanticProjector(
        core, ContextSettings(include_structural_uids=False)
    ).active_block(conflict_ref).semantic
    assert text.startswith("CONFLICT[")
    assert "NOT" in text


def _binary_assertion(local_id: str, predicate: str, subject: str, obj: str, *, negated: bool = False):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.OBJECT, mention=obj),
        ),
        negated=negated,
    )


def test_role_fill_and_exists_do_not_use_conflicted_fact_as_unconditional_premise() -> None:
    from ah.inference import ExistsGoal, RoleFillGoal

    core, context, service, engine = _env()
    positive = service.integrate_external(
        PerceptionResult(
            "Иван читает книгу",
            assertions=(_binary_assertion("P", "читать", "Иван", "книга"),),
        ),
        context,
    )
    service.integrate_external(
        PerceptionResult(
            "Иван не читает книгу",
            assertions=(_binary_assertion("N", "читать", "Иван", "книга", negated=True),),
        ),
        context,
    )
    node = core.store.get_hypernode(positive.assertions[0].ref.uid)
    subject = node.actants[ActantRole.SUBJECT]
    obj = node.actants[ActantRole.OBJECT]
    assert isinstance(subject, Ref) and isinstance(obj, Ref)

    role_outcome = engine.solve(
        InferenceQuery(
            GoalSpec(
                RoleFillGoal(
                    node.template,
                    {ActantRole.SUBJECT: subject},
                    ActantRole.OBJECT,
                )
            )
        )
    )
    assert role_outcome.status is LogicalStatus.UNKNOWN
    assert role_outcome.stop_reason is StopReason.CONFLICTED

    exists_outcome = engine.solve(
        InferenceQuery(
            GoalSpec(
                ExistsGoal(
                    node.template,
                    {
                        ActantRole.SUBJECT: subject,
                        ActantRole.OBJECT: obj,
                    },
                )
            )
        )
    )
    assert exists_outcome.status is LogicalStatus.UNKNOWN
    assert exists_outcome.stop_reason is StopReason.CONFLICTED


def test_relation_and_cause_paths_reject_conflicted_proposition_premise() -> None:
    from ah.inference import CauseEntailmentGoal, RelationGoal

    core, context, service, engine = _env()
    positive = service.integrate_external(
        PerceptionResult("Сигнал активен", assertions=(_assertion("P", "быть активным", "сигнал"),)),
        context,
    )
    p_ref = positive.assertions[0].ref
    service.integrate_external(
        PerceptionResult("Сигнал не активен", assertions=(_assertion("N", "быть активным", "сигнал", negated=True),)),
        context,
    )
    effect = service.integrate_external(
        PerceptionResult("Сирена звучит", assertions=(_assertion("E", "звучать", "сирена"),)),
        context,
    ).assertions[0].ref

    core.add_link("CAUSE", p_ref, effect, 0.4)
    core.add_link("FOLLOW", p_ref, effect, 0.4)

    relation_outcome = engine.solve(
        InferenceQuery(GoalSpec(RelationGoal("FOLLOW", p_ref, effect)))
    )
    assert relation_outcome.status is LogicalStatus.UNKNOWN
    assert relation_outcome.stop_reason is StopReason.CONFLICTED

    cause_outcome = engine.solve(
        InferenceQuery(
            GoalSpec(CauseEntailmentGoal(effect)),
            premise_refs=(p_ref,),
        )
    )
    assert cause_outcome.status is LogicalStatus.UNKNOWN
    assert cause_outcome.stop_reason is StopReason.CONFLICTED


def test_agent_h_only_output_does_not_create_world_conflict() -> None:
    core, context, service, _engine = _env()
    positive = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    service.integrate_to_h(
        PerceptionResult("Кошка не спит", assertions=(_assertion("A", "спать", "кошка", negated=True),)),
        context,
    )

    assert _conflict_groups(core) == ()
    assert not ConflictEngine(core).is_conflicted(positive.assertions[0].ref)
