from __future__ import annotations

from ah.config import InferenceSettings, IntegrationSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import (
    InferenceEngine,
    InferenceMaterializer,
    InferenceSchemaRegistry,
    LogicalStatus,
    RelationGoal,
)
from ah.model import BoundVar, Domain, Ref, RefKind, VariableSort


def _entity(core: AHCore, domain: Domain = Domain.C) -> Ref:
    return core.ref(core.add_entity(domain).uid)


def test_default_relation_schema_is_explicit_and_conservative() -> None:
    registry = InferenceSchemaRegistry.default()
    assert registry.is_transitive("IS-A")
    assert registry.is_transitive("FOLLOW")
    assert not registry.is_transitive("CAUSE")
    assert not registry.is_transitive("UNREGISTERED")
    assert registry.has_handler("CAUSE", "CAUSE_MP")


def test_binding_environment_scopes_and_sorts() -> None:
    from ah.inference import BindingEnvironment

    outer = BindingEnvironment()
    entity = Ref("m1", RefKind.M)
    proposition = Ref("n1", RefKind.N)
    outer.bind(BoundVar(0, VariableSort.ENTITY), entity)

    child = outer.child()
    assert child.resolve(BoundVar(0, VariableSort.ENTITY)) == entity
    child.bind(BoundVar(0, VariableSort.PROPOSITION), proposition)
    assert child.resolve(BoundVar(0, VariableSort.PROPOSITION)) == proposition
    assert outer.resolve(BoundVar(0, VariableSort.ENTITY)) == entity


def test_transitive_materialization_registers_proof_support(tmp_path) -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    a, b, c = _entity(core), _entity(core), _entity(core)
    l1 = core.add_link("IS-A", a, b, 0.4)
    l2 = core.add_link("IS-A", b, c, 0.4)

    engine = InferenceEngine(core, InferenceSettings(max_depth=6, max_expanded_states=100))
    outcome = engine.solve(RelationGoal("IS-A", a, c))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support
    assert outcome.proof_support[0].rule_id == "TRANSITIVITY"
    assert {ref.uid for ref in outcome.proof_support[0].premise_refs} >= {l1.uid, l2.uid}

    materializer = InferenceMaterializer(core, IntegrationSettings())
    result = materializer.materialize(outcome)
    assert result.ref is not None
    supports = core.resolve_supports(result.ref)
    assert len(supports) == 1
    assert supports[0].rule_id == "TRANSITIVITY"

    path = tmp_path / "memory.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    loaded_supports = loaded.resolve_supports(loaded.ref(result.ref.uid))
    assert loaded_supports == supports


def test_bound_var_function_operand_roundtrips(tmp_path) -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    domain = Domain.C
    var = BoundVar(0, VariableSort.ENTITY)
    g = core.add_function(domain, "FORALL", (var,))

    path = tmp_path / "memory.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(enabled=True, load_on_start=False, save_runtime_state=False),
    )
    persistence.save(core)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    restored = loaded.store.get_element_any_domain(g.uid)
    assert restored.operands == (var,)
