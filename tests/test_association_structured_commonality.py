from __future__ import annotations

from types import SimpleNamespace

from ah.association.coordinator import AssociationSearchState, _LEFT, _RIGHT
from ah.association.coordinator_specific import AssociationCoordinator
from ah.inference.contracts import AssociationGoal
from ah.core import AHCore, SequentialUidGenerator
from ah.model import ActantRole, Domain


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _coordinator(core: AHCore) -> AssociationCoordinator:
    return AssociationCoordinator(core, SimpleNamespace(core=core))


def _entity(core: AHCore, domain: Domain = Domain.C):
    return core.add_entity(domain)


def test_have_commonality_keeps_object_constraint_and_generalizes_is_a() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    have_s = core.add_abstract_symbol({"есть"})
    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    crow = _entity(core)
    table = _entity(core)
    paws = _entity(core)
    legs = _entity(core)
    core.add_link("IS-A", _ref(core, paws), _ref(core, legs), 1.0)
    left, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {ActantRole.SUBJECT: _ref(core, crow), ActantRole.OBJECT: _ref(core, paws)},
        1.0,
    )
    right, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {ActantRole.SUBJECT: _ref(core, table), ActantRole.OBJECT: _ref(core, legs)},
        1.0,
    )
    state = AssociationSearchState(AssociationGoal(_ref(core, crow), _ref(core, table)))

    pattern = _coordinator(core)._pattern_for_pair(
        state, _ref(core, left), left, _ref(core, right), right
    )

    assert pattern is not None
    assert pattern.variable_roles == (ActantRole.SUBJECT,)
    assert len(pattern.bindings) == 1
    assert pattern.bindings[0].role is ActantRole.OBJECT
    assert pattern.bindings[0].value == _ref(core, legs)
    assert pattern.bindings[0].generalized is True


def test_separate_h_events_share_seen_in_location_frame() -> None:
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
    state = AssociationSearchState(AssociationGoal(_ref(core, crow), _ref(core, table)))

    pattern = _coordinator(core)._pattern_for_pair(
        state, _ref(core, left), left, _ref(core, right), right
    )

    assert pattern is not None
    assert pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, observer)
    assert bindings[ActantRole.LOCATION] == _ref(core, yard)
    assert ActantRole.TIME not in bindings
    assert pattern.semantics.value == "EPISODIC"


def test_one_h_fact_with_group_supports_commonality_for_both_members() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION),
    )
    observer = _entity(core, Domain.P)
    crow = _entity(core)
    table = _entity(core)
    yard = _entity(core)
    pair = core.add_group(Domain.H, (_ref(core, crow), _ref(core, table)))
    fact, _ = core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, pair),
            ActantRole.LOCATION: _ref(core, yard),
        },
        1.0,
        deduplicate=False,
    )
    state = AssociationSearchState(AssociationGoal(_ref(core, crow), _ref(core, table)))

    pattern = _coordinator(core)._pattern_for_pair(
        state, _ref(core, fact), fact, _ref(core, fact), fact
    )

    assert pattern is not None
    assert pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, observer)
    assert bindings[ActantRole.LOCATION] == _ref(core, yard)
    assert pattern.semantics.value == "EPISODIC"


def test_previous_frame_signature_is_not_returned_as_next_commonality() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    have_s = core.add_abstract_symbol({"есть"})
    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    left_entity = _entity(core)
    right_entity = _entity(core)
    common_object = _entity(core)
    left, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, left_entity),
            ActantRole.OBJECT: _ref(core, common_object),
        },
        1.0,
    )
    right, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, right_entity),
            ActantRole.OBJECT: _ref(core, common_object),
        },
        1.0,
    )
    state = AssociationSearchState(
        AssociationGoal(_ref(core, left_entity), _ref(core, right_entity))
    )
    state.parents[_LEFT][left.uid] = None  # only membership/depth is needed here
    state.parents[_RIGHT][right.uid] = None
    state.depths[_LEFT][left.uid] = 1
    state.depths[_RIGHT][right.uid] = 1

    coordinator = _coordinator(core)
    first = coordinator._best_frame_pattern(state)
    assert first is not None

    coordinator._excluded_signatures = frozenset({first.signature})
    assert coordinator._best_frame_pattern(state) is None
