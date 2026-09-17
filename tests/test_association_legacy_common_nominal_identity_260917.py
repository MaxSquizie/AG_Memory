from __future__ import annotations

from ah.association import AssociationCoordinator
from ah.config import IgnitionSettings, LifecycleSettings, PacemakerSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference.association_session_goal import AssociationConstraint, AssociationScopedGoal
from ah.model import ActantRole, Domain, Property


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _named(core: AHCore, domain: Domain, name: str):
    return core.add_entity(
        domain,
        properties={"name": Property("name", name, "str")},
    )


def _runtime(core: AHCore) -> AssociationCoordinator:
    return AssociationCoordinator(
        core,
        IgnitionEngine(
            core,
            IgnitionSettings(pacemaker=PacemakerSettings(enabled=False)),
            WorkspaceSettings(),
            LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
        ),
    )


def test_scoped_association_reaches_episode_facts_through_legacy_common_noun_peers() -> None:
    """Open-event recall and association must agree on old duplicate noun M nodes.

    The current integrator tries to reuse a canonical common-noun entity across
    domains, but persisted memories from older builds can contain C/P duplicates.
    The demo symptom is characteristic: ``Что я видел во дворе?`` finds both SEE
    events from SUBJECT+LOCATION, while association seeded from C(ворона)/C(стол)
    cannot reach P(ворона)/P(стол) stored in those events.

    Association must bridge only the runtime representations; no canonical merge is
    performed by this test or by the coordinator.
    """
    core = AHCore(uid_generator=SequentialUidGenerator())
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.TIME),
    )

    canonical_crow = _named(core, Domain.C, "ворона")
    canonical_table = _named(core, Domain.C, "стол")
    canonical_yard = _named(core, Domain.C, "двор")

    episode_crow = _named(core, Domain.P, "ворона")
    episode_table = _named(core, Domain.P, "стол")
    episode_yard = _named(core, Domain.P, "двор")
    observer = _named(core, Domain.P, "наблюдатель")
    yesterday = _named(core, Domain.P, "вчера")
    today = _named(core, Domain.P, "сегодня")

    left_fact, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, episode_crow),
            ActantRole.LOCATION: _ref(core, episode_yard),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
        deduplicate=False,
    )
    right_fact, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, episode_table),
            ActantRole.LOCATION: _ref(core, episode_yard),
            ActantRole.TIME: _ref(core, yesterday),
        },
        1.0,
        deduplicate=False,
    )

    goal = AssociationScopedGoal(
        _ref(core, canonical_crow),
        _ref(core, canonical_table),
        constraints=(
            AssociationConstraint(ActantRole.LOCATION, _ref(core, canonical_yard)),
        ),
    )
    outcome = _runtime(core).solve(goal)

    assert outcome.found
    assert outcome.frame_pattern is not None
    pattern = outcome.frame_pattern
    assert pattern.predicate == _ref(core, see_s)
    assert {pattern.left_fact.uid, pattern.right_fact.uid} == {
        left_fact.uid,
        right_fact.uid,
    }
    assert pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, observer)
    assert bindings[ActantRole.LOCATION] == _ref(core, episode_yard)
    assert ActantRole.TIME not in bindings

    # The runtime search must actually have crossed the representation bridge,
    # proving that the result did not depend on canonical mutation or a global scan.
    relations = {
        hop.relation
        for path in (outcome.left_path, outcome.right_path)
        if path is not None
        for hop in path.hops
    }
    assert "COMMON_NOMINAL_REPRESENTATION" in relations
