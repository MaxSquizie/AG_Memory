from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    AllOfGoal,
    CauseEntailmentGoal,
    GoalSpec,
    InferenceEngine,
    InferenceQuery,
    LogicalStatus,
    RelationGoal,
    StopReason,
)
from ah.model import Domain, Property


def _entity(core: AHCore, name: str):
    obj = core.add_entity(Domain.C, properties={"name": Property("name", name, "str")})
    return core.ref(obj.uid)


def test_all_of_composes_cause_follow_and_isa_in_one_connected_proof():
    core = AHCore(uid_generator=SequentialUidGenerator())
    start = _entity(core, "Перегрев обнаружен")
    alarm = _entity(core, "Аварийный сигнал активирован")
    shutdown = _entity(core, "Остановка оборудования началась")
    inspect = _entity(core, "Проверка оборудования выполнена")
    safe = _entity(core, "Безопасное состояние достигнуто")
    state = _entity(core, "Состояние системы")
    condition = _entity(core, "Контролируемое состояние")

    links = [
        core.add_link("CAUSE", start, alarm, 0.4),
        core.add_link("CAUSE", alarm, shutdown, 0.4),
        core.add_link("FOLLOW", shutdown, inspect, 0.4),
        core.add_link("FOLLOW", inspect, safe, 0.4),
        core.add_link("IS-A", safe, state, 0.4),
        core.add_link("IS-A", state, condition, 0.4),
    ]
    goal = AllOfGoal((
        CauseEntailmentGoal(shutdown),
        RelationGoal("FOLLOW", shutdown, safe),
        RelationGoal("IS-A", safe, condition),
    ))
    outcome = InferenceEngine(core, InferenceSettings(max_depth=6, max_expanded_states=100)).solve(
        InferenceQuery(GoalSpec(goal), premise_refs=(start,), max_depth=6)
    )

    assert outcome.status is LogicalStatus.PROVED
    assert outcome.stop_reason is StopReason.GOAL_SATISFIED
    assert outcome.logical_depth == 6
    expected = (
        start.uid, links[0].uid, alarm.uid, links[1].uid, shutdown.uid,
        links[2].uid, inspect.uid, links[3].uid, safe.uid,
        links[4].uid, state.uid, links[5].uid, condition.uid,
    )
    assert tuple(ref.uid for ref in outcome.uid_trace) == expected


def test_all_of_uses_one_global_depth_budget():
    core = AHCore(uid_generator=SequentialUidGenerator())
    a = _entity(core, "A")
    b = _entity(core, "B")
    c = _entity(core, "C")
    d = _entity(core, "D")
    e = _entity(core, "E")
    core.add_link("CAUSE", a, b, 0.4)
    core.add_link("CAUSE", b, c, 0.4)
    core.add_link("FOLLOW", c, d, 0.4)
    core.add_link("FOLLOW", d, e, 0.4)
    goal = AllOfGoal((CauseEntailmentGoal(c), RelationGoal("FOLLOW", c, e)))

    outcome = InferenceEngine(core, InferenceSettings(max_depth=6, max_expanded_states=100)).solve(
        InferenceQuery(GoalSpec(goal), premise_refs=(a,), max_depth=3)
    )
    assert outcome.status is LogicalStatus.UNKNOWN
    assert outcome.stop_reason is StopReason.DEPTH_EXHAUSTED
    assert outcome.logical_depth == 3
