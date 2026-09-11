from __future__ import annotations

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus, StopReason
from ah.integration import CandidateValidationError, IntegrationConfig, IntegrationService
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Property, Ref, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifierCandidate,
    QuantifierKind,
    TemplateCandidate,
)


def _env():
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
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _unary(
    local_id: str,
    predicate: str,
    mention: str,
    *,
    entity_ref: str | None = None,
    negated: bool = False,
    quantifier_kind: QuantifierKind | None = None,
    restriction_lemma: str | None = None,
):
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
                quantifier=(
                    None
                    if quantifier_kind is None
                    else QuantifierCandidate(
                        quantifier_kind,
                        mention,
                        restriction_lemma,
                    )
                ),
            ),
        ),
        negated=negated,
    )


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def _function(core: AHCore, ref: Ref) -> FunctionSymbol:
    obj = core.store.get_element_any_domain(ref.uid)
    assert isinstance(obj, FunctionSymbol)
    return obj


def _unwrap_n(core: AHCore, ref: Ref) -> Ref:
    current = ref
    while current.kind is RefKind.G:
        obj = _function(core, current)
        if obj.function_id == "NOT" and len(obj.operands) == 1 and isinstance(obj.operands[0], Ref):
            current = obj.operands[0]
            continue
        break
    assert current.kind is RefKind.N
    return current


def _quantifier_spine(core: AHCore, ref: Ref) -> tuple[str, ...]:
    labels: list[str] = []
    current: object = ref
    while isinstance(current, Ref) and current.kind is RefKind.G:
        obj = _function(core, current)
        labels.append(obj.function_id)
        if obj.function_id == "FORALL" and len(obj.operands) == 2:
            current = obj.operands[1]
            continue
        if obj.function_id == "IMPLIES" and len(obj.operands) == 2:
            current = obj.operands[1]
            continue
        if obj.function_id == "NOT" and len(obj.operands) == 1:
            current = obj.operands[0]
            continue
        if obj.function_id == "EXISTS" and len(obj.operands) == 2:
            current = obj.operands[1]
            continue
        break
    if isinstance(current, Ref) and current.kind is RefKind.N:
        labels.append("BODY_N")
    return tuple(labels)


def test_someone_sleeps_remains_one_exists_scope() -> None:
    core, context, service, engine = _env()
    result = PerceptionResult(
        "Кто-то спит",
        assertions=(
            _unary(
                "A1",
                "спать",
                "Кто-то",
                entity_ref="E1",
                quantifier_kind=QuantifierKind.EXISTS,
            ),
        ),
    )
    commit = service.integrate_external(result, context)
    assert len(commit.existentials) == 1
    assert commit.universals == ()
    existential = commit.existentials[0]
    assert existential.variable_ids == (0,)
    assert _function(core, existential.ref).function_id == "EXISTS"
    assert core.store.find_entities_by_name("кто-то", Domain.C) == ()
    member = core.store.get_hypernode(existential.member_refs[0].uid)
    assert member.meta["semantic_scope"] == "QUANTIFIED"
    assert isinstance(member.actants[ActantRole.SUBJECT], BoundVar)
    assert _solve(engine, core.ref(member.uid)).status is LogicalStatus.UNKNOWN
    exists_outcome = _solve(engine, existential.ref)
    assert exists_outcome.status is LogicalStatus.PROVED
    assert exists_outcome.proof_support[0].rule_id == "EXISTS_ASSERTED"


def test_all_humans_are_mortal_proves_ivan_via_forall_implies_mp() -> None:
    core, context, service, engine = _env()
    universal_result = PerceptionResult(
        "Все люди смертны",
        assertions=(
            _unary(
                "A1",
                "смертен",
                "все люди",
                quantifier_kind=QuantifierKind.FORALL,
                restriction_lemma="человек",
            ),
        ),
    )
    plan = service.prepare_external_plan(universal_result, context)
    assert len(plan.candidate_ir.universal_bindings) == 1
    binding = plan.candidate_ir.universal_bindings[0]
    assert binding.restriction_lemma
    assert binding.negate_quantifier is False
    commit = service.integrate_plan(plan, context)
    assert len(commit.universals) == 1
    assert commit.existentials == ()
    universal = commit.universals[0]
    assert _quantifier_spine(core, universal.ref) == ("FORALL", "IMPLIES", "BODY_N")
    forall = _function(core, universal.ref)
    assert isinstance(forall.operands[0], BoundVar)
    implies = _function(core, forall.operands[1])
    assert implies.function_id == "IMPLIES"
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert event.actants[ActantRole.OBJECT] == universal.ref
    assert core.store.find_entities_by_name("все люди", Domain.C) == ()
    assert core.store.find_entities_by_name("все", Domain.C) == ()

    human_result = PerceptionResult(
        "Иван — человек",
        assertions=(_unary("A2", binding.restriction_lemma, "Иван"),),
    )
    human_commit = service.integrate_external(human_result, context)
    human_node = core.store.get_hypernode(human_commit.assertions[0].ref.uid)
    ivan = human_node.actants[ActantRole.SUBJECT]
    assert isinstance(ivan, Ref)

    mortal_pattern = _unwrap_n(core, universal.member_refs[0])
    mortal_node = core.store.get_hypernode(mortal_pattern.uid)
    target, _ = core.add_hypernode(
        Domain.C,
        mortal_node.template,
        {ActantRole.SUBJECT: ivan},
        0.5,
        count_occurrence=False,
    )
    outcome = _solve(engine, core.ref(target.uid))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert outcome.proof_support[0].rule_id == "FORALL_IMPLIES_MP"
    assert universal.ref in outcome.premise_refs
    assert human_commit.assertions[0].ref in outcome.premise_refs


def test_nl_universal_creates_a_rule_not_an_enumerated_list() -> None:
    core, context, service, engine = _env()
    commit = service.integrate_external(
        PerceptionResult(
            "Все люди смертны",
            assertions=(
                _unary(
                    "A1",
                    "смертен",
                    "все люди",
                    quantifier_kind=QuantifierKind.FORALL,
                    restriction_lemma="человек",
                ),
            ),
        ),
        context,
    )
    universal = commit.universals[0]
    member = core.store.get_hypernode(_unwrap_n(core, universal.member_refs[0]).uid)
    subject = member.actants[ActantRole.SUBJECT]
    assert isinstance(subject, BoundVar)
    assert str(subject.local_id) not in core.store.all_uids()
    assert member.meta["semantic_scope"] == "QUANTIFIED"
    assert int(member.meta.get("occurrence_count", 0) or 0) == 0

    service.integrate_external(
        PerceptionResult("Иван — человек", assertions=(_unary("A2", "человек", "Иван"),)),
        context,
    )
    service.integrate_external(
        PerceptionResult("Мария — человек", assertions=(_unary("A3", "человек", "Мария"),)),
        context,
    )
    # Known instances do not replace the asserted universal with a closed list.
    assert _function(core, universal.ref).function_id == "FORALL"
    assert len(universal.member_refs) == 1
    outcome = _solve(engine, universal.ref)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[0].rule_id == "FORALL_ASSERTED"


def test_nobody_sleeps_is_not_exists_without_m_nobody() -> None:
    core, context, service, engine = _env()
    nobody = service.integrate_external(
        PerceptionResult(
            "Никто не спит",
            assertions=(
                _unary(
                    "A1",
                    "спать",
                    "никто",
                    quantifier_kind=QuantifierKind.NOT_EXISTS,
                ),
            ),
        ),
        context,
    )
    assert len(nobody.existentials) == 1
    assert nobody.universals == ()
    root = nobody.existentials[0].ref
    assert _quantifier_spine(core, root) == ("NOT", "EXISTS", "BODY_N")
    not_g = _function(core, root)
    exists = _function(core, not_g.operands[0])
    assert exists.function_id == "EXISTS"
    member = core.store.get_hypernode(nobody.existentials[0].member_refs[0].uid)
    assert member.meta["semantic_scope"] == "QUANTIFIED"
    assert isinstance(member.actants[ActantRole.SUBJECT], BoundVar)
    assert core.store.find_entities_by_name("никто", Domain.C) == ()
    event = core.store.get_hypernode(nobody.experience_ref.uid)
    assert event.actants[ActantRole.OBJECT] == root

    assert _solve(engine, not_g.operands[0]).status is LogicalStatus.UNKNOWN
    assert _solve(engine, root).status is LogicalStatus.PROVED

    anna = service.integrate_external(
        PerceptionResult("Анна спит", assertions=(_unary("A2", "спать", "Анна"),)),
        context,
    )
    assert core.store.find_entities_by_name("никто", Domain.C) == ()
    witness = _solve(engine, not_g.operands[0])
    assert witness.status is LogicalStatus.PROVED
    assert witness.proof_support[0].rule_id == "EXISTS_WITNESS"
    # The witness proves EXISTS; that is the disproof of «никто». The asserted
    # NOT(EXISTS) remains on record as a polarity clash, not as m_никто.
    assert anna.assertions[0].semantic_scope is None
    nobody_n_uids = {item.uid for item in nobody.existentials[0].member_refs}
    assert anna.assertions[0].ref.uid not in nobody_n_uids


def test_not_all_came_vs_all_did_not_come_are_different_trees() -> None:
    _core, context, service, _engine = _env()
    not_all = service.integrate_external(
        PerceptionResult(
            "Не все сотрудники пришли",
            assertions=(
                _unary(
                    "A1",
                    "прийти",
                    "не все сотрудники",
                    quantifier_kind=QuantifierKind.NOT_FORALL,
                    restriction_lemma="сотрудник",
                ),
            ),
        ),
        context,
    )
    all_not = service.integrate_external(
        PerceptionResult(
            "Все сотрудники не пришли",
            assertions=(
                _unary(
                    "A2",
                    "прийти",
                    "все сотрудники",
                    negated=True,
                    quantifier_kind=QuantifierKind.FORALL,
                    restriction_lemma="сотрудник",
                ),
            ),
        ),
        context,
    )
    assert len(not_all.universals) == 1
    assert len(all_not.universals) == 1
    assert _quantifier_spine(_core, not_all.universals[0].ref) == (
        "NOT",
        "FORALL",
        "IMPLIES",
        "BODY_N",
    )
    assert _quantifier_spine(_core, all_not.universals[0].ref) == (
        "FORALL",
        "IMPLIES",
        "NOT",
        "BODY_N",
    )
    not_all_forall = _function(_core, _function(_core, not_all.universals[0].ref).operands[0])
    all_not_forall = _function(_core, all_not.universals[0].ref)
    assert not_all_forall.function_id == "FORALL"
    assert all_not_forall.function_id == "FORALL"
    assert not_all.universals[0].ref != all_not.universals[0].ref


def test_not_all_then_not_is_fail_closed() -> None:
    _core, context, service, _engine = _env()
    with pytest.raises(CandidateValidationError, match="scope metadata"):
        service.integrate_external(
            PerceptionResult(
                "Не все сотрудники не пришли",
                assertions=(
                    _unary(
                        "A1",
                        "прийти",
                        "не все сотрудники",
                        negated=True,
                        quantifier_kind=QuantifierKind.NOT_FORALL,
                        restriction_lemma="сотрудник",
                    ),
                ),
            ),
            context,
        )


def test_boundvar_from_nl_has_no_runtime_state_or_ah_uid() -> None:
    core, context, service, _engine = _env()
    commit = service.integrate_external(
        PerceptionResult(
            "Все люди смертны",
            assertions=(
                _unary(
                    "A1",
                    "смертен",
                    "все люди",
                    quantifier_kind=QuantifierKind.FORALL,
                    restriction_lemma="человек",
                ),
            ),
        ),
        context,
    )
    universal = commit.universals[0]
    forall = _function(core, universal.ref)
    variable = forall.operands[0]
    assert isinstance(variable, BoundVar)
    assert not hasattr(variable, "uid")
    assert str(variable.local_id) not in core.store.all_uids()
    runtime_uids = {uid for uid, _state in core.store.runtime_items()}
    assert str(variable.local_id) not in runtime_uids
    member = core.store.get_hypernode(_unwrap_n(core, universal.member_refs[0]).uid)
    subject = member.actants[ActantRole.SUBJECT]
    assert subject == variable
    for uid in core.store.all_uids():
        assert core.store.kind_of(uid) is not None
        assert uid != f"${variable.local_id}"
