from __future__ import annotations

from dataclasses import replace

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator, SupportRecord
from ah.inference import (
    CounterfactualContext,
    CounterfactualGoal,
    FormulaGoal,
    GoalSpec,
    InferenceEngine,
    InferenceMaterializer,
    InferenceQuery,
    LogicalStatus,
    StopReason,
)
from ah.integration import IntegrationConfig, IntegrationService, SemanticCorrectionService
from ah.model import ActantRole, Domain, FunctionSymbol, Hypernode, Property, Ref, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
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
    engine = InferenceEngine(core, InferenceSettings(max_depth=12, max_expanded_states=512))
    return core, context, service, engine


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def _unary_assertion(
    local_id: str,
    predicate: str,
    subject: str,
    *,
    status: AssertionStatus = AssertionStatus.ASSERTED,
):
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention=subject),),
        status=status,
    )


def _assert_formula_occurrence(core: AHCore, formula_ref: Ref) -> Ref:
    """Create the minimal H communication occurrence used by formula assertion tests."""
    speaker = core.store.find_entities_by_name("Пользователь", Domain.P)[0]
    predicate = core.ensure_abstract_symbol("утверждать")
    templates = core.store.find_templates_by_predicate(predicate.uid)
    if templates:
        template = templates[0]
    else:
        template = core.add_template(
            Domain.H,
            core.ref(predicate.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
    event, _ = core.add_hypernode(
        Domain.H,
        core.ref(template.uid),
        {ActantRole.SUBJECT: core.ref(speaker.uid), ActantRole.OBJECT: formula_ref},
        0.3,
        meta={"event_instance": True},
        deduplicate=False,
    )
    return core.ref(event.uid)


def _entity(core: AHCore, name: str) -> Ref:
    existing = core.store.find_entities_by_name(name, Domain.C)
    if existing:
        return core.ref(existing[0].uid)
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _atom(
    core: AHCore,
    predicate: str,
    subject: str,
    *,
    asserted: bool,
    scope: str | None = None,
) -> Ref:
    pred = core.ensure_abstract_symbol(predicate)
    templates = core.store.find_templates_by_predicate(pred.uid)
    if templates:
        template = templates[0]
    else:
        template = core.add_template(Domain.C, core.ref(pred.uid), (ActantRole.SUBJECT,))
    meta = {"semantic_scope": scope} if scope else {}
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: _entity(core, subject)},
        0.4,
        meta=meta,
        count_occurrence=asserted,
    )
    return core.ref(node.uid)


def test_proof_by_cases_uses_local_branch_assumptions_without_asserting_either_branch() -> None:
    core, _context, _service, engine = _env()
    a = _atom(core, "быть зелёным", "яблоко", asserted=False, scope="DISJUNCTIVE")
    b = _atom(core, "быть красным", "яблоко", asserted=False, scope="DISJUNCTIVE")
    c = _atom(core, "быть цветным", "яблоко", asserted=False)

    or_g, _ = core.ensure_function(Domain.C, "OR", (a, b))
    or_ref = core.ref(or_g.uid)
    _assert_formula_occurrence(core, or_ref)

    r1, _ = core.ensure_function(Domain.C, "IMPLIES", (a, c))
    r2, _ = core.ensure_function(Domain.C, "IMPLIES", (b, c))
    r1_ref, r2_ref = core.ref(r1.uid), core.ref(r2.uid)
    _assert_formula_occurrence(core, r1_ref)
    _assert_formula_occurrence(core, r2_ref)

    assert _solve(engine, a).status is LogicalStatus.UNKNOWN
    assert _solve(engine, b).status is LogicalStatus.UNKNOWN

    result = _solve(engine, c)
    assert result.status is LogicalStatus.PROVED
    assert result.stop_reason is StopReason.GOAL_SATISFIED
    assert result.proof_support[0].rule_id == "OR_CASES"
    premise_uids = {ref.uid for ref in result.premise_refs}
    assert or_ref.uid in premise_uids
    assert r1_ref.uid in premise_uids
    assert r2_ref.uid in premise_uids
    assert a.uid not in premise_uids
    assert b.uid not in premise_uids

    # Branch assumptions were never promoted to factual occurrences.
    assert core.store.get_hypernode(a.uid).meta["occurrence_count"] == 0
    assert core.store.get_hypernode(b.uid).meta["occurrence_count"] == 0


def test_proof_by_cases_fails_when_one_branch_has_no_route_to_goal() -> None:
    core, _context, _service, engine = _env()
    a = _atom(core, "быть зелёным", "яблоко", asserted=False, scope="DISJUNCTIVE")
    b = _atom(core, "быть красным", "яблоко", asserted=False, scope="DISJUNCTIVE")
    c = _atom(core, "быть цветным", "яблоко", asserted=False)
    or_g, _ = core.ensure_function(Domain.C, "OR", (a, b))
    _assert_formula_occurrence(core, core.ref(or_g.uid))
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (a, c))
    _assert_formula_occurrence(core, core.ref(rule.uid))

    result = _solve(engine, c)
    assert result.status is LogicalStatus.UNKNOWN


def test_counterfactual_positive_assumption_overrides_canonical_not_only_inside_overlay() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "работать", "сервер", asserted=True)
    not_g, _ = core.ensure_function(Domain.C, "NOT", (p,))
    not_ref = core.ref(not_g.uid)
    _assert_formula_occurrence(core, not_ref)
    q = _atom(core, "отвечать", "сервис", asserted=False)
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (p, q))
    _assert_formula_occurrence(core, core.ref(rule.uid))

    normal = _solve(engine, q)
    assert normal.status is LogicalStatus.UNKNOWN

    cf = engine.solve(
        InferenceQuery(
            GoalSpec(CounterfactualGoal((p,), FormulaGoal(q)))
        )
    )
    assert cf.status is LogicalStatus.PROVED
    assert isinstance(cf.proof_context, CounterfactualContext)
    assert "counterfactual overlay" in cf.diagnostics[0]

    # Canonical world did not change: outside the overlay P is still conflicted.
    assert _solve(engine, p).stop_reason is StopReason.CONFLICTED
    assert core.store.get_hypernode(p.uid).meta["occurrence_count"] == 1


def test_counterfactual_negative_assumption_filters_dependent_support_but_keeps_independent_support() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "быть включённым", "рубильник", asserted=True)
    r = _atom(core, "быть резервным", "питание", asserted=True)
    q_only_p = _atom(core, "получать питание", "узел А", asserted=False)
    q_independent = _atom(core, "получать питание", "узел Б", asserted=False)
    core.add_support(q_only_p, SupportRecord((p,), rule_id="TEST_P"))
    core.add_support(q_independent, SupportRecord((p,), rule_id="TEST_P"))
    core.add_support(q_independent, SupportRecord((r,), rule_id="TEST_R"))
    not_p_g, _ = core.ensure_function(Domain.C, "NOT", (p,))
    not_p = core.ref(not_p_g.uid)

    blocked = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((not_p,), FormulaGoal(q_only_p))))
    )
    assert blocked.status is LogicalStatus.UNKNOWN

    survives = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((not_p,), FormulaGoal(q_independent))))
    )
    assert survives.status is LogicalStatus.PROVED

    # Overlay filtering is non-destructive: both persisted supports still exist.
    assert len(core.resolve_supports(q_only_p)) == 1
    assert len(core.resolve_supports(q_independent)) == 2


def test_counterfactual_result_cannot_be_materialized_into_factual_ah() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "быть включённым", "рубильник", asserted=False)
    q = _atom(core, "запуститься", "насос", asserted=False)
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (p, q))
    _assert_formula_occurrence(core, core.ref(rule.uid))

    result = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((p,), FormulaGoal(q))))
    )
    assert result.status is LogicalStatus.PROVED

    materialized = InferenceMaterializer(core, IntegrationSettings()).materialize(result)
    assert materialized.ref is None
    assert core.resolve_supports(q) == ()
    assert core.store.get_hypernode(q.uid).meta["occurrence_count"] == 0


def test_mutually_incompatible_counterfactual_assumptions_are_rejected() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "работать", "сервер", asserted=False)
    not_g, _ = core.ensure_function(Domain.C, "NOT", (p,))
    not_p = core.ref(not_g.uid)
    result = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((p, not_p), FormulaGoal(p))))
    )
    assert result.status is LogicalStatus.UNKNOWN
    assert result.stop_reason is StopReason.CONFLICTED


def test_modal_and_hypothetical_scopes_do_not_become_factual_premises() -> None:
    core, context, service, engine = _env()
    modal = service.integrate_external(
        PerceptionResult(
            "Возможно сервер работает",
            assertions=(_unary_assertion("M", "работать", "сервер", status=AssertionStatus.MODAL),),
        ),
        context,
    )
    hypothetical = service.integrate_external(
        PerceptionResult(
            "Предположим насос запущен",
            assertions=(_unary_assertion("H", "быть запущенным", "насос", status=AssertionStatus.HYPOTHETICAL),),
        ),
        context,
    )

    m_ref = modal.assertions[0].ref
    h_ref = hypothetical.assertions[0].ref
    assert core.store.get_hypernode(m_ref.uid).meta["semantic_scope"] == "MODAL"
    assert core.store.get_hypernode(h_ref.uid).meta["semantic_scope"] == "HYPOTHETICAL"
    assert core.store.get_hypernode(m_ref.uid).meta["occurrence_count"] == 0
    assert core.store.get_hypernode(h_ref.uid).meta["occurrence_count"] == 0
    assert _solve(engine, m_ref).status is LogicalStatus.UNKNOWN
    assert _solve(engine, h_ref).status is LogicalStatus.UNKNOWN


def test_reported_content_is_not_world_fact_but_matrix_attitude_is_asserted() -> None:
    core, context, service, engine = _env()
    embedded = _unary_assertion("P", "работать", "сервер", status=AssertionStatus.EMBEDDED)
    matrix = AssertionCandidate(
        "B",
        PredicateCandidate(
            "считать",
            "считать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="Анна"),
            ActantCandidate(
                ActantRole.OBJECT,
                proposition=PropositionExprCandidate.ref_expr("P"),
            ),
        ),
    )
    commit = service.integrate_external(
        PerceptionResult("Анна считает, что сервер работает", assertions=(embedded, matrix)),
        context,
    )
    by_id = {item.local_id: item for item in commit.assertions}
    p_ref = by_id["P"].ref
    belief_ref = by_id["B"].ref

    assert _solve(engine, p_ref).status is LogicalStatus.UNKNOWN
    assert _solve(engine, belief_ref).status is LogicalStatus.PROVED
    belief_node = core.store.get_hypernode(belief_ref.uid)
    assert belief_node.actants[ActantRole.OBJECT] == p_ref


def test_correction_and_contradiction_are_explicit_meta_propositions_without_operand_truth_leak() -> None:
    core, _context, _service, engine = _env()
    old = _atom(core, "быть красным", "лампа", asserted=True)
    replacement = _atom(core, "быть зелёным", "лампа", asserted=True)
    correction = SemanticCorrectionService(core).correct(old, replacement)

    assert _solve(engine, old).status is LogicalStatus.DISPROVED
    meta = _solve(engine, correction.corrects_ref)
    assert meta.status is LogicalStatus.PROVED
    assert meta.proof_support[0].rule_id == "CORRECTS_EXPLICIT"
    assert _solve(engine, replacement).status is LogicalStatus.PROVED

    left = _atom(core, "быть открытым", "дверь A", asserted=False, scope="EMBEDDED")
    right = _atom(core, "быть закрытым", "дверь A", asserted=False, scope="EMBEDDED")
    contradiction = SemanticCorrectionService(core).mark_contradiction(left, right)
    assert _solve(engine, contradiction.contradicts_ref).status is LogicalStatus.PROVED
    assert _solve(engine, left).status is LogicalStatus.UNKNOWN
    assert _solve(engine, right).status is LogicalStatus.UNKNOWN


def test_self_referential_meta_expression_is_excluded_from_ordinary_proof() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "существовать", "утверждение", asserted=False)
    false_g, _ = core.ensure_function(Domain.C, "FALSE", (p,))
    false_ref = core.ref(false_g.uid)

    # Simulate a malformed/self-referential persisted expression without adding a
    # special paradox solver to canonical AH. Runtime proof must fail closed.
    core.store._replace_element(
        Domain.C,
        FunctionSymbol(false_g.uid, "FALSE", (false_ref,)),
        RefKind.G,
    )
    result = _solve(engine, false_ref)
    assert result.status is LogicalStatus.UNKNOWN
    assert any("Self-referential" in item for item in result.diagnostics)


def test_counterfactual_support_filtering_propagates_through_derived_dependency_chain() -> None:
    core, _context, _service, engine = _env()
    p = _atom(core, "быть доступным", "источник", asserted=True)
    q = _atom(core, "получать данные", "шлюз", asserted=False)
    r = _atom(core, "работать", "аналитика", asserted=False)
    core.add_support(q, SupportRecord((p,), rule_id="P_TO_Q"))
    core.add_support(r, SupportRecord((q,), rule_id="Q_TO_R"))
    not_p_g, _ = core.ensure_function(Domain.C, "NOT", (p,))
    not_p = core.ref(not_p_g.uid)

    assert _solve(engine, r).status is LogicalStatus.PROVED
    counterfactual = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((not_p,), FormulaGoal(r))))
    )
    assert counterfactual.status is LogicalStatus.UNKNOWN
    assert len(core.resolve_supports(q)) == 1
    assert len(core.resolve_supports(r)) == 1


def test_meta_functions_and_scoped_content_survive_persistence_roundtrip(tmp_path) -> None:
    from ah.config import PersistenceSettings
    from ah.core import JsonPersistence

    core, context, service, _engine = _env()
    modal = service.integrate_external(
        PerceptionResult(
            "Возможно сервер работает",
            assertions=(_unary_assertion("M", "работать", "сервер", status=AssertionStatus.MODAL),),
        ),
        context,
    )
    old = _atom(core, "быть красным", "индикатор", asserted=True)
    replacement = _atom(core, "быть зелёным", "индикатор", asserted=True)
    correction = SemanticCorrectionService(core).correct(old, replacement)

    path = tmp_path / "ah.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core, context=context)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    engine = InferenceEngine(loaded, InferenceSettings(max_depth=12, max_expanded_states=512))

    modal_ref = loaded.ref(modal.assertions[0].ref.uid)
    modal_node = loaded.store.get_hypernode(modal_ref.uid)
    assert modal_node.meta["semantic_scope"] == "MODAL"
    assert _solve(engine, modal_ref).status is LogicalStatus.UNKNOWN

    corrects_ref = loaded.ref(correction.corrects_ref.uid)
    result = _solve(engine, corrects_ref)
    assert result.status is LogicalStatus.PROVED
    assert result.proof_support[0].rule_id == "CORRECTS_EXPLICIT"


def test_counterfactual_scoped_assumption_overrides_structurally_equivalent_world_fact() -> None:
    core, _context, _service, engine = _env()
    factual = _atom(core, "работать", "сервер", asserted=True)
    scoped = _atom(core, "работать", "сервер", asserted=False, scope="HYPOTHETICAL")
    scoped_not_g, _ = core.ensure_function(Domain.C, "NOT", (scoped,))
    scoped_not = core.ref(scoped_not_g.uid)

    # Outside the sandbox the factual proposition remains true.
    assert _solve(engine, factual).status is LogicalStatus.PROVED
    inside = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((scoped_not,), FormulaGoal(factual))))
    )
    assert inside.status is LogicalStatus.DISPROVED
    assert _solve(engine, factual).status is LogicalStatus.PROVED


def test_counterfactual_applies_multiple_assumptions_simultaneously() -> None:
    core, _context, _service, engine = _env()
    a = _atom(core, "быть включённым", "контур A", asserted=False)
    b = _atom(core, "быть включённым", "контур B", asserted=False)
    c = _atom(core, "быть готовым", "система", asserted=False)
    and_g, _ = core.ensure_function(Domain.C, "AND", (a, b))
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (core.ref(and_g.uid), c))
    _assert_formula_occurrence(core, core.ref(rule.uid))

    one = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((a,), FormulaGoal(c))))
    )
    assert one.status is LogicalStatus.UNKNOWN

    both = engine.solve(
        InferenceQuery(GoalSpec(CounterfactualGoal((a, b), FormulaGoal(c))))
    )
    assert both.status is LogicalStatus.PROVED


def test_diagnostics_exposes_branch_and_counterfactual_scope_without_turning_it_into_memory() -> None:
    from ah.diagnostics.inference_proof import ProofSnapshotBuilder

    core, _context, _service, engine = _env()
    a = _atom(core, "режим A", "система", asserted=False, scope="DISJUNCTIVE")
    b = _atom(core, "режим B", "система", asserted=False, scope="DISJUNCTIVE")
    c = _atom(core, "быть безопасным", "система", asserted=False)
    or_g, _ = core.ensure_function(Domain.C, "OR", (a, b))
    _assert_formula_occurrence(core, core.ref(or_g.uid))
    for branch in (a, b):
        rule, _ = core.ensure_function(Domain.C, "IMPLIES", (branch, c))
        _assert_formula_occurrence(core, core.ref(rule.uid))

    by_cases = _solve(engine, c)
    snapshot = ProofSnapshotBuilder(core).build(
        by_cases, chain_id="cases", source="TEST", title="cases"
    )
    assert snapshot.steps[0].rule == "OR_CASES"
    assert "BranchContext" in snapshot.steps[0].explanation

    p = _atom(core, "быть включённым", "резерв", asserted=False)
    q = _atom(core, "быть доступным", "канал", asserted=False)
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (p, q))
    _assert_formula_occurrence(core, core.ref(rule.uid))
    cf = engine.solve(InferenceQuery(GoalSpec(CounterfactualGoal((p,), FormulaGoal(q)))))
    snapshot_cf = ProofSnapshotBuilder(core).build(
        cf, chain_id="cf", source="TEST", title="cf"
    )
    assert "при допущениях" in snapshot_cf.goal_text
    assert "CounterfactualContext" in snapshot_cf.steps[0].explanation
