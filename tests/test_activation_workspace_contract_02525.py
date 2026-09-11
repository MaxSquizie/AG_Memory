from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ah.config import (
    ActivationSettings,
    DecaySettings,
    IgnitionSettings,
    InferenceSettings,
    LifecycleSettings,
    PacemakerSettings,
    PlasticitySettings,
    SeedSettings,
    WorkspaceSettings,
    load_config,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import InferenceEngine, LogicalStatus, RelationGoal
from ah.integration import ActivationSeedRequest, SeedReason
from ah.model import Domain, Property


ROOT = Path(__file__).resolve().parents[1]


def _entity(core: AHCore, name: str):
    entity = core.add_entity(
        Domain.C,
        properties={"name": Property("name", name, "str")},
    )
    return core.ref(entity.uid)


def _settings(*, plasticity: PlasticitySettings | None = None) -> IgnitionSettings:
    return IgnitionSettings(
        activation=ActivationSettings(gain=1.0, epsilon=1e-9),
        decay=DecaySettings(alpha=0.0, midpoint_ticks=100.0, steepness=0.1),
        plasticity=plasticity or PlasticitySettings(),
        pacemaker=PacemakerSettings(enabled=False),
    )


def _engine(
    core: AHCore,
    *,
    settings: IgnitionSettings | None = None,
    threshold: float = 0.35,
) -> IgnitionEngine:
    return IgnitionEngine(
        core,
        settings or _settings(),
        WorkspaceSettings(threshold=threshold),
        LifecycleSettings(gc_enabled=False),
    )


def test_prompt_and_goal_seed_defaults_are_equal_but_independently_configurable() -> None:
    defaults = SeedSettings()
    assert defaults.resolved_symbol == defaults.query_recall == 0.95

    distinct = replace(defaults, resolved_symbol=0.91, query_recall=0.37)
    assert distinct.resolved_symbol == 0.91
    assert distinct.query_recall == 0.37

    for filename in ("default.toml", "lmstudio.toml", "ollama.toml"):
        configured = load_config(ROOT / "config" / filename).ignition.seeds
        assert configured.resolved_symbol == configured.query_recall == 0.95


def test_seed_reasons_use_their_separate_configured_gains() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    prompt_ref = _entity(core, "prompt")
    query_ref = _entity(core, "query")
    seeds = replace(SeedSettings(), resolved_symbol=0.91, query_recall=0.37)
    engine = _engine(core, settings=replace(_settings(), seeds=seeds))

    engine.apply_seed_requests(
        (
            ActivationSeedRequest(prompt_ref, SeedReason.RESOLVED_SYMBOL),
            ActivationSeedRequest(query_ref, SeedReason.QUERY_RECALL),
        )
    )
    engine.tick(include_pacemaker=False)

    assert core.store.runtime_state(prompt_ref.uid).excitation == pytest.approx(0.91)
    assert core.store.runtime_state(query_ref.uid).excitation == pytest.approx(0.37)


def test_plasticity_requires_nonzero_floor_and_nonnegative_steps() -> None:
    with pytest.raises(ValueError, match="link_weight_floor"):
        PlasticitySettings(link_weight_floor=0.0)
    with pytest.raises(ValueError, match="link_hebb_increment"):
        PlasticitySettings(link_hebb_increment=-0.01)
    with pytest.raises(ValueError, match="link_async_decrement"):
        PlasticitySettings(link_async_decrement=-0.01)
    with pytest.raises(ValueError, match="hypernode_confirmation_increment"):
        PlasticitySettings(hypernode_confirmation_increment=-0.01)
    with pytest.raises(ValueError, match="hypernode_refutation_decrement"):
        PlasticitySettings(hypernode_refutation_decrement=-0.01)


def test_workspace_is_an_uncapped_strict_floating_threshold() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    above = tuple(_entity(core, f"above-{index}") for index in range(64))
    boundary = _entity(core, "at-threshold")
    engine = _engine(core, threshold=0.4)
    for ref in above:
        engine.seed(ref, 0.41, reason=SeedReason.SENSORY_SYMBOL)
    engine.seed(boundary, 0.4, reason=SeedReason.SENSORY_SYMBOL)

    workspace = engine.tick(include_pacemaker=False).workspace

    assert {ref.uid for ref in workspace} == {ref.uid for ref in above}
    assert len(workspace) == 64


def _run_ordered_graph(entity_order: tuple[str, ...], link_order: tuple[int, ...]):
    core = AHCore(uid_generator=SequentialUidGenerator())
    refs = {name: _entity(core, name) for name in entity_order}
    edges = (("A", "B"), ("B", "C"), ("A", "C"))
    links = {}
    for index in link_order:
        source, target = edges[index]
        link = core.add_link("ASSOC", refs[source], refs[target], 0.5)
        links[(source, target)] = link.uid
    plasticity = PlasticitySettings(
        link_hebb_increment=0.1,
        link_async_decrement=0.01,
        link_weight_floor=0.02,
    )
    engine = _engine(core, settings=_settings(plasticity=plasticity))
    engine.seed(refs["A"], 0.5, reason=SeedReason.SENSORY_SYMBOL)
    engine.seed(refs["C"], 0.25, reason=SeedReason.SENSORY_SYMBOL)
    first = engine.tick(include_pacemaker=False)
    second = engine.tick(include_pacemaker=False)
    return {
        "x": {
            name: core.store.runtime_state(ref.uid).excitation
            for name, ref in refs.items()
        },
        "weights": {
            edge: core.store.get_link(uid).weight for edge, uid in links.items()
        },
        "first_scheduled": {
            name: first.outgoing_scheduled.get(ref.uid, 0.0)
            for name, ref in refs.items()
        },
        "second_scheduled": {
            name: second.outgoing_scheduled.get(ref.uid, 0.0)
            for name, ref in refs.items()
        },
    }


def test_synchronous_tick_is_independent_of_store_insertion_order() -> None:
    forward = _run_ordered_graph(("A", "B", "C"), (0, 1, 2))
    reverse = _run_ordered_graph(("C", "B", "A"), (2, 1, 0))
    assert forward == reverse


def test_propagation_on_the_next_tick_cannot_hebbian_reinforce_its_source_link() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    source = _entity(core, "source")
    target = _entity(core, "target")
    link = core.add_link("ASSOC", source, target, 0.5)
    engine = _engine(
        core,
        settings=_settings(
            plasticity=PlasticitySettings(
                link_hebb_increment=0.1,
                link_async_decrement=0.01,
                link_weight_floor=0.02,
            )
        ),
    )

    engine.seed(source, 0.5, reason=SeedReason.SENSORY_SYMBOL)
    first = engine.tick(include_pacemaker=False)
    first_weight = core.store.get_link(link.uid).weight
    second = engine.tick(include_pacemaker=False)
    second_weight = core.store.get_link(link.uid).weight

    assert {ref.uid for ref in first.activation_events} == {source.uid}
    assert {ref.uid for ref in second.activation_events} == {target.uid}
    assert first_weight < 0.5
    assert second_weight <= first_weight


def test_plasticity_changes_only_existing_links_and_depression_stops_at_floor() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    idle = _entity(core, "idle-source")
    active = _entity(core, "active-target")
    link = core.add_link("ASSOC", idle, active, 0.25)
    settings = _settings(
        plasticity=PlasticitySettings(
            link_hebb_increment=0.1,
            link_async_decrement=0.07,
            link_weight_floor=0.2,
        )
    )
    engine = _engine(core, settings=settings)
    link_count = len(core.store.links())

    engine.seed(active, 0.1, reason=SeedReason.SENSORY_SYMBOL)
    engine.tick(include_pacemaker=False)
    engine.seed(active, 0.1, reason=SeedReason.SENSORY_SYMBOL)
    engine.tick(include_pacemaker=False)
    floor_weight = core.store.get_link(link.uid).weight
    for _ in range(5):
        engine.tick(include_pacemaker=False)

    assert floor_weight == pytest.approx(0.2)
    assert core.store.get_link(link.uid).weight == pytest.approx(0.2)
    assert len(core.store.links()) == link_count
    assert core.store.has_uid(link.uid)


def test_activation_and_association_weight_are_attention_not_truth() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    source = _entity(core, "source")
    target = _entity(core, "target")
    core.add_link("ASSOC", source, target, 1.0)
    engine = _engine(core, threshold=0.2)
    engine.seed(source, 1.0, reason=SeedReason.RESOLVED_SYMBOL)
    engine.seed(target, 1.0, reason=SeedReason.RESOLVED_SYMBOL)
    engine.tick(include_pacemaker=False)

    outcome = InferenceEngine(core, InferenceSettings()).solve(
        RelationGoal("IS-A", source, target),
        engine.workspace_refs(),
    )

    assert outcome.status is LogicalStatus.UNKNOWN
