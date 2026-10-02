from __future__ import annotations

from ah.core import AHCore, SequentialUidGenerator
from ah.inference.association_session_goal import (
    AssociationConstraint,
    AssociationContinuationGoal,
    AssociationScopedGoal,
)
from ah.model import ActantRole, Domain


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _entity(core: AHCore):
    return core.add_entity(Domain.C)


def test_scoped_goal_slots_post_init_calls_base_contract_without_super_crash() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _ref(core, _entity(core))
    table = _ref(core, _entity(core))
    yard = _ref(core, _entity(core))

    goal = AssociationScopedGoal(
        crow,
        table,
        constraints=(AssociationConstraint(ActantRole.LOCATION, yard),),
    )

    assert goal.left == crow
    assert goal.right == table
    assert goal.constraints == (
        AssociationConstraint(ActantRole.LOCATION, yard),
    )


def test_continuation_goal_slots_post_init_calls_base_contract_without_super_crash() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _ref(core, _entity(core))
    table = _ref(core, _entity(core))
    yard = _ref(core, _entity(core))

    goal = AssociationContinuationGoal(
        crow,
        table,
        excluded_signatures=("FRAME:already-returned",),
        constraints=(AssociationConstraint(ActantRole.LOCATION, yard),),
    )

    assert goal.left == crow
    assert goal.right == table
    assert goal.excluded_signatures == ("FRAME:already-returned",)
    assert goal.constraints == (
        AssociationConstraint(ActantRole.LOCATION, yard),
    )
