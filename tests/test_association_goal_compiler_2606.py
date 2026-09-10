from __future__ import annotations

import pytest

from ah.agent import InteractionContext
from ah.association import (
    AssociationDomainPolicy,
    AssociationOutcome,
    AssociationPath,
    AssociationSemantics,
    AssociationStatus,
)
from ah.config import ContextSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import AssociationGoal, AssociationQueryBuildResult, SemanticGoalCompiler
from ah.integration.candidate_validator import CandidateValidator
from ah.integration.contracts import IntegratedAssertion, IntegrationCommit
from ah.integration.errors import CandidateValidationError
from ah.model import ActantRole, Domain, Property, RefKind
from ah.perception import (
    ActRelationCandidate,
    ActantCandidate,
    ActantCompositionCandidate,
    AssociationActRelationCandidate,
    CommandCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
)
from ah.projection import AssociationContextProjector, ProjectionMode


def _entity(core: AHCore, name: str, domain: Domain = Domain.C):
    item = core.add_entity(
        domain,
        properties={"name": Property("name", name, "str")},
    )
    return core.ref(item.uid)


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = _entity(core, "user", Domain.P)
    agent = _entity(core, "agent", Domain.P)
    return core, InteractionContext(user_ref=user, self_ref=agent)


def _commit(
    context: InteractionContext,
    *,
    assertions: tuple[IntegratedAssertion, ...] = (),
) -> IntegrationCommit:
    assert context.user_ref is not None
    return IntegrationCommit(
        assertions=assertions,
        experience_ref=context.user_ref,
        activation_seeds=(),
    )


def _query(
    actants: tuple[ActantCandidate, ...],
    relation: AssociationActRelationCandidate,
    *,
    text: str = "association query",
) -> PerceptionResult:
    query = QueryCandidate(
        PredicateCandidate("associate", normalized_hint="associate"),
        actants,
        local_id=relation.act_ref,
    )
    return PerceptionResult(
        source_text=text,
        queries=(query,),
        act_relations=(relation,),
    )


def _compile(
    core: AHCore,
    context: InteractionContext,
    perception: PerceptionResult,
    commit: IntegrationCommit | None = None,
) -> AssociationQueryBuildResult:
    built = SemanticGoalCompiler(core).build(
        commit or _commit(context),
        context,
        perception,
    )
    assert len(built) == 1
    assert isinstance(built[0], AssociationQueryBuildResult)
    return built[0]


def _fact(core: AHCore, predicate: str, subject_name: str):
    subject = _entity(core, subject_name)
    symbol = core.ensure_abstract_symbol(predicate)
    template = core.add_template(
        Domain.C,
        core.ref(symbol.uid),
        (ActantRole.SUBJECT,),
    )
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: subject},
        0.5,
    )
    return core.ref(node.uid)


def test_existing_entity_endpoints_compile_read_only_to_association_goal() -> None:
    core, context = _env()
    fire = _entity(core, "огонь")
    smoke = _entity(core, "дым")
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, mention="огонь", normalized_hint="огонь"),
            ActantCandidate(ActantRole.OBJECT, mention="дым", normalized_hint="дым"),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )
    before = set(core.store.all_uids())

    built = _compile(core, context, perception)

    assert built.goal is None
    assert built.association_goal is not None
    assert built.association_goal.left == fire
    assert built.association_goal.right == smoke
    assert set(core.store.all_uids()) == before


def test_composition_members_are_independent_same_role_endpoints() -> None:
    core, context = _env()
    sea = _entity(core, "море")
    lighthouse = _entity(core, "маяк")
    composition = ActantCompositionCandidate(
        CompositionOperator.AND,
        (
            CompositionMemberCandidate("море", "море"),
            CompositionMemberCandidate("маяк", "маяк"),
        ),
    )
    perception = _query(
        (ActantCandidate(ActantRole.OBJECT, composition=composition),),
        AssociationActRelationCandidate(
            "ASSOCIATION",
            "Q1",
            ActantRole.OBJECT,
            ActantRole.OBJECT,
            source_member_index=0,
            target_member_index=1,
        ),
    )

    built = _compile(core, context, perception)

    assert built.association_goal is not None
    assert built.association_goal.left == sea
    assert built.association_goal.right == lighthouse


def test_candidate_ref_endpoint_reuses_integrated_N_without_entity_flattening() -> None:
    core, context = _env()
    assertion_ref = _fact(core, "упасть", "сервер")
    network = _entity(core, "сеть")
    commit = _commit(
        context,
        assertions=(
            IntegratedAssertion("A1", assertion_ref, Domain.C, created=False),
        ),
    )
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, candidate_ref="A1"),
            ActantCandidate(ActantRole.OBJECT, mention="сеть", normalized_hint="сеть"),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )
    before = set(core.store.all_uids())

    built = _compile(core, context, perception, commit)

    assert built.association_goal is not None
    assert built.association_goal.left == assertion_ref
    assert built.association_goal.left.kind is RefKind.N
    assert built.association_goal.right == network
    assert set(core.store.all_uids()) == before


def test_proposition_expression_reuses_exact_existing_G_parent() -> None:
    core, context = _env()
    left_n = _fact(core, "упасть", "сервер")
    right_n = _fact(core, "пропасть", "сеть")
    conjunction = core.add_function(Domain.C, "AND", (left_n, right_n))
    conjunction_ref = core.ref(conjunction.uid)
    anchor = _entity(core, "инцидент")
    commit = _commit(
        context,
        assertions=(
            IntegratedAssertion("A1", left_n, Domain.C, created=False),
            IntegratedAssertion("A2", right_n, Domain.C, created=False),
        ),
    )
    expression = PropositionExprCandidate(
        PropositionOperator.AND,
        members=(
            PropositionExprCandidate.ref_expr("A1"),
            PropositionExprCandidate.ref_expr("A2"),
        ),
    )
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, proposition=expression),
            ActantCandidate(
                ActantRole.OBJECT,
                mention="инцидент",
                normalized_hint="инцидент",
            ),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )
    before = set(core.store.all_uids())

    built = _compile(core, context, perception, commit)

    assert built.association_goal is not None
    assert built.association_goal.left == conjunction_ref
    assert built.association_goal.left.kind is RefKind.G
    assert built.association_goal.right == anchor
    assert set(core.store.all_uids()) == before


def test_unique_existing_lexical_S_is_valid_read_only_fallback_origin() -> None:
    core, context = _env()
    lexical = core.ensure_abstract_symbol("ксарп")
    smoke = _entity(core, "дым")
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, mention="ксарп", normalized_hint="ксарп"),
            ActantCandidate(ActantRole.OBJECT, mention="дым", normalized_hint="дым"),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )
    before = set(core.store.all_uids())

    built = _compile(core, context, perception)

    assert built.association_goal is not None
    assert built.association_goal.left == core.ref(lexical.uid)
    assert built.association_goal.left.kind is RefKind.S
    assert built.association_goal.right == smoke
    assert set(core.store.all_uids()) == before


def test_unknown_endpoint_fails_closed_and_does_not_create_entity_or_symbol() -> None:
    core, context = _env()
    _entity(core, "дым")
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, mention="ксарп", normalized_hint="ксарп"),
            ActantCandidate(ActantRole.OBJECT, mention="дым", normalized_hint="дым"),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )
    before = set(core.store.all_uids())

    built = _compile(core, context, perception)

    assert built.association_goal is None
    assert built.goal is None
    assert built.diagnostics == (
        "semantic:association_endpoint_not_found:SUBJECT",
    )
    assert set(core.store.all_uids()) == before


def test_distinct_parser_endpoints_may_resolve_to_same_canonical_origin() -> None:
    core, context = _env()
    fire = _entity(core, "огонь")
    perception = _query(
        (
            ActantCandidate(ActantRole.SUBJECT, mention="огонь", normalized_hint="огонь"),
            ActantCandidate(ActantRole.OBJECT, mention="огонь", normalized_hint="огонь"),
        ),
        AssociationActRelationCandidate(
            "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
        ),
    )

    built = _compile(core, context, perception)

    assert built.association_goal is not None
    assert built.association_goal.left == fire
    assert built.association_goal.right == fire


def test_plain_act_relation_cannot_smuggle_association_into_world_relation_path() -> None:
    query = QueryCandidate(
        PredicateCandidate("associate"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="A"),
            ActantCandidate(ActantRole.OBJECT, mention="B"),
        ),
        local_id="Q1",
    )
    perception = PerceptionResult(
        "association query",
        queries=(query,),
        act_relations=(
            ActRelationCandidate(
                "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
            ),
        ),
    )

    with pytest.raises(
        CandidateValidationError,
        match="AssociationActRelationCandidate",
    ):
        CandidateValidator().validate(perception)


def test_negated_association_command_is_rejected_before_execution() -> None:
    command = CommandCandidate(
        PredicateCandidate("associate"),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="A"),
            ActantCandidate(ActantRole.OBJECT, mention="B"),
        ),
        local_id="C1",
        negated=True,
    )
    perception = PerceptionResult(
        "do not associate A and B",
        commands=(command,),
        act_relations=(
            AssociationActRelationCandidate(
                "ASSOCIATION", "C1", ActantRole.SUBJECT, ActantRole.OBJECT
            ),
        ),
    )

    with pytest.raises(CandidateValidationError, match="Negated command"):
        CandidateValidator().validate(perception)


def test_association_projection_has_own_channel_and_never_becomes_inference_block() -> None:
    core, _context = _env()
    same = _entity(core, "same")
    goal = AssociationGoal(same, same)
    path = AssociationPath(same, same, (same,), ())
    outcome = AssociationOutcome(
        status=AssociationStatus.FOUND,
        goal=goal,
        common_ref=same,
        left_path=path,
        right_path=path,
        common_candidates=(same,),
        left_activated=(same,),
        right_activated=(same,),
        expanded_states=0,
        ticks_executed=0,
        trace=(),
        domain_policy=AssociationDomainPolicy.ALL,
        semantics=AssociationSemantics.SEMANTIC,
        minimal_fact_count=0,
    )

    projected = AssociationContextProjector(
        core, ContextSettings()
    ).project_with_associations(
        "find association",
        (),
        association_results=(outcome,),
    )

    assert projected.inference_blocks == ()
    assert len(projected.association_blocks) == 1
    assert projected.association_blocks[0].mode is ProjectionMode.ASSOCIATION
    assert "# ASSOCIATION RESULTS" in projected.rendered
    assert "# INFERENCE RESULTS" not in projected.rendered
    assert "НЕ логическое доказательство" in projected.rendered
