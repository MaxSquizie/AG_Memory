from __future__ import annotations

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus, StopReason
from ah.integration import IntegrationConfig, IntegrationService, SemanticCorrectionService
from ah.model import ActantRole, Domain, FunctionSymbol, Property, Ref, RefKind
from ah.perception import (
    ActantCandidate,
    ActantCompositionCandidate,
    AssertionCandidate,
    AssertionStatus,
    CompositionMemberCandidate,
    CompositionOperator,
    ConditionalCandidate,
    PerceptionResult,
    PredicateCandidate,
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


def _assertion(local_id: str, predicate: str, subject: str, *, negated: bool = False, status=AssertionStatus.ASSERTED):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        negated=negated,
        status=status,
    )


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_object_negation_is_not_and_refutes_ground_positive_without_false_correction() -> None:
    core, context, service, engine = _env()
    commit = service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N1", "спать", "кошка", negated=True),)),
        context,
    )
    not_ref = commit.assertions[0].ref
    not_g = core.store.get_element_any_domain(not_ref.uid)
    assert isinstance(not_g, FunctionSymbol)
    assert not_g.function_id == "NOT"
    positive_ref = not_g.operands[0]
    assert isinstance(positive_ref, Ref)
    assert core.store.get_hypernode(positive_ref.uid).meta["occurrence_count"] == 0
    assert commit.refutations == ()

    positive = _solve(engine, positive_ref)
    assert positive.status is LogicalStatus.DISPROVED
    assert positive.stop_reason is StopReason.GOAL_REFUTED

    negative = _solve(engine, not_ref)
    assert negative.status is LogicalStatus.PROVED


def test_positive_and_not_positive_are_localized_conflict_not_auto_winner() -> None:
    core, context, service, engine = _env()
    positive_commit = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    positive_ref = positive_commit.assertions[0].ref
    service.integrate_external(
        PerceptionResult("Кошка не спит", assertions=(_assertion("N", "спать", "кошка", negated=True),)),
        context,
    )

    outcome = _solve(engine, positive_ref)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.CONFLICTED
    assert "Both P and NOT(P)" in outcome.diagnostics[0]


def test_false_remains_explicit_meta_refutation() -> None:
    core, context, service, engine = _env()
    positive_commit = service.integrate_external(
        PerceptionResult("Кошка спит", assertions=(_assertion("P", "спать", "кошка"),)),
        context,
    )
    target = positive_commit.assertions[0].ref
    correction = SemanticCorrectionService(core).refute(target)
    false_g = core.store.get_element_any_domain(correction.false_ref.uid)
    assert isinstance(false_g, FunctionSymbol)
    assert false_g.function_id == "FALSE"

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.DISPROVED
    assert outcome.stop_reason is StopReason.GOAL_REFUTED
    assert outcome.proof_support[0].rule_id == "EXPLICIT_REFUTATION"


def test_or_root_is_asserted_but_disjuncts_are_not_individual_facts() -> None:
    core, context, service, engine = _env()
    assertion = AssertionCandidate(
        "A1",
        PredicateCandidate(
            "быть",
            "быть",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="яблоко"),
            ActantCandidate(
                ActantRole.STATE,
                mention="зелёное или красное",
                composition=ActantCompositionCandidate(
                    CompositionOperator.OR,
                    (CompositionMemberCandidate("зелёное"), CompositionMemberCandidate("красное")),
                ),
            ),
        ),
    )
    commit = service.integrate_external(PerceptionResult("Яблоко зелёное или красное", assertions=(assertion,)), context)
    or_ref = commit.assertions[0].ref
    or_g = core.store.get_element_any_domain(or_ref.uid)
    assert isinstance(or_g, FunctionSymbol) and or_g.function_id == "OR"

    root = _solve(engine, or_ref)
    assert root.status is LogicalStatus.PROVED
    for operand in or_g.operands:
        assert isinstance(operand, Ref)
        node = core.store.get_hypernode(operand.uid)
        assert node.meta.get("semantic_scope") == "DISJUNCTIVE"
        assert node.meta.get("occurrence_count") == 0
        branch = _solve(engine, operand)
        assert branch.status is LogicalStatus.UNKNOWN


def test_ground_implies_uses_asserted_antecedent_and_scoped_rule_without_asserting_consequent() -> None:
    core, context, service, engine = _env()
    fact = service.integrate_external(
        PerceptionResult("Иван пришёл", assertions=(_assertion("F", "прийти", "Иван"),)),
        context,
    )
    asserted_a = fact.assertions[0].ref

    conditional = PerceptionResult(
        "Если Иван придёт, Мария уйдёт",
        assertions=(
            _assertion("A", "прийти", "Иван", status=AssertionStatus.CONDITIONAL),
            _assertion("B", "уйти", "Мария", status=AssertionStatus.CONDITIONAL),
        ),
        conditionals=(ConditionalCandidate(("A",), ("B",)),),
    )
    commit = service.integrate_external(conditional, context)
    rule = commit.conditionals[0]
    rule_g = core.store.get_element_any_domain(rule.ref.uid)
    assert isinstance(rule_g, FunctionSymbol)
    assert rule_g.function_id == "IMPLIES"
    consequent = rule.consequent
    assert core.store.get_hypernode(consequent.uid).meta.get("occurrence_count") == 0

    outcome = _solve(engine, consequent)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert asserted_a.uid in {ref.uid for ref in outcome.premise_refs}
    assert rule.ref.uid in {ref.uid for ref in outcome.premise_refs}
    assert outcome.proof_support[0].rule_id == "IMPLIES_MP"
    assert outcome.uid_trace[-2:] == (rule.ref, consequent)


def test_ground_implies_does_not_fire_without_antecedent() -> None:
    core, context, service, engine = _env()
    conditional = PerceptionResult(
        "Если Иван придёт, Мария уйдёт",
        assertions=(
            _assertion("A", "прийти", "Иван", status=AssertionStatus.CONDITIONAL),
            _assertion("B", "уйти", "Мария", status=AssertionStatus.CONDITIONAL),
        ),
        conditionals=(ConditionalCandidate(("A",), ("B",)),),
    )
    commit = service.integrate_external(conditional, context)
    consequent = commit.conditionals[0].consequent
    outcome = _solve(engine, consequent)
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.SEARCH_EXHAUSTED


def test_multi_premise_implies_requires_all_and_antecedents() -> None:
    core, context, service, engine = _env()
    service.integrate_external(
        PerceptionResult("Иван пришёл", assertions=(_assertion("F1", "прийти", "Иван"),)),
        context,
    )
    service.integrate_external(
        PerceptionResult("Мария позвонила", assertions=(_assertion("F2", "позвонить", "Мария"),)),
        context,
    )
    conditional = PerceptionResult(
        "Если Иван придёт и Мария позвонит, Пётр уйдёт",
        assertions=(
            _assertion("A", "прийти", "Иван", status=AssertionStatus.CONDITIONAL),
            _assertion("B", "позвонить", "Мария", status=AssertionStatus.CONDITIONAL),
            _assertion("C", "уйти", "Пётр", status=AssertionStatus.CONDITIONAL),
        ),
        conditionals=(ConditionalCandidate(("A", "B"), ("C",)),),
    )
    commit = service.integrate_external(conditional, context)
    rule = commit.conditionals[0]
    antecedent = core.store.get_element_any_domain(rule.antecedent.uid)
    assert isinstance(antecedent, FunctionSymbol)
    assert antecedent.function_id == "AND"

    outcome = _solve(engine, rule.consequent)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[0].rule_id == "IMPLIES_MP"


def test_multi_premise_implies_does_not_treat_partial_and_as_sufficient() -> None:
    core, context, service, engine = _env()
    service.integrate_external(
        PerceptionResult("Иван пришёл", assertions=(_assertion("F1", "прийти", "Иван"),)),
        context,
    )
    conditional = PerceptionResult(
        "Если Иван придёт и Мария позвонит, Пётр уйдёт",
        assertions=(
            _assertion("A", "прийти", "Иван", status=AssertionStatus.CONDITIONAL),
            _assertion("B", "позвонить", "Мария", status=AssertionStatus.CONDITIONAL),
            _assertion("C", "уйти", "Пётр", status=AssertionStatus.CONDITIONAL),
        ),
        conditionals=(ConditionalCandidate(("A", "B"), ("C",)),),
    )
    commit = service.integrate_external(conditional, context)
    outcome = _solve(engine, commit.conditionals[0].consequent)
    assert outcome.status is LogicalStatus.UNKNOWN
