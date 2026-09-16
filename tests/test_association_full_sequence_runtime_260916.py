from __future__ import annotations

from ah.association import AssociationCoordinator
from ah.association.history import emitted_signatures
from ah.config import IgnitionSettings, LifecycleSettings, PacemakerSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference.association_session_goal import (
    AssociationContinuationGoal,
    AssociationScopedGoal,
)
from ah.model import ActantRole, Domain


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _entity(core: AHCore, domain: Domain = Domain.C):
    return core.add_entity(domain)


def test_full_sequence_reaches_two_fact_yard_frame_without_repeating_results() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())

    have_s = core.add_abstract_symbol({"есть"})
    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.TIME),
    )
    make_s = core.add_abstract_symbol({"делать"})
    make_t = core.add_template(
        Domain.C,
        _ref(core, make_s),
        (ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.MATERIAL),
    )

    user = _entity(core, Domain.P)
    crow = _entity(core)
    table = _entity(core)
    paws = _entity(core)
    legs = _entity(core)
    yard = _entity(core)
    yesterday = _entity(core)
    today = _entity(core)
    workshop = _entity(core)
    wood = _entity(core)

    core.add_link("IS-A", _ref(core, paws), _ref(core, legs), 1.0)
    core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {ActantRole.SUBJECT: _ref(core, crow), ActantRole.OBJECT: _ref(core, paws)},
        1.0,
    )
    core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {ActantRole.SUBJECT: _ref(core, table), ActantRole.OBJECT: _ref(core, legs)},
        1.0,
    )
    core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, user),
            ActantRole.OBJECT: _ref(core, crow),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, yesterday),
        },
        1.0,
        deduplicate=False,
    )
    core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, user),
            ActantRole.OBJECT: _ref(core, table),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
        deduplicate=False,
    )
    pair = core.add_group(Domain.H, (_ref(core, crow), _ref(core, table)))
    core.add_hypernode(
        Domain.H,
        _ref(core, make_t),
        {
            ActantRole.OBJECT: _ref(core, pair),
            ActantRole.LOCATION: _ref(core, workshop),
            ActantRole.MATERIAL: _ref(core, wood),
        },
        1.0,
        deduplicate=False,
    )

    ignition = IgnitionEngine(
        core,
        IgnitionSettings(pacemaker=PacemakerSettings(enabled=False)),
        WorkspaceSettings(),
        LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
    )
    coordinator = AssociationCoordinator(core, ignition)
    left = _ref(core, crow)
    right = _ref(core, table)

    request = AssociationScopedGoal(left, right)
    outcomes = []
    for _ in range(6):
        outcome = coordinator.solve(request)
        if not outcome.found:
            break
        outcomes.append(outcome)
        request = AssociationContinuationGoal(
            left,
            right,
            excluded_signatures=emitted_signatures(core, left, right),
        )

    signatures = tuple(item.result_signature for item in outcomes)
    assert len(signatures) == len(set(signatures))
    assert any(
        item.frame_pattern is not None
        and item.frame_pattern.template == _ref(core, see_t)
        and {binding.role for binding in item.frame_pattern.bindings}
        >= {ActantRole.SUBJECT, ActantRole.LOCATION}
        for item in outcomes
    )
