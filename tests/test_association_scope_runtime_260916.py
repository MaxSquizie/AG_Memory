from __future__ import annotations

from types import SimpleNamespace

from ah.agent.interaction_context import AssociationDiscourseSession
from ah.association import AssociationCoordinator
from ah.association.history import emitted_signatures, remember_signature
from ah.config import IgnitionSettings, LifecycleSettings, PacemakerSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference.association_session_goal import AssociationConstraint, AssociationScopedGoal
from ah.model import ActantRole, Domain
from ah.projection.association_context import AssociationContextProjector


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


def test_scoped_association_finds_common_frame_from_two_distinct_h_facts() -> None:
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
    yard = _entity(core)
    yesterday = _entity(core)
    today = _entity(core)

    left, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, crow),
            ActantRole.LOCATION: _ref(core, yard),
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
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
        deduplicate=False,
    )

    goal = AssociationScopedGoal(
        _ref(core, crow),
        _ref(core, table),
        constraints=(AssociationConstraint(ActantRole.LOCATION, _ref(core, yard)),),
    )
    outcome = _runtime(core).solve(goal)

    assert outcome.found
    assert outcome.frame_pattern is not None
    pattern = outcome.frame_pattern
    assert {pattern.left_fact.uid, pattern.right_fact.uid} == {left.uid, right.uid}
    assert pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, observer)
    assert bindings[ActantRole.LOCATION] == _ref(core, yard)
    assert ActantRole.TIME not in bindings


def test_scoped_association_rejects_unrelated_have_and_workshop_commonalities() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    have_s = core.add_abstract_symbol({"есть"})
    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    make_s = core.add_abstract_symbol({"делать"})
    make_t = core.add_template(
        Domain.C,
        _ref(core, make_s),
        (ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.MATERIAL),
    )
    crow = _entity(core)
    table = _entity(core)
    paws = _entity(core)
    legs = _entity(core)
    yard = _entity(core)
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

    goal = AssociationScopedGoal(
        _ref(core, crow),
        _ref(core, table),
        constraints=(AssociationConstraint(ActantRole.LOCATION, _ref(core, yard)),),
    )
    outcome = _runtime(core).solve(goal)

    assert not outcome.found


def test_result_history_is_separate_for_same_pair_with_different_scope() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _entity(core)
    table = _entity(core)
    yard = _entity(core)
    left = _ref(core, crow)
    right = _ref(core, table)
    scoped = (AssociationConstraint(ActantRole.LOCATION, _ref(core, yard)),)

    remember_signature(core, left, right, "FRAME:global")
    remember_signature(core, left, right, "FRAME:yard", scoped)

    assert emitted_signatures(core, left, right) == ("FRAME:global",)
    assert emitted_signatures(core, left, right, scoped) == ("FRAME:yard",)


def test_discourse_session_scope_is_part_of_goal_identity() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _entity(core)
    table = _entity(core)
    yard = _entity(core)
    left = _ref(core, crow)
    right = _ref(core, table)
    session = AssociationDiscourseSession(left, right)

    assert session.same_goal(left, right, ())
    assert not session.same_goal(
        left,
        right,
        (AssociationConstraint(ActantRole.LOCATION, _ref(core, yard)),),
    )


def test_association_render_hides_unscoped_workspace_from_response_model() -> None:
    rendered = AssociationContextProjector._render_with_association_sections(
        "Что ещё?",
        (SimpleNamespace(semantic="UNRELATED WARM MEMORY"),),
        (),
        (SimpleNamespace(semantic="AUTHORITATIVE ASSOCIATION RESULT"),),
    )

    assert "AUTHORITATIVE ASSOCIATION RESULT" in rendered
    assert "UNRELATED WARM MEMORY" not in rendered
    assert "# ACTIVE MEMORY" not in rendered
