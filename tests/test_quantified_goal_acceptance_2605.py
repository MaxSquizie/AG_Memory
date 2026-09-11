from __future__ import annotations

import json
from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import FormulaGoal, InferenceEngine, LogicalStatus, SemanticGoalCompiler
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import (
    ActantRole,
    BoundVar,
    Domain,
    FunctionSymbol,
    Hypernode,
    Property,
    Ref,
    SemanticEntity,
)
from ah.perception import (
    ActantCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifiedQueryBinding,
    QuantifiedQuerySpec,
    QueryCandidate,
    QueryMode,
    QueryQuantifierOperator,
    TemplateCandidate,
)


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "data" / "acceptance_quantified_goal" / "oracle.json"


def _env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _ensure_template(core: AHCore, name: str, roles: tuple[ActantRole, ...]) -> Ref:
    symbol = core.ensure_abstract_symbol(name)
    templates = [
        item
        for item in core.store.find_templates_by_predicate(symbol.uid)
        if tuple(item.roles) == roles
    ]
    template = templates[0] if templates else core.add_template(Domain.C, core.ref(symbol.uid), roles)
    return core.ref(template.uid)


def _entity(core: AHCore, name: str) -> Ref:
    existing = core.store.find_entities_by_name(name, Domain.C)
    if existing:
        return core.ref(existing[0].uid)
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _ground(core: AHCore, template: Ref, actants: dict[ActantRole, Ref]) -> Ref:
    item, _ = core.add_hypernode(Domain.C, template, actants, 0.5)
    return core.ref(item.uid)


def _query_from_case(core: AHCore, case: dict) -> QueryCandidate:
    bindings = []
    actants = []
    roles = []
    for raw in case["bindings"]:
        role = ActantRole[raw["role"]]
        roles.append(role)
        actants.append(
            ActantCandidate(
                role,
                mention=raw.get("restriction") or raw["handle"],
                normalized_hint=(raw.get("restriction") or raw["handle"]).casefold(),
                entity_ref=raw["handle"],
            )
        )
        bindings.append(
            QuantifiedQueryBinding(
                raw["handle"],
                int(raw["variable_id"]),
                QueryQuantifierOperator(raw["operator"]),
                restriction_lemma=raw.get("restriction"),
                negated=bool(raw.get("negated", False)),
            )
        )

    for role_name, name in (case.get("fixed_roles") or {}).items():
        role = ActantRole[role_name]
        roles.append(role)
        _entity(core, name)
        actants.append(ActantCandidate(role, mention=name, normalized_hint=name.casefold()))

    _ensure_template(core, case["predicate"], tuple(roles))
    for raw in case["bindings"]:
        restriction = raw.get("restriction")
        if restriction:
            _ensure_template(core, restriction, (ActantRole.SUBJECT,))

    return QueryCandidate(
        PredicateCandidate(
            case["predicate"],
            case["predicate"],
            template_candidate=TemplateCandidate(tuple(roles)),
        ),
        tuple(actants),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
        quantified=QuantifiedQuerySpec(
            tuple(bindings),
            body_negated=bool(case.get("body_negated", False)),
        ),
    )


def _name(core: AHCore, ref: Ref) -> str:
    entity = core.store.get_element_any_domain(ref.uid)
    assert isinstance(entity, SemanticEntity)
    value = entity.properties.get("name")
    return str(value.value if value is not None else ref.uid)


def _render(core: AHCore, operand) -> str:
    if isinstance(operand, BoundVar):
        return f"${operand.local_id}"
    if not isinstance(operand, Ref):
        return repr(operand)
    obj = core.store.get_element_any_domain(operand.uid)
    if isinstance(obj, FunctionSymbol):
        return f"{obj.function_id}(" + ",".join(_render(core, item) for item in obj.operands) + ")"
    if isinstance(obj, Hypernode):
        template = core.store.get_template(obj.template.uid)
        symbol = core.store.get_symbol(template.predicate.uid)
        predicate = sorted(symbol.forms, key=lambda x: (len(x), x.casefold()))[0]
        args = [_render(core, obj.actants[role]) for role in template.roles]
        return f"{predicate}(" + ",".join(args) + ")"
    return _name(core, operand)


def _seed(case: dict, core: AHCore, query: QueryCandidate) -> None:
    mode = case["seed"]
    if mode in {"none", "assert_root"}:
        return

    bound = {item.entity_ref: item for item in query.quantified.bindings}
    first = query.quantified.bindings[0]
    witness_a = _entity(core, "WitnessA")
    witness_b = _entity(core, "WitnessB")
    predicate_template = _ensure_template(
        core,
        case["predicate"],
        tuple(item.role for item in query.actants),
    )

    body_actants = {}
    for actant in query.actants:
        binding = bound.get(actant.entity_ref or "")
        if binding is not None:
            body_actants[actant.role] = witness_a if mode != "split_witness" else witness_b
        else:
            found = core.store.find_entities_by_name(actant.lookup_text or "", Domain.C)
            assert found
            body_actants[actant.role] = core.ref(found[0].uid)
    _ground(core, predicate_template, body_actants)

    restriction = first.restriction_lemma
    if restriction:
        restriction_template = _ensure_template(
            core, restriction, (ActantRole.SUBJECT,)
        )
        _ground(
            core,
            restriction_template,
            {ActantRole.SUBJECT: witness_a},
        )


def _assert_root(core: AHCore, context: InteractionContext, root: Ref) -> None:
    result = ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="explicit quantified premise",
        speaker_ref=context.user_ref,
        semantic_refs=(root,),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )
    context.last_experience_ref = result.event_ref


CASES = json.loads(ORACLE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda item: item["id"])
def test_quantified_goal_acceptance(case: dict) -> None:
    core, context, service, engine = _env()
    query = _query_from_case(core, case)
    _seed(case, core, query)

    perception = PerceptionResult(case["text"], queries=(query,))
    commit = service.integrate_external(perception, context)
    assert len(commit.quantified_queries) == 1
    integrated = commit.quantified_queries[0]

    assert _render(core, integrated.ref) == case["expected_formula"]

    built = SemanticGoalCompiler(core).build(commit, context, perception)
    assert len(built) == 1
    assert built[0].goal is not None
    assert isinstance(built[0].goal.goal.target, FormulaGoal)
    assert built[0].goal.goal.target.expression == integrated.ref
    assert built[0].diagnostics == ("semantic:quantified_formula_goal",)

    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert event.actants.get(ActantRole.OBJECT) != integrated.ref

    if case["seed"] == "assert_root":
        _assert_root(core, context, integrated.ref)

    outcome = engine.solve(built[0].goal)
    assert outcome.status.value == case["expected_status"]


def test_quantified_goal_oracle_contract_is_complete() -> None:
    payload = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert payload["input_boundary"] == "QuantifiedQuerySpec"
    assert payload["case_count"] == len(payload["cases"]) == 12
    ids = [item["id"] for item in payload["cases"]]
    assert len(ids) == len(set(ids))
    formulas = {item["expected_formula"] for item in payload["cases"]}
    assert any(item.startswith("FORALL(") for item in formulas)
    assert any(item.startswith("EXISTS(") for item in formulas)
    assert any(item.startswith("NOT(EXISTS(") for item in formulas)
    assert any(item.startswith("NOT(FORALL(") for item in formulas)
    assert any("FORALL($0,IMPLIES(employee($0),NOT(" in item for item in formulas)
    assert any("EXISTS($1" in item for item in formulas)
