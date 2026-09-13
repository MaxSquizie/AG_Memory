from __future__ import annotations

import json
from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import FormulaGoal, InferenceEngine, LogicalStatus
from ah.integration import CandidateValidationError, IntegrationConfig, IntegrationService
from ah.integration.candidate_validator import CandidateValidator
from ah.model import ActantRole, Domain, FunctionSymbol, Group, Hypernode, Property, Ref
from ah.perception import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
    TemplateCandidate,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_semantic_composition" / "a4_cases.txt"
ORACLE = ROOT / "data" / "acceptance_semantic_composition" / "a4_oracle.json"


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(
        user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid)
    )
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    return core, context, service


def _entity(core: AHCore, name: str) -> Ref:
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _predicate(name: str = "transfer") -> PredicateCandidate:
    return PredicateCandidate(
        name,
        name,
        template_candidate=TemplateCandidate(
            (ActantRole.SUBJECT, ActantRole.OBJECT)
        ),
    )


def _variant(
    subject: str,
    obj: str,
    *,
    status: AssertionStatus = AssertionStatus.ASSERTED,
    local_id: str = "A1",
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        _predicate(),
        (
            ActantCandidate(ActantRole.SUBJECT, mention=subject),
            ActantCandidate(ActantRole.OBJECT, mention=obj),
        ),
        status=status,
    )


def _ambiguous(
    variants: tuple[AssertionCandidate, ...],
    *,
    status: AssertionStatus = AssertionStatus.ASSERTED,
    local_id: str = "A1",
) -> AssertionCandidate:
    return AssertionCandidate(
        local_id,
        _predicate(),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="кто-то"),
            ActantCandidate(ActantRole.OBJECT, mention="что-то"),
        ),
        alternatives=variants,
        status=status,
    )


def _pair(core: AHCore, ref: Ref) -> tuple[str, str]:
    node = core.store.get_hypernode(ref.uid)

    def name(role: ActantRole) -> str:
        value = node.actants[role]
        entity = core.store.get_element_any_domain(value.uid)
        return str(entity.properties["name"].value)

    return name(ActantRole.SUBJECT), name(ActantRole.OBJECT)


def _state(core: AHCore) -> tuple[tuple[str, str], ...]:
    rows = [
        (domain.value, repr(item))
        for domain in Domain
        for item in core.store.elements(domain)
    ]
    rows.extend(("L", repr(item)) for item in core.store.links())
    return tuple(sorted(rows))


def test_a4_acceptance_oracle_contract() -> None:
    cases = tuple(line for line in CASES.read_text(encoding="utf-8").splitlines() if line)
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["roadmap_step"] == "A4_CORRELATED_NESTED_AMBIGUITY"
    assert oracle["case_count"] == len(cases) == len(oracle["cases"]) == 18
    assert tuple(item["text"] for item in oracle["cases"]) == cases
    assert {item["expected"] for item in oracle["cases"]} >= {
        "PRESERVE_PAIRS",
        "NESTED_GROUP",
        "NONFACTIVE",
        "AMBIGUOUS",
        "UNKNOWN",
        "COLLAPSE_SINGLE",
        "ATOMIC_REJECT",
    }


def test_nested_runtime_alternatives_flatten_to_correlated_leaves_read_only() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key", "map", "letter"):
        _entity(core, name)
    first = _variant("Anna", "book")
    second = _variant("Maria", "key")
    third = _variant("Anna", "map")
    nested = _ambiguous((first, second))
    root = _ambiguous((nested, third))

    CandidateValidator().validate(PerceptionResult("nested", assertions=(root,)))
    before = _state(core)
    plan = service.prepare_external_plan(
        PerceptionResult("nested", assertions=(root,)), context
    )
    assert _state(core) == before
    alternatives = plan.perception.assertions[0].alternatives
    assert len(alternatives) == 3
    assert {
        tuple(actant.lookup_text for actant in item.actants)
        for item in alternatives
    } == {
        ("Anna", "book"),
        ("Maria", "key"),
        ("Anna", "map"),
    }


def test_correlated_role_variants_become_whole_proposition_options() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key"):
        _entity(core, name)
    assertion = _ambiguous(
        (_variant("Anna", "book"), _variant("Maria", "key"))
    )
    commit = service.integrate_external(
        PerceptionResult("correlated alternatives", assertions=(assertion,)),
        context,
    )

    assert commit.clarification_required
    assert len(commit.clarifications) == 1
    request = commit.clarifications[0]
    assert request.kind == "SEMANTIC_ALTERNATIVE"
    group = core.store.get_element_any_domain(request.ambiguous_ref.uid)
    assert isinstance(group, Group)
    assert group.meta["TYPE"] == "AMBIGUOUS_PROPOSITION"
    assert all(member.kind.value == "N" for member in group.members)
    assert {_pair(core, member) for member in group.members} == {
        ("Anna", "book"),
        ("Maria", "key"),
    }
    assert ("Anna", "key") not in {_pair(core, member) for member in group.members}
    assert ("Maria", "book") not in {_pair(core, member) for member in group.members}
    assert all(
        core.store.get_hypernode(member.uid).meta.get("semantic_scope")
        == "AMBIGUOUS_ALTERNATIVE"
        for member in group.members
    )
    assert all("transfer" in option.label for option in request.options)
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert event.actants[ActantRole.OBJECT] == request.ambiguous_ref


def test_semantic_alternative_resolution_asserts_only_selected_complete_reading() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key", "outsider"):
        _entity(core, name)
    assertion = _ambiguous(
        (_variant("Anna", "book"), _variant("Maria", "key"))
    )
    commit = service.integrate_external(
        PerceptionResult("correlated alternatives", assertions=(assertion,)),
        context,
    )
    request = commit.clarifications[0]
    selected = next(
        option.ref
        for option in request.options
        if _pair(core, option.ref) == ("Maria", "key")
    )
    unselected = next(member for member in request.options if member.ref != selected).ref

    outsider = core.store.find_entities_by_name("outsider", Domain.C)[0]
    before_invalid = _state(core)
    with pytest.raises(CandidateValidationError, match="not a member"):
        service.resolve_clarification(request.ambiguous_ref, core.ref(outsider.uid))
    assert _state(core) == before_invalid

    resolution = service.resolve_clarification(request.ambiguous_ref, selected)
    assert resolution.selected_ref == selected
    event = core.store.get_hypernode(commit.experience_ref.uid)
    assert event.actants[ActantRole.OBJECT] == selected
    chosen = core.store.get_hypernode(selected.uid)
    assert chosen.meta.get("semantic_scope") is None
    assert int(chosen.meta.get("occurrence_count", 0)) == 1
    other = core.store.get_hypernode(unselected.uid)
    assert other.meta.get("semantic_scope") == "AMBIGUOUS_ALTERNATIVE"
    group = core.store.get_element_any_domain(request.ambiguous_ref.uid)
    assert group.meta["resolved_to"] == selected.uid

    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    proved = engine.solve(FormulaGoal(selected))
    assert proved.status is LogicalStatus.PROVED
    assert proved.proof_support[-1].rule_id == "FACT_ASSERTED"
    assert engine.solve(FormulaGoal(unselected)).status is LogicalStatus.UNKNOWN


def test_correlated_alternative_nested_in_matrix_scope_remains_nonfactive() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key", "observer"):
        _entity(core, name)
    embedded = _ambiguous(
        (
            _variant("Anna", "book", status=AssertionStatus.EMBEDDED),
            _variant("Maria", "key", status=AssertionStatus.EMBEDDED),
        ),
        status=AssertionStatus.EMBEDDED,
    )
    parent = AssertionCandidate(
        "A2",
        PredicateCandidate(
            "believe",
            "believe",
            template_candidate=TemplateCandidate(
                (ActantRole.SUBJECT, ActantRole.OBJECT)
            ),
        ),
        (
            ActantCandidate(ActantRole.SUBJECT, mention="observer"),
            ActantCandidate(ActantRole.OBJECT, candidate_ref="A1"),
        ),
    )
    perception = PerceptionResult(
        "matrix ambiguity",
        assertions=(embedded, parent),
        act_dependencies=(
            ActDependencyCandidate("A2", "A1", ActDependencyKind.SUBORDINATE),
        ),
    )
    commit = service.integrate_external(perception, context)
    request = commit.clarifications[0]
    assert request.kind == "SEMANTIC_ALTERNATIVE"
    parent_ref = next(item.ref for item in commit.assertions if item.local_id == "A2")
    parent_node = core.store.get_hypernode(parent_ref.uid)
    assert parent_node.actants[ActantRole.OBJECT] == request.ambiguous_ref

    selected = request.options[0].ref
    service.resolve_clarification(request.ambiguous_ref, selected)
    parent_matches = tuple(
        item
        for item in core.store.hypernodes_for_actant(selected.uid)
        if item.template == parent_node.template
    )
    assert len(parent_matches) == 1
    assert parent_matches[0].actants[ActantRole.OBJECT] == selected
    selected_node = core.store.get_hypernode(selected.uid)
    assert selected_node.meta.get("semantic_scope") == "EMBEDDED"
    engine = InferenceEngine(core, InferenceSettings(max_depth=8, max_expanded_states=128))
    assert engine.solve(FormulaGoal(selected)).status is LogicalStatus.UNKNOWN


def test_ambiguity_inside_modal_formula_persists_and_resolves_in_place(tmp_path) -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key"):
        _entity(core, name)
    assertion = _ambiguous(
        (_variant("Anna", "book"), _variant("Maria", "key"))
    )
    modal_root = PropositionRootCandidate(
        "F1",
        PropositionExprCandidate(
            PropositionOperator.POSSIBLE,
            members=(PropositionExprCandidate.ref_expr("A1"),),
        ),
    )
    perception = PerceptionResult(
        "modal ambiguity",
        assertions=(assertion,),
        proposition_roots=(modal_root,),
    )
    commit = service.integrate_external(perception, context)
    request = commit.clarifications[0]
    formula_ref = commit.formulas[0].ref
    formula = core.store.get_element_any_domain(formula_ref.uid)
    assert isinstance(formula, FunctionSymbol)
    assert formula.operands == (request.ambiguous_ref,)
    context.pending_clarification_refs = [request.ambiguous_ref]

    path = tmp_path / "a4-memory.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(
            enabled=True,
            load_on_start=True,
            save_runtime_state=False,
        ),
    )
    persistence.save(core, context=context)
    loaded = persistence.load(uid_generator=SequentialUidGenerator())
    assert loaded.interaction_context is not None
    loaded_service = IntegrationService(
        loaded.core, IntegrationConfig(0.4, 0.3, 0.2)
    )
    loaded_request = loaded_service.clarification_request(
        loaded.interaction_context.pending_clarification_refs[0]
    )
    assert loaded_request.kind == "SEMANTIC_ALTERNATIVE"
    assert tuple(option.label for option in loaded_request.options) == tuple(
        option.label for option in request.options
    )

    selected = loaded_request.options[1].ref
    unselected = loaded_request.options[0].ref
    loaded_service.resolve_clarification(loaded_request.ambiguous_ref, selected)
    resolved_formula = loaded.core.store.get_element_any_domain(formula_ref.uid)
    assert isinstance(resolved_formula, FunctionSymbol)
    assert resolved_formula.operands == (selected,)
    selected_node = loaded.core.store.get_hypernode(selected.uid)
    assert selected_node.meta.get("semantic_scope") == "LOGICAL"
    engine = InferenceEngine(
        loaded.core, InferenceSettings(max_depth=8, max_expanded_states=128)
    )
    outcome = engine.solve(FormulaGoal(formula_ref))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[-1].rule_id == "POSSIBLE_ASSERTED"
    assert engine.solve(FormulaGoal(unselected)).status is LogicalStatus.UNKNOWN

    persistence.save(loaded.core, context=loaded.interaction_context)
    reloaded = persistence.load(uid_generator=SequentialUidGenerator())
    reloaded_formula = reloaded.core.store.get_element_any_domain(formula_ref.uid)
    assert isinstance(reloaded_formula, FunctionSymbol)
    assert reloaded_formula.operands == (reloaded.core.ref(selected.uid),)
    reloaded_group = reloaded.core.store.get_element_any_domain(
        loaded_request.ambiguous_ref.uid
    )
    assert reloaded_group.meta["resolved_to"] == selected.uid


def test_duplicate_correlated_readings_collapse_without_clarification() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "book"):
        _entity(core, name)
    assertion = _ambiguous(
        (_variant("Anna", "book"), _variant("Anna", "book"))
    )
    commit = service.integrate_external(
        PerceptionResult("duplicate alternatives", assertions=(assertion,)),
        context,
    )
    assert not commit.clarification_required
    assert commit.clarifications == ()
    assert commit.assertions[0].ref.kind.value == "N"
    node = core.store.get_hypernode(commit.assertions[0].ref.uid)
    assert node.meta.get("semantic_scope") is None
    assert int(node.meta.get("occurrence_count", 0)) == 1


def test_stale_semantic_option_is_rejected_atomically() -> None:
    core, context, service = _runtime()
    for name in ("Anna", "Maria", "book", "key"):
        _entity(core, name)
    assertion = _ambiguous(
        (_variant("Anna", "book"), _variant("Maria", "key"))
    )
    commit = service.integrate_external(
        PerceptionResult("stale option", assertions=(assertion,)), context
    )
    request = commit.clarifications[0]
    stale = request.options[1].ref
    core.store._remove_uid(stale.uid)
    before = _state(core)
    with pytest.raises(CandidateValidationError, match="not canonical"):
        service.resolve_clarification(request.ambiguous_ref, stale)
    assert _state(core) == before


def test_a4_corpus_sentences_are_not_production_rules() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for subtree in ("perception", "integration")
        for path in (ROOT / "src" / "ah" / subtree).rglob("*.py")
    ).casefold()
    for line in CASES.read_text(encoding="utf-8").splitlines():
        assert line.casefold() not in production
