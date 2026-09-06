from __future__ import annotations

from pathlib import Path

from ah.agent import InteractionContext
from ah.config import InferenceSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus, StopReason
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, BoundVar, Domain, Property, Ref, VariableSort


def _runtime():
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
    experience = ExperienceMapper(core, event_weight=0.3, follow_weight=0.2)
    engine = InferenceEngine(core, InferenceSettings(max_depth=12, max_expanded_states=512))
    return core, context, experience, engine


def _entity(core: AHCore, uid: str, name: str) -> Ref:
    obj = core.add_entity(
        Domain.C, {"name": Property("name", name, "str")}, uid=uid
    )
    return core.ref(obj.uid)


def _template(core: AHCore, stem: str, roles: tuple[ActantRole, ...]) -> Ref:
    s = core.add_abstract_symbol({stem.casefold()}, uid=f"S_{stem}")
    t = core.add_template(Domain.C, core.ref(s.uid), roles, uid=f"T_{stem}")
    return core.ref(t.uid)


def _ground(
    core: AHCore,
    template: Ref,
    actants: dict[ActantRole, Ref],
    *,
    uid: str,
    asserted: bool = True,
) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C,
        template,
        actants,
        0.5,
        uid=uid,
        count_occurrence=asserted,
    )
    return core.ref(node.uid)


def _pattern(
    core: AHCore,
    template: Ref,
    actants,
    *,
    uid: str,
) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C,
        template,
        actants,
        0.5,
        uid=uid,
        meta={"semantic_scope": "QUANTIFIED"},
        count_occurrence=False,
    )
    return core.ref(node.uid)


def _assert_expression(
    experience: ExperienceMapper,
    context: InteractionContext,
    expression: Ref,
    text: str = "универсальное правило",
) -> None:
    result = experience.record_turn(
        source_text=text,
        speaker_ref=context.user_ref,
        semantic_refs=(expression,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = result.event_ref


def _solve(engine: InferenceEngine, ref: Ref):
    return engine.solve(InferenceQuery(GoalSpec(FormulaGoal(ref))))


def test_exists_finds_one_witness_and_returns_runtime_binding() -> None:
    core, _context, _experience, engine = _runtime()
    t_sleep = _template(core, "SLEEP", (ActantRole.SUBJECT,))
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_sleep, {ActantRole.SUBJECT: maria}, uid="N_SLEEP_MARIA")

    var = BoundVar(0, VariableSort.ENTITY)
    body = _pattern(core, t_sleep, {ActantRole.SUBJECT: var}, uid="N_SLEEP_VAR")
    exists = core.add_function(Domain.C, "EXISTS", (var, body), uid="G_EXISTS_SLEEP")

    outcome = _solve(engine, core.ref(exists.uid))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert outcome.proof_support[0].rule_id == "EXISTS_WITNESS"
    assert outcome.bindings is not None
    assert dict(outcome.bindings.items())[0] == maria


def test_exists_is_unknown_when_no_witness_exists() -> None:
    core, _context, _experience, engine = _runtime()
    t_sleep = _template(core, "SLEEP", (ActantRole.SUBJECT,))
    var = BoundVar(0, VariableSort.ENTITY)
    body = _pattern(core, t_sleep, {ActantRole.SUBJECT: var}, uid="N_SLEEP_VAR")
    exists = core.add_function(Domain.C, "EXISTS", (var, body), uid="G_EXISTS_SLEEP")

    outcome = _solve(engine, core.ref(exists.uid))
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.SEARCH_EXHAUSTED


def test_exists_conjunction_requires_same_witness_for_repeated_variable() -> None:
    core, _context, _experience, engine = _runtime()
    t_enter = _template(core, "ENTER", (ActantRole.SUBJECT,))
    t_sit = _template(core, "SIT", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_enter, {ActantRole.SUBJECT: ivan}, uid="N_ENTER_IVAN")
    _ground(core, t_sit, {ActantRole.SUBJECT: maria}, uid="N_SIT_MARIA")

    var = BoundVar(0, VariableSort.ENTITY)
    enter = _pattern(core, t_enter, {ActantRole.SUBJECT: var}, uid="N_ENTER_VAR")
    sit = _pattern(core, t_sit, {ActantRole.SUBJECT: var}, uid="N_SIT_VAR")
    both = core.add_function(Domain.C, "AND", (enter, sit), uid="G_ENTER_AND_SIT")
    exists = core.add_function(Domain.C, "EXISTS", (var, core.ref(both.uid)), uid="G_EXISTS_BOTH")

    outcome = _solve(engine, core.ref(exists.uid))
    assert outcome.status is LogicalStatus.UNKNOWN

    _ground(core, t_sit, {ActantRole.SUBJECT: ivan}, uid="N_SIT_IVAN")
    outcome = _solve(engine, core.ref(exists.uid))
    assert outcome.status is LogicalStatus.PROVED
    assert {ref.uid for ref in outcome.premise_refs} >= {"N_ENTER_IVAN", "N_SIT_IVAN"}


def test_nested_quantifier_shadows_same_local_id() -> None:
    core, _context, _experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_sit = _template(core, "SIT", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    _ground(core, t_sit, {ActantRole.SUBJECT: maria}, uid="N_SIT_MARIA")

    outer = BoundVar(0, VariableSort.ENTITY)
    inner = BoundVar(0, VariableSort.ENTITY)
    human = _pattern(core, t_human, {ActantRole.SUBJECT: outer}, uid="N_HUMAN_VAR")
    sit = _pattern(core, t_sit, {ActantRole.SUBJECT: inner}, uid="N_SIT_VAR")
    inner_exists = core.add_function(Domain.C, "EXISTS", (inner, sit), uid="G_INNER_EXISTS")
    body = core.add_function(Domain.C, "AND", (human, core.ref(inner_exists.uid)), uid="G_OUTER_BODY")
    outer_exists = core.add_function(Domain.C, "EXISTS", (outer, core.ref(body.uid)), uid="G_OUTER_EXISTS")

    outcome = _solve(engine, core.ref(outer_exists.uid))
    assert outcome.status is LogicalStatus.PROVED
    assert {ref.uid for ref in outcome.premise_refs} >= {"N_HUMAN_IVAN", "N_SIT_MARIA"}


def test_forall_rule_instantiates_ground_goal_then_validates_antecedent_forward() -> None:
    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(
        core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False
    )

    var = BoundVar(0, VariableSort.ENTITY)
    human_pattern = _pattern(core, t_human, {ActantRole.SUBJECT: var}, uid="N_HUMAN_VAR")
    mortal_pattern = _pattern(core, t_mortal, {ActantRole.SUBJECT: var}, uid="N_MORTAL_VAR")
    rule = core.add_function(
        Domain.C, "IMPLIES", (human_pattern, mortal_pattern), uid="G_HUMAN_IMPLIES_MORTAL"
    )
    forall = core.add_function(
        Domain.C, "FORALL", (var, core.ref(rule.uid)), uid="G_FORALL_HUMAN_MORTAL"
    )
    _assert_expression(experience, context, core.ref(forall.uid))

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert outcome.proof_support[0].rule_id == "FORALL_IMPLIES_MP"
    assert "N_HUMAN_IVAN" in {ref.uid for ref in outcome.premise_refs}
    assert "G_FORALL_HUMAN_MORTAL" in {ref.uid for ref in outcome.premise_refs}
    assert outcome.bindings is not None
    assert dict(outcome.bindings.items())[0] == ivan


def test_unasserted_universal_container_cannot_fire_as_rule() -> None:
    core, _context, _experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False)

    var = BoundVar(0, VariableSort.ENTITY)
    p = _pattern(core, t_human, {ActantRole.SUBJECT: var}, uid="N_HUMAN_VAR")
    q = _pattern(core, t_mortal, {ActantRole.SUBJECT: var}, uid="N_MORTAL_VAR")
    rule = core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_RULE")
    core.add_function(Domain.C, "FORALL", (var, core.ref(rule.uid)), uid="G_FORALL")

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.UNKNOWN


def test_nested_forall_two_variables_preserves_binding_identity() -> None:
    core, context, experience, engine = _runtime()
    roles = (ActantRole.SUBJECT, ActantRole.OBJECT)
    t_friend = _template(core, "FRIEND", roles)
    t_knows = _template(core, "KNOWS", roles)
    ivan = _entity(core, "M_IVAN", "Иван")
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_friend, {ActantRole.SUBJECT: ivan, ActantRole.OBJECT: maria}, uid="N_FRIEND")
    target = _ground(
        core,
        t_knows,
        {ActantRole.SUBJECT: ivan, ActantRole.OBJECT: maria},
        uid="N_KNOWS",
        asserted=False,
    )

    x = BoundVar(0, VariableSort.ENTITY)
    y = BoundVar(1, VariableSort.ENTITY)
    p = _pattern(core, t_friend, {ActantRole.SUBJECT: x, ActantRole.OBJECT: y}, uid="N_FRIEND_VAR")
    q = _pattern(core, t_knows, {ActantRole.SUBJECT: x, ActantRole.OBJECT: y}, uid="N_KNOWS_VAR")
    implication = core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_RULE")
    inner = core.add_function(Domain.C, "FORALL", (y, core.ref(implication.uid)), uid="G_FORALL_Y")
    outer = core.add_function(Domain.C, "FORALL", (x, core.ref(inner.uid)), uid="G_FORALL_X")
    _assert_expression(experience, context, core.ref(outer.uid))

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.bindings is not None
    bindings = dict(outcome.bindings.items())
    assert bindings[0] == ivan
    assert bindings[1] == maria


def test_forall_is_not_proved_by_enumerating_known_instances() -> None:
    core, _context, _experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    _ground(core, t_human, {ActantRole.SUBJECT: maria}, uid="N_HUMAN_MARIA")

    x = BoundVar(0, VariableSort.ENTITY)
    body = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    universal = core.add_function(Domain.C, "FORALL", (x, body), uid="G_FORALL_HUMAN")

    outcome = _solve(engine, core.ref(universal.uid))
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.SEARCH_EXHAUSTED
    assert "Open-world FORALL" in outcome.diagnostics[0]


def test_boundvar_hypernode_roundtrips_without_becoming_an_ah_uid(tmp_path: Path) -> None:
    core, _context, _experience, _engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    x = BoundVar(3, VariableSort.ENTITY)
    pattern = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    universal = core.add_function(Domain.C, "FORALL", (x, pattern), uid="G_FORALL_HUMAN")

    path = tmp_path / "ah.json"
    persistence = JsonPersistence(path, PersistenceSettings())
    persistence.save(core)
    loaded = persistence.load().core

    node = loaded.store.get_hypernode("N_HUMAN_VAR")
    assert node.actants[ActantRole.SUBJECT] == x
    assert "3" not in loaded.store.all_uids()
    assert loaded.store.get_element_any_domain("G_FORALL_HUMAN").operands[0] == x


def test_ground_factual_hypernode_rejects_boundvar_actant() -> None:
    core, _context, _experience, _engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    x = BoundVar(0, VariableSort.ENTITY)
    try:
        core.add_hypernode(
            Domain.C,
            t_human,
            {ActantRole.SUBJECT: x},
            0.5,
            uid="N_BAD",
        )
    except ValueError as exc:
        assert "QUANTIFIED formula-pattern" in str(exc)
    else:
        raise AssertionError("BoundVar must not be allowed in an ordinary factual N")


def test_quantified_derived_n_persists_proof_support_and_loses_it_after_premise_refutation() -> None:
    from ah.config import IntegrationSettings
    from ah.inference import InferenceMaterializer
    from ah.integration import SemanticCorrectionService

    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    human = _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(
        core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False
    )

    x = BoundVar(0, VariableSort.ENTITY)
    p = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    q = _pattern(core, t_mortal, {ActantRole.SUBJECT: x}, uid="N_MORTAL_VAR")
    implication = core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_RULE")
    universal = core.add_function(Domain.C, "FORALL", (x, core.ref(implication.uid)), uid="G_FORALL")
    _assert_expression(experience, context, core.ref(universal.uid))

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    InferenceMaterializer(core, IntegrationSettings()).materialize(outcome)
    supports = core.resolve_supports(target)
    assert len(supports) == 1
    assert supports[0].rule_id == "FORALL_IMPLIES_MP"
    assert human in supports[0].premise_refs

    correction = SemanticCorrectionService(core).refute(human)
    assert target in correction.unsupported_conclusions
    assert core.resolve_supports(target) == ()
    assert _solve(engine, target).status is LogicalStatus.UNKNOWN


def test_nested_exists_can_supply_extra_variable_in_universal_antecedent() -> None:
    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_friend = _template(core, "FRIEND", (ActantRole.SUBJECT, ActantRole.OBJECT))
    t_social = _template(core, "SOCIAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    maria = _entity(core, "M_MARIA", "Мария")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    _ground(
        core,
        t_friend,
        {ActantRole.SUBJECT: ivan, ActantRole.OBJECT: maria},
        uid="N_FRIEND_IVAN_MARIA",
    )
    target = _ground(
        core, t_social, {ActantRole.SUBJECT: ivan}, uid="N_SOCIAL_IVAN", asserted=False
    )

    x = BoundVar(0, VariableSort.ENTITY)
    y = BoundVar(1, VariableSort.ENTITY)
    human = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    friend = _pattern(
        core,
        t_friend,
        {ActantRole.SUBJECT: x, ActantRole.OBJECT: y},
        uid="N_FRIEND_VAR",
    )
    exists_friend = core.add_function(
        Domain.C, "EXISTS", (y, friend), uid="G_EXISTS_FRIEND"
    )
    antecedent = core.add_function(
        Domain.C, "AND", (human, core.ref(exists_friend.uid)), uid="G_ANTECEDENT"
    )
    social = _pattern(core, t_social, {ActantRole.SUBJECT: x}, uid="N_SOCIAL_VAR")
    implication = core.add_function(
        Domain.C,
        "IMPLIES",
        (core.ref(antecedent.uid), social),
        uid="G_RULE",
    )
    universal = core.add_function(
        Domain.C, "FORALL", (x, core.ref(implication.uid)), uid="G_FORALL"
    )
    _assert_expression(experience, context, core.ref(universal.uid))

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    assert {ref.uid for ref in outcome.premise_refs} >= {
        "N_HUMAN_IVAN",
        "N_FRIEND_IVAN_MARIA",
        "G_FORALL",
    }


def test_quantified_proof_moves_focus_through_ignition_and_boundvar_has_no_runtime_state() -> None:
    from dataclasses import replace

    from ah.config import IgnitionSettings, PacemakerSettings, WorkspaceSettings
    from ah.ignition import IgnitionEngine
    from ah.inference import IgnitionInferenceAttention

    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(
        core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False
    )
    x = BoundVar(0, VariableSort.ENTITY)
    p = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    q = _pattern(core, t_mortal, {ActantRole.SUBJECT: x}, uid="N_MORTAL_VAR")
    implication = core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_RULE")
    universal = core.add_function(Domain.C, "FORALL", (x, core.ref(implication.uid)), uid="G_FORALL")
    _assert_expression(experience, context, core.ref(universal.uid))

    ignition = IgnitionEngine(
        core,
        replace(IgnitionSettings(), pacemaker=PacemakerSettings(enabled=False)),
        WorkspaceSettings(threshold=0.35),
    )
    attention = IgnitionInferenceAttention(ignition)
    outcome = engine.solve(
        InferenceQuery(GoalSpec(FormulaGoal(target))),
        attention=attention,
    )
    assert outcome.status is LogicalStatus.PROVED
    focused = [event.ref.uid for event in attention.events]
    assert "G_FORALL" in focused
    assert "N_HUMAN_IVAN" in focused
    assert "N_HUMAN_VAR" in focused
    assert "G_RULE" in focused
    assert "N_MORTAL_IVAN" in focused
    # A BoundVar has no UID/runtime slot and is never an ignition endpoint.
    assert all(uid != "$0" for uid in core.store.all_uids())


def test_quantified_search_cost_depends_on_relevant_template_not_unrelated_graph_noise() -> None:
    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(
        core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False
    )

    # Large unrelated noise: separate templates mean the quantified matcher must
    # not walk these nodes while solving a HUMAN/MORTAL rule.
    for index in range(500):
        t_noise = _template(core, f"NOISE_{index}", (ActantRole.SUBJECT,))
        entity = _entity(core, f"M_NOISE_{index}", f"Шум {index}")
        _ground(core, t_noise, {ActantRole.SUBJECT: entity}, uid=f"N_NOISE_{index}")

    x = BoundVar(0, VariableSort.ENTITY)
    p = _pattern(core, t_human, {ActantRole.SUBJECT: x}, uid="N_HUMAN_VAR")
    q = _pattern(core, t_mortal, {ActantRole.SUBJECT: x}, uid="N_MORTAL_VAR")
    implication = core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_RULE")
    universal = core.add_function(Domain.C, "FORALL", (x, core.ref(implication.uid)), uid="G_FORALL")
    _assert_expression(experience, context, core.ref(universal.uid))

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.expanded_states < 20


def test_quantifier_nesting_has_no_fixed_eight_level_semantic_cap() -> None:
    core, context, experience, engine = _runtime()
    t_human = _template(core, "HUMAN", (ActantRole.SUBJECT,))
    t_mortal = _template(core, "MORTAL", (ActantRole.SUBJECT,))
    ivan = _entity(core, "M_IVAN", "Иван")
    _ground(core, t_human, {ActantRole.SUBJECT: ivan}, uid="N_HUMAN_IVAN")
    target = _ground(
        core, t_mortal, {ActantRole.SUBJECT: ivan}, uid="N_MORTAL_IVAN", asserted=False
    )

    variables = tuple(BoundVar(index, VariableSort.ENTITY) for index in range(9))
    p = _pattern(core, t_human, {ActantRole.SUBJECT: variables[0]}, uid="N_HUMAN_VAR")
    q = _pattern(core, t_mortal, {ActantRole.SUBJECT: variables[0]}, uid="N_MORTAL_VAR")
    body_ref = core.ref(
        core.add_function(Domain.C, "IMPLIES", (p, q), uid="G_DEEP_RULE").uid
    )
    # Nine nested FORALL scopes deliberately exceed the old implementation-local
    # cap of eight. Unused variables are still legitimate universal binders.
    for index, variable in reversed(tuple(enumerate(variables))):
        body_ref = core.ref(
            core.add_function(
                Domain.C, "FORALL", (variable, body_ref), uid=f"G_FORALL_{index}"
            ).uid
        )
    _assert_expression(experience, context, body_ref)

    outcome = _solve(engine, target)
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[0].rule_id == "FORALL_IMPLIES_MP"
    assert dict(outcome.bindings.items())[0] == ivan
