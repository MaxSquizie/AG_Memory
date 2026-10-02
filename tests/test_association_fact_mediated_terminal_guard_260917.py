from __future__ import annotations

from ah.association import AssociationCoordinator, AssociationGoal
from ah.config import IgnitionSettings, LifecycleSettings, PacemakerSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.model import ActantRole, Domain


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _entity(core: AHCore, domain: Domain = Domain.C):
    return core.add_entity(domain)


def _runtime(core: AHCore) -> AssociationCoordinator:
    ignition = IgnitionEngine(
        core,
        IgnitionSettings(pacemaker=PacemakerSettings(enabled=False)),
        WorkspaceSettings(),
        LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
    )
    return AssociationCoordinator(core, ignition)


def test_unscoped_shared_event_participant_does_not_preempt_common_frame() -> None:
    """A shared M reached through two H facts is propagation, not the answer.

    Regression for the live sequence where crow/table were both seen by the same
    user in the same place.  The two activation fronts can meet at the user entity
    before the full SEE frame is available.  Production search must continue and
    return the richer common event schema instead of raw M(user).
    """
    core = AHCore(uid_generator=SequentialUidGenerator())
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.TIME),
    )
    observer = _entity(core, Domain.P)
    crow = _entity(core)
    table = _entity(core)
    street = _entity(core)
    yesterday = _entity(core)
    today = _entity(core)

    left, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, crow),
            ActantRole.LOCATION: _ref(core, street),
            ActantRole.TIME: _ref(core, yesterday),
        },
        1.0,
        deduplicate=False,
    )
    right, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, table),
            ActantRole.LOCATION: _ref(core, street),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
        deduplicate=False,
    )

    outcome = _runtime(core).solve(
        AssociationGoal(_ref(core, crow), _ref(core, table))
    )

    assert outcome.found
    assert outcome.common_ref != _ref(core, observer)
    assert outcome.frame_pattern is not None
    pattern = outcome.frame_pattern
    assert {pattern.left_fact.uid, pattern.right_fact.uid} == {left.uid, right.uid}
    assert pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, observer)
    assert bindings[ActantRole.LOCATION] == _ref(core, street)
    assert ActantRole.TIME not in bindings


def test_direct_raw_entity_convergence_remains_eligible() -> None:
    """The guard is structural, not a blanket ban on M commonalities."""
    core = AHCore(uid_generator=SequentialUidGenerator())
    left = _entity(core)
    right = _entity(core)
    common = _entity(core)

    # Direct positive links do not traverse an N fact.  This remains a legitimate
    # raw conceptual convergence and protects ordinary semantic associations.
    core.add_link("RELATED", _ref(core, left), _ref(core, common), 1.0)
    core.add_link("RELATED", _ref(core, right), _ref(core, common), 1.0)

    outcome = _runtime(core).solve(
        AssociationGoal(_ref(core, left), _ref(core, right))
    )

    assert outcome.found
    assert outcome.common_ref == _ref(core, common)
    assert outcome.frame_pattern is None
