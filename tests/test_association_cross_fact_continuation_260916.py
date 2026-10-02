from __future__ import annotations

from types import SimpleNamespace

from ah.association.contracts import (
    AssociationDomainPolicy,
    AssociationOutcome,
    AssociationSemantics,
    AssociationStatus,
)
from ah.association.coordinator import AssociationSearchState, _LEFT, _RIGHT
from ah.association.coordinator_session import AssociationCoordinator
from ah.association.history import emitted_signatures
from ah.core import AHCore, SequentialUidGenerator
from ah.inference.contracts import AssociationGoal
from ah.model import ActantRole, Domain


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _entity(core: AHCore, domain: Domain = Domain.C):
    return core.add_entity(domain)


def _coordinator(core: AHCore) -> AssociationCoordinator:
    return AssociationCoordinator(core, SimpleNamespace(core=core))


def test_continuation_skips_supporting_raw_fact_and_reaches_two_fact_frame() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _entity(core)
    table = _entity(core)
    user = _entity(core, Domain.P)
    yard = _entity(core)
    workshop = _entity(core)
    yesterday = _entity(core)
    today = _entity(core)

    # One coordinated fact contains both endpoints and is therefore reachable as a
    # raw N from both fronts.  After its structured frame has been emitted, that N
    # must not be returned again as a supposedly new commonality.
    make_s = core.add_abstract_symbol({"делать"})
    make_t = core.add_template(
        Domain.C,
        _ref(core, make_s),
        (ActantRole.OBJECT, ActantRole.LOCATION),
    )
    pair = core.add_group(Domain.C, (_ref(core, crow), _ref(core, table)))
    make_fact, _ = core.add_hypernode(
        Domain.P,
        _ref(core, make_t),
        {
            ActantRole.OBJECT: _ref(core, pair),
            ActantRole.LOCATION: _ref(core, workshop),
        },
        1.0,
    )

    # The next valid commonality is assembled from two distinct facts.  Their TIME
    # fillers differ, while predicate, observer and LOCATION are shared.
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.LOCATION,
            ActantRole.TIME,
        ),
    )
    see_crow, _ = core.add_hypernode(
        Domain.P,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, user),
            ActantRole.OBJECT: _ref(core, crow),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, yesterday),
        },
        1.0,
    )
    see_table, _ = core.add_hypernode(
        Domain.P,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, user),
            ActantRole.OBJECT: _ref(core, table),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
    )

    goal = AssociationGoal(_ref(core, crow), _ref(core, table))
    state = AssociationSearchState(goal)
    state.parents[_LEFT][make_fact.uid] = None
    state.parents[_RIGHT][make_fact.uid] = None
    state.depths[_LEFT][make_fact.uid] = 1
    state.depths[_RIGHT][make_fact.uid] = 1
    state.parents[_LEFT][see_crow.uid] = None
    state.parents[_RIGHT][see_table.uid] = None
    state.depths[_LEFT][see_crow.uid] = 2
    state.depths[_RIGHT][see_table.uid] = 2

    coordinator = _coordinator(core)
    make_pattern = coordinator._pattern_for_pair(
        state,
        _ref(core, make_fact),
        make_fact,
        _ref(core, make_fact),
        make_fact,
    )
    assert make_pattern is not None

    coordinator._remember_outcome(
        AssociationOutcome(
            status=AssociationStatus.FOUND,
            goal=goal,
            common_ref=_ref(core, make_t),
            left_path=None,
            right_path=None,
            common_candidates=(_ref(core, make_t),),
            left_activated=(),
            right_activated=(),
            expanded_states=0,
            ticks_executed=0,
            trace=(),
            domain_policy=AssociationDomainPolicy.ALL,
            semantics=AssociationSemantics.SEMANTIC,
            minimal_fact_count=1,
            frame_pattern=make_pattern,
            result_signature=make_pattern.signature,
        )
    )

    history = emitted_signatures(core, goal.left, goal.right)
    assert f"REF:{make_fact.uid}" in history
    coordinator._excluded_signatures = frozenset(history)

    # The same MAKE fact is no longer eligible as a raw fallback.
    assert coordinator._raw_common_allowed(state, make_fact.uid) is False

    next_pattern = coordinator._best_frame_pattern(state)
    assert next_pattern is not None
    assert next_pattern.template == _ref(core, see_t)
    assert next_pattern.left_fact == _ref(core, see_crow)
    assert next_pattern.right_fact == _ref(core, see_table)
    assert next_pattern.variable_roles == (ActantRole.OBJECT,)
    bindings = {item.role: item.value for item in next_pattern.bindings}
    assert bindings[ActantRole.SUBJECT] == _ref(core, user)
    assert bindings[ActantRole.LOCATION] == _ref(core, yard)
    assert ActantRole.TIME not in bindings
