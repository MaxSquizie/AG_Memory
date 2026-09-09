from __future__ import annotations

from dataclasses import replace

import pytest

from ah.association import (
    AssociationBudget,
    AssociationCoordinator,
    AssociationDomainPolicy,
    AssociationGoal,
    AssociationHopKind,
    AssociationSemantics,
    AssociationStatus,
)
from ah.config import IgnitionSettings, LifecycleSettings, PacemakerSettings, PlasticitySettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import GoalMode, GoalSpec
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property, RefKind


def _entity(core: AHCore, name: str, domain: Domain = Domain.C):
    obj = core.add_entity(domain, properties={"name": Property("name", name, "str")})
    return core.ref(obj.uid)


def _engine(core: AHCore) -> IgnitionEngine:
    settings = replace(
        IgnitionSettings(),
        plasticity=PlasticitySettings(enabled=False),
        pacemaker=PacemakerSettings(enabled=False),
    )
    return IgnitionEngine(
        core,
        settings,
        WorkspaceSettings(threshold=0.10),
        LifecycleSettings(gc_enabled=False),
    )


def _have_fixture():
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _entity(core, "ворона")
    table = _entity(core, "стол")
    legs = _entity(core, "ножки")
    have_s = core.ensure_abstract_symbol("иметь")
    have_t = core.add_template(
        Domain.C,
        core.ref(have_s.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    left_n, _ = core.add_hypernode(
        Domain.C,
        core.ref(have_t.uid),
        {ActantRole.SUBJECT: crow, ActantRole.OBJECT: legs},
        0.8,
    )
    right_n, _ = core.add_hypernode(
        Domain.C,
        core.ref(have_t.uid),
        {ActantRole.SUBJECT: table, ActantRole.OBJECT: legs},
        0.8,
    )
    return core, crow, table, legs, core.ref(have_t.uid), core.ref(left_n.uid), core.ref(right_n.uid)


def test_association_is_intersection_not_entailment_and_finds_shared_representation() -> None:
    core, crow, table, legs, have_t, left_n, right_n = _have_fixture()
    ignition = _engine(core)
    coordinator = AssociationCoordinator(core, ignition)

    outcome = coordinator.solve(
        GoalSpec(AssociationGoal(crow, table), mode=GoalMode.ASSOCIATION),
        budget=AssociationBudget(max_depth=5, max_expanded_states=200, max_ticks=12),
    )

    assert outcome.status is AssociationStatus.FOUND
    assert outcome.common_ref is not None
    common_uids = {ref.uid for ref in outcome.common_candidates}
    # Architecture v4 explicitly allows both a semantic bridge and a generic T hub.
    assert legs.uid in common_uids
    assert have_t.uid in common_uids
    assert outcome.left_path is not None and outcome.right_path is not None
    assert outcome.left_path.refs[0] == crow
    assert outcome.right_path.refs[0] == table
    assert outcome.left_path.common == outcome.right_path.common == outcome.common_ref
    # Search provenance is activation/query ancestry, not a ProofSupport/LogicalStatus.
    assert any(h.kind in {AssociationHopKind.MEMORY_QUERY, AssociationHopKind.PROPAGATION}
               for h in outcome.left_path.hops)


def test_association_can_converge_on_first_order_S() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core, "биологическая ножка")
    right = _entity(core, "ножка мебели")
    lexical = core.add_abstract_symbol({"ножка", "ножки"})
    lexical_ref = core.ref(lexical.uid)
    core.add_link("LEXICAL_ASSOC", left, lexical_ref, 0.9)
    core.add_link("LEXICAL_ASSOC", right, lexical_ref, 0.9)

    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=50, max_ticks=6),
    )

    assert outcome.status is AssociationStatus.FOUND
    assert lexical_ref.uid in {ref.uid for ref in outcome.common_candidates}
    assert outcome.common_ref is not None
    assert outcome.common_ref.kind is RefKind.S


def test_generic_template_hub_is_not_filtered_out() -> None:
    core, crow, table, _legs, have_t, _left_n, _right_n = _have_fixture()
    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(crow, table),
        budget=AssociationBudget(max_depth=3, max_expanded_states=100, max_ticks=8),
    )
    assert have_t.uid in {ref.uid for ref in outcome.common_candidates}


def test_warm_workspace_node_is_not_false_convergence_without_front_ancestry() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core, "A")
    right = _entity(core, "B")
    noise = _entity(core, "warm noise")
    ignition = _engine(core)
    ignition.seed(noise, 0.9, reason=SeedReason.SENSORY_SYMBOL)
    ignition.tick(include_pacemaker=False)
    assert noise.uid in {ref.uid for ref in ignition.workspace_refs()}

    outcome = AssociationCoordinator(core, ignition).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=20, max_ticks=5),
    )

    assert outcome.status in {AssociationStatus.NOT_FOUND, AssociationStatus.DEPTH_EXHAUSTED}
    assert outcome.common_ref is None
    assert noise.uid not in {ref.uid for ref in outcome.left_activated}
    assert noise.uid not in {ref.uid for ref in outcome.right_activated}


def _h_bridge(policy: AssociationDomainPolicy):
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core, "left", Domain.C)
    right = _entity(core, "right", Domain.P)
    episode = _entity(core, "episode bridge", Domain.H)
    core.add_link("ASSOC", left, episode, 1.0)
    core.add_link("ASSOC", right, episode, 1.0)
    return AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=30, max_ticks=5),
        domain_policy=policy,
    ), episode


def test_h_domain_policy_is_runtime_option_not_canonical_decision() -> None:
    all_outcome, episode = _h_bridge(AssociationDomainPolicy.ALL)
    assert all_outcome.status is AssociationStatus.FOUND
    assert episode.uid in {ref.uid for ref in all_outcome.common_candidates}

    semantic_outcome, episode2 = _h_bridge(AssociationDomainPolicy.EXCLUDE_H)
    assert semantic_outcome.status in {AssociationStatus.NOT_FOUND, AssociationStatus.DEPTH_EXHAUSTED}
    assert episode2.uid not in {ref.uid for ref in semantic_outcome.left_activated}
    assert episode2.uid not in {ref.uid for ref in semantic_outcome.right_activated}


def test_reverse_directed_L_is_activation_query_not_reverse_logical_fact() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    cause = _entity(core, "cause")
    effect = _entity(core, "effect")
    other = _entity(core, "other")
    link = core.add_link("CAUSE", cause, effect, 0.8)
    core.add_link("ASSOC", other, cause, 0.8)

    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(effect, other),
        budget=AssociationBudget(max_depth=3, max_expanded_states=80, max_ticks=8),
    )

    assert outcome.status is AssociationStatus.FOUND
    assert cause.uid in {ref.uid for ref in outcome.common_candidates}
    assert core.store.find_link("CAUSE", effect.uid, cause.uid) is None
    assert core.store.find_link("CAUSE", cause.uid, effect.uid).uid == link.uid
    assert outcome.left_path is not None
    assert any(h.relation == "L_BACKWARD:CAUSE" for h in outcome.left_path.hops)


def test_association_search_does_not_create_canonical_nodes_links_or_supports() -> None:
    core, crow, table, _legs, _have_t, _left_n, _right_n = _have_fixture()
    before_uids = set(core.store.all_uids())
    before_supports = core.supports.items()
    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(crow, table),
        budget=AssociationBudget(max_depth=4, max_expanded_states=100, max_ticks=10),
    )
    assert outcome.status is AssociationStatus.FOUND
    assert set(core.store.all_uids()) == before_uids
    assert core.supports.items() == before_supports


def test_tight_budget_stops_without_unrestricted_expansion() -> None:
    core, crow, table, _legs, _have_t, _left_n, _right_n = _have_fixture()
    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(crow, table),
        budget=AssociationBudget(max_depth=6, max_expanded_states=2, max_ticks=10),
    )
    assert outcome.status is AssociationStatus.BUDGET_EXHAUSTED
    assert outcome.expanded_states == 2


def test_wrong_goalspec_mode_is_rejected() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core, "left")
    right = _entity(core, "right")
    coordinator = AssociationCoordinator(core, _engine(core))
    with pytest.raises(ValueError, match="mode=ASSOCIATION"):
        coordinator.solve(GoalSpec(AssociationGoal(left, right), mode=GoalMode.PROOF))


def test_association_needs_no_broad_global_enumerator(monkeypatch) -> None:
    core, crow, table, _legs, _have_t, _left_n, _right_n = _have_fixture()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unrestricted global read is forbidden in association search")

    ignition = _engine(core)
    monkeypatch.setattr(core.store, "all_elements", forbidden)
    monkeypatch.setattr(core.store, "all_uids", forbidden)
    monkeypatch.setattr(core.store, "elements", forbidden)
    monkeypatch.setattr(core.store, "links", forbidden)

    outcome = AssociationCoordinator(core, ignition).solve(
        AssociationGoal(crow, table),
        budget=AssociationBudget(max_depth=4, max_expanded_states=100, max_ticks=10),
    )
    assert outcome.status is AssociationStatus.FOUND


def test_identical_origins_are_immediate_association_without_extra_tick() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    same = _entity(core, "same")
    ignition = _engine(core)
    before = ignition.tick_index
    outcome = AssociationCoordinator(core, ignition).solve(AssociationGoal(same, same))
    assert outcome.status is AssociationStatus.FOUND
    assert outcome.common_ref == same
    assert outcome.left_path is not None and outcome.left_path.depth == 0
    assert outcome.right_path is not None and outcome.right_path.depth == 0
    assert ignition.tick_index == before


def test_group_k_can_be_the_association_common_node() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core, "member-left")
    right = _entity(core, "member-right")
    group = core.add_group(Domain.C, (left, right), meta={"TYPE": "TEST_GROUP"})
    group_ref = core.ref(group.uid)

    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=30, max_ticks=5),
    )
    assert outcome.status is AssociationStatus.FOUND
    assert group_ref.uid in {ref.uid for ref in outcome.common_candidates}
    assert outcome.common_ref == group_ref


def test_function_g_can_be_the_association_common_node() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    pred = core.ensure_abstract_symbol("p")
    template = core.add_template(Domain.C, core.ref(pred.uid), ())
    left_n, _ = core.add_hypernode(Domain.C, core.ref(template.uid), {}, 0.7)
    right_n, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {},
        0.7,
        meta={"semantic_scope": "DISJUNCTIVE"},
    )
    left = core.ref(left_n.uid)
    right = core.ref(right_n.uid)
    conjunction = core.add_function(Domain.C, "AND", (left, right))
    g_ref = core.ref(conjunction.uid)

    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=30, max_ticks=5),
    )
    assert outcome.status is AssociationStatus.FOUND
    assert g_ref.uid in {ref.uid for ref in outcome.common_candidates}
    assert outcome.common_ref == g_ref


def test_association_outcome_distinguishes_semantic_and_episodic_paths() -> None:
    semantic_core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(semantic_core, "semantic-left")
    right = _entity(semantic_core, "semantic-right")
    bridge = _entity(semantic_core, "semantic-bridge")
    semantic_core.add_link("ASSOC", left, bridge, 1.0)
    semantic_core.add_link("ASSOC", right, bridge, 1.0)
    semantic = AssociationCoordinator(semantic_core, _engine(semantic_core)).solve(
        AssociationGoal(left, right),
        budget=AssociationBudget(max_depth=2, max_expanded_states=30, max_ticks=5),
    )
    assert semantic.status is AssociationStatus.FOUND
    assert semantic.semantics is AssociationSemantics.SEMANTIC
    assert semantic.minimal_fact_count == 0

    episodic, _episode = _h_bridge(AssociationDomainPolicy.ALL)
    assert episodic.status is AssociationStatus.FOUND
    assert episodic.semantics is AssociationSemantics.EPISODIC
    assert episodic.minimal_fact_count == 0


def test_association_reports_minimal_number_of_distinct_n_facts_in_discovered_routes() -> None:
    core, crow, table, _legs, _have_t, left_n, right_n = _have_fixture()
    outcome = AssociationCoordinator(core, _engine(core)).solve(
        AssociationGoal(crow, table),
        budget=AssociationBudget(max_depth=5, max_expanded_states=200, max_ticks=12),
    )
    assert outcome.status is AssociationStatus.FOUND
    assert outcome.semantics is AssociationSemantics.SEMANTIC
    assert outcome.minimal_fact_count == 2
    assert left_n.uid != right_n.uid
