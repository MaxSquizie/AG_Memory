from __future__ import annotations

from types import SimpleNamespace

from ah.association.contracts import (
    AssociationDomainPolicy,
    AssociationFrameBinding,
    AssociationFramePattern,
    AssociationOutcome,
    AssociationSemantics,
    AssociationStatus,
)
from ah.association.coordinator import AssociationSearchState
from ah.association.coordinator_session import AssociationCoordinator
from ah.config import ContextSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference.contracts import AssociationGoal
from ah.model import ActantRole, Domain, Property
from ah.projection.association_context import AssociationContextProjector


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def _named_entity(core: AHCore, name: str, domain: Domain = Domain.C):
    return core.add_entity(
        domain,
        properties={"name": Property("name", name, "str")},
    )


def _projector(core: AHCore) -> AssociationContextProjector:
    return AssociationContextProjector(
        core,
        ContextSettings(include_structural_uids=False),
    )


def _outcome(goal, common_ref, pattern, *, fact_count: int = 2):
    return AssociationOutcome(
        status=AssociationStatus.FOUND,
        goal=goal,
        common_ref=common_ref,
        left_path=None,
        right_path=None,
        common_candidates=(common_ref,),
        left_activated=(),
        right_activated=(),
        expanded_states=0,
        ticks_executed=0,
        trace=(),
        domain_policy=AssociationDomainPolicy.ALL,
        semantics=pattern.semantics,
        minimal_fact_count=fact_count,
        frame_pattern=pattern,
        result_signature=pattern.signature,
    )


def test_projection_exposes_supporting_facts_and_generalized_role_values() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    have_s = core.add_abstract_symbol({"иметь"})
    have_t = core.add_template(
        Domain.C,
        _ref(core, have_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT),
    )
    crow = _named_entity(core, "ворона")
    table = _named_entity(core, "стол")
    paws = _named_entity(core, "лапки")
    legs = _named_entity(core, "ножки")
    left, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, crow),
            ActantRole.OBJECT: _ref(core, paws),
        },
        1.0,
    )
    right, _ = core.add_hypernode(
        Domain.C,
        _ref(core, have_t),
        {
            ActantRole.SUBJECT: _ref(core, table),
            ActantRole.OBJECT: _ref(core, legs),
        },
        1.0,
    )
    pattern = AssociationFramePattern(
        template=_ref(core, have_t),
        predicate=_ref(core, have_s),
        variable_roles=(ActantRole.SUBJECT,),
        bindings=(
            AssociationFrameBinding(ActantRole.OBJECT, _ref(core, legs), True),
        ),
        left_fact=_ref(core, left),
        right_fact=_ref(core, right),
        signature="FRAME:have",
        semantics=AssociationSemantics.SEMANTIC,
    )
    goal = AssociationGoal(_ref(core, crow), _ref(core, table))

    text = _projector(core)._association_block(
        _outcome(goal, _ref(core, have_t), pattern)
    ).semantic

    assert "иметь(OBJECT=ножки [IS-A generalization], SUBJECT=_)" in text
    assert "Левый опорный канонический факт: иметь(SUBJECT=ворона, OBJECT=лапки)." in text
    assert "Правый опорный канонический факт: иметь(SUBJECT=стол, OBJECT=ножки)." in text
    assert "Переменная роль SUBJECT: левый сравниваемый объект=ворона" in text
    assert "правый сравниваемый объект=стол" in text
    assert (
        "Общая фиксированная роль OBJECT: слева=лапки; справа=ножки; "
        "каноническое обобщение=ножки через IS-A."
    ) in text
    assert "Интерпретируй predicate только вместе с ролями и опорными фактами" in text


def test_projection_exposes_distinct_episode_facts_without_calling_time_common() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    see_s = core.add_abstract_symbol({"видеть"})
    see_t = core.add_template(
        Domain.C,
        _ref(core, see_s),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION, ActantRole.TIME),
    )
    user = _named_entity(core, "Пользователь", Domain.P)
    crow = _named_entity(core, "ворона")
    table = _named_entity(core, "стол")
    yard = _named_entity(core, "двор")
    yesterday = _named_entity(core, "вчера")
    today = _named_entity(core, "сегодня")
    left, _ = core.add_hypernode(
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
    right, _ = core.add_hypernode(
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
    pattern = AssociationFramePattern(
        template=_ref(core, see_t),
        predicate=_ref(core, see_s),
        variable_roles=(ActantRole.OBJECT,),
        bindings=(
            AssociationFrameBinding(ActantRole.LOCATION, _ref(core, yard), False),
            AssociationFrameBinding(ActantRole.SUBJECT, _ref(core, user), False),
        ),
        left_fact=_ref(core, left),
        right_fact=_ref(core, right),
        signature="FRAME:see-yard",
        semantics=AssociationSemantics.EPISODIC,
    )
    goal = AssociationGoal(_ref(core, crow), _ref(core, table))

    text = _projector(core)._association_block(
        _outcome(goal, _ref(core, see_t), pattern)
    ).semantic

    assert "видеть(SUBJECT=Пользователь, OBJECT=ворона, LOCATION=двор, TIME=вчера)" in text
    assert "видеть(SUBJECT=Пользователь, OBJECT=стол, LOCATION=двор, TIME=сегодня)" in text
    assert "Общая фиксированная роль LOCATION" in text
    assert "Общая фиксированная роль SUBJECT" in text
    assert "Роли, которые различаются в опорных фактах" in text


def test_raw_function_that_only_contains_both_endpoints_is_not_a_commonality() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = _named_entity(core, "ворона")
    table = _named_entity(core, "стол")
    pair = core.add_function(
        Domain.C,
        "AND",
        (_ref(core, crow), _ref(core, table)),
    )
    goal = AssociationGoal(_ref(core, crow), _ref(core, table))
    state = AssociationSearchState(goal)
    coordinator = AssociationCoordinator(core, SimpleNamespace(core=core))

    assert coordinator._raw_common_allowed(state, pair.uid) is False
