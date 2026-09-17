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


def test_continuation_skips_pair_members_and_reaches_independent_common_frames() -> None:
    """A pair carrier must not turn its own members into later answers.

    This mirrors the demo memory:
      * crow/table are co-objects of MAKE in a workshop;
      * crow/table have generalized legs via two separate HAVE facts;
      * crow/table occur in two separate SEE episodes sharing observer+yard.

    After one valid result, continuation used to walk through the coordination K/g
    that packages (crow, table), unpack the opposite member and stop on raw ``crow``
    or ``table``.  The remaining independent frames were therefore never reached.
    """
    core = AHCore(uid_generator=SequentialUidGenerator())

    have_s = core.add_abstract_symbol({"иметь"})
    make_s = core.add_abstract_symbol({"делать"})
    see_s = core.add_abstract_symbol({"видеть"})

    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    make_t = core.add_template(
        Domain.C,
        _ref(core, make_s),
        (ActantRole.OBJECT, ActantRole.LOCATION),
    )
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.TIME),
    )

    crow = _entity(core)
    table = _entity(core)
    paws = _entity(core)
    legs = _entity(core)
    workshop = _entity(core)
    yard = _entity(core)
    observer = _entity(core, Domain.P)
    yesterday = _entity(core)
    today = _entity(core)

    core.add_link("IS-A", _ref(core, paws), _ref(core, legs), 1.0)

    core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, crow),
            ActantRole.OBJECT: _ref(core, paws),
        },
        1.0,
    )
    core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, table),
            ActantRole.OBJECT: _ref(core, legs),
        },
        1.0,
    )

    pair = core.add_group(Domain.H, (_ref(core, crow), _ref(core, table)))
    core.add_hypernode(
        Domain.H,
        _ref(core, make_t),
        {
            ActantRole.OBJECT: _ref(core, pair),
            ActantRole.LOCATION: _ref(core, workshop),
        },
        1.0,
        deduplicate=False,
    )

    core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, crow),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, today),
        },
        1.0,
        deduplicate=False,
    )
    core.add_hypernode(
        Domain.H,
        _ref(core, see_t),
        {
            ActantRole.SUBJECT: _ref(core, observer),
            ActantRole.OBJECT: _ref(core, table),
            ActantRole.LOCATION: _ref(core, yard),
            ActantRole.TIME: _ref(core, yesterday),
        },
        1.0,
        deduplicate=False,
    )

    runtime = _runtime(core)
    left = _ref(core, crow)
    right = _ref(core, table)
    request = AssociationScopedGoal(left, right)
    predicate_uids: set[str] = set()

    for _ in range(3):
        outcome = runtime.solve(request)
        assert outcome.found
        assert outcome.frame_pattern is not None, (
            "continuation must return a structured independent frame, not a raw "
            f"common ref {outcome.common_ref}"
        )
        assert outcome.common_ref not in {left, right}
        predicate_uids.add(outcome.frame_pattern.predicate.uid)

        request = AssociationContinuationGoal(
            left,
            right,
            excluded_signatures=emitted_signatures(core, left, right),
        )

    assert predicate_uids == {have_s.uid, make_s.uid, see_s.uid}
